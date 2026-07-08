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


def download_geotiff(image, region, out_path, scale=10):
    """Download a full-resolution single-file GeoTIFF.

    Returns the path on success, or None if GEE refuses (usually because the
    AOI is too large for a direct download — use a Drive export instead).
    """
    try:
        url = image.getDownloadURL({
            "region": region,
            "scale": scale,
            "format": "GEO_TIFF",
            "filePerBand": False,
        })
    except Exception as e:  # noqa: BLE001 — surface GEE's message, keep going
        print(f"NOTE: direct GeoTIFF download unavailable ({e}).")
        print("      AOI may be too large — use --drive for a Drive export.")
        return None
    _fetch(url, out_path)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"Saved: {os.path.normpath(out_path)} ({size_mb:.1f} MB GeoTIFF)")
    return out_path


def wants_drive_export(argv=None):
    """True if the user passed --drive (opt-in full-res Drive export)."""
    argv = sys.argv if argv is None else argv
    return "--drive" in argv
