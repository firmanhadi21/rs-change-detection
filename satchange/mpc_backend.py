#!/usr/bin/env python3
"""Microsoft Planetary Computer backend — change detection WITHOUT Earth Engine.

Pulls Sentinel-1 (RTC) and Sentinel-2 L2A Cloud-Optimized GeoTIFFs from the
Planetary Computer STAC API (free, no account — assets are signed anonymously)
and processes them locally with odc-stac / xarray / numpy / rasterio.

Selected by `detect.py --backend mpc`. Produces the same outputs as the GEE
backend (PNG + GeoTIFF + stats JSON + .meta.json), so `--map` works unchanged.

Requires: pystac-client, planetary-computer, odc-stac, rioxarray, rasterio.
"""

import os
import json
import math

# Remove a stale external PROJ override (e.g. an OTB install exporting PROJ_LIB)
# so rasterio and pyproj each use their OWN bundled PROJ database. Do NOT set a
# shared PROJ_DATA — rasterio's PROJ (v6+) can't read pyproj's older layout.
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import numpy as np
import rasterio

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
DIVERGING = ["#a50026", "#d73027", "#fee08b", "#ffffbf", "#d9ef8b", "#1a9850", "#006837"]

# Bands to load per index, and the numpy formula (mirrors indices.py for GEE).
INDEX_LOAD = {
    "NDVI": ["B08", "B04"], "NDBI": ["B11", "B08"],
    "NDWI": ["B03", "B08"], "NBR": ["B08", "B12"],
    "UI": ["B12", "B08"], "BU": ["B11", "B08", "B04"],
    "IBI": ["B11", "B08", "B04", "B03"],
}


def _b(ds, name):
    return ds[name].astype("float32").values


def _nd(a, b):
    return (a - b) / (a + b)


def _savi_np(ds, L=0.5):
    nir, red = _b(ds, "B08") / 10000.0, _b(ds, "B04") / 10000.0
    return (1 + L) * (nir - red) / (nir + red + L)


def _ix_ibi(ds):
    nd = _nd(_b(ds, "B11"), _b(ds, "B08"))                       # NDBI
    x = (_savi_np(ds) + _nd(_b(ds, "B03"), _b(ds, "B11"))) / 2.0  # (SAVI+MNDWI)/2
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.clip((nd - x) / (nd + x), -1, 1)  # clamp unstable ratio


def _ix_ndisi(ds):  # Landsat bands GREEN/NIR/SWIR1/TIR (°C)
    tir = np.clip(_b(ds, "TIR") / 50.0, 0, 1)       # °C -> [0,1]
    nir = np.clip(_b(ds, "NIR"), 0, 1)
    swir1 = np.clip(_b(ds, "SWIR1"), 0, 1)
    mndwi = (_nd(_b(ds, "GREEN"), _b(ds, "SWIR1")) + 1) / 2.0
    x = (mndwi + nir + swir1) / 3.0
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.clip((tir - x) / (tir + x), -1, 1)


def _ix_ebbi(ds):   # As-syakur 2012, x100
    swir1, nir, tir = _b(ds, "SWIR1"), _b(ds, "NIR"), _b(ds, "TIR")
    denom = 10.0 * np.sqrt(np.clip(swir1 + tir, 1e-6, None))
    return (swir1 - nir) / denom * 100.0


INDEX_NP = {
    "NDVI": lambda ds: _nd(_b(ds, "B08"), _b(ds, "B04")),
    "NDBI": lambda ds: _nd(_b(ds, "B11"), _b(ds, "B08")),
    "NDWI": lambda ds: _nd(_b(ds, "B03"), _b(ds, "B08")),
    "NBR": lambda ds: _nd(_b(ds, "B08"), _b(ds, "B12")),
    "UI": lambda ds: _nd(_b(ds, "B12"), _b(ds, "B08")),
    "BU": lambda ds: _nd(_b(ds, "B11"), _b(ds, "B08")) - _nd(_b(ds, "B08"), _b(ds, "B04")),
    "IBI": _ix_ibi,
    "NDISI": _ix_ndisi,
    "EBBI": _ix_ebbi,
}
S2_RES = 0.0001   # ~11 m in degrees (EPSG:4326)
S1_RES = 0.0002   # ~22 m
L_RES = 0.0003    # ~30 m (Landsat)
CLOUD_MAX = 60
SCL_BAD = [3, 8, 9, 10, 11]  # shadow, cloud med/high, cirrus, snow
L8_METHODS = ("NDISI", "EBBI")  # thermal indices — need Landsat, not Sentinel-2


def _catalog():
    import planetary_computer
    import pystac_client
    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)


def square_bbox(lon, lat, radius_km):
    """Axis-aligned square bbox [W,S,E,N], half-side = radius_km."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


# --------------------------- Sentinel-2 optical ---------------------------
def _s2_median(bbox, start, end, bands, geobox=None):
    """Cloud-masked median Sentinel-2 composite. Returns (dataset, count, geobox)."""
    import odc.stac
    cat = _catalog()
    items = list(cat.search(
        collections=["sentinel-2-l2a"], bbox=bbox,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": CLOUD_MAX}}).items())
    if not items:
        return None, 0, geobox
    load_kw = dict(bands=list(bands) + ["SCL"], groupby="solar_day",
                   chunks={"x": 2048, "y": 2048}, resampling="bilinear")
    if geobox is not None:
        ds = odc.stac.load(items, geobox=geobox, **load_kw)
    else:
        ds = odc.stac.load(items, bbox=bbox, crs="EPSG:4326",
                           resolution=S2_RES, **load_kw)
    keep = ~ds["SCL"].isin(SCL_BAD)
    med = ds[list(bands)].where(keep).median(dim="time")
    return med.compute(), len(items), ds.odc.geobox


def _landsat_median(bbox, start, end, geobox=None):
    """Cloud-masked median Landsat 8/9 composite -> reflectance + °C (TIR)."""
    import odc.stac
    import xarray as xr
    cat = _catalog()
    items = [it for it in cat.search(
        collections=["landsat-c2-l2"], bbox=bbox, datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": CLOUD_MAX}}).items()
        if it.properties.get("platform") in ("landsat-8", "landsat-9")]
    if not items:
        return None, 0, geobox
    bands = ["green", "red", "nir08", "swir16", "swir22", "lwir11", "qa_pixel"]
    load_kw = dict(bands=bands, groupby="solar_day",
                   chunks={"x": 2048, "y": 2048}, resampling="bilinear")
    if geobox is not None:
        ds = odc.stac.load(items, geobox=geobox, **load_kw)
    else:
        ds = odc.stac.load(items, bbox=bbox, crs="EPSG:4326",
                           resolution=L_RES, **load_kw)
    qa = ds["qa_pixel"].astype("uint16")
    bad = (qa & ((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4))) != 0
    m = ds.where(~bad).median(dim="time").compute()
    out = xr.Dataset({  # scale C2-L2 to surface reflectance and °C
        "GREEN": m["green"] * 0.0000275 - 0.2,
        "RED": m["red"] * 0.0000275 - 0.2,
        "NIR": m["nir08"] * 0.0000275 - 0.2,
        "SWIR1": m["swir16"] * 0.0000275 - 0.2,
        "SWIR2": m["swir22"] * 0.0000275 - 0.2,
        "TIR": m["lwir11"] * 0.00341802 + 149.0 - 273.15,
    })
    return out, len(items), ds.odc.geobox


def _l_sr_median(bbox, start, end, geobox=None):
    """Median Landsat 5/7/8/9 surface reflectance (uniform bands, no thermal)."""
    import odc.stac
    import xarray as xr
    cat = _catalog()
    # Exclude Landsat 7 (SLC-off gaps since 2003 stripe every scene).
    items = [it for it in cat.search(collections=["landsat-c2-l2"], bbox=bbox,
             datetime=f"{start}/{end}",
             query={"eo:cloud_cover": {"lt": CLOUD_MAX}}).items()
             if it.properties.get("platform") != "landsat-7"]
    if not items:
        return None, 0, geobox
    bands = ["green", "red", "nir08", "swir16", "swir22", "qa_pixel"]
    load_kw = dict(bands=bands, groupby="solar_day",
                   chunks={"x": 2048, "y": 2048}, resampling="bilinear")
    if geobox is not None:
        ds = odc.stac.load(items, geobox=geobox, **load_kw)
    else:
        ds = odc.stac.load(items, bbox=bbox, crs="EPSG:4326",
                           resolution=L_RES, **load_kw)
    qa = ds["qa_pixel"].astype("uint16")
    bad = (qa & ((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4))) != 0
    m = ds.where(~bad).median(dim="time").compute()
    out = xr.Dataset({
        "GREEN": m["green"] * 0.0000275 - 0.2,
        "RED": m["red"] * 0.0000275 - 0.2,
        "NIR": m["nir08"] * 0.0000275 - 0.2,
        "SWIR1": m["swir16"] * 0.0000275 - 0.2,
        "SWIR2": m["swir22"] * 0.0000275 - 0.2,
    })
    return out, len(items), ds.odc.geobox


def run_urban_trend(bbox, params, bu_thr=0.0):
    """NDBI at 3 epochs (Landsat) -> R/G/B timing composite."""
    epochs = params["epochs"]
    ndbis, counts, gbox = [], [], None
    for (start, end) in epochs:
        ds, n, gb = _l_sr_median(bbox, start, end, geobox=gbox)
        if ds is None:
            raise SystemExit(f"No Landsat scenes for epoch {start}..{end} (MPC).")
        gbox = gbox or gb
        ndbis.append(_nd(_b(ds, "SWIR1"), _b(ds, "NIR")))
        counts.append(n)

    def norm(x):  # NDBI [-0.2,0.4] -> [0,255]
        return (np.clip((np.nan_to_num(x, nan=-0.2) + 0.2) / 0.6, 0, 1) * 255).astype("uint8")

    rgb = np.stack([norm(ndbis[0]), norm(ndbis[1]), norm(ndbis[2])])
    valid = np.isfinite(ndbis[0]) & np.isfinite(ndbis[-1])
    bu_first, bu_last = ndbis[0] > bu_thr, ndbis[-1] > bu_thr
    new = bu_last & (~bu_first) & valid
    n = max(int(valid.sum()), 1)
    stats = {"method": "NDBI trend (Landsat, MPC)",
             "epochs": [list(e) for e in epochs], "scenes_per_epoch": counts,
             "pct_builtup_first": 100.0 * int((bu_first & valid).sum()) / n,
             "pct_builtup_last": 100.0 * int((bu_last & valid).sum()) / n,
             "pct_new_builtup": 100.0 * int(new.sum()) / n}
    product = {"key": "trend", "data": rgb, "geobox": gbox,
               "vis": {"bands": ["R", "G", "B"]}, "is_rgb": True}
    return {"products": [product], "stats": stats,
            "interpretation": "R/G/B = NDBI epoch-1/2/3. Biru = built-up baru; putih = selalu terbangun."}


def run_optical(bbox, params, index, direction, thr, severe, vmax=0.6):
    if index in L8_METHODS:  # thermal indices -> Landsat
        pre, n_pre, gbox = _landsat_median(bbox, *params["pre"])
        if pre is None:
            raise SystemExit("No Landsat scenes in the pre window (MPC).")
        post, n_post, _ = _landsat_median(bbox, *params["post"], geobox=gbox)
        if post is None:
            raise SystemExit("No Landsat scenes in the post window (MPC).")
    else:
        bands = INDEX_LOAD[index]
        pre, n_pre, gbox = _s2_median(bbox, *params["pre"], bands)
        if pre is None:
            raise SystemExit("No Sentinel-2 scenes in the pre window (MPC).")
        post, n_post, _ = _s2_median(bbox, *params["post"], bands, geobox=gbox)
        if post is None:
            raise SystemExit("No Sentinel-2 scenes in the post window (MPC).")

    fn = INDEX_NP[index]
    delta = fn(post) - fn(pre)
    valid = np.isfinite(delta)
    if direction == "loss":
        aff, sev = (delta < thr) & valid, (delta < severe) & valid
    else:
        aff, sev = (delta > thr) & valid, (delta > severe) & valid
    n = max(int(valid.sum()), 1)
    stats = {"metric": "d" + index, "direction": direction,
             "mean": float(np.nanmean(delta)),
             "pct_affected": 100.0 * int(aff.sum()) / n,
             ("pct_severe" if direction == "loss" else "pct_strong"): 100.0 * int(sev.sum()) / n,
             "threshold": thr, "scenes_pre": n_pre, "scenes_post": n_post}
    vis = {"min": -vmax, "max": vmax, "palette": DIVERGING, "label": "d" + index}
    product = {"key": "d" + index.lower(), "data": delta, "geobox": gbox,
               "vis": vis, "is_rgb": False}
    return {"products": [product], "stats": stats}


# --------------------------- Sentinel-1 SAR ---------------------------
def _s1_items(bbox, start, end, orbit=None):
    cat = _catalog()
    q = {}
    if orbit:
        q["sat:orbit_state"] = {"eq": orbit}
    return list(cat.search(collections=["sentinel-1-rtc"], bbox=bbox,
                           datetime=f"{start}/{end}", query=q or None).items())


def _s1_mean_db(bbox, start, end, pol, orbit, geobox=None):
    """Mean backscatter in dB for a polarisation/orbit. Returns (2-D array, count, geobox)."""
    import odc.stac
    items = _s1_items(bbox, start, end, orbit)
    if not items:
        return None, 0, geobox
    load_kw = dict(bands=[pol], groupby="solar_day",
                   chunks={"x": 2048, "y": 2048}, resampling="bilinear")
    if geobox is not None:
        ds = odc.stac.load(items, geobox=geobox, **load_kw)
    else:
        ds = odc.stac.load(items, bbox=bbox, crs="EPSG:4326",
                           resolution=S1_RES, **load_kw)
    lin = ds[pol].where(ds[pol] > 0)
    mean_lin = lin.mean(dim="time").compute()
    db = 10.0 * np.log10(mean_lin.values)
    return db, len(items), ds.odc.geobox


def _best_orbit(bbox, periods, pol):
    best = None
    for orbit in ("ascending", "descending"):
        counts = [len(_s1_items(bbox, s, e, orbit)) for (s, e) in periods]
        cand = (all(c > 0 for c in counts), sum(counts), orbit, counts)
        if best is None or cand[:2] > best[:2]:
            best = cand
    covered, _t, orbit, counts = best
    return orbit, covered, counts


def run_flood(bbox, params, water_thr=-16.0):
    periods = [params["pre"], params["post"]]
    orbit, covered, counts = _best_orbit(bbox, periods, "vv")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers both windows (MPC): {counts}")
    pre, _n, gbox = _s1_mean_db(bbox, *params["pre"], "vv", orbit)
    post, _n2, _ = _s1_mean_db(bbox, *params["post"], "vv", orbit, geobox=gbox)
    pre_water = pre < water_thr
    post_water = post < water_thr
    flood = post_water & (~pre_water) & np.isfinite(post) & np.isfinite(pre)
    n = max(int(np.isfinite(post).sum()), 1)
    stats = {"method": "SAR water (VV, MPC)", "orbit": orbit,
             "water_threshold_db": water_thr,
             "pct_flooded": 100.0 * int(flood.sum()) / n,
             "pct_permanent_water": 100.0 * int((pre_water & np.isfinite(pre)).sum()) / n,
             "scenes_pre": counts[0], "scenes_post": counts[1]}
    arr = np.where(flood, 1.0, np.nan)
    product = {"key": "flood", "data": arr, "geobox": gbox,
               "vis": {"min": 0, "max": 1, "palette": ["#00b3ff"], "label": "flood"},
               "is_rgb": False}
    return {"products": [product], "stats": stats,
            "interpretation": "Biru = area tergenang saat kejadian (bukan air permanen)."}


def run_mining(bbox, params):
    periods = params["sirad_periods"]
    orbit, covered, counts = _best_orbit(bbox, periods, "vh")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers all periods (MPC): {counts}")
    bands, gbox = [], None
    for (s, e) in periods:
        db, _n, gb = _s1_mean_db(bbox, s, e, "vh", orbit, geobox=gbox)
        gbox = gbox or gb
        bands.append(db)
    # scale each period to 0..255 over [-25,-5] dB for an R/G/B composite
    def scale(x):
        return np.clip((np.nan_to_num(x, nan=-25) + 25) / 20 * 255, 0, 255).astype("uint8")
    rgb = np.stack([scale(bands[0]), scale(bands[1]), scale(bands[2])])  # (3,y,x)
    sirad = {"key": "sirad", "data": rgb, "geobox": gbox,
             "vis": {"bands": ["R", "G", "B"]}, "is_rgb": True}

    ndvi = run_optical(bbox, {"pre": periods[0], "post": periods[-1]},
                       "NDVI", "loss", -0.15, -0.30)
    stats = {"sirad": {"method": "SIRAD (MPC)", "orbit": orbit,
                       "images_per_period": counts},
             "ndvi": ndvi["stats"]}
    return {"products": [sirad] + ndvi["products"], "stats": stats,
            "interpretation": "SIRAD biru = ekspansi baru; peta NDVI merah = hilangnya vegetasi."}


# --------------------------- output writing ---------------------------
def _write_tif(path, data, geobox, is_rgb):
    transform = geobox.affine
    crs = str(geobox.crs)
    if is_rgb:
        arr = data  # (3,y,x) uint8
        dtype, nodata, count = "uint8", None, 3
    else:
        arr = data[None]
        dtype, nodata, count = "float32", None, 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1],
                       width=arr.shape[2], count=count, dtype=dtype, crs=crs,
                       transform=transform, nodata=nodata, compress="deflate") as dst:
        dst.write(arr.astype(dtype))


def _write_png(path, data, vis, is_rgb):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if is_rgb:
        rgb = np.transpose(data, (1, 2, 0))  # (y,x,3)
        plt.imsave(path, rgb)
        return
    cols = vis["palette"] * 2 if len(vis["palette"]) == 1 else vis["palette"]
    cmap = LinearSegmentedColormap.from_list("s", cols)
    cmap.set_bad(alpha=0.0)
    norm = Normalize(vis["min"], vis["max"])
    rgba = cmap(norm(np.ma.masked_invalid(data)))
    plt.imsave(path, rgba)


def run_mpc(scenario, cfg, lat, lon, radius, name, params,
            run_dir, run_id, window, provider, do_map=False, basemap="osm"):
    """Entry point called by detect.py for --backend mpc. Writes to run_dir."""
    print("Backend: Microsoft Planetary Computer (no Earth Engine)")
    bbox = square_bbox(lon, lat, radius)
    method = cfg.get("method")
    if method == "optical":
        result = run_optical(bbox, params, cfg["index"], cfg["direction"],
                             cfg["thr"], cfg["severe"], cfg.get("vmax", 0.6))
    elif method == "flood":
        result = run_flood(bbox, params, cfg.get("water_thr", -16.0))
    elif method == "mining":
        result = run_mining(bbox, params)
    elif method == "trend":
        result = run_urban_trend(bbox, params)
    else:
        raise SystemExit(f"Scenario '{scenario}' not supported by the MPC backend yet.")

    os.makedirs(run_dir, exist_ok=True)
    for prod in result["products"]:
        base = f"{scenario}_{prod['key']}_{name}"
        png = os.path.join(run_dir, base + ".png")
        tif = os.path.join(run_dir, base + ".tif")
        print(f"Writing {prod['key']} PNG + GeoTIFF...")
        _write_png(png, prod["data"], prod["vis"], prod["is_rgb"])
        _write_tif(tif, prod["data"], prod["geobox"], prod["is_rgb"])
        print(f"Saved: {os.path.normpath(tif)}")

        vis = dict(prod["vis"])
        meta = {"tif": tif, "scenario": scenario, "label": cfg["label"],
                "product_key": prod["key"], "name": name, "run_id": run_id,
                "source": "Microsoft Planetary Computer", "provider": provider,
                "lat": lat, "lon": lon, "radius_km": radius,
                "vis": vis, "is_rgb": prod["is_rgb"], "metric": vis.get("label"),
                "interpretation": result.get("interpretation",
                                             cfg.get("interpretation", "")),
                "stats": result["stats"], "window": window}
        with open(os.path.join(run_dir, base + ".meta.json"), "w") as mf:
            json.dump(meta, mf, indent=2)
        if do_map:
            from .mapmaker import render_map
            render_map(meta, os.path.join(run_dir, base + "_map"), basemap=basemap)

    stats = {"run_id": run_id, "scenario": scenario, "backend": "mpc",
             "location": {"lat": lat, "lon": lon}, "radius_km": radius,
             "results": result["stats"]}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("\n=== Results ===")
    print(json.dumps(result["stats"], indent=2))
    print(result.get("interpretation", cfg.get("interpretation", "")))
