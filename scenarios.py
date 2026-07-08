#!/usr/bin/env python3
"""Change-detection scenarios — each maps to a remote-sensing method.

A scenario's run(aoi, p) returns:
    {
      "products": [ {"key", "thumb", "thumb_vis", "tif", "scale"}, ... ],
      "stats": {...},
      "interpretation": "<one line>",
    }
detect.py downloads every product (PNG quick-look + GeoTIFF) and writes stats.

Add a scenario by adding an entry to SCENARIOS (optionally a new run function).
"""

import ee
from indices import (
    s2_median, l2_median, l_sr_median, INDEX_FN, SENSOR, s1, best_orbit)

# Diverging palette: negative -> red, 0 -> pale, positive -> green
DIVERGING = ["a50026", "d73027", "fee08b", "ffffbf", "d9ef8b", "1a9850", "006837"]


# ----------------------------- stat helpers -----------------------------
def _reduce(img, aoi, reducer, scale):
    d = img.reduceRegion(reducer=reducer, geometry=aoi, scale=scale,
                         maxPixels=int(1e9), bestEffort=True).getInfo()
    vals = list(d.values())
    return vals[0] if vals else None


def _pct(mask_img, aoi, scale=10):
    """Percent of valid AOI pixels where a 0/1 mask is 1."""
    v = _reduce(mask_img, aoi, ee.Reducer.mean(), scale)
    return (v or 0) * 100.0


def _mean(img, aoi, scale=10):
    return _reduce(img, aoi, ee.Reducer.mean(), scale)


# ----------------------------- methods -----------------------------
def run_optical_change(aoi, p, index_name, direction, thr, severe_thr, vmax=0.6):
    """Generic Sentinel-2 index change: delta = post - pre.

    direction 'loss' reports pixels below thr (e.g. NDVI drop); 'gain' reports
    pixels above thr (e.g. NDBI/NDWI rise).
    """
    fn = INDEX_FN[index_name]
    loader = l2_median if SENSOR.get(index_name) == "L8" else s2_median
    sensor = "Landsat" if SENSOR.get(index_name) == "L8" else "Sentinel-2"
    pre_img, n_pre = loader(aoi, *p["pre"])
    post_img, n_post = loader(aoi, *p["post"])
    if n_pre == 0 or n_post == 0:
        raise SystemExit(
            f"No {sensor} scenes in {'pre' if n_pre == 0 else 'post'} window "
            f"for this AOI — adjust --pre/--post dates."
        )
    delta = fn(post_img).subtract(fn(pre_img)).rename("d" + index_name).clip(aoi)

    if direction == "loss":
        affected, severe = delta.lt(thr), delta.lt(severe_thr)
        stats = {"metric": "d" + index_name, "direction": "loss",
                 "mean": _mean(delta, aoi),
                 "pct_affected": _pct(affected, aoi),
                 "pct_severe": _pct(severe, aoi),
                 "threshold": thr, "severe_threshold": severe_thr}
    else:
        affected, severe = delta.gt(thr), delta.gt(severe_thr)
        stats = {"metric": "d" + index_name, "direction": "gain",
                 "mean": _mean(delta, aoi),
                 "pct_affected": _pct(affected, aoi),
                 "pct_strong": _pct(severe, aoi),
                 "threshold": thr, "strong_threshold": severe_thr}
    stats.update({"scenes_pre": n_pre, "scenes_post": n_post})

    vis = {"min": -vmax, "max": vmax, "palette": DIVERGING}
    product = {"key": "d" + index_name.lower(), "thumb": delta,
               "thumb_vis": vis, "tif": delta, "scale": 10}
    return {"products": [product], "stats": stats}


def run_sirad(aoi, p):
    """SIRAD radar temporal RGB: mean VH per period -> R/G/B composite."""
    periods = p["sirad_periods"]  # list of 3 (start, end)
    orbit, covered, counts = best_orbit(aoi, periods, pol="VH")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers all periods: {counts}")
    labels = ["R", "G", "B"]
    bands = [
        s1(aoi, s, e, orbit, "VH").map(lambda im: im.clip(aoi))
        .mean().rename(labels[i])
        for i, (s, e) in enumerate(periods)
    ]
    sirad = ee.Image.cat(bands)
    vis = {"bands": labels, "min": -25, "max": -5}
    stats = {"method": "SIRAD", "orbit": orbit,
             "images_per_period": counts, "periods": [list(x) for x in periods]}
    product = {"key": "sirad", "thumb": sirad, "thumb_vis": vis,
               "tif": sirad.visualize(**vis), "scale": 10}
    return {"products": [product], "stats": stats,
            "interpretation": ("SIRAD RGB: R=periode-1, G=periode-2, B=periode-3. "
                               "Biru = aktivitas baru hanya di periode terakhir.")}


def run_mining(aoi, p):
    """Mining: SIRAD radar (cloud-proof) + NDVI loss (quantitative)."""
    res = run_sirad(aoi, p)
    periods = p["sirad_periods"]
    ndvi_res = run_optical_change(
        aoi, {"pre": periods[0], "post": periods[-1]},
        "NDVI", "loss", -0.15, -0.30)
    res["products"] += ndvi_res["products"]
    res["stats"] = {"sirad": res["stats"], "ndvi": ndvi_res["stats"]}
    res["interpretation"] = ("SIRAD biru = ekspansi baru; peta NDVI merah = "
                             "hilangnya vegetasi (bukaan tambang).")
    return res


def run_urban_trend(aoi, p, bu_thr=0.0):
    """Multi-epoch built-up timing: NDBI (Landsat) at 3 epochs -> R/G/B.

    New built-up appears blue (last epoch only), older growth cyan, always-built
    white. Uses Landsat so historical epochs (e.g. 2010) are covered.
    """
    epochs = p["epochs"]  # list of 3 (start, end)
    ndbis, counts = [], []
    for (start, end) in epochs:
        img, n = l_sr_median(aoi, start, end)
        ndbis.append(img.normalizedDifference(["SWIR1", "NIR"]))  # NDBI
        counts.append(n)
    if min(counts) == 0:
        raise SystemExit(f"No Landsat scenes in one epoch: {counts}. "
                         "Adjust --epochs windows.")

    def norm(x):  # NDBI [-0.2, 0.4] -> [0, 1] for display
        return x.subtract(-0.2).divide(0.6).clamp(0, 1)

    labels = ["R", "G", "B"]
    rgb = ee.Image.cat([norm(ndbis[0]), norm(ndbis[1]), norm(ndbis[2])]) \
        .rename(labels).clip(aoi)
    vis = {"bands": labels, "min": 0, "max": 1}

    bu_first, bu_last = ndbis[0].gt(bu_thr), ndbis[-1].gt(bu_thr)
    new = bu_last.And(bu_first.Not())
    stats = {"method": "NDBI trend (Landsat)",
             "epochs": [list(e) for e in epochs], "scenes_per_epoch": counts,
             "pct_builtup_first": _pct(bu_first, aoi),
             "pct_builtup_last": _pct(bu_last, aoi),
             "pct_new_builtup": _pct(new, aoi)}
    product = {"key": "trend", "thumb": rgb, "thumb_vis": vis,
               "tif": rgb.visualize(**vis), "scale": 30}
    return {"products": [product], "stats": stats,
            "interpretation": ("R/G/B = NDBI epoch-1/2/3. Biru = built-up baru di "
                               "epoch terakhir; cyan = lebih lama; putih = selalu terbangun.")}


def run_flood(aoi, p, water_thr=-16.0):
    """Flood: Sentinel-1 VV water extent, event vs baseline.

    Water = smooth surface = low VV backscatter. Flood = water present in the
    event window but not in the baseline window.
    """
    periods = [p["pre"], p["post"]]
    orbit, covered, counts = best_orbit(aoi, periods, pol="VV")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers both windows: {counts}")
    pre = s1(aoi, *p["pre"], orbit, "VV").mean().clip(aoi)
    post = s1(aoi, *p["post"], orbit, "VV").mean().clip(aoi)
    pre_water = pre.lt(water_thr)
    post_water = post.lt(water_thr)
    flood = post_water.And(pre_water.Not()).rename("flood")

    stats = {"method": "SAR water (VV)", "orbit": orbit,
             "water_threshold_db": water_thr,
             "pct_flooded": _pct(flood, aoi),
             "pct_permanent_water": _pct(pre_water, aoi),
             "scenes_pre": counts[0], "scenes_post": counts[1]}
    thumb_vis = {"min": 0, "max": 1, "palette": ["000000", "00b3ff"]}
    product = {"key": "flood", "thumb": flood.selfMask(),
               "thumb_vis": {"palette": ["00b3ff"], "min": 0, "max": 1},
               "tif": flood.toByte(), "scale": 10}
    return {"products": [product], "stats": stats,
            "interpretation": "Biru = area tergenang saat kejadian (bukan air permanen)."}


# ----------------------------- registry -----------------------------
def _optical(index, direction, thr, severe, vmax=0.6):
    def run(aoi, p):
        return run_optical_change(aoi, p, index, direction, thr, severe, vmax)
    return run


SCENARIOS = {
    "deforestation": {
        "label": "Deforestation — vegetation loss (Sentinel-2 NDVI)",
        "run": _optical("NDVI", "loss", -0.15, -0.30),
        "method": "optical", "index": "NDVI", "direction": "loss",
        "thr": -0.15, "severe": -0.30,
        "radius": 5.0, "needs": "pre_post",
        "pre": ("2023-01-01", "2023-12-31"),
        "post": ("2025-01-01", "2025-12-31"),
        "interpretation": "Merah = kehilangan vegetasi (deforestasi).",
    },
    "mining": {
        "label": "Mining — radar temporal (SIRAD) + NDVI loss (S1 + S2)",
        "run": run_mining,
        "method": "mining", "index": "NDVI", "direction": "loss",
        "thr": -0.15, "severe": -0.30,
        "radius": 6.0, "needs": "sirad",
        "sirad_periods": [("2024-01-01", "2024-12-31"),
                          ("2025-01-01", "2025-12-31"),
                          ("2026-01-01", "2026-06-30")],
        "interpretation": "SIRAD biru + NDVI merah = ekspansi tambang baru.",
    },
    "urbanization": {
        "label": "Urbanisation — built-up gain (Sentinel-2 NDBI)",
        "run": _optical("NDBI", "gain", 0.10, 0.20, vmax=0.5),
        "method": "optical", "index": "NDBI", "direction": "gain",
        "thr": 0.10, "severe": 0.20,
        "radius": 8.0, "needs": "pre_post",
        "pre": ("2020-01-01", "2020-12-31"),
        "post": ("2025-01-01", "2025-12-31"),
        "interpretation": "Hijau = indeks terbangun naik (urbanisasi baru).",
    },
    "urban-trend": {
        "label": "Urban growth timing — NDBI over 3 epochs (Landsat)",
        "run": run_urban_trend,
        "method": "trend",
        "radius": 10.0, "needs": "epochs",
        "epochs": [("2010-01-01", "2010-12-31"),
                   ("2015-01-01", "2015-12-31"),
                   ("2020-01-01", "2020-12-31")],
        "interpretation": "R/G/B = 2010/2015/2020; biru = pertumbuhan terbaru.",
    },
    "flood": {
        "label": "Flood — SAR water extent, event vs baseline (Sentinel-1 VV)",
        "run": run_flood,
        "method": "flood", "water_thr": -16.0,
        "radius": 15.0, "needs": "pre_post_required",
        "interpretation": "Biru = area tergenang saat kejadian banjir.",
    },
    "burn": {
        "label": "Burn severity — dNBR (Sentinel-2)",
        "run": _optical("NBR", "loss", -0.10, -0.27),
        "method": "optical", "index": "NBR", "direction": "loss",
        "thr": -0.10, "severe": -0.27,
        "radius": 10.0, "needs": "pre_post_required",
        "interpretation": "Merah = area terbakar (severity tinggi).",
    },
    "water": {
        "label": "Surface-water change (Sentinel-2 NDWI)",
        "run": _optical("NDWI", "gain", 0.10, 0.25),
        "method": "optical", "index": "NDWI", "direction": "gain",
        "thr": 0.10, "severe": 0.25,
        "radius": 10.0, "needs": "pre_post",
        "pre": ("2023-01-01", "2023-12-31"),
        "post": ("2025-01-01", "2025-12-31"),
        "interpretation": "Hijau = air permukaan bertambah; merah = menyusut.",
    },
}
