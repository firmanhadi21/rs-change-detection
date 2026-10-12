#!/usr/bin/env python3
"""Fire recurrence inside any polygon layer — KHG, concessions, catchments.

`fire-national` answers "where does Indonesia burn repeatedly" on a province
grid. The questions that follow are all the same shape: how much of *this*
peat hydrological unit, *this* concession, *this* catchment burned, and how
often. So the zone accounting is one function, and the layer is an argument.

It needs no Earth Engine. Every figure is read back out of the province
rasters `fire-national` already wrote, with the same spherical area formula,
so a zone total and a province total cannot disagree about what a hectare is.

The one subtlety is double counting. The 38 province rasters are each clipped
to their own boundary but their bounding boxes overlap, and summing a zone
across two of them would count the border twice -- the provinces' own land
areas already add up about 1% over Indonesia for exactly this reason. Because
every raster sits on the same global lattice, the fix is to composite them
back onto that lattice in horizontal bands before counting anything, so each
ground pixel is visited once however many provinces claim it.

A zone's statistics describe what burned inside its boundary. They say nothing
about who lit it.
"""

import csv
import json
import os

from .fire_national import GRID_DEG, _popcount, slug

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

BAND_ROWS = 1024                 # global rows composited at a time
MIN_HA = 0.0                     # keep every zone by default


def _grid_index(x, deg=GRID_DEG):
    """Which column of the global lattice a longitude falls on."""
    return int(round(x / deg))


def _raster_frames(provinces_dir):
    """Each province raster's global row/col origin and shape."""
    import glob

    import rasterio
    out = []
    for p in sorted(glob.glob(os.path.join(provinces_dir, "*",
                                           "recurrence.tif"))):
        with rasterio.open(p) as ds:
            t = ds.transform
            out.append({"path": p, "count": ds.count,
                        "col0": _grid_index(t.c, abs(t.a)),
                        "row0": _grid_index(-t.f, abs(t.e)),
                        "w": ds.width, "h": ds.height, "deg": abs(t.a)})
    if not out:
        raise SystemExit(f"no province rasters in {provinces_dir} — run "
                         "fire-national first")
    degs = {r["deg"] for r in out}
    if len(degs) > 1:
        raise SystemExit(f"province rasters are on different grids ({degs}); "
                         "they cannot be composited")
    counts = {r["count"] for r in out}
    if len(counts) > 1:
        raise SystemExit(f"province rasters carry different band counts "
                         f"({counts}) — rerun fire-national so they match")
    return out


def _read_zones(path, field, layer=None, label=None):
    """The zone polygons in EPSG:4326, dissolved to one row per `field`.

    `label` carries a readable name alongside the key. KHG units are keyed by
    a code like KHG.62.11-14.02, which is the right thing to group on and the
    wrong thing to put on a chart.
    """
    import geopandas as gpd
    g = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    have = [c for c in g.columns if c != "geometry"]
    for opt, val in (("--zone-field", field), ("--zone-label", label)):
        if val and val not in g.columns:
            raise SystemExit(f"{opt} {val!r} is not in "
                             f"{os.path.basename(path)}; it has "
                             f"{', '.join(have)}")
    keep = [field, "geometry"] if not label else [field, label, "geometry"]
    g = g[keep].copy()
    g[field] = g[field].astype(str)
    if label:
        g[label] = g[label].astype(str)
    if g.crs is None:
        raise SystemExit(f"{os.path.basename(path)} has no CRS; it cannot be "
                         "placed on the fire grid")
    g = g.to_crs(4326)
    # An invalid polygon rasterises to nothing rather than raising, which
    # would quietly give a zone zero hectares. Repair first.
    bad = int((~g.geometry.is_valid).sum())
    if bad:
        print(f"  repairing {bad} invalid geometries (buffer 0)")
        g["geometry"] = g.geometry.buffer(0)
    # aggfunc only when there is a column to aggregate; newer pandas raises
    # on aggfunc=None rather than treating it as "nothing to do".
    return (g.dissolve(by=field, as_index=False, aggfunc="first") if label
            else g.dissolve(by=field, as_index=False))


def zone_stats(provinces_dir, zones, field, years, peat_keys, label=None,
               band_rows=BAND_ROWS, progress=print):
    """Hectares per zone, composited band by band off the global lattice."""
    import numpy as np
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from rasterio.windows import Window

    from .paddy_island import row_areas_ha

    frames = _raster_frames(provinces_dir)
    deg = frames[0]["deg"]
    nband = frames[0]["count"]
    if nband != len(peat_keys) + 2:
        raise SystemExit(f"the rasters have {nband} bands but {len(peat_keys)} "
                         "peat definitions were named")
    r0 = min(f["row0"] for f in frames)
    r1 = max(f["row0"] + f["h"] for f in frames)
    c0 = min(f["col0"] for f in frames)
    c1 = max(f["col0"] + f["w"] for f in frames)
    width = c1 - c0
    names = list(zones[field])
    shapes = [(geom, i + 1) for i, geom in enumerate(zones.geometry)]

    n = len(names)
    acc = {k: np.zeros(n + 1) for k in
           ("land", "burned", "repeat", "repeat3")}
    acc.update({f"peat_{k}": np.zeros(n + 1) for k in peat_keys})
    acc.update({f"burnpeat_{k}": np.zeros(n + 1) for k in peat_keys})
    acc.update({f"year_{y}": np.zeros(n + 1) for y in years})
    maxt = np.zeros(n + 1, dtype="uint8")
    pop = _popcount()

    opened = {}
    try:
        for top in range(r0, r1, band_rows):
            bot = min(top + band_rows, r1)
            h = bot - top
            inside = np.zeros((h, width), dtype=bool)
            bits = np.zeros((h, width), dtype="uint16")
            peat = {k: np.zeros((h, width), dtype=bool) for k in peat_keys}
            touched = False
            for f in frames:
                fr0, fr1 = f["row0"], f["row0"] + f["h"]
                if fr1 <= top or fr0 >= bot:
                    continue
                touched = True
                sr = max(fr0, top)
                er = min(fr1, bot)
                win = Window(0, sr - fr0, f["w"], er - sr)
                ds = opened.get(f["path"]) or rasterio.open(f["path"])
                opened[f["path"]] = ds
                a = ds.read(window=win)
                ys, ye = sr - top, er - top
                xs = f["col0"] - c0
                xe = xs + f["w"]
                ins = a[0] > 0
                # np.maximum, not assignment: where two provinces claim the
                # same ground pixel it is still one pixel, counted once.
                sl = (slice(ys, ye), slice(xs, xe))
                inside[sl] |= ins
                np.maximum(bits[sl], np.where(ins, a[-1], 0), out=bits[sl])
                for i, k in enumerate(peat_keys):
                    peat[k][sl] |= (a[i + 1] > 0) & ins
            if not touched or not inside.any():
                continue

            north = -top * deg
            tr = from_origin(c0 * deg, north, deg, deg)
            zid = rasterize(shapes, out_shape=(h, width), transform=tr,
                            fill=0, dtype="int32", all_touched=False)
            m = inside & (zid > 0)
            if not m.any():
                continue
            ha = np.repeat(row_areas_ha(tr, h)[:, None], width, axis=1)
            z = zid[m]
            w = ha[m]
            times = pop[bits[m]]

            def add(key, sel):
                acc[key] += np.bincount(z[sel], weights=w[sel],
                                        minlength=n + 1)

            add("land", np.ones(z.shape, dtype=bool))
            add("burned", times >= 1)
            add("repeat", times >= 2)
            add("repeat3", times >= 3)
            for k in peat_keys:
                pm = peat[k][m]
                add(f"peat_{k}", pm)
                add(f"burnpeat_{k}", pm & (times >= 1))
            bm = bits[m]
            for i, y in enumerate(years):
                add(f"year_{y}", ((bm >> i) & 1).astype(bool))
            np.maximum.at(maxt, z, times)
            if progress:
                progress(f"  rows {top - r0:,}–{bot - r0:,} of {r1 - r0:,}")
    finally:
        for ds in opened.values():
            ds.close()

    labels = list(zones[label]) if label else None
    rows = []
    for i, nm in enumerate(names, start=1):
        land, burned = acc["land"][i], acc["burned"][i]
        rec = {field: nm}
        if labels:
            rec[label] = labels[i - 1]
        rec.update({
            "land_ha": round(land, 1),
            "burned_ha": round(burned, 1),
            "repeat_ha": round(acc["repeat"][i], 1),
            "repeat3_ha": round(acc["repeat3"][i], 1),
            "max_times": int(maxt[i]),
            "burned_pct_of_zone": round(100 * burned / (land or 1), 2),
            "repeat_share_of_burned_pct": round(
                100 * acc["repeat"][i] / (burned or 1), 1),
            "burned_ha_by_year": {y: round(acc[f"year_{y}"][i], 1)
                                  for y in years}})
        bp = {}
        for k in peat_keys:
            rec[f"peat_ha_{k}"] = round(acc[f"peat_{k}"][i], 1)
            bp[k] = acc[f"burnpeat_{k}"][i]
            rec[f"burned_peat_ha_{k}"] = round(bp[k], 1)
            rec[f"peat_share_of_burned_pct_{k}"] = round(
                100 * bp[k] / (burned or 1), 1)
        rec["burned_peat_ha_range"] = [round(min(bp.values()), 1),
                                       round(max(bp.values()), 1)]
        rows.append(rec)
    return rows


def write_csv(rows, field, peat_keys, path, label=None):
    flat = [{k: v for k, v in r.items()
             if k not in ("burned_ha_by_year", "burned_peat_ha_range")}
            for r in rows]
    fields = [field] + ([label] if label else []) + [
        "land_ha", "burned_ha", "repeat_ha", "repeat3_ha",
        "max_times", "burned_pct_of_zone", "repeat_share_of_burned_pct"]
    fields += [f"{c}_{k}" for k in peat_keys for c in
               ("peat_ha", "burned_peat_ha", "peat_share_of_burned_pct")]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(flat, key=lambda r: -r["burned_ha"]))
    print(f"Table: {os.path.normpath(path)}")


def write_gpkg(zones, rows, field, path):
    """The polygons with their statistics attached, ready to open in QGIS."""
    try:
        import pandas as pd
    except ImportError:
        return None
    flat = [{k: v for k, v in r.items()
             if k not in ("burned_ha_by_year", "burned_peat_ha_range")}
            for r in rows]
    g = zones.merge(pd.DataFrame(flat), on=field, how="left")
    try:
        g.to_file(path, driver="GPKG", layer="zones")
    except Exception as e:                  # noqa: BLE001 — the CSV still ships
        print(f"  (GeoPackage skipped: {e.__class__.__name__}: {e})")
        return None
    print(f"Zones: {os.path.normpath(path)}")
    return path


def _render(rows, field, run_dir, years, peat_keys, title, top=20, label=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    rs = sorted(rows, key=lambda r: -r["burned_ha"])[:top]
    if not rs or not rs[0]["burned_ha"]:
        print("  (chart skipped: nothing burned in any zone)")
        return
    names = [str(r.get(label) or r[field])[:46] for r in rs]
    y = np.arange(len(rs))
    rep = [r["repeat_ha"] / 1e3 for r in rs]
    once = [(r["burned_ha"] - r["repeat_ha"]) / 1e3 for r in rs]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 0.44 * len(rs) + 2.8),
                                 dpi=150, gridspec_kw={"width_ratios": [2, 1]})
    fig.patch.set_facecolor("#faf8f4")
    a1.barh(y, rep, color="#7f2704", label="terbakar ≥ 2 tahun")
    a1.barh(y, once, left=rep, color="#fdae6b", label="terbakar 1 tahun")
    a1.set_yticks(y); a1.set_yticklabels(names, fontsize=8); a1.invert_yaxis()
    a1.set_xlabel("ribu ha terbakar", fontsize=9)
    a1.set_title("Luas terbakar", fontsize=11, fontweight="bold", loc="left")
    a1.legend(fontsize=8, loc="lower right")
    a1.grid(True, axis="x", ls=":", alpha=0.35)
    share = [r["burned_pct_of_zone"] for r in rs]
    a2.barh(y, share, color="#b30000")
    a2.set_yticks(y); a2.set_yticklabels([]); a2.invert_yaxis()
    a2.set_xlabel("% luas zona yang pernah terbakar", fontsize=9)
    a2.set_title("Porsi zona", fontsize=11, fontweight="bold", loc="left")
    for i, v in enumerate(share):
        a2.text(v + max(share) * 0.01, i, f"{v:.0f}%", va="center", fontsize=8)
    a2.grid(True, axis="x", ls=":", alpha=0.35)
    fig.suptitle(f"{title}, {years[0]}–{years[-1]}", fontsize=13,
                 fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(run_dir, "fire_zones_ranking.png")
    fig.savefig(out, facecolor="#faf8f4"); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


def run(run_dir, run_id, zones_file, zone_field, national_dir,
        zone_layer=None, zone_label=None, name="zones", min_ha=MIN_HA,
        title=None, **_):
    """Fire recurrence per zone, from an existing fire-national run."""
    for mod in ("numpy", "rasterio", "geopandas"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"fire-zones needs {mod}: "
                             "pip install 'earthchange[maps]' geopandas")
    pdir = os.path.join(national_dir, "provinces")
    nat_json = os.path.join(national_dir, "stats.json")
    if not os.path.isdir(pdir) or not os.path.exists(nat_json):
        raise SystemExit(
            f"{national_dir} is not a finished fire-national run "
            "(expected provinces/ and stats.json). Run fire-national first.")
    with open(nat_json) as f:
        nat = json.load(f)
    years = nat["years"]
    peat_keys = list(nat["peat_definitions"])
    print(f"  zones: {os.path.basename(zones_file)} by {zone_field!r}")
    zones = _read_zones(zones_file, zone_field, zone_layer, zone_label)
    print(f"  {len(zones)} zones, grid {GRID_DEG}°, "
          f"{years[0]}–{years[-1]}, peat: {', '.join(peat_keys)}")

    rows = zone_stats(pdir, zones, zone_field, years, peat_keys,
                      label=zone_label)
    if min_ha:
        rows = [r for r in rows if r["burned_ha"] >= min_ha]
        print(f"  {len(rows)} zones with ≥ {min_ha:g} ha burned")

    write_csv(rows, zone_field, peat_keys,
              os.path.join(run_dir, "zones.csv"), label=zone_label)
    write_gpkg(zones, rows, zone_field, os.path.join(run_dir, "zones.gpkg"))
    _render(rows, zone_field, run_dir, years, peat_keys,
            title or f"Kebakaran per zona — {name}", label=zone_label)

    tot = {k: round(sum(r[k] for r in rows), 1) for k in
           ("land_ha", "burned_ha", "repeat_ha", "repeat3_ha")}
    bp = {k: round(sum(r[f"burned_peat_ha_{k}"] for r in rows), 1)
          for k in peat_keys}
    stats = {
        "run_id": run_id, "scenario": "fire-zones", "name": name,
        "zones_file": os.path.abspath(zones_file), "zone_field": zone_field,
        "zone_label": zone_label,
        "from_run": os.path.abspath(national_dir),
        "years": years, "peat_definitions": nat["peat_definitions"],
        "zones": len(rows), "total": tot,
        "burned_peat_ha_by_definition": bp,
        "burned_pct_of_zones": round(
            100 * tot["burned_ha"] / (tot["land_ha"] or 1), 2),
        "repeat_share_of_burned_pct": round(
            100 * tot["repeat_ha"] / (tot["burned_ha"] or 1), 1),
        "by_zone": {str(r[zone_field]): r for r in rows},
        "caveats": nat.get("caveats", []) + [
            "A zone's burned area is what burned inside its boundary. It is "
            "not evidence about who lit it, or about whether the boundary's "
            "holder complied with anything.",
            "Zone totals are composited onto one global lattice before "
            "counting, so a zone crossing a province boundary is counted "
            "once -- but the zone layer's own overlaps, if it has any, are "
            "not resolved.",
        ],
    }
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n{len(rows)} zona · {tot['land_ha']:,.0f} ha · "
          f"{tot['burned_ha']:,.0f} ha terbakar "
          f"({stats['burned_pct_of_zones']:.1f}%), "
          f"{stats['repeat_share_of_burned_pct']:.0f}% berulang")
    for r in sorted(rows, key=lambda r: -r["burned_ha"])[:8]:
        print(f"    {str(r.get(zone_label) or r[zone_field])[:44]:<46}"
              f"{r['burned_ha']:>11,.0f} ha "
              f"({r['burned_pct_of_zone']:>5.1f}% zona, "
              f"{r['repeat_share_of_burned_pct']:>3.0f}% berulang)")
    return stats
