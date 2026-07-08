#!/usr/bin/env python3
"""Spectral indices, composites, and Sentinel-1 helpers for change detection.

All functions operate server-side in Google Earth Engine. Sentinel-2 composites
mask cloud per pixel (SCL) and take a median over many scenes, so the result is
near cloud-free regardless of any single scene's cloud cover.
"""

import ee
from gee_utils import mask_s2_clouds

S2 = "COPERNICUS/S2_SR_HARMONIZED"
S1 = "COPERNICUS/S1_GRD"
ORBITS = ("ASCENDING", "DESCENDING")


def s2_median(aoi, start, end, scene_cloud_max=60):
    """Cloud-masked median Sentinel-2 SR composite over a date window.

    Returns (image, scene_count). scene_count is a Python int.
    """
    coll = (ee.ImageCollection(S2)
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", scene_cloud_max))
            .map(mask_s2_clouds))
    return coll.median(), coll.size().getInfo()


# --- Normalised-difference indices on a Sentinel-2 SR image ---
def ndvi(img):  # vegetation
    return img.normalizedDifference(["B8", "B4"]).rename("NDVI")


def ndbi(img):  # built-up
    return img.normalizedDifference(["B11", "B8"]).rename("NDBI")


def ndwi(img):  # open water (McFeeters)
    return img.normalizedDifference(["B3", "B8"]).rename("NDWI")


def nbr(img):   # burn
    return img.normalizedDifference(["B8", "B12"]).rename("NBR")


INDEX_FN = {"NDVI": ndvi, "NDBI": ndbi, "NDWI": ndwi, "NBR": nbr}


# --- Sentinel-1 SAR helpers ---
def s1(aoi, start, end, orbit, pol):
    """Sentinel-1 IW collection for one polarisation and orbit direction."""
    return (ee.ImageCollection(S1)
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.eq("orbitProperties_pass", orbit))
            .select(pol))


def best_orbit(aoi, periods, pol="VH", forced=None):
    """Pick the orbit direction (ASC/DESC) that has imagery in every period.

    `periods` is a list of (start, end) tuples. Returns (orbit, covered, counts).
    """
    orbits = [forced] if forced else list(ORBITS)
    best = None  # (covered, total, orbit, counts)
    for orbit in orbits:
        counts = [s1(aoi, s, e, orbit, pol).size().getInfo() for (s, e) in periods]
        cand = (all(c > 0 for c in counts), sum(counts), orbit, counts)
        if best is None or cand[:2] > best[:2]:
            best = cand
    covered, _total, orbit, counts = best
    return orbit, covered, counts
