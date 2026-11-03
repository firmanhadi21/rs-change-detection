#!/usr/bin/env python3
"""Where did Kalimantan burn, and how much of it was inside oil-palm concessions?

THREE LAYERS ON ONE 500 m GRID (the fire-national lattice, 0.0045 deg,
anchored at 0,0):

  burned area   MODIS MCD64A1 v6.1, day of first burn per pixel per year.
                For the current year it stops at the last published month,
                which runs two to three months behind.
  hotspots      NASA FIRMS (MODIS Terra + Aqua, 1 km), confidence >= 30, for
                the stretch MCD64A1 has not reached yet. Hotspots are fire
                detections, not burned area; they are counted, never turned
                into hectares.
  concessions   GFW "Indonesia oil palm concessions" (1,845 polygons, company
                and parent group named). Boundaries come from the Ministry of
                Forestry around 2012 and have not been refreshed for
                Indonesia since, so permits issued, revoked or redrawn after
                that are not in it. Legal status in the layer is uneven: HGU
                (granted), HGU in process, location permits, and a large
                share with nothing recorded.

WHAT IS REPORTED
  - per year: burned hectares in Kalimantan, inside any concession, and the
    share of land the concessions cover, so the burned share can be read
    against what chance alone would put there
  - per concession and per group: burned hectares, burned share of the
    concession, late-season hotspot count
  - every contiguous burned patch of the current year, with its centroid,
    kabupaten, and the concession (if any) holding most of it

WHAT IT DOES NOT ESTABLISH. A burn inside a concession boundary says where
the fire was, not who lit it or why. Fires cross boundaries, community land
and smallholdings sit inside some concessions, and the boundaries are a
decade old. MCD64A1 is 500 m and misses burns of a few hectares, so small
clearing fires are under-counted inside and outside alike.

    conda run -n base python scripts/kalimantan_burn_concessions.py
    conda run -n base python scripts/kalimantan_burn_concessions.py --years 2026 2023 2019
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.join(_DATA_ROOT, "output", "fire", "kalimantan_concessions")
CONC = os.path.join(_DATA_ROOT, "data", "concessions", "gfw_idn_oil_palm.gpkg")
CONC_URL = ("https://gis-gfw.wri.org/arcgis/rest/services/country_data/asia/"
            "MapServer/2")

sys.path.insert(0, _REPO_ROOT)
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from earthchange.fire_national import GRID_DEG, BURN_IC  # noqa: E402

MIN_CONF = 30
TILES = 3                       # TILES x TILES downloads
R_EARTH = 6371008.8

# Legal status, coarsened. The layer's own `type` is blank for about half the
# polygons; `po_legalst` fills some of those.
STATUS = {
    "HGU": "HGU (granted)", "Sudah HGU": "HGU (granted)",
    "HGU in process": "HGU in process", "Proses": "HGU in process",
    "Ijin Lokasi": "location permit", "Izin Lokasi": "location permit",
    "Ijin Prinsip": "location permit", "Pencadangan": "location permit",
    "Informasi Lahan": "location permit", "Aspek PGT": "location permit",
}


def status(row):
    for k in ("type", "po_legalst"):
        v = (row.get(k) or "").strip()
        if v and v != "No Data":
            return STATUS.get(v, v)
    return "not recorded"


# ----------------------------- Earth Engine -----------------------------
def ee_layers(years):
    import ee
    from earthchange.gee_utils import gaul
    l2 = gaul(2).filter(ee.Filter.stringContains("ADM1_NAME", "Kalimantan"))
    rows = l2.reduceColumns(ee.Reducer.toList(2),
                            ["ADM1_NAME", "ADM2_NAME"]).get("list").getInfo()
    rows = sorted({tuple(r) for r in rows})
    provs = sorted({p for p, _ in rows})
    kab_idx = ee.Dictionary({f"{p}|{k}": i + 1 for i, (p, k) in enumerate(rows)})
    l2 = l2.map(lambda f: f.set("kab", kab_idx.get(
        ee.String(f.get("ADM1_NAME")).cat("|").cat(f.get("ADM2_NAME")))))
    kab = ee.Image(0).paint(l2, "kab").toUint16().rename("kab")

    last = ee.Date(ee.ImageCollection(BURN_IC).sort("system:time_start", False)
                   .first().get("system:time_start"))
    last_month = last.format("YYYY-MM").getInfo()

    img = kab
    for y in years:
        ic = (ee.ImageCollection(BURN_IC)
              .filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("BurnDate"))
        doy = (ic.map(lambda im: im.updateMask(im.gt(0))).min()
               .unmask(0).toUint16().rename(f"doy{y}"))
        img = img.addBands(doy)
    return img, l2, rows, provs, last_month


def ee_hotspots(geom, start, end):
    """FIRMS detections as (lon, lat, confidence, date)."""
    import ee
    from earthchange.fire_hotspot import _points
    return _points(ee, ee.ImageCollection("FIRMS"), ee.Date(start),
                   ee.Date(end), geom, MIN_CONF)


def download(img, bounds, out_dir):
    """The image on the shared lattice, in TILES x TILES pieces, merged."""
    import ee
    import numpy as np
    import rasterio
    from rasterio.merge import merge
    from earthchange.fire_national import grid_transform
    from earthchange.gee_utils import download_geotiff

    d = GRID_DEG
    x0, y0, x1, y1 = bounds
    c0, c1 = int(np.floor(x0 / d)), int(np.ceil(x1 / d))
    r0, r1 = int(np.floor(-y1 / d)), int(np.ceil(-y0 / d))  # rows go south
    cs = np.linspace(c0, c1, TILES + 1).astype(int)
    rs = np.linspace(r0, r1, TILES + 1).astype(int)
    paths = []
    for i in range(TILES):
        for j in range(TILES):
            p = os.path.join(out_dir, f"tile_{i}{j}.tif")
            if not os.path.exists(p):
                reg = ee.Geometry.Rectangle(
                    [cs[j] * d, -rs[i + 1] * d, cs[j + 1] * d, -rs[i] * d],
                    None, False)
                if not download_geotiff(img, reg, p,
                                        crs_transform=grid_transform()):
                    raise SystemExit(f"download failed for {p}")
                with rasterio.open(p) as ds:
                    if abs(ds.transform.a - d) > 1e-12:
                        os.remove(p)
                        raise SystemExit(f"{p} came back coarsened; lower "
                                         "the tile size")
            paths.append(p)
    srcs = [rasterio.open(p) for p in paths]
    arr, tr = merge(srcs, method="max")      # tiles share edges, not data
    names = srcs[0].descriptions
    for s in srcs:
        s.close()
    return arr, tr, names


# ------------------------------- local ----------------------------------
def pixel_ha(transform, shape):
    """Spherical area of each row's pixels, hectares (column vector)."""
    import numpy as np
    d = abs(transform.a)
    lat_top = transform.f - np.arange(shape[0]) * d
    lat_bot = lat_top - d
    a = (R_EARTH ** 2 * np.radians(d)
         * np.abs(np.sin(np.radians(lat_top)) - np.sin(np.radians(lat_bot))))
    return (a / 1e4)[:, None]


def render_map(path, tr, land, inside, burned, hs, top, prov, year,
               last_month, hs_start, hs_end):
    """Land, concessions, burned area inside/outside them, late hotspots."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    cls = np.zeros(land.shape, np.uint8)
    cls[land] = 1
    cls[inside] = 2
    cls[burned & ~inside] = 3
    cls[burned & inside] = 4
    cmap = ListedColormap(["#ffffff", "#e6e3dc", "#b9c9a8", "#f08a24", "#b3001b"])
    h, w = land.shape
    ext = (tr.c, tr.c + w * tr.a, tr.f + h * tr.e, tr.f)

    fig, ax = plt.subplots(figsize=(11, 10), dpi=150)
    ax.imshow(cls, cmap=cmap, vmin=0, vmax=4, extent=ext,
              interpolation="nearest")
    # Province edges from the kabupaten raster: a pixel whose neighbour is in
    # another province.
    codes = {p: i + 1 for i, p in enumerate(sorted(set(prov[land])))}
    pi = np.vectorize(lambda s: codes.get(s, 0))(prov) if codes else prov
    edge = np.zeros_like(land)
    edge[:, 1:] |= pi[:, 1:] != pi[:, :-1]
    edge[1:, :] |= pi[1:, :] != pi[:-1, :]
    edge &= land
    ax.imshow(np.ma.masked_where(~edge, edge), cmap=ListedColormap(["#555"]),
              extent=ext, interpolation="nearest")
    if len(hs):
        ax.scatter(hs.lon, hs.lat, s=0.3, c="#6a1b9a", alpha=0.25, lw=0)
    for k, (_, r) in enumerate(top.iterrows(), 1):
        ax.annotate(str(k), (r.lon, r.lat), xytext=(6, 6),
                    textcoords="offset points", fontsize=8, weight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#333",
                              lw=0.5))
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")
    ax.set_title(f"Kalimantan: burned area {year} (Jan–{last_month[5:]}) and "
                 f"oil-palm concessions", fontsize=13, loc="left")
    ax.legend(handles=[
        Patch(fc="#b9c9a8", label="oil-palm concession (GFW / KLHK c.2012)"),
        Patch(fc="#b3001b", label=f"burned {year}, inside a concession"),
        Patch(fc="#f08a24", label=f"burned {year}, outside"),
        Line2D([], [], marker="o", ls="", mfc="#6a1b9a", mec="none", ms=4,
               alpha=0.6, label=f"FIRMS hotspot {hs_start} – {hs_end}"),
    ], loc="lower left", fontsize=8, frameon=True)
    ax.text(0.99, 0.01, "Burned area: MODIS MCD64A1 (500 m). Hotspots: NASA "
            "FIRMS MODIS, conf ≥ 30.\nConcessions: Global Forest Watch. "
            "Numbers mark the 15 largest burned patches.",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7,
            color="#444")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, nargs="+", default=[2026, 2023, 2019],
                    help="first is the current year (patches are listed for it)")
    ap.add_argument("--concessions", default=CONC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--min-patch-ha", type=float, default=100.0)
    a = ap.parse_args()

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    from rasterio import features
    from rasterio.windows import from_bounds
    from scipy import ndimage

    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    import ee

    os.makedirs(a.out, exist_ok=True)
    tiles_dir = os.path.join(a.out, "tiles_" + "_".join(map(str, a.years)))
    os.makedirs(tiles_dir, exist_ok=True)
    cur = a.years[0]

    img, l2, kab_rows, provs, last_month = ee_layers(a.years)
    geom = l2.geometry()
    bounds = ee.Geometry(geom.bounds(1000)).coordinates().getInfo()[0]
    xs, ys = [p[0] for p in bounds], [p[1] for p in bounds]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    print(f"MCD64A1 last month {last_month}; Kalimantan bbox {bbox}")

    # The hotspot window runs from the first day MCD64A1 has not covered.
    ly, lm = map(int, last_month.split("-"))
    hs_start = f"{ly + (lm == 12)}-{lm % 12 + 1:02d}-01"
    hs_end = ee.Date(ee.ImageCollection("FIRMS").sort("system:time_start", False)
                     .first().get("system:time_start")).format("YYYY-MM-dd").getInfo()
    hs_path = os.path.join(a.out, f"firms_{hs_start}_{hs_end}.csv")
    if os.path.exists(hs_path):
        hs = pd.read_csv(hs_path)
    else:
        print(f"FIRMS {hs_start} .. {hs_end} ...")
        hs = pd.DataFrame(ee_hotspots(geom, hs_start, hs_end),
                          columns=["lon", "lat", "confidence", "date"])
        hs.to_csv(hs_path, index=False)
    print(f"  {len(hs):,} hotspot pixel-days")

    print("downloading burned-area stack ...")
    arr, tr, _ = download(img, bbox, tiles_dir)
    # GEE's GeoTIFFs carry no band descriptions; the order is the image's.
    names = ["kab"] + [f"doy{y}" for y in a.years]
    if arr.shape[0] != len(names):
        raise SystemExit(f"expected {len(names)} bands, got {arr.shape[0]}")
    band = {n: arr[i] for i, n in enumerate(names)}
    kab = band["kab"].astype(np.int32)
    land = kab > 0
    ha = np.broadcast_to(pixel_ha(tr, kab.shape), kab.shape)
    kab_prov = np.array([""] + [p for p, _ in kab_rows])
    kab_name = np.array([""] + [k for _, k in kab_rows])

    # --- concessions -----------------------------------------------------
    conc = gpd.read_file(a.concessions).to_crs(4326)
    conc["geometry"] = conc.geometry.make_valid()
    conc = conc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]].copy()
    conc["status"] = conc.apply(status, axis=1)
    conc["group_comp"] = conc["group_comp"].fillna("").replace("", "No group")
    shape = kab.shape
    # Overlap count per pixel, so a pixel claimed twice is visible rather than
    # silently double counted in the "inside any" total.
    n_in = np.zeros(shape, np.uint8)
    for g in conc.geometry:
        n_in += features.rasterize([(g, 1)], out_shape=shape, transform=tr,
                                   dtype="uint8")
    inside = (n_in > 0) & land
    # Pixel -> one concession (the largest wins where they overlap) for
    # labelling patches.
    owner = features.rasterize(
        [(g, i + 1) for i, g in sorted(enumerate(conc.geometry),
                                       key=lambda t: -conc.iloc[t[0]].area_ha)],
        out_shape=shape, transform=tr, dtype="int32")
    kal_conc = conc.iloc[[i for i in range(len(conc))
                          if (land & (owner == i + 1)).any()]].copy()

    land_ha = ha[land].sum()
    in_ha = ha[inside].sum()
    overlap_ha = ha[(n_in > 1) & land].sum()
    print(f"Kalimantan land {land_ha:,.0f} ha; concessions cover "
          f"{in_ha:,.0f} ha ({100 * in_ha / land_ha:.1f}%), "
          f"{overlap_ha:,.0f} ha claimed by more than one")

    summary = {"mcd64a1_last_month": last_month, "land_ha": land_ha,
               "concession_ha": in_ha, "concession_overlap_ha": overlap_ha,
               "concession_polygons_in_kalimantan": int(len(kal_conc)),
               "hotspot_window": [hs_start, hs_end], "years": {},
               "provinces": {}}

    # --- per year, overall and by status / province ----------------------
    st_img = {}
    for s in sorted(conc.status.unique()):
        geoms = conc.geometry[conc.status == s]
        st_img[s] = features.rasterize([(g, 1) for g in geoms], out_shape=shape,
                                       transform=tr, dtype="uint8").astype(bool) & land
    for y in a.years:
        b = (band[f"doy{y}"] > 0) & land
        bh = ha[b].sum()
        bi = ha[b & inside].sum()
        yr = {"burned_ha": bh, "burned_in_concession_ha": bi,
              "share_in_concession": bi / bh if bh else None,
              "ratio_to_land_share": (bi / bh) / (in_ha / land_ha) if bh else None,
              "by_status": {s: {"area_ha": ha[m].sum(),
                                "burned_ha": ha[b & m].sum()}
                            for s, m in st_img.items()},
              "period": (f"{y}-01..{last_month}" if y == ly else f"{y}-01..{y}-12")}
        summary["years"][str(y)] = yr
        print(f"\n{y} ({yr['period']}): burned {bh:,.0f} ha, "
              f"in concessions {bi:,.0f} ha = {100 * yr['share_in_concession']:.1f}%"
              f"  (concessions are {100 * in_ha / land_ha:.1f}% of land, "
              f"{yr['ratio_to_land_share']:.2f}x)")
        for s, v in yr["by_status"].items():
            print(f"   {s:<18} {v['burned_ha']:>10,.0f} ha of {v['area_ha']:>11,.0f}")

    kp = kab_prov[kab]
    for p in provs:
        m = land & (kp == p)
        row = {"land_ha": ha[m].sum(), "concession_ha": ha[m & inside].sum()}
        for y in a.years:
            b = (band[f"doy{y}"] > 0) & m
            row[f"burned_{y}_ha"] = ha[b].sum()
            row[f"burned_{y}_in_conc_ha"] = ha[b & inside].sum()
        summary["provinces"][p] = row

    # --- hotspots in concessions ----------------------------------------
    hs_g = gpd.GeoDataFrame(hs, geometry=gpd.points_from_xy(hs.lon, hs.lat),
                            crs=4326)
    if len(hs_g):
        cols = ((hs_g.lon - tr.c) / tr.a).astype(int)
        rows = ((hs_g.lat - tr.f) / tr.e).astype(int)
        ok = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
        hs_g = hs_g[ok]
        hs_g["kab"] = kab[rows[ok], cols[ok]]
        hs_g = hs_g[hs_g.kab > 0]
        j = gpd.sjoin(hs_g, kal_conc[["gfwid", "geometry"]], predicate="within",
                      how="left")
        in_any = j.groupby(level=0).gfwid.apply(lambda s: s.notna().any())
        summary["hotspots"] = {"total": int(len(hs_g)),
                               "in_concession": int(in_any.sum())}
        hs_per = j.dropna(subset=["gfwid"]).groupby("gfwid").size()
        print(f"\nFIRMS {hs_start}..{hs_end}: {len(hs_g):,} hotspots in "
              f"Kalimantan, {int(in_any.sum()):,} "
              f"({100 * in_any.mean():.1f}%) inside a concession")
    else:
        hs_per = pd.Series(dtype=int)
        summary["hotspots"] = {"total": 0, "in_concession": 0}

    # --- per concession --------------------------------------------------
    recs = []
    for _, c in kal_conc.iterrows():
        try:
            w = from_bounds(*c.geometry.bounds, transform=tr).round_offsets().round_lengths()
        except Exception:  # noqa: BLE001
            continue
        r0, c0 = max(int(w.row_off), 0), max(int(w.col_off), 0)
        r1 = min(int(w.row_off + w.height) + 1, shape[0])
        c1 = min(int(w.col_off + w.width) + 1, shape[1])
        if r1 <= r0 or c1 <= c0:
            continue
        sub_tr = tr * tr.translation(c0, r0)
        m = features.rasterize([(c.geometry, 1)], out_shape=(r1 - r0, c1 - c0),
                               transform=sub_tr, dtype="uint8").astype(bool)
        m &= land[r0:r1, c0:c1]
        sha = ha[r0:r1, c0:c1]
        k = kab[r0:r1, c0:c1][m]
        rec = {"company": c.company or c["name"], "group": c.group_comp,
               "status": c.status, "hgu_no": c.po_hgu or "",
               "gfwid": c.gfwid, "area_ha": sha[m].sum(),
               "province": kab_prov[np.bincount(k).argmax()] if k.size else "",
               "kabupaten": kab_name[np.bincount(k).argmax()] if k.size else "",
               "hotspots_late": int(hs_per.get(c.gfwid, 0))}
        for y in a.years:
            b = band[f"doy{y}"][r0:r1, c0:c1] > 0
            rec[f"burned_{y}_ha"] = sha[m & b].sum()
        rec[f"burned_{cur}_pct"] = (100 * rec[f"burned_{cur}_ha"] / rec["area_ha"]
                                    if rec["area_ha"] else 0)
        recs.append(rec)
    per = pd.DataFrame(recs).sort_values(f"burned_{cur}_ha", ascending=False)
    per.to_csv(os.path.join(a.out, "concessions_burned.csv"), index=False)
    grp = (per.groupby("group")
           .agg(concessions=("gfwid", "size"), area_ha=("area_ha", "sum"),
                **{f"burned_{y}_ha": (f"burned_{y}_ha", "sum") for y in a.years},
                hotspots_late=("hotspots_late", "sum"))
           .sort_values(f"burned_{cur}_ha", ascending=False))
    grp.to_csv(os.path.join(a.out, "groups_burned.csv"))

    # --- patches of the current year -------------------------------------
    b = (band[f"doy{cur}"] > 0) & land
    lab, n = ndimage.label(b, structure=np.ones((3, 3)))
    idx = np.arange(1, n + 1)
    p_ha = ndimage.sum(ha, lab, idx)
    p_in = ndimage.sum(ha * inside, lab, idx)
    keep = idx[p_ha >= a.min_patch_ha]
    objs = ndimage.find_objects(lab)
    doy = band[f"doy{cur}"]
    prec, polys = [], []
    for i in keep:
        sl = objs[i - 1]
        m = lab[sl] == i
        rr, cc = np.nonzero(m)
        w = ha[sl][m]
        r_c = (rr + sl[0].start + 0.5) @ w / w.sum()
        c_c = (cc + sl[1].start + 0.5) @ w / w.sum()
        lon, lat = tr * (c_c, r_c)
        k = kab[sl][m]
        o = owner[sl][m]
        o = o[o > 0]
        top = (conc.iloc[np.bincount(o).argmax() - 1] if o.size else None)
        d = doy[sl][m]
        prec.append({
            "patch": int(i), "area_ha": round(float(p_ha[i - 1]), 1),
            "in_concession_ha": round(float(p_in[i - 1]), 1),
            "lon": round(float(lon), 4), "lat": round(float(lat), 4),
            "province": kab_prov[np.bincount(k).argmax()],
            "kabupaten": kab_name[np.bincount(k).argmax()],
            "first_burn_doy": int(d.min()), "last_burn_doy": int(d.max()),
            "main_concession": (top.company or top["name"]) if top is not None else "",
            "main_group": top.group_comp if top is not None else "",
            "main_status": top.status if top is not None else ""})
    pat = pd.DataFrame(prec).sort_values("area_ha", ascending=False)
    pat["first_burn"] = pd.to_datetime(f"{cur}-01-01") + pd.to_timedelta(pat.first_burn_doy - 1, "D")
    pat["last_burn"] = pd.to_datetime(f"{cur}-01-01") + pd.to_timedelta(pat.last_burn_doy - 1, "D")
    pat.to_csv(os.path.join(a.out, f"patches_{cur}.csv"), index=False)

    # Polygons of every burned pixel, current year, for maps.
    shp = [{"type": "Feature", "geometry": g, "properties": {"patch": int(v)}}
           for g, v in features.shapes(lab.astype(np.int32), mask=b, transform=tr)]
    with open(os.path.join(a.out, f"burned_{cur}.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": shp}, f)
    kal_conc.to_file(os.path.join(a.out, "concessions_kalimantan.gpkg"),
                     driver="GPKG")

    render_map(os.path.join(a.out, f"map_{cur}.png"), tr, land, inside, b,
               hs_g, pat.head(15), kab_prov[kab], cur, last_month,
               hs_start, hs_end)

    summary["patches"] = {"count_all": int(n), "count_ge_min": int(len(keep)),
                          "min_patch_ha": a.min_patch_ha}
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=float)

    pd.set_option("display.width", 200)
    print(f"\nTop concessions by burned area {cur}:")
    print(per.head(20)[["company", "group", "status", "province", "area_ha",
                        f"burned_{cur}_ha", f"burned_{cur}_pct",
                        "hotspots_late"]].round(0).to_string(index=False))
    print(f"\nTop groups {cur}:")
    print(grp.head(15).round(0).to_string())
    print(f"\n{len(keep)} patches >= {a.min_patch_ha:.0f} ha (of {n:,}); largest:")
    print(pat.head(20).drop(columns=["first_burn_doy", "last_burn_doy"])
          .to_string(index=False))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
