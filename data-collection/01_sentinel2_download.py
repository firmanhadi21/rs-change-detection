#!/usr/bin/env python3
"""
Download Sentinel-2 true color image for Capkala mining zone.

Uses Google Earth Engine (Python API) by default, with a Copernicus Data Space
fallback. Set --site NAME (or SITE env) to target a different location.

Output (per site, e.g. konawe):
    images/sentinel2_<site>.png       # true-color quick-look
    data/sentinel2_<site>.tif         # full-resolution GeoTIFF (open in QGIS)
"""

import os, sys, json, requests
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sites import get_site
from gee_utils import download_png, download_geotiff, mask_s2_clouds, square_aoi

# === Configuration (site-parameterised: --site NAME or SITE env) ===
SITE = get_site()
AOI = {"lat": SITE["lat"], "lon": SITE["lon"], "radius_km": SITE["radius_km"]}
DATE = SITE["sentinel2_date"]
WINDOW_DAYS = 45  # ± search window around DATE when the exact date is empty/cloudy
MAX_CLOUD = 10    # hard cap on scene cloud cover (%)
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
    
    # Define AOI (square clip, not a circle)
    aoi = square_aoi(AOI["lon"], AOI["lat"], AOI["radius_km"])

    # Search a window around DATE. Prefer the single cleanest scene at
    # <= MAX_CLOUD% cloud; if none qualifies, fall back to a cloud-masked
    # median of many scenes to reduce cloud cover.
    start = ee.Date(DATE).advance(-WINDOW_DAYS, "day")
    end = ee.Date(DATE).advance(WINDOW_DAYS, "day")
    window = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
              .filterBounds(aoi)
              .filterDate(start, end))

    clear = (window.filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD))
                   .sort("CLOUDY_PIXEL_PERCENTAGE"))
    n_clear = clear.size().getInfo()

    if n_clear > 0:
        image = clear.first()
        cloud = image.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
        print(f"Using cleanest single scene: {cloud:.1f}% cloud "
              f"({n_clear} scene(s) <= {MAX_CLOUD}%)")
    else:
        composite_src = (window
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 80))
            .map(mask_s2_clouds))
        n = composite_src.size().getInfo()
        if n == 0:
            print(f"No Sentinel-2 scenes within ±{WINDOW_DAYS} days of {DATE} "
                  f"for this AOI. Widen WINDOW_DAYS or change the date.")
            return
        print(f"No single scene <= {MAX_CLOUD}% cloud; compositing {n} "
              f"cloud-masked scenes (median) to reduce cloud.")
        image = composite_src.median()
    
    # True color visualization (R, G, B)
    vis_params = {
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "gamma": 1.4
    }
    
    tc_vis = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.4}
    truecolor = image.select(["B4", "B3", "B2"])

    # 1) True-color quick-look PNG -> images/
    print("Downloading true-color quick-look PNG...")
    download_png(image, aoi, IMG_OUT, vis=tc_vis)

    # 2) Full-resolution georeferenced GeoTIFF -> data/
    print("Downloading full-resolution GeoTIFF...")
    download_geotiff(truecolor, aoi, OUTPUT, scale=10)

    return IMG_OUT


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
