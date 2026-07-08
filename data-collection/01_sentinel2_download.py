#!/usr/bin/env python3
"""
Download Sentinel-2 true color image for Capkala mining zone.

Uses Copernicus Data Space Ecosystem API (free, no authentication for basic downloads).
Alternatively can use Google Earth Engine (see 02_sirad_gee.js for GEE setup).

Output: data/sentinel2_capkala.tif
"""

import os, sys, requests
from datetime import datetime

# === Configuration ===
AOI = {
    "lat": 0.6784,
    "lon": 109.0836,
    "radius_km": 1.5
}
DATE = "2026-06-19"  # Cloud cover <1%
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "sentinel2_capkala.tif")

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
    
    # Authenticate with service account
    key_path = os.path.expanduser("~/.config/earthengine/ee-geodetic.json")
    if os.path.exists(key_path):
        credentials = ee.ServiceAccountCredentials(
            email=None, key_file=key_path
        )
        ee.Initialize(credentials)
    else:
        ee.Initialize()
    
    # Define AOI
    aoi = ee.Geometry.Point(AOI["lon"], AOI["lat"]).buffer(AOI["radius_km"] * 1000)
    
    # Search Sentinel-2
    collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(DATE, DATE.replace("19", "20"))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 5))
        .sort("CLOUDY_PIXEL_PERCENTAGE"))
    
    image = collection.first()
    
    if image is None:
        print("No Sentinel-2 image found for this date/AOI.")
        return
    
    # True color visualization (R, G, B)
    vis_params = {
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "gamma": 1.4
    }
    
    # Export to Drive or download directly
    url = image.getThumbURL({
        "region": aoi,
        "dimensions": "1920x1920",
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "gamma": 1.4,
        "format": "png"
    })
    
    print(f"GEE thumbnail URL: {url}")
    print("For full-resolution download, use GEE Export.image.toDrive()")
    
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
