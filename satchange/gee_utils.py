#!/usr/bin/env python3
"""Helpers to download Earth Engine results directly to local disk.

Two ways to get a result out of GEE:
  * download_png()     — a quick-look RGB thumbnail (capped resolution)
  * download_geotiff() — the full-resolution, georeferenced GeoTIFF you can
                         open in QGIS/rasterio. Uses ee.Image.getDownloadURL,
                         which has a per-request size limit (~32-48 MB); for
                         very large AOIs, fall back to a Drive export.
"""

import os
import sys
import requests


def _fetch(url, out_path):
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return out_path


def download_png(image, region, out_path, dimensions="1920x1920", vis=None):
    """Download an RGB quick-look PNG thumbnail."""
    params = {"region": region, "dimensions": dimensions, "format": "png"}
    if vis:
        params.update(vis)
    _fetch(image.getThumbURL(params), out_path)
    print(f"Saved: {os.path.normpath(out_path)}")
    return out_path


def download_geotiff(image, region, out_path, scale=10, max_scale_mult=16):
    """Download a full-resolution single-file GeoTIFF.

    Earth Engine's direct download has a per-request size/compute limit, so a
    large AOI can 400. Retry at progressively coarser scale until it fits.
    Returns the path on success, or None if it fails even coarsened.
    """
    s, mult = scale, 1
    last_err = None
    while mult <= max_scale_mult:
        try:
            url = image.getDownloadURL({
                "region": region, "scale": s, "crs": "EPSG:4326",
                "format": "GEO_TIFF", "filePerBand": False,
            })
            _fetch(url, out_path)  # the pixel fetch can also fail for large AOIs
            size_mb = os.path.getsize(out_path) / 1e6
            note = f" (coarsened to {s:.0f} m to fit)" if s != scale else ""
            print(f"Saved: {os.path.normpath(out_path)} ({size_mb:.1f} MB GeoTIFF){note}")
            return out_path
        except Exception as e:  # noqa: BLE001 — retry coarser
            last_err = e
            mult *= 2
            s = scale * mult
    print(f"NOTE: GeoTIFF download failed even at {scale * max_scale_mult:.0f} m "
          f"({last_err}).")
    print("      Reduce --radius, or add --drive to export the full-res GeoTIFF "
          "to Google Drive.")
    return None


def wants_drive_export(argv=None):
    """True if the user passed --drive (opt-in full-res Drive export)."""
    argv = sys.argv if argv is None else argv
    return "--drive" in argv


def square_aoi(lon, lat, radius_km):
    """Square AOI centred on (lon, lat), half-side = radius_km.

    Side length = 2 * radius_km (the square that circumscribes the old circle),
    axis-aligned in lon/lat. Use instead of Point.buffer() (a circle).
    """
    import ee
    return ee.Geometry.Point([lon, lat]).buffer(radius_km * 1000).bounds()


def mask_s2_clouds(img):
    """Mask cloud / shadow / cirrus / snow using Sentinel-2 SCL band.

    Applied per pixel so a median of many scenes yields a near cloud-free
    composite even when individual scenes are partly cloudy.
    """
    scl = img.select("SCL")
    keep = (scl.neq(3)       # cloud shadow
            .And(scl.neq(8))    # cloud medium probability
            .And(scl.neq(9))    # cloud high probability
            .And(scl.neq(10))   # thin cirrus
            .And(scl.neq(11)))  # snow / ice
    return img.updateMask(keep)


def initialize_ee(config_key=None):
    """Initialise Earth Engine with a service-account key if one is present."""
    import json
    import ee

    candidates = [
        p for p in (config_key,
                    os.path.expanduser("~/.config/earthengine/ee-geodetic.json"))
        if p
    ]
    for key_path in candidates:
        if os.path.exists(key_path):
            with open(key_path) as f:
                email = json.load(f).get("client_email")
            ee.Initialize(ee.ServiceAccountCredentials(email, key_file=key_path))
            print(f"GEE: service account {email}")
            return
    ee.Initialize()  # falls back to `earthengine authenticate`
    print("GEE: user credentials (earthengine authenticate)")
