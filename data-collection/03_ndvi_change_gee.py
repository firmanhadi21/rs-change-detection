#!/usr/bin/env python3
"""Sentinel-2 NDVI change detection in Google Earth Engine — free, any site.

Compares a cloud-masked median NDVI composite of a *baseline* window against a
*recent* window and maps the difference (dNDVI). Negative dNDVI = vegetation
loss (land clearing, mining expansion). Works for any site in sites.py using
only free Sentinel-2 data — no commercial imagery required.

For high-resolution (3 m) NDVI change from PlanetScope, see
03_planetscope_ndvi.py instead.

Setup:
    pip install earthengine-api requests
    earthengine authenticate     # or place scripts/config/ee-geodetic.json

Output (per site, e.g. konawe):
    data/ndvi_change_<site>.tif        # dNDVI GeoTIFF (open in QGIS)
    images/ndvi_change_<site>.png      # red=loss / green=gain quick-look
    data/ndvi_<site>_stats.json        # mean dNDVI, % area affected/severe

Run:
    python3 data-collection/03_ndvi_change_gee.py --site konawe
"""

import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sites import get_site
from gee_utils import (
    download_png, download_geotiff, initialize_ee, mask_s2_clouds, square_aoi)

try:
    import ee
except ImportError:
    sys.exit("Install earthengine-api: pip install earthengine-api")

HERE = os.path.dirname(__file__)
IMAGES_DIR = os.path.join(HERE, "..", "images")
DATA_DIR = os.path.join(HERE, "..", "data")
CONFIG_KEY = os.path.join(HERE, "..", "scripts", "config", "ee-geodetic.json")

# Loss thresholds on dNDVI
LOSS = -0.10      # noticeable vegetation loss
SEVERE = -0.20    # severe loss / bare ground

# Change detection composites MANY scenes and masks cloud per pixel (SCL) before
# taking the median, so the composite is near cloud-free regardless of any one
# scene. SCENE_CLOUD_MAX just drops hopeless (mostly-cloud) scenes up front.
SCENE_CLOUD_MAX = 60

DNDVI_VIS = {"min": -0.4, "max": 0.4,
             "palette": ["a50026", "ffffbf", "006837"]}  # red → yellow → green


def median_ndvi(start, end, aoi):
    """Cloud-masked median NDVI over a period (many scenes → cloud reduced)."""
    coll = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", SCENE_CLOUD_MAX))
            .map(mask_s2_clouds))
    count = coll.size().getInfo()
    ndvi = coll.map(
        lambda i: i.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ).median()
    return ndvi, count


def main():
    site = get_site()
    key = site["key"]
    print("=== Sentinel-2 NDVI Change Detection (GEE) ===")
    print(f"Site: {site['label']} [{key}]")

    initialize_ee(CONFIG_KEY)

    aoi = square_aoi(site["lon"], site["lat"], site["radius_km"])  # square clip
    pre_dates = site["ndvi_pre"]
    post_dates = site["ndvi_post"]

    print(f"Pre : {pre_dates[0]} .. {pre_dates[1]}")
    print(f"Post: {post_dates[0]} .. {post_dates[1]}")
    ndvi_pre, n_pre = median_ndvi(*pre_dates, aoi)
    ndvi_post, n_post = median_ndvi(*post_dates, aoi)
    print(f"Scenes — pre: {n_pre}, post: {n_post}")
    if n_pre == 0 or n_post == 0:
        raise SystemExit(
            "No Sentinel-2 scenes in one of the windows for this AOI. "
            "Adjust ndvi_pre / ndvi_post in sites.py."
        )

    dndvi = ndvi_post.subtract(ndvi_pre).rename("dNDVI").clip(aoi)

    # --- Statistics over the AOI ---
    reducers = (ee.Reducer.mean()
                .combine(ee.Reducer.count(), sharedInputs=True))
    base = dndvi.reduceRegion(reducer=reducers, geometry=aoi,
                              scale=10, maxPixels=int(1e9), bestEffort=True)
    mean_dndvi = base.getInfo()
    total = mean_dndvi.get("dNDVI_count", 0)

    def pct_below(threshold):
        m = dndvi.lt(threshold).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi,
            scale=10, maxPixels=int(1e9), bestEffort=True).getInfo()
        return (m.get("dNDVI") or 0) * 100.0

    stats = {
        "site": key,
        "ndvi_pre_window": list(pre_dates),
        "ndvi_post_window": list(post_dates),
        "scenes_pre": n_pre,
        "scenes_post": n_post,
        "dndvi_mean": mean_dndvi.get("dNDVI_mean"),
        "valid_pixels": total,
        "percent_affected": pct_below(LOSS),
        "percent_severe": pct_below(SEVERE),
    }

    print("\n=== Results ===")
    print(f"Mean dNDVI:              {stats['dndvi_mean']:.3f}")
    print(f"Area affected (< {LOSS}):  {stats['percent_affected']:.1f}%")
    print(f"Severe loss   (< {SEVERE}):  {stats['percent_severe']:.1f}%")

    os.makedirs(DATA_DIR, exist_ok=True)
    stats_path = os.path.join(DATA_DIR, f"ndvi_{key}_stats.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Saved: {os.path.normpath(stats_path)}")

    # --- Downloadable outputs ---
    png_out = os.path.join(IMAGES_DIR, f"ndvi_change_{key}.png")
    tif_out = os.path.join(DATA_DIR, f"ndvi_change_{key}.tif")
    print("\nDownloading dNDVI quick-look PNG...")
    download_png(dndvi, aoi, png_out, vis=DNDVI_VIS)
    print("Downloading dNDVI GeoTIFF...")
    download_geotiff(dndvi, aoi, tif_out, scale=10)


if __name__ == "__main__":
    main()
