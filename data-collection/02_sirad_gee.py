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

Output (per site, e.g. konawe):
    images/sirad_<site>.png           # RGB quick-look thumbnail
    data/sirad_<site>.tif             # full-resolution GeoTIFF (open in QGIS)
    optionally a Drive export task with --drive

Run:
    python3 data-collection/02_sirad_gee.py --site konawe
    python3 data-collection/02_sirad_gee.py --site konawe --drive   # + Drive
"""

import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sites import get_site
from gee_utils import (
    download_png, download_geotiff, wants_drive_export, square_aoi)

try:
    import ee
except ImportError:
    sys.exit("Install earthengine-api: pip install earthengine-api")

try:
    import requests
except ImportError:
    sys.exit("Install requests: pip install requests")

# Fixed R/G/B visualisation (the period labels are the band names)
VIS = {"bands": ["R_2024", "G_2025", "B_2026"], "min": -25, "max": -5, "gamma": 1.0}

HERE = os.path.dirname(__file__)
IMAGES_DIR = os.path.join(HERE, "..", "images")
DATA_DIR = os.path.join(HERE, "..", "data")
CONFIG_KEY = os.path.join(HERE, "..", "scripts", "config", "ee-geodetic.json")


def initialize():
    """Initialise Earth Engine with a service-account key if one is present."""
    candidates = [
        CONFIG_KEY,
        os.path.expanduser("~/.config/earthengine/ee-geodetic.json"),
    ]
    for key_path in candidates:
        if os.path.exists(key_path):
            with open(key_path) as f:
                email = json.load(f).get("client_email")
            creds = ee.ServiceAccountCredentials(email, key_file=key_path)
            ee.Initialize(creds)
            print(f"GEE: service account {email}")
            return
    # Falls back to credentials from `earthengine authenticate`.
    ee.Initialize()
    print("GEE: user credentials (earthengine authenticate)")


ORBITS = ("ASCENDING", "DESCENDING")


def vh_collection(start, end, geometry, orbit):
    """Sentinel-1 IW VH collection for a period and orbit direction."""
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(geometry)
        .filterDate(start, end)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", orbit))
        .select("VH")
    )


def select_orbit(periods, geometry, forced=None):
    """Pick the orbit direction that has imagery in *every* period.

    Sentinel-1 ascending/descending coverage varies by location and year, so a
    hardcoded orbit that works at one site can leave a period empty at another.
    """
    orbits = [forced] if forced else ORBITS
    best = None  # (all_periods_covered, total_images, orbit, counts)
    for orbit in orbits:
        counts = {
            band: vh_collection(s, e, geometry, orbit).size().getInfo()
            for band, (s, e) in periods.items()
        }
        total = sum(counts.values())
        covered = all(c > 0 for c in counts.values())
        print(f"  {orbit}: {counts} (total {total})")
        cand = (covered, total, orbit, counts)
        if best is None or cand[:2] > best[:2]:
            best = cand

    covered, total, orbit, counts = best
    if not covered:
        raise SystemExit(
            f"No single orbit covers all periods for this AOI (counts: {counts}).\n"
            "Try a larger radius_km, adjust the period dates in sites.py, or "
            "check Sentinel-1 coverage for the area."
        )
    print(f"  → using {orbit} orbit\n")
    return orbit


def mean_vh(start, end, geometry, orbit):
    """Mean VH backscatter (dB) over a period, clipped to the AOI."""
    collection = vh_collection(start, end, geometry, orbit).map(
        lambda img: img.clip(geometry)
    )
    return collection.mean().rename("VH_mean")


def main():
    site = get_site()
    out_png = os.path.join(IMAGES_DIR, f"sirad_{site['key']}.png")

    print("=== SIRAD (Sentinel-1 RGB Anomaly Detection) ===")
    print(f"Site: {site['label']} [{site['key']}]")
    print(f"AOI: {site['lat']}, {site['lon']}, radius {site['radius_km']} km\n")

    initialize()

    aoi = square_aoi(site["lon"], site["lat"], site["radius_km"])  # square clip
    periods = site["sirad_periods"]

    print("Checking Sentinel-1 coverage per orbit...")
    orbit = select_orbit(periods, aoi, forced=site.get("orbit"))

    bands = [
        mean_vh(start, end, aoi, orbit).rename(band_name)
        for band_name, (start, end) in periods.items()
    ]
    sirad = ee.Image.cat(bands)
    out_tif = os.path.join(DATA_DIR, f"sirad_{site['key']}.tif")

    # 1) RGB quick-look thumbnail -> images/
    print("Downloading SIRAD quick-look PNG...")
    vis = {"bands": VIS["bands"], "min": VIS["min"],
           "max": VIS["max"], "gamma": VIS["gamma"]}
    download_png(sirad, aoi, out_png, vis=vis)

    # 2) Full-resolution georeferenced GeoTIFF (visualised RGB) -> data/
    print("Downloading full-resolution GeoTIFF...")
    download_geotiff(sirad.visualize(**VIS), aoi, out_tif, scale=10)

    # 3) Optional: also export full-res to Google Drive with --drive
    if wants_drive_export():
        task = ee.batch.Export.image.toDrive(
            image=sirad.visualize(**VIS),
            description=f"SIRAD_{site['key']}_2024_2026",
            folder="GEE_Exports",
            fileNamePrefix=f"sirad_{site['key']}",
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
