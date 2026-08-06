#!/usr/bin/env python3
"""Spectral indices, composites, and Sentinel-1 helpers for change detection.

All functions operate server-side in Google Earth Engine. Sentinel-2 composites
mask cloud per pixel (SCL) and take a median over many scenes, so the result is
near cloud-free regardless of any single scene's cloud cover.
"""

try:
    import ee  # only needed for the GEE backend
except ImportError:
    ee = None
from .gee_utils import mask_s2_clouds

S2 = "COPERNICUS/S2_SR_HARMONIZED"
S1 = "COPERNICUS/S1_GRD"
ORBITS = ("ASCENDING", "DESCENDING")


# SWIR false colour (SWIR2 / NIR / RED) for quick-look previews. Used instead
# of true colour because the Landsat paths rename to a band set with no BLUE,
# so this is the one scheme available on every sensor — and for a burn it is
# the more informative composite anyway: scars read orange-red, healthy
# vegetation green, water near-black.
PREVIEW_VIS = {
    "s2": {"bands": ["B12", "B8", "B4"], "min": 0, "max": 3500},
    "landsat": {"bands": ["SWIR2", "NIR", "RED"], "min": 0, "max": 0.35},
}


def s2_scenes(aoi, start, end, scene_cloud_max=60):
    """The Sentinel-2 scenes a composite is built from, BEFORE cloud masking.

    Inventory has to be taken here rather than from the mapped collection:
    per-scene prep uses multiply/add/rename, and those drop image properties in
    Earth Engine, so system:index and the cloud field come back null afterwards.
    Cloud masking itself is updateMask, which does preserve them, but the
    Landsat preps do not — so all three sensors take the same route.
    """
    return (ee.ImageCollection(S2)
            .filterBounds(aoi)
            .filterDate(start, end)
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", scene_cloud_max)))


def s2_median(aoi, start, end, scene_cloud_max=60):
    """Cloud-masked median Sentinel-2 SR composite over a date window.

    Returns (image, scene_count). scene_count is a Python int.
    """
    coll = s2_scenes(aoi, start, end, scene_cloud_max).map(mask_s2_clouds)
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


# --- Alternative built-up indices (all computable on Sentinel-2) ---
def ui(img):    # Urban Index — (SWIR2-NIR)/(SWIR2+NIR)
    return img.normalizedDifference(["B12", "B8"]).rename("UI")


def _savi(img, L=0.5):  # Soil-Adjusted Vegetation Index (reflectance-scaled)
    nir = img.select("B8").divide(10000)
    red = img.select("B4").divide(10000)
    return nir.subtract(red).multiply(1 + L).divide(nir.add(red).add(L))


def bu(img):    # Built-Up index = NDBI - NDVI (Kawamura 1996)
    return ndbi(img).subtract(ndvi(img)).rename("BU")


def ibi(img):   # Index-Based Built-up Index (Xu 2008)
    nd = img.normalizedDifference(["B11", "B8"])            # NDBI
    mndwi = img.normalizedDifference(["B3", "B11"])         # water
    x = _savi(img).add(mndwi).divide(2)
    # The ratio form is unstable where the denominator crosses zero; clamp it.
    return nd.subtract(x).divide(nd.add(x)).clamp(-1, 1).rename("IBI")


INDEX_FN = {"NDVI": ndvi, "NDBI": ndbi, "NDWI": ndwi, "NBR": nbr,
            "UI": ui, "BU": bu, "IBI": ibi}
# Interchangeable built-up methods for the urbanization scenario (Sentinel-2).
# NDISI/EBBI need a thermal band (Landsat), so they are NOT listed here.
BUILTUP_METHODS = ["NDBI", "UI", "BU", "IBI"]


# --- The same indices on a Landsat SR composite (unified GREEN/RED/NIR/SWIR1/SWIR2
#     bands from l_sr_median) so optical scenarios can reach back to 1984 (L5 TM). ---
def _lndvi(img):  return img.normalizedDifference(["NIR", "RED"]).rename("NDVI")
def _lndbi(img):  return img.normalizedDifference(["SWIR1", "NIR"]).rename("NDBI")
def _lndwi(img):  return img.normalizedDifference(["GREEN", "NIR"]).rename("NDWI")
def _lnbr(img):   return img.normalizedDifference(["NIR", "SWIR2"]).rename("NBR")
def _lui(img):    return img.normalizedDifference(["SWIR2", "NIR"]).rename("UI")
def _lbu(img):    return _lndbi(img).subtract(_lndvi(img)).rename("BU")

LANDSAT_INDEX_FN = {"NDVI": _lndvi, "NDBI": _lndbi, "NDWI": _lndwi,
                    "NBR": _lnbr, "UI": _lui, "BU": _lbu}

# Green/SWIR1 band pair for the water mask (MNDWI) per sensor.
MNDWI_BANDS = {"s2": ("B3", "B11"), "landsat": ("GREEN", "SWIR1")}

# Per-method change-detection defaults: (direction, affected_thr, severe_thr, vmax).
# Different indices have different ranges, so each needs its own thresholds.
METHOD_DEFAULTS = {
    "NDVI": ("loss", -0.15, -0.30, 0.6),
    "NDBI": ("gain", 0.10, 0.20, 0.5),
    "UI":   ("gain", 0.08, 0.18, 0.5),
    "BU":   ("gain", 0.10, 0.25, 0.8),
    "IBI":  ("gain", 0.10, 0.25, 1.0),
    "NDWI": ("gain", 0.10, 0.25, 0.6),
    "NBR":  ("loss", -0.10, -0.27, 0.6),
}


# --- Landsat 8/9 Collection-2 Level-2 (adds a thermal band for NDISI/EBBI) ---
L8_COL, L9_COL = "LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"
LSR_TM = "LANDSAT/LT05/C02/T1_L2"   # Landsat 5 TM; L7 excluded (SLC-off, 2003)


def _l2_prep(img):
    """Scale a Landsat C2-L2 scene to reflectance + °C and mask clouds."""
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)).eq(0)
    opt = (img.select(["SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"])
           .multiply(0.0000275).add(-0.2))
    tir = img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
    return (opt.addBands(tir)
               .rename(["GREEN", "RED", "NIR", "SWIR1", "SWIR2", "TIR"])
               .updateMask(clear))


def _l_filter(cid, aoi, start, end, cloud_max):
    """One Landsat collection, filtered but not yet prepped. Shared by the
    median builders and the scene inventory so the two cannot drift apart."""
    return (ee.ImageCollection(cid).filterBounds(aoi).filterDate(start, end)
            .filter(ee.Filter.lt("CLOUD_COVER", cloud_max)))


def l2_scenes(aoi, start, end, cloud_max=60):
    """Landsat 8/9 scenes behind the composite, before prep. See s2_scenes."""
    return (_l_filter(L8_COL, aoi, start, end, cloud_max)
            .merge(_l_filter(L9_COL, aoi, start, end, cloud_max)))


def l2_median(aoi, start, end, cloud_max=60):
    """Cloud-masked median Landsat 8/9 composite. Returns (image, scene_count)."""
    col = l2_scenes(aoi, start, end, cloud_max).map(_l2_prep)
    return col.median(), col.size().getInfo()


def _prep_l_sr(img, bands):
    """Scale a Landsat C2-L2 scene to surface reflectance (no thermal), masked."""
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)).eq(0)
    opt = img.select(bands).multiply(0.0000275).add(-0.2)
    return opt.rename(["GREEN", "RED", "NIR", "SWIR1", "SWIR2"]).updateMask(clear)


def l_sr_median(aoi, start, end, cloud_max=60):
    """Median Landsat surface-reflectance composite (archive back to 1984).

    Uses Landsat 5 (TM) and 8/9 (OLI); Landsat 7 is EXCLUDED because its
    Scan Line Corrector failed in 2003 (SLC-off gaps stripe every scene).
    Uniform band naming across sensors so historical epochs (e.g. 2010) work.
    """
    tm = (_l_filter(LSR_TM, aoi, start, end, cloud_max)  # L5 TM (ends 2011)
          .map(lambda i: _prep_l_sr(i, ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"])))
    oli = (_l_filter(L8_COL, aoi, start, end, cloud_max)
           .merge(_l_filter(L9_COL, aoi, start, end, cloud_max))
           .map(lambda i: _prep_l_sr(i, ["SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"])))
    col = tm.merge(oli)
    return col.median(), col.size().getInfo()


def l_sr_scenes(aoi, start, end, cloud_max=60):
    """Landsat archive scenes behind the composite, before prep. See s2_scenes.

    TM and OLI need different band mappings, so the composite maps them
    separately; the inventory only needs the scene list, which is the same
    filter on the same three collections.
    """
    return (_l_filter(LSR_TM, aoi, start, end, cloud_max)
            .merge(_l_filter(L8_COL, aoi, start, end, cloud_max))
            .merge(_l_filter(L9_COL, aoi, start, end, cloud_max)))


# --- Plain imagery (no index): keep BLUE so true colour is possible ---
# The index composites drop blue, which is fine for NDVI/NBR but makes a
# natural-colour preview impossible. This path is separate for that reason.
IMAGERY_NAMES = ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"]
_S2_IMAGERY = ["B2", "B3", "B4", "B8", "B11", "B12"]
_TM_IMAGERY = ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"]
_OLI_IMAGERY = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
IMAGERY_VIS = {
    # Sentinel-2 SR is scaled by 10000; Landsat C2-L2 is scaled to reflectance.
    "s2": {"true": {"bands": ["RED", "GREEN", "BLUE"], "min": 0, "max": 3000},
           "swir": {"bands": ["SWIR2", "NIR", "RED"], "min": 0, "max": 3500}},
    "landsat": {"true": {"bands": ["RED", "GREEN", "BLUE"], "min": 0, "max": 0.30},
                "swir": {"bands": ["SWIR2", "NIR", "RED"], "min": 0, "max": 0.35}},
}


def _prep_l_imagery(img, bands):
    """Landsat C2-L2 scene as 6-band reflectance, cloud-masked, BLUE kept."""
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)).eq(0)
    return (img.select(bands).multiply(0.0000275).add(-0.2)
            .rename(IMAGERY_NAMES).updateMask(clear))


def imagery_composite(aoi, start, end, sensor="s2", cloud_max=60):
    """Reflectance composite for the plain-imagery scenario.

    Returns (image, scenes_for_inventory, scale_m, cloud_property). A single
    date and a multi-month window take exactly the same path — a one-day window
    simply medians one scene — so nothing special is needed for the two cases.
    """
    if sensor == "landsat":
        tm = (_l_filter(LSR_TM, aoi, start, end, cloud_max)
              .map(lambda i: _prep_l_imagery(i, _TM_IMAGERY)))
        oli = (_l_filter(L8_COL, aoi, start, end, cloud_max)
               .merge(_l_filter(L9_COL, aoi, start, end, cloud_max))
               .map(lambda i: _prep_l_imagery(i, _OLI_IMAGERY)))
        return (tm.merge(oli).median(),
                l_sr_scenes(aoi, start, end, cloud_max), 30, "CLOUD_COVER")
    scenes = s2_scenes(aoi, start, end, cloud_max)
    img = scenes.map(mask_s2_clouds).select(_S2_IMAGERY, IMAGERY_NAMES).median()
    return img, scenes, 10, "CLOUDY_PIXEL_PERCENTAGE"


def available_dates(scenes, span_days=30):
    """Acquisition dates near a window, for when an exact date has no overpass."""
    import datetime as _dt
    ts = scenes.aggregate_array("system:time_start").getInfo() or []
    out = sorted({_dt.datetime.fromtimestamp(t / 1000, _dt.UTC).date().isoformat()
                  for t in ts})
    return out


def scene_inventory(coll, cloud_prop, limit=200):
    """Which scenes went into a composite: id, date and cloud cover.

    A bare count ('12 scenes') can be neither checked nor reproduced; the ids
    can. Capped, because a multi-year window over a busy path can run to
    thousands and the list is provenance, not data.
    """
    sub = ee.ImageCollection(coll.toList(limit))
    got = ee.Dictionary({
        "n": coll.size(),
        "id": sub.aggregate_array("system:index"),
        "t": sub.aggregate_array("system:time_start"),
        "cloud": sub.aggregate_array(cloud_prop),
    }).getInfo()
    import datetime as _dt
    ids, ts = got.get("id") or [], got.get("t") or []
    clouds = got.get("cloud") or []
    scenes = []
    for i, sid in enumerate(ids):
        ms = ts[i] if i < len(ts) else None
        cl = clouds[i] if i < len(clouds) else None
        scenes.append({
            "id": sid,
            "date": (_dt.datetime.fromtimestamp(ms / 1000, _dt.UTC)
                     .date().isoformat() if ms else None),
            "cloud_pct": round(cl, 1) if isinstance(cl, (int, float)) else None,
        })
    scenes.sort(key=lambda s: s["date"] or "")
    return {"count": int(got.get("n") or 0), "listed": len(scenes),
            "truncated": int(got.get("n") or 0) > len(scenes),
            "scenes": scenes}


def _norm01(band, lo, hi):
    return band.subtract(lo).divide(hi - lo).clamp(0, 1)


def ndisi(img):   # Normalized Difference Impervious Surface Index (Xu 2010)
    tir = _norm01(img.select("TIR"), 0, 50)                 # °C -> [0,1]
    nir = img.select("NIR").clamp(0, 1)
    swir1 = img.select("SWIR1").clamp(0, 1)
    mndwi = img.normalizedDifference(["GREEN", "SWIR1"]).add(1).divide(2)  # ->[0,1]
    x = mndwi.add(nir).add(swir1).divide(3)
    return tir.subtract(x).divide(tir.add(x)).clamp(-1, 1).rename("NDISI")


def ebbi(img):    # Enhanced Built-up & Bareness Index (As-syakur 2012), x100
    swir1, nir, tir = img.select("SWIR1"), img.select("NIR"), img.select("TIR")
    denom = swir1.add(tir).max(1e-6).sqrt().multiply(10)
    return swir1.subtract(nir).divide(denom).multiply(100).rename("EBBI")


INDEX_FN.update({"NDISI": ndisi, "EBBI": ebbi})

# Which sensor each index needs. Thermal indices require Landsat (not Sentinel-2).
SENSOR = {k: "S2" for k in ("NDVI", "NDBI", "NDWI", "NBR", "UI", "BU", "IBI")}
SENSOR.update({"NDISI": "L8", "EBBI": "L8"})
THERMAL_METHODS = ["NDISI", "EBBI"]  # Landsat-only built-up/impervious methods

METHOD_DEFAULTS.update({
    "NDISI": ("gain", 0.05, 0.12, 0.5),
    "EBBI": ("gain", 0.10, 0.25, 1.0),
})


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


def s1_relorbits(coll):
    """Distinct relative-orbit (track) numbers in a Sentinel-1 collection."""
    return coll.aggregate_array("relativeOrbitNumber_start")


def s1_latest(coll):
    """The most recent single scene in a Sentinel-1 collection."""
    return ee.Image(coll.sort("system:time_start", False).first())


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
