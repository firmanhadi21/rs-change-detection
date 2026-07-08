#!/usr/bin/env python3
"""
Download Sentinel-2 true color image for Capkala mining zone.

Uses Copernicus Data Space Ecosystem API (free, no authentication for basic downloads).
Alternatively can use Google Earth Engine (see 02_sirad_gee.js for GEE setup).

Output: data/sentinel2_capkala.tif
"""

import os, sys, json, requests
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sites import get_site

# === Configuration (site-parameterised: --site NAME or SITE env) ===
SITE = get_site()
AOI = {"lat": SITE["lat"], "lon": SITE["lon"], "radius_km": SITE["radius_km"]}
DATE = SITE["sentinel2_date"]
WINDOW_DAYS = 30  # ± search window around DATE when the exact date is empty/cloudy
OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "data", f"sentinel2_{SITE['key']}.tif"
)
IMG_OUT = os.path.join(
    os.path.dirname(__file__), "..", "images", f"sentinel2_{SITE['key']}.png"
)
CONFIG_KEY = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "config", "ee-geodetic.json"
)

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

# === Copernicus Data Space API ===
# Sentinel-2 L2A tile search for Capkala (UTM zone 49N, tile NMF)
# Tile covering 0.6784N, 109.0836E

BASE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"

def search_sentinel2(date, lat, lon):
    """Search for Sentinel-2 L2A product covering the AOI."""
    # This queries the Copernicus catalog
    params = {
        "$filter": (
            f"Collection/Name eq 'SENTINEL-2' "
            f"and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' "
            f"and att/Value lt 5.0) "
            f"and ContentDate/Start gt {date}T00:00:00.000Z "
            f"and ContentDate/Start lt {date}T23:59:59.000Z "
            f"and OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon} {lat})')"
        ),
        "$top": 3,
        "$expand": "Attributes",
        "$orderby": "ContentDate/Start asc"
    }
    
    resp = requests.get(f"{BASE_URL}/Products", params=params)
    resp.raise_for_status()
    return resp.json()

def download_product(product_id, output_path):
    """Download a product by ID using the Copernicus Data Space API."""
    # Requires Copernicus Data Space credentials
    # Set COPERNICUS_USER and COPERNICUS_PASS env vars
    user = os.environ.get("COPERNICUS_USER")
    password = os.environ.get("COPERNICUS_PASS")
    
    if not user or not password:
        print("NOTE: Set COPERNICUS_USER and COPERNICUS_PASS to download from Copernicus.")
        print("Alternatives:")
        print("  1. Google Earth Engine: use 02_sirad_gee.js setup")
        print("  2. Copernicus Browser: https://browser.dataspace.copernicus.eu/")
        print("  3. Sentinel Hub EO Browser: https://apps.sentinel-hub.com/eo-browser/")
        return False
    
    # Get access token
    token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    token_resp = requests.post(token_url, data={
        "grant_type": "password",
        "client_id": "cdse-public",
        "username": user,
        "password": password
    })
    token = token_resp.json()["access_token"]
    
    # Download
    headers = {"Authorization": f"Bearer {token}"}
    download_url = f"{BASE_URL}/Products({product_id})/$value"
    
    print(f"Downloading {product_id}...")
    with requests.get(download_url, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    
    print(f"Saved: {output_path}")
    return True


def download_via_gee():
    """
    Alternative: download via Google Earth Engine Python API.
    Requires: pip install earthengine-api
    Service account key: ~/.config/earthengine/ee-geodetic.json
    """
    try:
        import ee
    except ImportError:
        print("Install earthengine-api: pip install earthengine-api")
        return
    
    # Authenticate with a service-account key if available
    for key_path in (CONFIG_KEY,
                     os.path.expanduser("~/.config/earthengine/ee-geodetic.json")):
        if os.path.exists(key_path):
            with open(key_path) as kf:
                email = json.load(kf).get("client_email")
            ee.Initialize(ee.ServiceAccountCredentials(email, key_file=key_path))
            break
    else:
        ee.Initialize()
    
    # Define AOI
    aoi = ee.Geometry.Point(AOI["lon"], AOI["lat"]).buffer(AOI["radius_km"] * 1000)

    # Search Sentinel-2 within a window around DATE, least-cloudy first.
    # (An exact single date is often empty or cloudy at an arbitrary site, so
    #  widen the window and relax the cloud threshold until something is found.)
    start = ee.Date(DATE).advance(-WINDOW_DAYS, "day")
    end = ee.Date(DATE).advance(WINDOW_DAYS, "day")
    image, count = None, 0
    for cloud_max in (5, 20, 60):
        collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
            .sort("CLOUDY_PIXEL_PERCENTAGE"))
        count = collection.size().getInfo()  # server-side emptiness check
        if count > 0:
            image = collection.first()
            print(f"Found {count} scene(s) within ±{WINDOW_DAYS}d, cloud <{cloud_max}%")
            break

    if image is None:
        print(f"No Sentinel-2 scene found within ±{WINDOW_DAYS} days of {DATE} "
              f"(cloud <60%) for this AOI. Widen WINDOW_DAYS or change the date.")
        return
    
    # True color visualization (R, G, B)
    vis_params = {
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "gamma": 1.4
    }
    
    # Download a true-color thumbnail straight into images/
    url = image.getThumbURL({
        "region": aoi,
        "dimensions": "1920x1920",
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "gamma": 1.4,
        "format": "png"
    })

    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(IMG_OUT), exist_ok=True)
    with open(IMG_OUT, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Saved: {os.path.normpath(IMG_OUT)}")
    print("For full-resolution GeoTIFF, use GEE Export.image.toDrive().")

    return url


if __name__ == "__main__":
    print(f"=== Sentinel-2 Download ===")
    print(f"AOI: {AOI['lat']}N, {AOI['lon']}E, {AOI['radius_km']}km radius")
    print(f"Date: {DATE}")
    print()
    
    # Try GEE approach first (easier, no Copernicus credentials needed)
    print("Attempting via Google Earth Engine...")
    url = download_via_gee()
    
    if not url:
        print("\nAttempting via Copernicus API...")
        try:
            results = search_sentinel2(DATE, AOI["lat"], AOI["lon"])
            if results.get("value"):
                product = results["value"][0]
                print(f"Found: {product['Name']}")
                download_product(product["Id"], OUTPUT)
        except Exception as e:
            print(f"Copernicus API error: {e}")
            print("\nManual download options:")
            print("  1. Copernicus Browser: https://browser.dataspace.copernicus.eu/")
            print("     → Search 'Capkala', date 2026-06-19, S2 L2A, cloud <5%")
            print("  2. Sentinel Hub: https://apps.sentinel-hub.com/eo-browser/")
            print(f"     → Coordinates: {AOI['lat']}, {AOI['lon']}")
