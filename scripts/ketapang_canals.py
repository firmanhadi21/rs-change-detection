#!/usr/bin/env python3
"""Drainage canals on the Ketapang coast, inside the four concessions and out.

Drained peat burns: canals lower the water table, the surface peat dries and
fire can enter it. To test whether drainage explains why the four concessions
burned more than comparable land outside, this maps straight drainage lines
the same way on both sides of every boundary.

  OSM         waterway = canal | ditch | drain (volunteer-mapped; patchy, kept
              as a cross-check, never the main measure)
  Sentinel-2  B8 (NIR) median of clear dry-season scenes (Jun-Sep 2025 and
              May-mid Jul 2026), on a 0.000075 deg (~8.3 m) lattice nested 3x3
              in the 25 m grid. Water in a canal is dark in NIR against
              vegetation, so a black-ridge (Sato) filter at 1-2 px picks thin
              dark lines; the response is thresholded, skeletonised, and
              kept only as segments >= MIN_LEN_M long and STRAIGHT (end-to-end
              span / skeleton length >= STRAIGHT). Rivers meander and are
              dropped; canals and their dark spoil banks are straight.
Output: canal density (km per km2) on a 1 km window, written onto the 25 m
grid for ketapang_excess_burn.py, and a check figure over the PlanetScope
windows.

LIMITS. A canal filled in, overgrown or narrower than ~5 m is missed; a
straight road edge or firebreak in shadow can be picked up. Both errors apply
inside and outside alike, which is what a comparison needs; absolute lengths
should not be quoted as a canal inventory.

    conda run -n base python scripts/ketapang_canals.py
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import CONC, FOUR, OUT as ORIGIN, GRID  # noqa: E402
from ketapang_landprep_tests import ee_download  # noqa: E402

OUT = os.path.join(ORIGIN, "canals")
FINE = GRID / 3                      # ~8.3 m
PAD = 0.12                           # deg around the four (~13 km)
TILES = 16
MIN_LEN_M = 300
STRAIGHT = 0.85
WIN_KM = 1.0
OVERPASS = "https://overpass-api.de/api/interpreter"


def s2_nir(bbox):
    import ee

    def one(im):
        scl = im.select("SCL")
        ok = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        return im.select("B8").updateMask(ok)
    # filterBounds matters: without it every tile asked EE for a median over
    # the whole planet's scenes in the window and timed out
    ic = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(ee.Geometry.Rectangle(list(bbox), None, False))
          .filter(ee.Filter.Or(ee.Filter.date("2025-06-01", "2025-10-01"),
                               ee.Filter.date("2026-05-01", "2026-07-15")))
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(one))
    return ic.median().unmask(0).toInt16()


def osm_lines(bbox, path):
    import geopandas as gpd
    import requests
    from shapely.geometry import LineString
    if os.path.exists(path):
        return gpd.read_file(path)
    s, w, n, e = bbox[1], bbox[0], bbox[3], bbox[2]
    q = f"""[out:json][timeout:180];
(way["waterway"~"canal|ditch|drain"]({s},{w},{n},{e});
 way["highway"]({s},{w},{n},{e}););
out geom;"""
    r = requests.post(OVERPASS, data={"data": q}, timeout=240,
                      headers={"User-Agent": "rs-change-detection/1.0"})
    r.raise_for_status()
    rows = []
    for el in r.json().get("elements", []):
        g = el.get("geometry")
        if not g or len(g) < 2:
            continue
        t = el.get("tags", {})
        kind = "canal" if "waterway" in t else "road"
        rows.append({"kind": kind, "tag": t.get("waterway") or t.get("highway"),
                     "geometry": LineString([(p["lon"], p["lat"]) for p in g])})
    gdf = gpd.GeoDataFrame(rows, crs=4326)
    gdf.to_file(path)
    print(f"OSM: {len(gdf)} ways ({(gdf.kind == 'canal').sum()} waterways)")
    return gdf


def detect(nir):
    """Straight dark lines in NIR -> boolean skeleton."""
    import numpy as np
    from skimage.filters import sato
    from skimage.morphology import skeletonize, remove_small_objects
    from skimage.measure import label, regionprops
    x = nir.astype(np.float32)
    valid = x > 0
    if valid.sum() < 1000:
        return np.zeros(x.shape, bool)
    lo, hi = np.percentile(x[valid], [1, 99])
    x = np.clip((x - lo) / (hi - lo + 1e-9), 0, 1)
    x[~valid] = 1.0
    resp = sato(x, sigmas=[1, 1.5, 2], black_ridges=True)
    thr = np.percentile(resp[valid], 95)
    m = (resp > thr) & valid
    m = remove_small_objects(m, 20)
    sk = skeletonize(m)
    lab = label(sk, connectivity=2)
    keep = np.zeros_like(sk)
    px = FINE * 111320
    for rp in regionprops(lab):
        n = rp.area
        if n * px < MIN_LEN_M:
            continue
        r0, c0, r1, c1 = rp.bbox
        span = np.hypot(r1 - r0, c1 - c0)
        if span / n >= STRAIGHT:
            keep[lab == rp.label] = True
    return keep


def main():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from rasterio.merge import merge
    from scipy import ndimage
    from earthchange.gee_utils import initialize_ee
    import glob
    initialize_ee()
    os.makedirs(OUT, exist_ok=True)

    conc = gpd.read_file(CONC).to_crs(4326)
    four = conc[conc.company.str.contains("|".join(FOUR.values()), na=False)]
    x0, y0, x1, y1 = four.total_bounds
    bbox = (x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD)

    osm = osm_lines(bbox, os.path.join(OUT, "osm_lines.gpkg"))

    print("Sentinel-2 NIR, ~8 m ...")
    arr, ftr = ee_download(s2_nir(bbox), bbox, os.path.join(OUT, "s2nir"), "nir", FINE, TILES)
    nir = arr[0]
    print("detecting lines ...", nir.shape)
    can = np.zeros(nir.shape, bool)
    # tile the filter with overlap so long lines are not cut at tile edges
    T, ov = 2000, 100
    for r in range(0, nir.shape[0], T):
        for c in range(0, nir.shape[1], T):
            r0, c0 = max(r - ov, 0), max(c - ov, 0)
            sub = detect(nir[r0:r + T + ov, c0:c + T + ov])
            can[r:r + T, c:c + T] = sub[r - r0:r - r0 + T, c - c0:c - c0 + T]
    prof = dict(driver="GTiff", height=can.shape[0], width=can.shape[1], count=1,
                dtype="uint8", crs="EPSG:4326", transform=ftr, compress="deflate")
    with rasterio.open(os.path.join(OUT, "canals_s2_8m.tif"), "w", **prof) as ds:
        ds.write(can.astype(np.uint8), 1)

    # density: km of line per km2 in a WIN_KM window, at 8 m then onto 25 m
    px_km = FINE * 111.32
    win = int(round(WIN_KM / px_km))
    dens = ndimage.uniform_filter(can.astype(np.float32), win) * (win * win) * px_km \
        / (WIN_KM ** 2)
    # OSM waterways rasterised the same way
    oc = osm[osm.kind == "canal"]
    om = features.rasterize([(g, 1) for g in oc.geometry], out_shape=can.shape,
                            transform=ftr, dtype="uint8", all_touched=True) > 0 \
        if len(oc) else np.zeros(can.shape, bool)
    odens = ndimage.uniform_filter(om.astype(np.float32), win) * (win * win) * px_km \
        / (WIN_KM ** 2)

    # onto the 25 m stack grid
    srcs = [rasterio.open(p) for p in sorted(glob.glob(os.path.join(ORIGIN, "stack", "stack_*.tif")))]
    stack, tr = merge(srcs, method="first")
    for s in srcs:
        s.close()
    shape = stack.shape[1:]
    from rasterio.warp import reproject, Resampling
    out = np.full((2,) + shape, -1, np.float32)
    for i, a in enumerate((dens, odens)):
        reproject(a.astype(np.float32), out[i], src_transform=ftr, src_crs="EPSG:4326",
                  dst_transform=tr, dst_crs="EPSG:4326", resampling=Resampling.average,
                  dst_nodata=-1)
    prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=2,
                dtype="float32", crs="EPSG:4326", transform=tr, compress="deflate",
                nodata=-1)
    with rasterio.open(os.path.join(OUT, "canal_density_25m.tif"), "w", **prof) as ds:
        ds.write(out)
        ds.descriptions = ("S2 straight-line density km/km2 (1 km window)",
                           "OSM waterway density km/km2 (1 km window)")

    # quick zone comparison
    land = stack[5] == 1
    anyc = features.rasterize([(g, 1) for g in conc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]].geometry],
                              out_shape=shape, transform=tr, dtype="uint8") > 0
    res = {}
    cov = out[0] >= 0
    for _, r in four.iterrows():
        acr = next(k for k, v in FOUR.items() if v in r.company)
        m = features.rasterize([(r.geometry, 1)], out_shape=shape, transform=tr,
                               dtype="uint8") > 0
        res[acr] = {"s2_km_per_km2": float(out[0][m & land & cov].mean()),
                    "osm_km_per_km2": float(out[1][m & land & cov].mean())}
    m4 = features.rasterize([(g, 1) for g in four.geometry], out_shape=shape,
                            transform=tr, dtype="uint8") > 0
    for nm, m in (("the four", m4), ("other concessions", anyc & ~m4),
                  ("unconceded", ~anyc)):
        res[nm] = {"s2_km_per_km2": float(out[0][m & land & cov].mean()),
                   "osm_km_per_km2": float(out[1][m & land & cov].mean())}
    print(json.dumps({k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in res.items()},
                     indent=1))
    json.dump(res, open(os.path.join(OUT, "summary.json"), "w"), indent=2)

    # check figure over the PlanetScope windows
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ketapang_planet_check import OUT as PLANET, read_ps, rgb
    plan = json.load(open(os.path.join(PLANET, "plan.json")))
    fig, axes = plt.subplots(3, 3, figsize=(15, 15.5), dpi=130)
    for ax, s in zip(axes.ravel(), plan):
        a, ptr, pcrs, pb = read_ps(s["pre"]["tif"])
        ax.imshow(rgb(a), interpolation="nearest",
                  extent=(pb.left, pb.right, pb.bottom, pb.top))
        w, so, e, n = s["bbox"]
        c0, r0 = ~ftr * (w, n)
        c1, r1 = ~ftr * (e, so)
        sub = can[int(r0):int(r1), int(c0):int(c1)]
        ys, xs = np.nonzero(sub)
        lon = ftr.c + (xs + int(c0) + 0.5) * ftr.a
        lat = ftr.f + (ys + int(r0) + 0.5) * ftr.e
        from pyproj import Transformer
        tx = Transformer.from_crs(4326, pcrs, always_xy=True)
        X, Y = tx.transform(lon, lat)
        ax.scatter(X, Y, s=0.3, c="#ff2bd6", lw=0)
        ax.set_title(f"{s['concession']} · {s['kind']}", fontsize=10, loc="left")
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Detected straight drainage lines (magenta, Sentinel-2) over PlanetScope",
                 x=0.01, ha="left", fontsize=13, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    p = os.path.join(OUT, "canals_check_planet.png")
    fig.savefig(p)
    plt.close(fig)
    print(f"Saved: {p}")


if __name__ == "__main__":
    main()
