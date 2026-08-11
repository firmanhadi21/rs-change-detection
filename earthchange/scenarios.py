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

try:
    import ee  # only needed for the GEE backend
except ImportError:
    ee = None
from .indices import (
    s2_median, l2_median, l_sr_median, INDEX_FN, SENSOR, s1, best_orbit,
    s1_relorbits, s1_latest)

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
def _round1(v):
    return round(v, 1) if isinstance(v, (int, float)) else None


def run_optical_change(aoi, p, index_name, direction, thr, severe_thr, vmax=0.6,
                       preview=True, min_obs=2):
    """Generic optical index change: delta = post - pre.

    direction 'loss' reports pixels below thr (e.g. NDVI drop); 'gain' reports
    pixels above thr (e.g. NDBI/NDWI rise). `p['sensor']` = 'landsat' forces the
    Landsat SR composite (archive to 1984) instead of Sentinel-2 (2015+). Water is
    masked out by default (except for the NDWI/water scenario) so sea and lakes
    don't pollute NDVI/NBR change — essential on coasts and islands.
    """
    from .indices import (LANDSAT_INDEX_FN, MNDWI_BANDS, OBS_BAND, PREVIEW_VIS,
                          clear_obs, l2_masked, l2_scenes, l_sr_masked,
                          l_sr_scenes, s2_masked, s2_scenes, scene_inventory)
    thermal = SENSOR.get(index_name) == "L8"          # NDISI/EBBI need Landsat thermal
    want_landsat = p.get("sensor") == "landsat"
    if thermal:
        loader, fn, sensor, scale, wsensor = l2_median, INDEX_FN[index_name], "Landsat", 30, None
        scenes_fn, pvis, cloud_prop = l2_scenes, PREVIEW_VIS["landsat"], "CLOUD_COVER"
        masked_fn, obs_band = l2_masked, OBS_BAND["landsat"]
    elif want_landsat:
        if index_name not in LANDSAT_INDEX_FN:
            raise SystemExit(f"--sensor landsat is not available for {index_name}.")
        loader, fn = l_sr_median, LANDSAT_INDEX_FN[index_name]
        sensor, scale, wsensor = "Landsat (archive to 1984)", 30, "landsat"
        scenes_fn, pvis, cloud_prop = l_sr_scenes, PREVIEW_VIS["landsat"], "CLOUD_COVER"
        masked_fn, obs_band = l_sr_masked, OBS_BAND["landsat"]
    else:
        loader, fn, sensor, scale, wsensor = s2_median, INDEX_FN[index_name], "Sentinel-2", 10, "s2"
        scenes_fn, pvis, cloud_prop = s2_scenes, PREVIEW_VIS["s2"], "CLOUDY_PIXEL_PERCENTAGE"
        masked_fn, obs_band = s2_masked, OBS_BAND["s2"]

    pre_img, n_pre = loader(aoi, *p["pre"])
    post_img, n_post = loader(aoi, *p["post"])
    if n_pre == 0 or n_post == 0:
        raise SystemExit(
            f"No {sensor} scenes in {'pre' if n_pre == 0 else 'post'} window "
            f"for this AOI — adjust --pre/--post dates."
        )
    delta = fn(post_img).subtract(fn(pre_img)).rename("d" + index_name).clip(aoi)

    # Refuse to report change where there is too little evidence to tell change
    # from cloud. Cloud masks are imperfect -- SCL misses thin cloud and is
    # weakest on shadow -- and a median over many looks absorbs that, while a
    # median over ONE look simply reproduces it. Shadow lowers NIR more than
    # SWIR, so it depresses both NDVI and NBR: it reads as vegetation loss or
    # burn, never as gain. That asymmetry is what makes it a false-positive
    # engine rather than noise.
    pre_obs = clear_obs(masked_fn(aoi, *p["pre"]), obs_band)
    post_obs = clear_obs(masked_fn(aoi, *p["post"]), obs_band)
    thin = None
    if min_obs > 1:
        enough = pre_obs.gte(min_obs).And(post_obs.gte(min_obs))
        # Measured before the water mask so the number means "dropped for thin
        # coverage", not "dropped for coverage or being sea".
        thin = round(100.0 - _pct(enough, aoi, scale), 1)
        delta = delta.updateMask(enough)

    # Mask permanent water (MNDWI>0 in either date) so it isn't counted as change.
    water_masked = False
    if p.get("mask_water", True) and index_name != "NDWI" and wsensor:
        gb = list(MNDWI_BANDS[wsensor])
        land = pre_img.normalizedDifference(gb).lt(0).And(post_img.normalizedDifference(gb).lt(0))
        delta = delta.updateMask(land)
        water_masked = True

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
    stats.update({"scenes_pre": n_pre, "scenes_post": n_post,
                  "sensor": sensor, "water_masked": water_masked})
    stats["clear_observations"] = {
        "min_obs_required": min_obs,
        "pct_dropped_too_few": thin,
        "pre_median_per_pixel": _round1(_mean(pre_obs, aoi, scale)),
        "post_median_per_pixel": _round1(_mean(post_obs, aoi, scale)),
        "note": ("Change is only reported where BOTH windows have at least "
                 "min_obs clear looks. A pixel seen once has a 'median' of one "
                 "image, so cloud or shadow the mask missed becomes change. "
                 "Shadow depresses NDVI and NBR, so it mimics loss/burn, never "
                 "gain."),
    }
    if thin:
        print(f"  {thin:.1f}% of the AOI had fewer than {min_obs} clear looks "
              f"in one of the windows and is excluded from the change stats.")

    vis = {"min": -vmax, "max": vmax, "palette": DIVERGING}
    products = [{"key": "d" + index_name.lower(), "thumb": delta,
                 "thumb_vis": vis, "tif": delta, "scale": scale}]

    if preview:
        # Quick-looks of the two composites the change was measured between,
        # so the result can be eyeballed against the imagery rather than taken
        # on trust. PNG only: a multi-band 10 m GeoTIFF of each composite would
        # dwarf every other download for something meant to be glanced at.
        for key, img, window in (("pre", pre_img, p["pre"]),
                                 ("post", post_img, p["post"])):
            products.append({"key": f"preview_{key}", "thumb": img.clip(aoi),
                             "thumb_vis": dict(pvis), "png_only": True,
                             "window": list(window)})
        stats["images_used"] = {
            "preview_composite": "SWIR false colour (SWIR2/NIR/RED)",
            "pre": scene_inventory(scenes_fn(aoi, *p["pre"]), cloud_prop),
            "post": scene_inventory(scenes_fn(aoi, *p["post"]), cloud_prop),
        }
    return {"products": products, "stats": stats}


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


def run_imagery(aoi, p):
    """Just the imagery: a 6-band GeoTIFF plus quick-looks. No change detection.

    One specific date or a composite over a window. A single date arrives here
    already widened to [d, d+1) — filterDate is half-open, so a literal (d, d)
    is an empty range Earth Engine refuses.

    Two previews are written because the two questions people bring here
    differ: natural colour for 'what does this place look like', SWIR false
    colour for burn scars and vegetation stress.
    """
    import datetime as dt
    from .indices import (IMAGERY_NAMES, IMAGERY_VIS, available_dates,
                          imagery_composite, scene_inventory)

    start, end = p["window"]
    sensor = "landsat" if p.get("sensor") == "landsat" else "s2"
    img, scenes, scale, cloud_prop = imagery_composite(aoi, start, end, sensor)
    inv = scene_inventory(scenes, cloud_prop)

    if inv["count"] == 0:
        label = "Landsat" if sensor == "landsat" else "Sentinel-2"
        # Two very different failures land here and the fix differs: the
        # satellite never passed, or it did and every pass was too cloudy.
        # Saying "widen the window" for the second one sends people the wrong way.
        loose = scene_inventory(
            imagery_composite(aoi, start, end, sensor, cloud_max=100)[1], cloud_prop)
        if loose["count"]:
            cl = sorted(s["cloud_pct"] for s in loose["scenes"]
                        if s["cloud_pct"] is not None)
            raise SystemExit(
                f"{loose['count']} {label} scene(s) cover this AOI for "
                f"{start}..{end}, but none is under the 60% cloud limit "
                f"(cloud cover: {', '.join(f'{c:.0f}%' for c in cl[:8])}). "
                f"Widen the window so the composite can see past the cloud.")
        a = (dt.date.fromisoformat(start) - dt.timedelta(days=30)).isoformat()
        b = (dt.date.fromisoformat(end) + dt.timedelta(days=30)).isoformat()
        near = available_dates(imagery_composite(aoi, a, b, sensor)[1])
        hint = (f" Nearby usable acquisitions: {', '.join(near[:8])}"
                f"{' …' if len(near) > 8 else ''}." if near
                else " No usable scenes within 30 days either — widen the window.")
        raise SystemExit(f"No {label} scenes over this AOI for {start}..{end}.{hint}")

    vis = IMAGERY_VIS[sensor]
    products = [
        # One product yields both the GeoTIFF and the natural-colour PNG.
        {"key": "reflectance", "tif": img.clip(aoi), "scale": scale,
         "thumb": img.clip(aoi), "thumb_vis": dict(vis["true"])},
        {"key": "swir", "thumb": img.clip(aoi), "thumb_vis": dict(vis["swir"]),
         "png_only": True},
    ]
    single = p.get("single_date")
    # How much of the AOI actually survived cloud masking. On a single date
    # this is routinely well under half, and without it a mostly-empty raster
    # looks like a successful download.
    coverage = round(_pct(img.select(0).mask(), aoi, scale), 1)
    stats = {
        "mode": "single date" if single else "composite",
        "date": single, "window": [start, end], "sensor": sensor, "scale_m": scale,
        "bands": IMAGERY_NAMES, "composite": "median (cloud-masked per pixel)",
        "valid_pct": coverage,
        "images_used": {"preview_composite": "natural colour + SWIR false colour",
                        "window": inv},
    }
    if coverage < 60:
        print(f"  NOTE: only {coverage:.0f}% of the AOI has data after cloud "
              f"masking. {'Widen --date into a range to composite more scenes.'
                          if single else 'Widen the window or raise cloud tolerance.'}")
    return {"products": products, "stats": stats,
            "interpretation": ("Citra sumber apa adanya — tanpa deteksi "
                               "perubahan. / Source imagery as-is, no change "
                               "detection.")}


def run_mining(aoi, p):
    """Mining: SIRAD radar (cloud-proof) + NDVI loss (quantitative)."""
    res = run_sirad(aoi, p)
    periods = p["sirad_periods"]
    ndvi_res = run_optical_change(
        aoi, {"pre": periods[0], "post": periods[-1]},
        "NDVI", "loss", -0.15, -0.30, preview=p.get("preview", True))
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


def _s1_single_pair(aoi, pre_win, post_win, orbit, pol):
    """Pick ONE pre and ONE post Sentinel-1 scene for change detection.

    Each is the most recent pass in its window, and both are forced to the SAME
    relative orbit (track) so the viewing geometry is identical. Of the tracks
    present in both windows, the one whose post pass is most recent is chosen;
    if none overlap, the scenes may differ in track ("mixed").

    Returns (pre_img, post_img, rel_orbit_or_None, date_pre, date_post).
    """
    pre_coll = s1(aoi, *pre_win, orbit, pol)
    post_coll = s1(aoi, *post_win, orbit, pol)
    pre_ro = set(s1_relorbits(pre_coll).getInfo())
    post_ro = post_coll.aggregate_array("relativeOrbitNumber_start").getInfo()
    post_t = post_coll.aggregate_array("system:time_start").getInfo()
    common = [(t, ro) for ro, t in zip(post_ro, post_t) if ro in pre_ro]
    rel = None
    if common:
        rel = max(common)[1]
        pre_coll = pre_coll.filter(ee.Filter.eq("relativeOrbitNumber_start", rel))
        post_coll = post_coll.filter(ee.Filter.eq("relativeOrbitNumber_start", rel))
    pre_img = s1_latest(pre_coll)
    post_img = s1_latest(post_coll)
    date_pre = pre_img.date().format("YYYY-MM-dd").getInfo()
    date_post = post_img.date().format("YYYY-MM-dd").getInfo()
    return pre_img, post_img, rel, date_pre, date_post


def run_flood(aoi, p, water_thr=-16.0):
    """Flood: Sentinel-1 VV water extent, event vs baseline.

    Standard S1 rapid-flood method: ONE pre scene and ONE post scene (not a
    window mean), same relative orbit, each the most recent pass in its window.
    Water = smooth surface = low VV backscatter; flood = water in the post scene
    but not the pre scene.
    """
    periods = [p["pre"], p["post"]]
    orbit, covered, counts = best_orbit(aoi, periods, pol="VV")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers both windows: {counts}")

    pre_img, post_img, rel, date_pre, date_post = _s1_single_pair(
        aoi, p["pre"], p["post"], orbit, "VV")

    def prep(img):  # smooth to suppress SAR speckle before thresholding
        return img.clip(aoi).focal_median(50, "circle", "meters")

    pre, post = prep(pre_img), prep(post_img)
    pre_water = pre.lt(water_thr)
    post_water = post.lt(water_thr)

    # Land mask: SRTM is void over the OPEN SEA, so this drops the ocean while
    # KEEPING coastal ponds and low-lying land. Permanent water (ponds, rivers)
    # is still excluded from "new flood" by the baseline (pre_water), so we don't
    # need to erase it — that would also erase genuine flooding around the ponds.
    land = ee.Image("USGS/SRTMGL1_003").mask()
    flood = post_water.And(pre_water.Not()).updateMask(land)
    # Drop isolated speckle: keep only clusters of >= 8 connected flood pixels.
    keep = flood.selfMask().connectedPixelCount(50, True).unmask(0).gte(8)
    flood = flood.multiply(keep).rename("flood")

    stats = {"method": "SAR water (VV), single-scene pre/post, ocean masked (SRTM), ponds kept",
             "orbit": orbit, "relative_orbit": rel if rel is not None else "mixed",
             "date_pre": date_pre, "date_post": date_post,
             "water_threshold_db": water_thr,
             "pct_flooded": _pct(flood, aoi),
             "pct_permanent_water": _pct(pre_water.updateMask(land), aoi),
             "scenes_pre": counts[0], "scenes_post": counts[1]}
    product = {"key": "flood", "thumb": flood.selfMask(),
               "thumb_vis": {"palette": ["00b3ff"], "min": 0, "max": 1},
               "tif": flood.selfMask().toByte(), "scale": 10}
    return {"products": [product], "stats": stats,
            "interpretation": "Biru = area tergenang saat kejadian (air permanen & laut di-mask)."}


def run_disturbance(aoi, p, drop_thr=-3.0, severe_thr=-6.0, steep_deg=15.0):
    """Disturbance / impact mapping via Sentinel-1 VH change (cloud-proof).

    For terrain where open-water detection fails (forested hills, flash floods,
    landslides), the impact signal is a LOSS of vegetation/structure — which
    drops VH backscatter. Uses ONE pre and ONE post scene (same relative orbit)
    and flags where VH fell by more than `drop_thr` dB (severe below `severe_thr`).
    SRTM slope attributes steep drops as landslide-like vs flat drops as
    sediment/inundation-like. Works when the `flood` scenario shows nothing.
    """
    periods = [p["pre"], p["post"]]
    orbit, covered, counts = best_orbit(aoi, periods, pol="VH")
    if not covered:
        raise SystemExit(f"No Sentinel-1 orbit covers both windows: {counts}")

    pre_img, post_img, rel, date_pre, date_post = _s1_single_pair(
        aoi, p["pre"], p["post"], orbit, "VH")

    def prep(img):  # smooth to suppress SAR speckle before differencing
        return img.clip(aoi).focal_median(50, "circle", "meters")

    pre, post = prep(pre_img), prep(post_img)
    dvh = post.subtract(pre).rename("dVH")

    moderate = dvh.lt(drop_thr)
    severe = dvh.lt(severe_thr)
    # Drop isolated speckle: keep only clusters of >= 8 connected pixels.
    keep = moderate.selfMask().connectedPixelCount(50, True).unmask(0).gte(8)
    moderate = moderate.multiply(keep)
    severe = severe.multiply(keep)

    # Graded product: 1 = moderate VH drop, 2 = severe VH drop.
    graded = moderate.add(severe).selfMask().rename("disturbance")

    # Slope-based attribution of the disturbed pixels.
    slope = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003"))
    steep = slope.gt(steep_deg)
    landslide = moderate.And(steep)      # steep + VH drop -> likely landslide/scar
    flat = moderate.And(steep.Not())     # flat + VH drop  -> likely sediment/inundation

    stats = {"method": "SAR VH-drop disturbance (single-scene, slope-attributed)",
             "orbit": orbit, "relative_orbit": rel if rel is not None else "mixed",
             "date_pre": date_pre, "date_post": date_post,
             "vh_drop_db": drop_thr, "severe_db": severe_thr, "steep_deg": steep_deg,
             "mean_dVH_db": _mean(dvh, aoi),
             "pct_disturbed": _pct(moderate, aoi),
             "pct_severe": _pct(severe, aoi),
             "pct_landslide_like": _pct(landslide, aoi),
             "pct_sediment_flat": _pct(flat, aoi),
             "scenes_pre": counts[0], "scenes_post": counts[1]}
    vis = {"palette": ["fdae61", "d7191c"], "min": 1, "max": 2}
    product = {"key": "disturbance", "thumb": graded, "thumb_vis": vis,
               "tif": graded.toByte(), "scale": 10}
    return {"products": [product], "stats": stats,
            "interpretation": ("Oranye/merah = penurunan backscatter VH (vegetasi/"
                               "permukaan hilang). Di lereng curam ≈ longsor; di "
                               "dataran ≈ endapan/genangan.")}


# ----------------------------- registry -----------------------------
def _optical(index, direction, thr, severe, vmax=0.6):
    def run(aoi, p):
        return run_optical_change(aoi, p, index, direction, thr, severe, vmax,
                                  preview=p.get("preview", True))
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
    "urban-history": {
        "label": "Urban history — built-up by decade since 1980 (GHSL + Landsat)",
        "method": "urban-history",
        "radius": 45.0, "needs": "none",
        "interpretation": ("Peta dekade pertama terbangun + panel per dekade + "
                           "grafik luas terbangun & penurunan vegetasi."),
    },
    "flood": {
        "label": "Flood — SAR water extent, event vs baseline (Sentinel-1 VV)",
        "run": run_flood,
        "method": "flood", "water_thr": -16.0,
        "radius": 15.0, "needs": "pre_post_required",
        "interpretation": "Biru = area tergenang saat kejadian banjir.",
    },
    "disturbance": {
        "label": "Disturbance — flood/landslide impact via SAR VH change (Sentinel-1)",
        "run": run_disturbance,
        "method": "disturbance",
        "radius": 15.0, "needs": "pre_post_required",
        "interpretation": ("Oranye/merah = permukaan terganggu (VH turun). "
                           "Lereng curam ≈ longsor; dataran ≈ endapan/genangan."),
    },
    "smoke-track": {
        "label": ("Smoke trajectories — air-parcel paths from the fires "
                  "(kinematic, or HYSPLIT with --engine hysplit)"),
        "method": "smoke_track", "needs": "none",
        "radius": 300.0,
        "interpretation": ("Kinematic: ILUSTRASI, bukan atribusi. HYSPLIT: "
                           "lintasan yang dapat dipertahankan, tetapi tetap "
                           "lintasan — melintas bukan berarti menurunkan asap."),
    },
    "smoke-exposure": {
        "label": "Smoke exposure — person-days by ISPU class, per district, with age split",
        "method": "smoke_exposure", "needs": "none",
        "radius": 300.0,
        "interpretation": ("Berapa orang menghirup udara seburuk apa, "
                           "berapa lama, dan berapa di antaranya balita/lansia."),
    },
    "smoke-video": {
        "label": "Wildfire smoke map video — 3-D terrain + CAMS smoke + FIRMS fires (no GEE)",
        "method": "smoke_video", "needs": "none",
        "radius": 150.0,
        "interpretation": ("Animasi 1080x1080: relief gelap, asap CAMS, "
                           "titik api VIIRS 7 hari terakhir."),
    },
    "fire-record": {
        "label": "Fire-season accountability record — danger, hotspots & burned area by zone",
        "method": "fire_record", "needs": "none",
        "radius": 60.0,
        "interpretation": ("Catatan per kawasan yang dapat dihitung ulang: "
                           "kapan mengering, di mana terbakar, berapa luasnya."),
    },
    "fire-danger": {
        "label": "Fire danger rating — Canadian FWI System (ERA5-Land)",
        "method": "fire_danger", "needs": "none",
        "radius": 60.0,
        "interpretation": ("DC/BUI memimpin, bukan FWI: kebakaran gambut "
                           "Indonesia didorong pengeringan lapisan dalam."),
    },
    "imagery": {
        "label": "Imagery — source GeoTIFF + previews, no change detection",
        "run": run_imagery,
        "method": "imagery", "needs": "window",
        "radius": 10.0,
        "interpretation": "Citra sumber apa adanya (tanpa deteksi perubahan).",
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
    "coastline": {
        "label": "Coastline — sea boundary & shoreline change (Sentinel-1 SAR)",
        "method": "coastline",
        "radius": 15.0, "needs": "pre_post",
        "post": ("2025-01-01", "2025-12-31"),
        "interpretation": ("Garis pantai laut (SAR). Dengan --pre/--post: "
                           "abrasi (merah) & akresi/ reklamasi (hijau)."),
    },
    "transit-access": {
        "label": "Transit access — % population near public transport (SDG 11.2.1, WorldPop + OSM)",
        "method": "transit-access",
        "radius": 12.0, "needs": "none",
        "interpretation": ("Persentase populasi (WorldPop) yang dapat menjangkau "
                           "halte/stasiun dengan berjalan kaki di jaringan jalan "
                           "(default 500 m, SDG 11.2.1)."),
    },
    "island-heat": {
        "label": "Island heat — SST + LST + wet-bulb trends for small islands (OISST/Landsat/ERA5)",
        "method": "island-heat",
        "radius": 30.0, "needs": "none",
        "interpretation": ("Tren suhu laut (SST), suhu darat (LST) & wet-bulb "
                           "(panas lembab) pulau kecil; hari berbahaya per tahun."),
    },
    "urban-heat": {
        "label": "Urban heat island — SUHII + hot-spot map + decadal trend (GHSL + Landsat LST)",
        "method": "urban-heat",
        "radius": 20.0, "needs": "none",
        "interpretation": ("Intensitas pulau panas perkotaan (SUHII = kota − desa), "
                           "peta titik panas, dan tren antar-dekade."),
    },
    "forest-history": {
        "label": "Forest history — multi-epoch deforestation, year-of-loss map + trajectory (S2/Landsat NDVI)",
        "method": "forest-history",
        "radius": 12.0, "needs": "none",
        "interpretation": ("Kapan tiap piksel hutan hilang (peta) + tren luas hutan "
                           "antar-periode. Pakai --sensor landsat untuk sejak 1980-an."),
    },
    "haze": {
        "label": "Haze — smoke & air quality from fires: PM2.5 + aerosol index + hotspots (CAMS/S5P/FIRMS)",
        "method": "haze",
        "radius": 25.0, "needs": "none",
        "interpretation": ("Kualitas udara saat karhutla: PM2.5 harian (kategori "
                           "ISPU), indeks aerosol Sentinel-5P, titik panas, dan "
                           "peta sebaran asap."),
    },
    "drought": {
        "label": "Drought — rainfall deficit (CHIRPS), vegetation health (MODIS VCI/TCI/VHI) & ENSO state (OISST)",
        "method": "drought",
        "radius": 40.0, "needs": "none",
        "interpretation": ("Kekeringan: anomali hujan terstandar per tahun, "
                           "kesehatan vegetasi (VCI/TCI/VHI), dan kondisi "
                           "El Nino/La Nina dari indeks Nino 3.4."),
    },
    "fire-history": {
        "label": "Fire history — burned area per year, recurrence map & fire season (MODIS + FIRMS)",
        "method": "fire-history",
        "radius": 30.0, "needs": "none",
        "interpretation": ("Riwayat karhutla: luas terbakar per tahun (gambut vs "
                           "mineral), peta berapa kali tiap piksel terbakar, dan "
                           "musim kebakaran (puncak kemarau)."),
    },
    "population-change": {
        "label": "Population change — two GHSL epochs, gained/lost/present map + 3D spike forest (GHS_POP)",
        "method": "population-change",
        "radius": 40.0, "needs": "none",
        "interpretation": ("Perubahan populasi antar dua epoch GHSL (mis. 1990→2020): "
                           "sel bertambah (hijau) / berkurang (magenta) / tetap (abu). "
                           "Peta 2D + hutan paku 3D + ekspor untuk forge3d."),
    },
}


# ---------------------------------------------------------------------------
# Which flags belong to which scenario, for `-s <scenario> --help`.
#
# The full --help lists 100-odd options, and for any single scenario most of
# them are noise -- someone running `burn` does not need to read about
# --transect-spacing. These tables let the CLI show only what applies.
#
# Keeping this correct by hand would fail quietly, so unclaimed_flags() below
# reports any option that no scenario claims and that is not common. A new flag
# added without being listed here shows up there rather than disappearing.
# ---------------------------------------------------------------------------

# Shown for every scenario: where to look, what to call it, where to put it.
# Deliberately small. A flag whose own help text has to name a scenario
# ("island-heat: also render...") is not common, however convenient it would be
# to put it here -- it would appear under 24 scenarios and be wrong for 23.
COMMON_FLAGS = (
    "--scenario", "--list", "--lat", "--lon", "--location", "--city", "--site",
    "--admin", "--bbox", "--radius", "--name", "--out-dir", "--backend",
    "--ee-key", "--lang", "--drive", "--drive-folder",
)

# Date windows most change-detection scenarios share.
# Window flags are DERIVED from each scenario's "needs", not listed by hand.
# The dispatcher already branches on that field to decide whether a scenario
# takes a single --date, a --pre/--post pair or three --epochs, so reading the
# same field keeps help and behaviour from drifting. Hand-grouping them as one
# "_WINDOW" bundle is what put fire-record's --season into urbanization's help.
_BY_NEEDS = {
    "pre_post": ("--pre", "--post"),
    "pre_post_required": ("--pre", "--post"),
    "window": ("--date",),
    "sirad": ("--epochs",),
    "epochs": ("--epochs",),
    "none": (),
}
# Optical scene selection, and the A4 map layout those scenarios can render.
_OPTICAL = ("--sensor", "--min-obs", "--preview", "--method")
_MAP = ("--map", "--basemap")
# Anything reading a zone layer the user supplies.
_ZONES = ("--zones", "--zone-field", "--zone-grid")
# Very-high-resolution confirmation via Planet.
_PLANET = ("--planet", "--planet-confirm", "--planet-key", "--planet-pre",
           "--planet-post")

SCENARIO_FLAGS = {
    "deforestation": _OPTICAL + _PLANET + _MAP + ("--thr", "--forest-thr"),
    "mining": _OPTICAL + _PLANET + _MAP + ("--thr", "--drop-thr"),
    "urbanization": _OPTICAL + _MAP + ("--thr",),
    "urban-trend": ("--start-year", "--end-year", "--epochs", "--cell-km"),
    # urban-history is the scenario that confirms change against Planet imagery,
    # which is where the --hotspot-* window actually belongs.
    "urban-history": ("--start-year", "--end-year", "--epochs", "--cell-km",
                      "--hotspot-km", "--hotspot-from", "--hotspot-to")
                     + _PLANET,
    "flood": _MAP + ("--thr", "--no-water-mask", "--severe"),
    "disturbance": _MAP + ("--drop-thr", "--severe"),
    "burn": _OPTICAL + _MAP + ("--thr", "--severe", "--min-obs"),
    # --months is read only by urban-heat; water never sees it.
    "water": _MAP + ("--no-water-mask",),
    "imagery": ("--sensor", "--preview", "--min-obs"),
    "coastline": ("--pre", "--post", "--coast-method", "--coast-smooth",
                  "--transect-spacing", "--transects-file", "--snap-dist",
                  "--boundary", "--islands-file", "--island-mode") + _MAP,
    "transit-access": ("--transit-file", "--walk-dist", "--access-buffer",
                       "--min-pop", "--pop-year", "--boundary", "--aoi-file"),
    # Neither heat scenario reads --season; both are bounded by --epochs, and
    # only urban-heat reads --months.
    "island-heat": ("--lst-source", "--wetbulb-thr", "--infographic"),
    "urban-heat": ("--lst-source", "--months", "--neutral-pct", "--epochs"),
    "population-change": ("--epochs", "--cell-km", "--pop-years", "--forge3d",
                          "--forge3d-prep-only", "--country"),
    "forest-history": ("--start-year", "--end-year", "--forest-thr"),
    # detect.py passes fire-history neither --season nor --months; it is bounded
    # by --start-year/--end-year.
    "fire-history": ("--start-year", "--end-year", "--areas", "--regions",
                     "--vs-baseline", "--peat-file", "--peat-source",
                     "--peat-thr"),
    # fire-danger and smoke-track read args.date directly rather than through
    # the needs branch, so they name it here.
    "fire-danger": ("--date", "--fdrs-end", "--spinup", "--rain-source"
                    ) + _ZONES,
    "fire-record": ("--season", "--record-step", "--spinup", "--rain-source"
                    ) + _ZONES,
    # haze takes its window from --haze-start/--haze-end or --days, and nothing
    # else: the hotspot and firms-region flags belong to other scenarios.
    "haze": ("--haze-start", "--haze-end", "--days"),
    # drought is bounded by --drought-end and --spi-months, not --season.
    "drought": ("--drought-end", "--spi-months", "--start-year",
                "--rain-source", "--cdi", "--cdi-scale", "--cdi-grid",
                "--cdi-mask", "--cdi-mask-name", "--cdi-basemap"),
    "smoke-exposure": ("--season", "--pop-year"),
    # No --date or --days: the FIRMS public feed is a rolling seven days and
    # smoke_video.run takes neither, so offering them promised a window the
    # scenario cannot honour.
    "smoke-video": ("--firms-region", "--video-size", "--video-title",
                    "--video-subtitle", "--video-cities", "--video-labels",
                    "--video-clean"),
    "smoke-track": ("--date", "--engine", "--direction", "--track-hours",
                    "--track-parcels", "--track-heights", "--receptors",
                    "--hysplit-bin", "--met-cache"),
}


def unclaimed_flags(all_flags):
    """Options no scenario lists and that are not common.

    A hand-maintained table drifts the moment someone adds a flag and forgets
    this file. This turns that from a silent omission into something a test can
    print.
    """
    claimed = set(COMMON_FLAGS)
    for flags in SCENARIO_FLAGS.values():
        claimed.update(flags)
    for flags in _BY_NEEDS.values():
        claimed.update(flags)
    return sorted(set(all_flags) - claimed)


def flags_for(scenario):
    """Options worth showing for one scenario: common, window, and its own.

    The window flags come from the scenario's own "needs", which is the field
    the dispatcher branches on, so the two cannot disagree.
    """
    needs = (SCENARIOS.get(scenario) or {}).get("needs")
    return (set(COMMON_FLAGS)
            | set(_BY_NEEDS.get(needs, ()))
            | set(SCENARIO_FLAGS.get(scenario, ())))
