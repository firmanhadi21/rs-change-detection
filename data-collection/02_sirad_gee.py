#!/usr/bin/env python3
"""SIRAD (Sentinel-1 RGB Anomaly Detection) for the Capkala mining zone.

Runs entirely in Google Earth Engine via the Python API (earthengine-api) —
no Code Editor / JavaScript needed.

Builds an RGB composite of mean VH backscatter from three periods:
    Red   = 2024
    Green = 2025
    Blue  = Mar-Jun 2026 (post police raid)

Bright blue => new activity in 2026 (mining continued after the arrest).

Setup (one time):
    pip install earthengine-api requests
    earthengine authenticate          # opens a browser to link your GEE account

Output:
    images/sirad_raw.png              # downloaded thumbnail (for video assembly)
    plus an optional Drive export task (full-resolution GeoTIFF/PNG)

Run:
    python3 data-collection/02_sirad_gee.py
"""

import os
import sys

try:
    import ee
except ImportError:
    sys.exit("Install earthengine-api: pip install earthengine-api")

try:
    import requests
except ImportError:
    sys.exit("Install requests: pip install requests")

# === Configuration ===
LON, LAT = 109.0836, 0.6784
RADIUS_METERS = 1500  # 1.5 km

PERIODS = {
    "R_2024": ("2024-01-01", "2024-12-31"),
    "G_2025": ("2025-01-01", "2025-12-31"),
    "B_2026": ("2026-03-01", "2026-06-30"),  # post-arrest
}

VIS = {"bands": ["R_2024", "G_2025", "B_2026"], "min": -25, "max": -5, "gamma": 1.0}

OUT_PNG = os.path.join(os.path.dirname(__file__), "..", "images", "sirad_raw.png")


def initialize():
    """Initialise Earth Engine, using a service-account key if present."""
    key_path = os.path.expanduser("~/.config/earthengine/ee-geodetic.json")
    if os.path.exists(key_path):
        creds = ee.ServiceAccountCredentials(email=None, key_file=key_path)
        ee.Initialize(creds)
    else:
        # Falls back to credentials from `earthengine authenticate`.
        ee.Initialize()


def mean_vh(start, end, geometry):
    """Mean VH backscatter (dB) over a period, clipped to the AOI."""
    collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(geometry)
        .filterDate(start, end)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
        .select("VH")
        .map(lambda img: img.clip(geometry))
    )
    count = collection.size().getInfo()
    print(f"  {start} .. {end}: {count} images")
    return collection.mean().rename("VH_mean"), count


def main():
    print("=== SIRAD (Sentinel-1 RGB Anomaly Detection) ===")
    print(f"AOI: {LAT}N, {LON}E, radius {RADIUS_METERS} m\n")

    initialize()

    aoi = ee.Geometry.Point([LON, LAT]).buffer(RADIUS_METERS)

    bands, total = [], 0
    for band_name, (start, end) in PERIODS.items():
        img, count = mean_vh(start, end, aoi)
        bands.append(img.rename(band_name))
        total += count
    print(f"  total: {total} Sentinel-1 images\n")

    sirad = ee.Image.cat(bands)

    # --- Download a thumbnail straight into images/ for the video pipeline ---
    print("Fetching SIRAD thumbnail from GEE...")
    url = sirad.getThumbURL({
        "region": aoi,
        "dimensions": "1920x1920",
        "bands": VIS["bands"],
        "min": VIS["min"],
        "max": VIS["max"],
        "gamma": VIS["gamma"],
        "format": "png",
    })
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    with open(OUT_PNG, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved: {os.path.normpath(OUT_PNG)}")

    # --- Optional: full-resolution export to Google Drive ---
    task = ee.batch.Export.image.toDrive(
        image=sirad.visualize(**VIS),
        description="SIRAD_Capkala_2024_2026",
        folder="GEE_Exports",
        fileNamePrefix="sirad_capkala",
        region=aoi,
        scale=10,
        crs="EPSG:4326",
        maxPixels=int(1e9),
    )
    task.start()
    print(f"Started Drive export task id={task.id} (folder: GEE_Exports)")

    print("\n=== Interpretation ===")
    print("White/Gray = activity in all periods (ongoing)")
    print("Red        = 2024 only (stopped)")
    print("Yellow     = 2024 + 2025 (no 2026)")
    print("Cyan       = 2025 + 2026 (newer)")
    print("Blue       = 2026 ONLY (post-arrest — KEY EVIDENCE)")


if __name__ == "__main__":
    main()
