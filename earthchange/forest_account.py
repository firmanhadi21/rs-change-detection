#!/usr/bin/env python3
"""Forest account — how much tree cover an area lost, when, and what drove it.

The counting companion to forest-history. forest-history maps *where* forest
went from an NDVI baseline the run builds itself; this scenario books the loss
against the published global layers, so the totals are comparable with other
studies and other provinces:

  * Hansen et al. Global Forest Change (UMD/Google): tree cover in 2000 above
    --canopy-thr percent, and the year each 30 m pixel lost it;
  * Turubanova et al. 2018 humid tropical primary forest (2001): how much of
    the loss was primary forest;
  * WRI/Google Drivers of Forest Loss (Sims et al. 2025), 1 km: the dominant
    driver of each cell, applied to the Hansen loss inside it, by year;
  * optionally (--open-ground) Dynamic World: bare + built area per year, the
    footprint of mines, pits, industrial estates and roads, which tree-cover
    loss misses once the ground is already cleared.

With --admin naming a province (FAO GAUL level 1), every regency inside it is
also accounted separately. Outputs: stats.json, units.csv, loss_by_year.png
(stacked by driver), units.png, open_ground.png.

Caveats the outputs carry: Hansen "tree cover" includes plantations and tree
crops; the driver is one class per 1 km cell for the whole period, not proof
of who cleared a pixel. Backend: needs --backend gee.
"""

import csv
import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

HANSEN = "UMD/hansen/global_forest_change_2025_v1_13"
HANSEN_LAST = 2025                       # last loss year in the asset above
PRIMARY = "UMD/GLAD/PRIMARY_HUMID_TROPICAL_FORESTS/v1"
DRIVERS = "projects/landandcarbon/assets/wri_gdm_drivers_forest_loss_1km/v1_2_2001_2024"
DRIVERS_LAST = 2024
DRIVER_NAMES = {1: "Permanent agriculture", 2: "Hard commodities (mining, energy)",
                3: "Shifting cultivation", 4: "Logging", 5: "Wildfire",
                6: "Settlements & infrastructure", 7: "Other natural disturbances"}
DRIVER_COLORS = {1: "#c9a227", 2: "#d7301f", 3: "#8c6d31", 4: "#6b8e23",
                 5: "#fd8d3c", 6: "#636363", 7: "#9ecae1"}
RECENT_YEARS = 6                         # "recent" window for the driver rates
DW_FIRST = 2016                          # Dynamic World starts mid-2015


# ----------------------------- pure helpers (testable) -----------------------------
def parse_groups(groups, key="y", base=2000):
    """Earth Engine grouped-sum output -> {year: ha}, rounded to 0.1 ha."""
    return {base + int(g[key]): round(g["sum"], 1) for g in groups}


def split_driver_year(groups):
    """Groups keyed driver*100 + lossyear -> {driver name: {year: ha}}."""
    out = {}
    for g in groups:
        c = int(g["c"])
        dr, y = c // 100, 2000 + c % 100
        out.setdefault(DRIVER_NAMES.get(dr, f"class {dr}"), {})[y] = round(g["sum"], 1)
    return out


def driver_rates(by_driver_year, last=DRIVERS_LAST, recent=RECENT_YEARS, first=2001):
    """Mean ha/yr per driver before and within the last `recent` years, and the
    driver's share of all attributed loss in each period. This is the number
    that shows a small driver growing fast (e.g. mining 2.9% -> 10.1%)."""
    cut = last - recent + 1
    n_early, n_late = cut - first, recent
    tot_e = sum(v for d in by_driver_year.values() for y, v in d.items() if y < cut)
    tot_l = sum(v for d in by_driver_year.values() for y, v in d.items() if y >= cut)
    out = {"early": f"{first}-{cut - 1}", "recent": f"{cut}-{last}", "drivers": {}}
    for k, d in by_driver_year.items():
        e = sum(v for y, v in d.items() if y < cut)
        r = sum(v for y, v in d.items() if y >= cut)
        out["drivers"][k] = {
            "early_ha_per_yr": round(e / n_early, 1) if n_early else None,
            "recent_ha_per_yr": round(r / n_late, 1),
            "early_share_pct": round(100 * e / tot_e, 1) if tot_e else None,
            "recent_share_pct": round(100 * r / tot_l, 1) if tot_l else None,
        }
    return out


# ----------------------------- GEE building blocks -----------------------------
def _layers(canopy_thr):
    import ee
    g = ee.Image(HANSEN)
    f2000 = g.select("treecover2000").gte(canopy_thr)
    ly = g.select("lossyear")
    loss = f2000.And(ly.gt(0))
    prim = ee.ImageCollection(PRIMARY).mosaic().unmask(0).gt(0)
    drv = ee.Image(DRIVERS).select("classification")
    area = ee.Image.pixelArea().divide(1e4)
    return f2000, ly, loss, prim, drv, area


def _get(obj, tries=3):
    """getInfo with a retry: a province-sized reduction sometimes times out once
    and then succeeds, because Earth Engine caches the tiles it got through."""
    import ee
    for k in range(tries):
        try:
            return obj.getInfo()
        except ee.EEException as e:
            if "timed out" not in str(e).lower() or k == tries - 1:
                raise
            print("  (Earth Engine timed out, retrying)")


def account(geom, canopy_thr=30, scale=30):
    """Totals, loss by year, and loss by driver x year for one geometry."""
    import ee
    f2000, ly, loss, prim, drv, A = _layers(canopy_thr)
    # A GAUL coastline carries every islet; 100 m simplification changes the
    # area by a fraction of a percent and is the difference between a province
    # finishing and timing out.
    geom = ee.Geometry(geom).simplify(maxError=100)
    kw = dict(geometry=geom, scale=scale, maxPixels=1e12, tileScale=2)
    s = lambda m: _get(A.updateMask(m).reduceRegion(ee.Reducer.sum(), **kw).get("area"))  # noqa: E731
    d = {"area_ha": _get(A.reduceRegion(ee.Reducer.sum(), **kw).get("area")),
         "forest2000_ha": s(f2000), "primary2001_ha": s(prim),
         "loss_primary_ha": s(loss.And(prim))}
    d = {k: round(v or 0, 1) for k, v in d.items()}
    by = _get(A.addBands(ly).updateMask(loss).reduceRegion(
        ee.Reducer.sum().group(1, "y"), **kw))["groups"]
    d["loss_by_year_ha"] = parse_groups(by)
    d["loss_total_ha"] = round(sum(d["loss_by_year_ha"].values()), 1)
    d["loss_pct_of_2000"] = (round(100 * d["loss_total_ha"] / d["forest2000_ha"], 2)
                             if d["forest2000_ha"] else None)
    code = drv.multiply(100).add(ly)
    bd = _get(A.addBands(code).updateMask(loss.And(ly.lte(DRIVERS_LAST - 2000))).reduceRegion(
        ee.Reducer.sum().group(1, "c"), **kw))["groups"]
    d["loss_by_driver_year_ha"] = split_driver_year(bd)
    d["loss_by_driver_ha"] = {k: round(sum(v.values()), 1)
                              for k, v in d["loss_by_driver_year_ha"].items()}
    d["driver_rates"] = driver_rates(d["loss_by_driver_year_ha"])
    return d


def open_ground(geom, years, scale=10):
    """Dynamic World bare (7) + built (6) area per year, from the annual mode."""
    import ee
    A = ee.Image.pixelArea().divide(1e4)
    out = {}
    for y in years:
        lab = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom)
               .filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("label").mode())
        st = (A.updateMask(lab.eq(7)).rename("bare")
              .addBands(A.updateMask(lab.eq(6)).rename("built"))
              .reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e12, tileScale=4)
              .getInfo())
        out[y] = {k: round(st.get(k) or 0, 1) for k in ("bare", "built")}
        print(f"  open ground {y}: bare {out[y]['bare']:.0f} ha, built {out[y]['built']:.0f} ha")
    return out


def _subunits(admin):
    """Level-2 names inside a level-1 admin, or [] if admin is not a province."""
    import ee
    from .gee_utils import gaul
    if gaul(1).filter(ee.Filter.eq("ADM1_NAME", admin)).size().getInfo() == 0:
        return []
    return sorted(gaul(2).filter(ee.Filter.eq("ADM1_NAME", admin))
                  .aggregate_array("ADM2_NAME").distinct().getInfo())


# ----------------------------- figures -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def render_loss_by_year(d, path, title):
    plt = _plt()
    years = list(range(2001, HANSEN_LAST + 1))
    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    bottom = [0.0] * len(years)
    dy = d["loss_by_driver_year_ha"]
    for code, name in DRIVER_NAMES.items():
        vals = [dy.get(name, {}).get(y, 0) for y in years]
        if sum(vals) == 0:
            continue
        ax.bar(years, vals, bottom=bottom, color=DRIVER_COLORS[code], label=name, width=0.8)
        bottom = [b + v for b, v in zip(bottom, vals)]
    rest = [max(0.0, d["loss_by_year_ha"].get(y, 0) - b) for y, b in zip(years, bottom)]
    ax.bar(years, rest, bottom=bottom, color="#cccccc", width=0.8,
           label=f"Not attributed (after {DRIVERS_LAST})")
    ax.set_ylabel("Tree-cover loss (ha)")
    ax.set_title(title, loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, frameon=False, ncol=2)
    fig.text(0.01, 0.005, "Hansen et al. GFC v1.13 (tree cover in 2000 above threshold); drivers: "
             "WRI/Google 1 km v1.2, dominant driver per cell", fontsize=7, color="#555")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def render_units(units, path, title):
    plt = _plt()
    rows = sorted(units.items(), key=lambda kv: kv[1]["loss_total_ha"])
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(rows) + 1.2), constrained_layout=True)
    ax.barh([k for k, _ in rows], [v["loss_total_ha"] for _, v in rows], color="#d7301f")
    for i, (_, v) in enumerate(rows):
        ax.text(v["loss_total_ha"], i, f"  {v['loss_total_ha']:,.0f} ha ({v['loss_pct_of_2000'] or 0:.1f}%)",
                va="center", fontsize=8)
    ax.set_xlabel("Tree-cover loss 2001–%d (ha)" % HANSEN_LAST)
    ax.set_title(title, loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def render_open_ground(og, path, title):
    plt = _plt()
    ys = sorted(og)
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    ax.bar(ys, [og[y]["built"] for y in ys], color="#636363", label="built")
    ax.bar(ys, [og[y]["bare"] for y in ys], bottom=[og[y]["built"] for y in ys],
           color="#e6550d", label="bare")
    ax.set_ylabel("ha")
    ax.set_title(title, loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, 0.005, "Dynamic World v1, annual mode of the label; the current year is partial",
             fontsize=7, color="#555")
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        admin=None, bbox=None, canopy_thr=30, with_open_ground=False,
        start_year=None, end_year=None, per_unit=True):
    if backend != "gee":
        raise SystemExit("forest-account needs --backend gee (Hansen, WRI drivers and "
                         "Dynamic World are Earth Engine assets).")
    import datetime as dt
    from .gee_utils import initialize_ee
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)
    geom = _resolve_aoi(admin, bbox, lon, lat, radius)
    os.makedirs(run_dir, exist_ok=True)

    print(f"Forest account: {name} (tree cover >= {canopy_thr}% in 2000)")
    total = account(geom, canopy_thr)
    print(f"  loss 2001-{HANSEN_LAST}: {total['loss_total_ha']:,.0f} ha "
          f"({total['loss_pct_of_2000']}% of {total['forest2000_ha']:,.0f} ha)")

    units = {}
    if admin and per_unit:
        import ee
        from .gee_utils import gaul
        for u in _subunits(admin):
            g = gaul(2).filter(ee.Filter.eq("ADM1_NAME", admin)).filter(
                ee.Filter.eq("ADM2_NAME", u)).geometry()
            units[u] = account(g, canopy_thr)
            print(f"  {u}: {units[u]['loss_total_ha']:,.0f} ha")

    og = None
    if with_open_ground:
        y0 = max(DW_FIRST, start_year or DW_FIRST)
        y1 = end_year or dt.date.today().year
        og = open_ground(geom, range(y0, y1 + 1), scale=10 if radius and radius <= 30 else 30)

    stats = {"run_id": run_id, "scenario": "forest-account", "name": name,
             "admin": admin, "bbox": bbox,
             "location": {"lat": lat, "lon": lon, "radius_km": radius},
             "canopy_thr_pct": canopy_thr,
             "sources": {"loss": HANSEN, "primary": PRIMARY, "drivers": DRIVERS,
                         "open_ground": "GOOGLE/DYNAMICWORLD/V1" if og else None},
             "caveats": ["Hansen tree cover includes plantations and tree crops.",
                         "The driver is the dominant class of a 1 km cell over "
                         f"2001-{DRIVERS_LAST}, applied to the loss year inside it; it is "
                         "not proof of who cleared a pixel.",
                         f"Loss after {DRIVERS_LAST} has no driver."],
             "total": total, "units": units,
             "open_ground_ha": {str(k): v for k, v in og.items()} if og else None}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1, ensure_ascii=False)

    render_loss_by_year(total, os.path.join(run_dir, "loss_by_year.png"),
                        f"{name}: tree-cover loss by year and driver")
    if units:
        render_units(units, os.path.join(run_dir, "units.png"), f"{name}: loss by regency")
        with open(os.path.join(run_dir, "units.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["unit", "forest2000_ha", "loss_total_ha", "loss_pct_of_2000",
                        "loss_primary_ha"] + list(DRIVER_NAMES.values()))
            for u, v in sorted(units.items(), key=lambda kv: -kv[1]["loss_total_ha"]):
                w.writerow([u, v["forest2000_ha"], v["loss_total_ha"], v["loss_pct_of_2000"],
                            v["loss_primary_ha"]] +
                           [v["loss_by_driver_ha"].get(n, 0) for n in DRIVER_NAMES.values()])
    if og:
        render_open_ground(og, os.path.join(run_dir, "open_ground.png"),
                           f"{name}: open ground (bare + built)")
    print(f"\nOutputs in {run_dir}")
    return stats
