#!/usr/bin/env python3
"""Sea coastline extraction & shoreline change from Sentinel-1 SAR (cloud-proof).

Water is smooth → low VV backscatter. We threshold a despeckled VV composite to a
water mask, keep only the water body connected to the AOI edge (the SEA — inland
lakes/ponds are dropped), and extract the sea↔land boundary as both a raster and a
vector polyline (GeoJSON) you can open in QGIS.

Single date (default, or --post window): coastline + sea/land areas.
Two dates (--pre and --post): shoreline CHANGE — erosion (land→sea) and
accretion/reclamation (sea→land), with areas in hectares.

GEE-only. Registered as scenario `coastline`; detect.py dispatches here.
"""

import os
import json
import math

# Clear a stale external PROJ override so rasterio/contextily use their own PROJ.
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

try:
    import ee
except ImportError:
    ee = None

VV_WATER_THR = -18.0   # dB — open sea water is very smooth
DEFAULT_WIN = ("2025-01-01", "2025-12-31")


# ------------------------------- SAR sea mask -------------------------------
def _vv_water(aoi, win, orbit, thr):
    from .indices import s1
    img = s1(aoi, *win, orbit, "VV").median().clip(aoi)
    img = img.focal_median(50, "circle", "meters")   # despeckle
    water = img.lt(thr)
    # morphological closing: fill small dry patches / speckle holes in the sea
    return water.focal_max(60, "circle", "meters").focal_min(60, "circle", "meters")


def _open_sea(mask, m):
    """Morphological opening (erode→dilate) of the WATER mask: removes water features
    narrower than ~2*m — tambak/pond fingers and thin channels — so they disconnect
    from the sea and get dropped, leaving the open-sea mainland shoreline. m in metres;
    0 = no smoothing. Applied BEFORE sea isolation so we still vectorise only once."""
    if not m:
        return mask
    return mask.focal_min(m, "circle", "meters").focal_max(m, "circle", "meters")


def _sea(water, aoi, scale):
    """Keep only water connected to the AOI edge (the sea). Returns (sea_fc, sea_img)."""
    polys = water.selfMask().reduceToVectors(
        geometry=aoi, scale=scale, geometryType="polygon",
        eightConnected=True, maxPixels=int(1e10), bestEffort=True)
    frame = ee.Feature(aoi).geometry()
    edge = frame.difference(frame.buffer(-scale * 3), ee.ErrorMargin(1))
    sea_fc = polys.filterBounds(edge)                  # water touching the AOI edge
    sea_img = ee.Image(0).paint(sea_fc, 1).clip(aoi)   # rasterise sea (1 = sea)
    return sea_fc, sea_img


def _km2(mask, aoi, scale):
    a = mask.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=scale,
        maxPixels=int(1e10), bestEffort=True).values().get(0)
    return ee.Number(a).divide(1e6).getInfo()


# --------------------------- coastline vector (client side) ---------------------------
def _haversine_km(a, b):
    R = 6371.0088
    lon1, lat1, lon2, lat2 = a[0], a[1], b[0], b[1]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def _ring_coastline(ring, on_frame):
    """One polygon ring → (coastline polylines, length km), dropping AOI-frame edges."""
    seg, lines, length = [], [], 0.0
    for i in range(len(ring) - 1):
        a, b = ring[i], ring[i + 1]
        if on_frame(a) and on_frame(b):                # frame edge → break the line here
            if len(seg) >= 2:
                lines.append(seg)
            seg = []
        else:
            if not seg:
                seg = [a]
            seg.append(b)
            length += _haversine_km(a, b)
    if len(seg) >= 2:
        lines.append(seg)
    return lines, length


def _coastline_lines(sea_geojson, bbox, eps=1.5e-4, min_ring_km=0.4):
    """Sea-polygon rings → coastline polylines, dropping rings (small holes/islets)
    whose coastline portion is shorter than `min_ring_km`."""
    w, s, e, n = bbox

    def on_frame(pt):
        return (abs(pt[0] - w) < eps or abs(pt[0] - e) < eps
                or abs(pt[1] - s) < eps or abs(pt[1] - n) < eps)

    g = sea_geojson or {}
    polys = ([g["coordinates"]] if g.get("type") == "Polygon"
             else g["coordinates"] if g.get("type") == "MultiPolygon" else [])
    lines, total = [], 0.0
    for poly in polys:
        for ring in poly:
            rl, rlen = _ring_coastline(ring, on_frame)
            if rlen >= min_ring_km:                     # drop tiny holes/islets
                lines.extend(rl)
                total += rlen
    return lines, total


def _write_geojson(path, geometry_dict, props=None):
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": props or {},
                        "geometry": geometry_dict}]}
    with open(path, "w") as f:
        json.dump(fc, f)


def _extract_coastline(sea_fc, aoi, bbox, run_dir, tag):
    """Write sea.geojson + coastline.geojson for one date; return coastline length km."""
    sea_geom = sea_fc.geometry(ee.ErrorMargin(60)).simplify(ee.ErrorMargin(60)).getInfo()
    suffix = f"_{tag}" if tag else ""
    _write_geojson(os.path.join(run_dir, f"sea{suffix}.geojson"), sea_geom, {"kind": "sea"})
    lines, length_km = _coastline_lines(sea_geom, bbox)
    _write_geojson(os.path.join(run_dir, f"coastline{suffix}.geojson"),
                   {"type": "MultiLineString", "coordinates": lines},
                   {"kind": "coastline", "length_km": round(length_km, 2)})
    return round(length_km, 2), lines


# ------------------------------- rendering -------------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _render_map(run_dir, name, bbox, coast_lines, extras, title):
    """Coastline (+ optional erosion/accretion rasters) over a basemap."""
    plt = _plt()
    import numpy as np
    import rasterio
    w, s, e, n = bbox
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron,
                       attribution=False)
    except Exception as ex:  # noqa: BLE001
        print(f"  (basemap skipped: {ex})")
    for label, tif, color in extras:                    # erosion/accretion rasters
        p = os.path.join(run_dir, tif)
        if not os.path.exists(p):
            continue
        with rasterio.open(p) as src:
            arr = src.read(1, masked=True); b = src.bounds
        ax.imshow(np.where(np.ma.filled(arr, 0) > 0, 1.0, np.nan),
                  extent=[b.left, b.right, b.bottom, b.top], origin="upper",
                  cmap=_solid(color), vmin=0, vmax=1, alpha=0.75, zorder=3)
    for seg in coast_lines:                              # coastline polyline
        xs = [p[0] for p in seg]; ys = [p[1] for p in seg]
        ax.plot(xs, ys, color="#d62728", lw=1.4, zorder=6)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    out = os.path.join(run_dir, "coastline_map.png")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    print(f"Map: coastline_map.png")


def _solid(hexcol):
    from matplotlib.colors import ListedColormap
    return ListedColormap([hexcol])


# ------------------------------- orchestration -------------------------------
def _download(img, aoi, run_dir, key, vis, scale):
    from .gee_utils import download_png, download_geotiff
    download_png(img, aoi, os.path.join(run_dir, key + ".png"), vis=vis)
    download_geotiff(img, aoi, os.path.join(run_dir, key + ".tif"), scale=scale)


def _run_single(aoi, bbox, orbit, win, run_dir, name, scale, thr, smooth_m):
    water = _open_sea(_vv_water(aoi, win, orbit, thr), smooth_m)
    sea_fc, sea_img = _sea(water, aoi, scale)
    _download(sea_img.selfMask(), aoi, run_dir, "sea_mask",
              {"min": 0, "max": 1, "palette": ["1f6fb2"]}, scale)
    length_km, lines = _extract_coastline(sea_fc, aoi, bbox, run_dir, "")
    sea_km2 = _km2(sea_img, aoi, scale)
    aoi_km2 = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians((bbox[1] + bbox[3]) / 2)) \
        * (bbox[3] - bbox[1]) * 110.57
    stats = {"mode": "single", "orbit": orbit, "window": list(win),
             "coastline_length_km": length_km,
             "sea_area_km2": round(sea_km2, 2),
             "land_area_km2": round(max(aoi_km2 - sea_km2, 0), 2)}
    _render_map(run_dir, name, bbox, lines, [],
                f"Coastline (Sentinel-1 SAR) — {name}  ·  {length_km:.1f} km")
    return stats


def _declutter(mask):
    """Keep only change clusters >= ~25 connected pixels (drop scattered pond/wave speckle)."""
    keep = mask.selfMask().connectedPixelCount(100, True).unmask(0).gte(25)
    return mask.And(keep)


def _run_change(aoi, bbox, orbit, pre, post, run_dir, name, scale, thr, smooth_m):
    _, sea_pre = _sea(_open_sea(_vv_water(aoi, pre, orbit, thr), smooth_m), aoi, scale)
    sea_post_fc, sea_post = _sea(_open_sea(_vv_water(aoi, post, orbit, thr), smooth_m), aoi, scale)
    ero = _declutter(sea_post.And(sea_pre.Not()))
    acc = _declutter(sea_pre.And(sea_post.Not()))
    _download(ero.selfMask().clip(aoi).rename("erosion"), aoi, run_dir, "erosion",
              {"min": 0, "max": 1, "palette": ["d62728"]}, scale)
    _download(acc.selfMask().clip(aoi).rename("accretion"), aoi, run_dir, "accretion",
              {"min": 0, "max": 1, "palette": ["2ca02c"]}, scale)
    length_km, lines = _extract_coastline(sea_post_fc, aoi, bbox, run_dir, "post")
    ero_ha = _km2(ero, aoi, scale) * 100.0
    acc_ha = _km2(acc, aoi, scale) * 100.0
    stats = {"mode": "change", "orbit": orbit,
             "pre": list(pre), "post": list(post),
             "coastline_length_km_post": length_km,
             "erosion_ha": round(ero_ha, 1), "accretion_ha": round(acc_ha, 1),
             "net_land_change_ha": round(acc_ha - ero_ha, 1)}
    _render_map(run_dir, name, bbox, lines,
                [("erosion (land→sea)", "erosion.tif", "#d62728"),
                 ("accretion (sea→land)", "accretion.tif", "#2ca02c")],
                f"Shoreline change — {name}  ·  erosion {ero_ha:.0f} ha, accretion {acc_ha:.0f} ha")
    return stats


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        pre=None, post=None, thr=VV_WATER_THR, smooth_m=150):
    """Entry point called by detect.py for the coastline scenario (GEE only).

    `smooth_m` (metres) morphologically opens the sea to strip tambak/pond fingers
    and narrow inlets, yielding the open-sea mainland shoreline (0 = raw water edge).
    """
    if backend == "mpc":
        raise SystemExit("coastline currently needs --backend gee (SAR + vector via GEE).")
    from .gee_utils import initialize_ee, square_aoi
    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    scale = 10

    from .indices import best_orbit
    post = post or DEFAULT_WIN
    periods = [pre, post] if pre else [post]
    orbit, covered, counts = best_orbit(aoi, periods, pol="VV")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers all windows: {counts}")
    print(f"Sentinel-1 VV, orbit {orbit}, scenes {counts}")

    print(f"Sea smoothing (open-sea): {smooth_m} m" if smooth_m else "Sea smoothing: off (raw water edge)")
    if pre:
        print(f"Shoreline CHANGE: {pre[0]}..{pre[1]}  →  {post[0]}..{post[1]}")
        stats = _run_change(aoi, bbox, orbit, pre, post, run_dir, name, scale, thr, smooth_m)
    else:
        print(f"Coastline (single date): {post[0]}..{post[1]}")
        stats = _run_single(aoi, bbox, orbit, post, run_dir, name, scale, thr, smooth_m)

    stats.update({"run_id": run_id, "scenario": "coastline", "smooth_m": smooth_m,
                  "location": {"lat": lat, "lon": lon}, "radius_km": radius})
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("\n=== Results ===")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("run_id",)}, indent=2))
