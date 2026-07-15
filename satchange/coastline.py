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
MAX_RATE_M_YR = 30.0   # transects with |rate| beyond this are measurement artifacts


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


# ================= optical (Sentinel-2 MNDWI, sub-pixel shoreline) =================
# Our own MIT implementation of the published MNDWI + Otsu + marching-squares method
# (Vos et al. 2019) — NOT CoastSat code (which is GPL). Cloud-limited but sub-pixel.
def _mndwi_tif(aoi, win, run_dir, tag, scale, sensor):
    """MNDWI (Green,SWIR1) composite downloaded as a GeoTIFF. sensor: 's2' or 'landsat'."""
    from .gee_utils import download_geotiff
    if sensor == "landsat":
        from .indices import l_sr_median          # L5 TM + L8/9 OLI, archive to 1984
        img, n = l_sr_median(aoi, *win)
        bands = ["GREEN", "SWIR1"]
    else:
        from .indices import s2_median
        img, n = s2_median(aoi, *win)
        bands = ["B3", "B11"]
    if n == 0:
        raise SystemExit(f"No {sensor} scenes in {win[0]}..{win[1]} for this AOI. "
                         "Widen the window or change --coast-method.")
    mndwi = img.normalizedDifference(bands).rename("MNDWI").clip(aoi)
    path = os.path.join(run_dir, f"mndwi_{tag}.tif")
    download_geotiff(mndwi, aoi, path, scale=scale)
    return path, n


def _read_band(tif):
    import numpy as np
    import rasterio
    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float32")
        nod, tr, crs = src.nodata, src.transform, src.crs
    valid = np.isfinite(arr)
    if nod is not None:
        valid &= arr != nod
    return arr, valid, tr, crs


def _px_km2(tr, midlat):
    return abs(tr.a) * 111.32 * math.cos(math.radians(midlat)) * abs(tr.e) * 110.57


def _declutter_np(mask, min_size=25):
    import numpy as np
    from scipy import ndimage
    lbl, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lbl, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= min_size]
    return np.isin(lbl, keep)


def _otsu_sea(arr, valid, smooth_px):
    """Otsu-threshold MNDWI → water → border-connected sea (opened by smooth_px)."""
    import numpy as np
    from skimage import filters, morphology
    from scipy import ndimage
    thr = float(filters.threshold_otsu(arr[valid]))
    water = (arr > thr) & valid
    lbl, _ = ndimage.label(water)
    border = set(lbl[0]) | set(lbl[-1]) | set(lbl[:, 0]) | set(lbl[:, -1])
    border.discard(0)
    sea = np.isin(lbl, list(border))
    if smooth_px:
        sea = ndimage.binary_opening(sea, structure=morphology.disk(smooth_px))
    return sea, thr


def _subpixel_coast(arr, valid, thr, sea, tr, band_px, min_len_km=0.4):
    """Marching-squares sub-pixel contour of MNDWI at the Otsu level, kept to the coast band."""
    import numpy as np
    import rasterio
    from skimage import measure
    from scipy import ndimage
    edge = ndimage.binary_dilation(sea) & ~ndimage.binary_erosion(sea)
    band = ndimage.binary_dilation(edge, iterations=max(int(band_px), 2))
    filled = np.where(valid, arr, thr)
    H, W = arr.shape
    lines = []
    for c in measure.find_contours(filled, thr):
        xs, ys = rasterio.transform.xy(tr, c[:, 0], c[:, 1])
        rr = np.clip(np.round(c[:, 0]).astype(int), 0, H - 1)
        cc = np.clip(np.round(c[:, 1]).astype(int), 0, W - 1)
        inband = band[rr, cc]
        seg = []
        for k in range(len(xs)):
            if inband[k]:
                seg.append([xs[k], ys[k]])
            else:
                if len(seg) >= 2:
                    lines.append(seg)
                seg = []
        if len(seg) >= 2:
            lines.append(seg)
    kept, total = [], 0.0
    for ln in lines:
        L = sum(_haversine_km(ln[i], ln[i + 1]) for i in range(len(ln) - 1))
        if L >= min_len_km:
            kept.append(ln)
            total += L
    return kept, round(total, 2)


def _write_mask_tif(path, mask, tr, crs):
    import numpy as np
    import rasterio
    arr = np.where(mask, 1.0, np.nan).astype("float32")[None]
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2],
                       count=1, dtype="float32", crs=crs, transform=tr, compress="deflate") as d:
        d.write(arr)


def _run_optical(aoi, bbox, run_dir, name, scale, smooth_m, pre, post, sensor, label):
    try:
        import skimage  # noqa: F401
    except ImportError:
        raise SystemExit("optical coastline needs scikit-image: pip install 'satchange[maps]'")
    smooth_px = max(int((smooth_m or 0) / scale), 0)
    band_px = max(int((smooth_m or 30) / scale), 2)
    midlat = (bbox[1] + bbox[3]) / 2.0

    post_tif, n_post = _mndwi_tif(aoi, post, run_dir, "post" if pre else "now", scale, sensor)
    arr, valid, tr, crs = _read_band(post_tif)
    sea_post, thr = _otsu_sea(arr, valid, smooth_px)
    _write_mask_tif(os.path.join(run_dir, "sea_mask.tif"), sea_post, tr, crs)
    lines, length_km = _subpixel_coast(arr, valid, thr, sea_post, tr, band_px)
    _write_geojson(os.path.join(run_dir, "coastline.geojson"),
                   {"type": "MultiLineString", "coordinates": lines},
                   {"kind": "coastline", "length_km": length_km,
                    "method": "optical MNDWI Otsu sub-pixel"})
    px = _px_km2(tr, midlat)

    if pre:
        pre_tif, n_pre = _mndwi_tif(aoi, pre, run_dir, "pre", scale, sensor)
        parr, pvalid, ptr, _ = _read_band(pre_tif)
        if parr.shape != arr.shape:
            raise SystemExit("optical pre/post grids differ; try equal --pre/--post windows.")
        sea_pre, _ = _otsu_sea(parr, pvalid, smooth_px)
        ero = _declutter_np(sea_post & ~sea_pre)
        acc = _declutter_np(sea_pre & ~sea_post)
        _write_mask_tif(os.path.join(run_dir, "erosion.tif"), ero, tr, crs)
        _write_mask_tif(os.path.join(run_dir, "accretion.tif"), acc, tr, crs)
        ero_ha, acc_ha = int(ero.sum()) * px * 100.0, int(acc.sum()) * px * 100.0
        _render_map(run_dir, name, bbox, lines,
                    [("erosion", "erosion.tif", "#d62728"), ("accretion", "accretion.tif", "#2ca02c")],
                    f"Shoreline change ({label} MNDWI ~sub-pixel) — {name}  ·  "
                    f"erosion {ero_ha:.0f} ha, accretion {acc_ha:.0f} ha")
        return {"mode": "change", "method": sensor, "pre": list(pre), "post": list(post),
                "coastline_length_km_post": length_km, "erosion_ha": round(ero_ha, 1),
                "accretion_ha": round(acc_ha, 1), "net_land_change_ha": round(acc_ha - ero_ha, 1),
                "scenes_pre": n_pre, "scenes_post": n_post}

    sea_km2 = int(sea_post.sum()) * px
    aoi_km2 = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians(midlat)) * (bbox[3] - bbox[1]) * 110.57
    _render_map(run_dir, name, bbox, lines, [],
                f"Coastline ({label} MNDWI ~sub-pixel) — {name}  ·  {length_km:.1f} km")
    return {"mode": "single", "method": sensor, "window": list(post),
            "coastline_length_km": length_km, "sea_area_km2": round(sea_km2, 2),
            "land_area_km2": round(max(aoi_km2 - sea_km2, 0), 2), "scenes": n_post}


# ===================== periodical / time-series (optical, landsat) =====================
def _shift_year(datestr, delta):
    y, m, d = datestr.split("-")
    return f"{int(y) + delta:04d}-{m}-{d}"


def _epoch_shoreline(aoi, win, run_dir, scale, sensor, smooth_px, band_px, midlat, aoi_km2):
    yr = win[0][:4]
    tif = n = None
    for pad in (0, 1, 2):                      # widen the window if an epoch is empty
        try:
            tif, n = _mndwi_tif(aoi, (_shift_year(win[0], -pad), _shift_year(win[1], pad)),
                                run_dir, yr, scale, sensor)
            break
        except SystemExit:
            tif = None
    if tif is None:
        return None, None, None, None
    arr, valid, tr, _crs = _read_band(tif)
    sea, thr = _otsu_sea(arr, valid, smooth_px)
    lines, length_km = _subpixel_coast(arr, valid, thr, sea, tr, band_px)
    _write_geojson(os.path.join(run_dir, f"coastline_{yr}.geojson"),
                   {"type": "MultiLineString", "coordinates": lines},
                   {"year": int(yr), "length_km": length_km})
    sea_km2 = int(sea.sum()) * _px_km2(tr, midlat)
    rec = {"year": int(yr), "window": list(win), "scenes": n,
           "coastline_length_km": length_km, "sea_area_km2": round(sea_km2, 2),
           "land_area_km2": round(max(aoi_km2 - sea_km2, 0), 2)}
    return rec, lines, sea, tr


def _run_timeseries(aoi, bbox, run_dir, name, scale, smooth_m, epochs, sensor, label,
                    transect_spacing=500):
    try:
        import skimage  # noqa: F401
    except ImportError:
        raise SystemExit("optical coastline needs scikit-image: pip install 'satchange[maps]'")
    smooth_px = max(int((smooth_m or 0) / scale), 0)
    band_px = max(int((smooth_m or 30) / scale), 2)
    midlat = (bbox[1] + bbox[3]) / 2.0
    aoi_km2 = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians(midlat)) * (bbox[3] - bbox[1]) * 110.57
    series, year_lines, ref_sea, ref_tr = [], {}, None, None
    for win in epochs:
        print(f"  epoch {win[0][:4]}: {win[0]}..{win[1]}")
        rec, lines, sea, tr = _epoch_shoreline(aoi, win, run_dir, scale, sensor,
                                               smooth_px, band_px, midlat, aoi_km2)
        if rec is None:
            print(f"    {win[0][:4]}: no scenes (even ±2 yr) — skipped")
            continue
        series.append(rec)
        year_lines[rec["year"]] = lines
        ref_sea, ref_tr = sea, tr        # latest usable epoch = landward-most baseline
        print(f"    scenes={rec['scenes']:3d}  coastline={rec['coastline_length_km']:6.1f} km  "
              f"land={rec['land_area_km2']:.0f} km²")
    if not series:
        raise SystemExit("No epoch had usable scenes — widen the windows or check the AOI.")
    feats = [{"type": "Feature", "properties": {"year": yr},
              "geometry": {"type": "MultiLineString", "coordinates": year_lines[yr]}}
             for yr in sorted(year_lines)]
    with open(os.path.join(run_dir, "shorelines.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    _render_series_map(run_dir, name, bbox, year_lines, label)
    _render_trend(run_dir, name, series)
    first, last = series[0], series[-1]
    out = {"mode": "timeseries", "method": sensor, "label": label,
           "epochs": [s["year"] for s in series], "series": series,
           "from_year": first["year"], "to_year": last["year"],
           "net_land_change_ha": round((last["land_area_km2"] - first["land_area_km2"]) * 100, 1)}
    if transect_spacing and len(series) >= 2 and ref_sea is not None:
        t = _run_transects(run_dir, name, bbox, year_lines, ref_sea, ref_tr, transect_spacing)
        if t:
            out["transects"] = t
    return out


def _add_basemap(ax):
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron, attribution=False)
    except Exception as ex:  # noqa: BLE001
        print(f"  (basemap skipped: {ex})")


def _render_series_map(run_dir, name, bbox, year_lines, label):
    plt = _plt()
    from matplotlib.lines import Line2D
    w, s, e, n = bbox
    years = sorted(year_lines)
    cmap = plt.get_cmap("viridis")
    cols = [cmap(i / max(len(years) - 1, 1)) for i in range(len(years))]  # one per epoch
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    for col, yr in zip(cols, years):
        for seg in year_lines[yr]:
            xs = [p[0] for p in seg]; ys = [p[1] for p in seg]
            ax.plot(xs, ys, color=col, lw=1.2, alpha=0.9, zorder=5)
    ax.legend(handles=[Line2D([0], [0], color=c, lw=2.6, label=str(y))
                       for c, y in zip(cols, years)],
              title="Shoreline year", loc="lower right", framealpha=0.92, fontsize=9)
    ax.set_title(f"Shoreline time-series ({label} MNDWI ~sub-pixel) — {name}",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    fig.tight_layout(); fig.savefig(os.path.join(run_dir, "shorelines_map.png")); plt.close(fig)
    print("Time-series map: shorelines_map.png")


def _render_trend(run_dir, name, series):
    plt = _plt()
    yrs = [s["year"] for s in series]
    land = [s["land_area_km2"] for s in series]
    length = [s["coastline_length_km"] for s in series]
    fig, ax1 = plt.subplots(figsize=(7, 4.2), dpi=150)
    ax1.plot(yrs, land, "-o", color="#8c564b", label="Land area (km²)")
    ax1.set_xlabel("Year"); ax1.set_ylabel("Land area in AOI (km²)", color="#8c564b")
    ax1.tick_params(axis="y", labelcolor="#8c564b")
    for x, y in zip(yrs, land):
        ax1.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, 6),
                     ha="center", fontsize=7, color="#8c564b")
    ax2 = ax1.twinx()
    ax2.plot(yrs, length, "--s", color="#1f6fb2")
    ax2.set_ylabel("Coastline length (km)", color="#1f6fb2")
    ax2.tick_params(axis="y", labelcolor="#1f6fb2")
    ax1.set_title(f"Coastal trend — {name}")
    ax1.grid(True, ls=":", alpha=0.5)
    fig.tight_layout(); fig.savefig(os.path.join(run_dir, "trend.png")); plt.close(fig)
    print("Trend chart: trend.png")


# ===================== transects (cross-shore retreat rate, m/yr) =====================
def _proj(bbox):
    """Local equirectangular projection to metres (accurate over a small AOI)."""
    lon0, lat0 = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110570.0
    return (lambda lon, lat: ((lon - lon0) * kx, (lat - lat0) * ky),
            lambda x, y: (lon0 + x / kx, lat0 + y / ky))


def _lines_to_m(lines, to_m):
    from shapely.geometry import LineString, MultiLineString
    segs = [LineString([to_m(p[0], p[1]) for p in seg]) for seg in lines if len(seg) >= 2]
    return MultiLineString(segs) if segs else None


def _baseline_normals(ref_sea, tr, to_m, spacing):
    """Longest contour of the reference sea → baseline points + unit normals (metres)."""
    import numpy as np
    import rasterio
    from skimage import measure
    contours = measure.find_contours(ref_sea.astype(float), 0.5)
    if not contours:
        return None, None
    c = max(contours, key=len)
    lon, lat = rasterio.transform.xy(tr, c[:, 0], c[:, 1])
    xy = np.array([to_m(lo, la) for lo, la in zip(lon, lat)])
    d = np.r_[0.0, np.cumsum(np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1])))]
    if d[-1] < spacing * 2:
        return None, None
    ss = np.arange(spacing, d[-1], spacing)
    pts = np.column_stack([np.interp(ss, d, xy[:, 0]), np.interp(ss, d, xy[:, 1])])
    from scipy.ndimage import uniform_filter1d           # smooth for stable normals
    pts[:, 0] = uniform_filter1d(pts[:, 0], size=5, mode="nearest")
    pts[:, 1] = uniform_filter1d(pts[:, 1], size=5, mode="nearest")
    tang = np.gradient(pts, axis=0)
    tl = np.hypot(tang[:, 0], tang[:, 1]); tl[tl == 0] = 1
    tang /= tl[:, None]
    nrm = np.column_stack([-tang[:, 1], tang[:, 0]])
    return pts, nrm


def _sea_votes(pt, direction, ref_sea, tr, to_ll, step, nsteps):
    """Count sea pixels sampled `nsteps` along `direction` from `pt` (metres)."""
    import rasterio
    H, W = ref_sea.shape
    v = 0
    for k in range(1, nsteps + 1):
        lon, lat = to_ll(*(pt + direction * step * k))
        row, col = rasterio.transform.rowcol(tr, lon, lat)
        if 0 <= row < H and 0 <= col < W and ref_sea[row, col]:
            v += 1
    return v


def _orient_seaward(pts, nrm, ref_sea, tr, to_ll, step=90.0, nsteps=8):
    """Point each transect toward the sea: vote over several steps on both sides."""
    out = nrm.copy()
    for i in range(len(pts)):
        pos = _sea_votes(pts[i], nrm[i], ref_sea, tr, to_ll, step, nsteps)
        neg = _sea_votes(pts[i], -nrm[i], ref_sea, tr, to_ll, step, nsteps)
        if neg > pos:
            out[i] = -nrm[i]           # more sea on the -normal side → flip
    return out


def _intersection_dist(tline, ml, ox, oy):
    import numpy as np
    inter = tline.intersection(ml)
    if inter.is_empty:
        return None
    coords = []
    for g in (inter.geoms if hasattr(inter, "geoms") else [inter]):
        coords += list(g.coords) if g.geom_type != "Point" else [(g.x, g.y)]
    if not coords:
        return None
    return max(np.hypot(x - ox, y - oy) for x, y in coords)   # seaward-most crossing


def _transect_rates(pts, nrm, length, year_lines_m, years):
    from shapely.geometry import LineString
    import numpy as np
    out = []
    for i in range(len(pts)):
        o = pts[i]; end = o + nrm[i] * length
        tline = LineString([tuple(o), tuple(end)])
        dby = {}
        for yr in years:
            ml = year_lines_m.get(yr)
            if ml is None:
                continue
            dist = _intersection_dist(tline, ml, o[0], o[1])
            if dist is not None:
                dby[yr] = dist
        if len(dby) >= 2:
            yy = np.array(sorted(dby)); dd = np.array([dby[y] for y in yy])
            rate = float(np.polyfit(yy, dd, 1)[0])       # m/yr; <0 = retreat
            if abs(rate) <= MAX_RATE_M_YR:               # drop artifacts on complex coasts
                out.append({"origin": tuple(o), "end": tuple(end), "rate": rate,
                            "n": len(dby),
                            "dist_by_year": {int(y): round(float(dby[y]), 1) for y in dby}})
    return out


def _run_transects(run_dir, name, bbox, year_lines, ref_sea, tr, spacing, length=2500.0):
    to_m, to_ll = _proj(bbox)
    pts, nrm = _baseline_normals(ref_sea, tr, to_m, spacing)
    if pts is None:
        print("  (transects skipped: no usable baseline contour)")
        return None
    nrm = _orient_seaward(pts, nrm, ref_sea, tr, to_ll)
    ylm = {yr: _lines_to_m(year_lines[yr], to_m) for yr in year_lines}
    tr_res = _transect_rates(pts, nrm, length, ylm, sorted(year_lines))
    if not tr_res:
        print("  (transects skipped: no transect crossed >=2 shorelines)")
        return None
    import numpy as np
    feats = []
    for k, t in enumerate(tr_res):
        feats.append({"type": "Feature",
                      "properties": {"id": k, "rate_m_per_yr": round(t["rate"], 2),
                                     "n_years": t["n"], "dist_by_year": t["dist_by_year"]},
                      "geometry": {"type": "LineString",
                                   "coordinates": [list(to_ll(*t["origin"])), list(to_ll(*t["end"]))]}})
    with open(os.path.join(run_dir, "transects.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    rates = np.array([t["rate"] for t in tr_res])
    _render_transects(run_dir, name, bbox, year_lines, tr_res, to_ll)
    print(f"Transects: {len(tr_res)} @ {spacing:.0f} m  ·  median rate {np.median(rates):+.1f} m/yr")
    return {"n_transects": len(tr_res), "spacing_m": spacing,
            "mean_rate_m_per_yr": round(float(rates.mean()), 2),
            "median_rate_m_per_yr": round(float(np.median(rates)), 2),
            "max_retreat_m_per_yr": round(float(rates.min()), 2),
            "pct_retreating": round(100.0 * float((rates < 0).mean()), 1)}


def _render_transects(run_dir, name, bbox, year_lines, tr_res, to_ll):
    plt = _plt()
    import numpy as np
    from matplotlib import cm, colors
    w, s, e, n = bbox
    rates = np.array([t["rate"] for t in tr_res])
    lim = max(1.0, float(np.nanpercentile(np.abs(rates), 95)))
    norm = colors.Normalize(-lim, lim)
    cmap = plt.get_cmap("RdBu")               # red = retreat (neg), blue = advance (pos)
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    for yr in sorted(year_lines):             # faint shorelines for context
        for seg in year_lines[yr]:
            ax.plot([p[0] for p in seg], [p[1] for p in seg], color="#999", lw=0.4, alpha=0.5, zorder=3)
    for t in tr_res:
        (ox, oy), (ex, ey) = to_ll(*t["origin"]), to_ll(*t["end"])
        ax.plot([ox, ex], [oy, ey], color=cmap(norm(t["rate"])), lw=1.6, zorder=5)
    sm = cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
    fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label="Shoreline change rate (m/yr)  ·  red = retreat")
    ax.set_title(f"Shoreline retreat rate along transects — {name}", fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    fig.tight_layout(); fig.savefig(os.path.join(run_dir, "transects_map.png")); plt.close(fig)
    print("Transect map: transects_map.png")


def _dispatch_optical(aoi, bbox, run_dir, name, method, smooth_m, pre, post, epochs, spacing):
    sensor = "landsat" if method == "landsat" else "s2"
    osc = 30 if method == "landsat" else 10          # Landsat 30 m, S2 10 m
    label = "Landsat" if method == "landsat" else "Sentinel-2"
    print(f"Optical ({label} MNDWI sub-pixel, {osc} m); smoothing {smooth_m} m")
    if epochs:
        print(f"Time-series: {len(epochs)} epochs; transects @ {spacing} m" if spacing
              else f"Time-series: {len(epochs)} epochs (no transects)")
        return _run_timeseries(aoi, bbox, run_dir, name, osc, smooth_m, epochs, sensor, label, spacing)
    return _run_optical(aoi, bbox, run_dir, name, osc, smooth_m, pre, post, sensor, label)


def _dispatch_sar(aoi, bbox, run_dir, name, scale, smooth_m, thr, pre, post, epochs):
    if epochs:
        raise SystemExit("--epochs time-series needs --coast-method optical or landsat.")
    from .indices import best_orbit
    periods = [pre, post] if pre else [post]
    orbit, covered, counts = best_orbit(aoi, periods, pol="VV")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers all windows: {counts}")
    print(f"Sentinel-1 VV, orbit {orbit}, scenes {counts}; smoothing {smooth_m} m")
    if pre:
        print(f"Shoreline CHANGE: {pre[0]}..{pre[1]}  →  {post[0]}..{post[1]}")
        return _run_change(aoi, bbox, orbit, pre, post, run_dir, name, scale, thr, smooth_m)
    print(f"Coastline (single date): {post[0]}..{post[1]}")
    return _run_single(aoi, bbox, orbit, post, run_dir, name, scale, thr, smooth_m)


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        pre=None, post=None, thr=VV_WATER_THR, smooth_m=150, method="sar", epochs=None,
        transect_spacing=500):
    """Entry point called by detect.py for the coastline scenario (GEE only).

    method: 'sar' (Sentinel-1 VV water mask → vector; cloud-proof) or 'optical'
    (Sentinel-2 MNDWI + Otsu + marching-squares sub-pixel contour; cloud-limited,
    sharper). `smooth_m` opens the sea to strip tambak/pond fingers (0 = raw edge).
    """
    if backend == "mpc":
        raise SystemExit("coastline currently needs --backend gee.")
    from .gee_utils import initialize_ee, square_aoi
    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    scale = 10
    post = post or DEFAULT_WIN

    if method in ("optical", "landsat"):
        stats = _dispatch_optical(aoi, bbox, run_dir, name, method, smooth_m,
                                  pre, post, epochs, transect_spacing)
    else:
        stats = _dispatch_sar(aoi, bbox, run_dir, name, scale, smooth_m, thr, pre, post, epochs)

    stats.update({"run_id": run_id, "scenario": "coastline", "smooth_m": smooth_m,
                  "location": {"lat": lat, "lon": lon}, "radius_km": radius})
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("\n=== Results ===")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("run_id",)}, indent=2))
