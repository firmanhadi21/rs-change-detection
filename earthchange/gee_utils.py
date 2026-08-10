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


# A layer with less valid data than this is not a measurement, it is an empty
# raster wearing one. Below it, read_band() says so instead of handing back
# numbers that look real.
MIN_VALID_FRAC = 0.02


def read_band(path, band=1, label=None, min_valid=MIN_VALID_FRAC, hard=False):
    """Read a downloaded band as float64, with EVERY non-finite value masked.

    Earth Engine returns a wholly-masked image as -inf (sometimes NaN) in every
    pixel. Read with masked=True and .filled(0), that is indistinguishable from
    a real zero -- and three separate bugs in this package shipped exactly that
    way: sea counted as low fire danger, a burned-area total of zero hectares,
    and a coastal reserve missing from an area sum. Each produced a confident
    wrong number rather than an error, and each was caught by an external check
    rather than by reading the code.

    Returns (array with NaN where there is no data, valid_fraction). Warns when
    the layer is effectively empty; raises instead if hard=True, for callers
    whose output would be meaningless without it.
    """
    import numpy as np
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(band, masked=True).astype("float64").filled(np.nan)
    # posinf and neginf as well as nan: the -inf case is the one that slipped
    # through, because it survives .filled() and compares quietly as "not > 0".
    arr[~np.isfinite(arr)] = np.nan
    valid = float(np.isfinite(arr).mean()) if arr.size else 0.0

    if valid < min_valid:
        what = label or os.path.basename(path)
        msg = (f"{what}: only {valid * 100:.2f}% of the raster has data "
               f"({'wholly masked' if valid == 0 else 'effectively empty'}). "
               f"Any total from it will read as a real zero.")
        if hard:
            raise SystemExit(f"  {msg}")
        print(f"  WARNING: {msg}")
    return arr, valid


ZONES_NOT_SHIPPED = (
    "This package does not ship a zone layer, and cannot: forest designation, "
    "concession and tenure boundaries are national datasets with their own "
    "licences and their own custodians. You must supply your own.\n"
    "  For Indonesia the forest designation layer (SK Penunjukan Kawasan "
    "Hutan, attribute FUNGSI_HTN) comes from KLHK; concession boundaries from "
    "the relevant ministry or from open datasets you have the right to use.\n"
    "  Any polygon layer works, in geographic (lon/lat) coordinates, grouped "
    "by whichever attribute names the responsible party.")


def missing_zones(path):
    """The error for a zone layer that is not there.

    Worth spelling out rather than just reporting a missing path: the docs
    examples name forest.gpkg, which is one user's local file and will not
    exist for anyone else.
    """
    return SystemExit(f"--zones not found: {path}\n  {ZONES_NOT_SHIPPED}")


def _fetch(url, out_path):
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return out_path


def download_png(image, region, out_path, dimensions="1920x1920", vis=None):
    """Download an RGB quick-look PNG thumbnail.

    Earth Engine's thumbnail endpoint has a per-user memory limit; large AOIs
    or heavy composites (e.g. 3-band SIRAD at 1920x1920) can 400 with
    'User memory limit exceeded'. Retry at progressively smaller dimensions.
    """
    candidates = [int(d) for d in str(dimensions).split("x")]
    sizes = [dimensions,
             f"{candidates[0]//2}x{candidates[1]//2}",
             f"{candidates[0]//4}x{candidates[1]//4}"]
    last_err = None
    for d in sizes:
        try:
            params = {"region": region, "dimensions": d, "format": "png"}
            if vis:
                params.update(vis)
            _fetch(image.getThumbURL(params), out_path)
            print(f"Saved: {os.path.normpath(out_path)}")
            return out_path
        except Exception as e:  # noqa: BLE001 — retry smaller
            last_err = e
            print(f"  thumbnail {d} failed ({e.__class__.__name__}); trying smaller…")
    raise last_err


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


def start_drive_export(image, region, description, folder="earthchange",
                       scale=10, crs="EPSG:4326"):
    """Start an async full-resolution GeoTIFF export to Google Drive.

    Returns the ee.batch.Task. The file appears in Drive/<folder>/ once the task
    finishes (monitor in the EE Code Editor 'Tasks' tab or Drive). Needs personal
    Google auth — see initialize_ee(prefer_user=True).
    """
    import re
    import ee
    desc = re.sub(r"[^A-Za-z0-9._-]", "_", description)[:100]
    task = ee.batch.Export.image.toDrive(
        image=image, description=desc, folder=folder, fileNamePrefix=desc,
        region=region, scale=scale, crs=crs, maxPixels=int(1e13),
        fileFormat="GeoTIFF")
    task.start()
    print(f"  Drive export started: '{desc}' → Drive/{folder}/ (task {task.id}); "
          "monitor in the EE Tasks tab.")
    return task


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


def initialize_ee(config_key=None, prefer_user=False):
    """Initialise Earth Engine with a service-account key if one is present.

    Looks for a key JSON in priority order:
      1. `config_key` (e.g. the CLI --ee-key, or <cwd>/scripts/config/…)
      2. $EARTHCHANGE_EE_KEY  (works from any directory — best for pip installs)
      3. ~/.config/earthengine/ee-geodetic.json  (global fallback)
    Falls back to user credentials (`earthengine authenticate`) if none exist.

    `prefer_user=True` skips service-account keys and uses personal credentials —
    required for Drive exports (a service account writes to its OWN Drive, which
    you can't browse), so `--drive` initialises this way.
    """
    import json
    import ee

    if prefer_user:
        try:
            ee.Initialize()
            print("GEE: user credentials (personal Google account)")
            return
        except Exception:  # noqa: BLE001
            raise SystemExit(
                "Drive export needs your PERSONAL Google account, but Earth Engine "
                "isn't authenticated for it.\nRun:  earthengine authenticate\n"
                "then retry with --drive. (A service-account key exports to the "
                "service account's own Drive, which you can't access.)")

    candidates = [
        p for p in (config_key,
                    os.environ.get("EARTHCHANGE_EE_KEY"),
                    os.environ.get("SATCHANGE_EE_KEY"),   # backward-compat (former name)
                    os.path.expanduser("~/.config/earthengine/ee-geodetic.json"))
        if p
    ]
    for key_path in candidates:
        if os.path.exists(key_path):
            with open(key_path) as f:
                email = json.load(f).get("client_email")
            ee.Initialize(ee.ServiceAccountCredentials(email, key_file=key_path))
            print(f"GEE: service account {email}  [{key_path}]")
            return
    try:
        ee.Initialize()  # user credentials from `earthengine authenticate`
        print("GEE: user credentials (earthengine authenticate)")
    except Exception:  # noqa: BLE001 — give an actionable message, not a stack trace
        raise SystemExit(
            "Earth Engine is not authenticated and no service-account key was found.\n"
            "Point earthchange at your key JSON in one of these ways:\n"
            "  earthchange ... --ee-key /path/to/ee-geodetic.json\n"
            "  export EARTHCHANGE_EE_KEY=/path/to/ee-geodetic.json   (any directory)\n"
            "  cp /path/to/ee-geodetic.json ~/.config/earthengine/ee-geodetic.json\n"
            "or run `earthengine authenticate` for personal user credentials.")


# --------------------------------------------------------------------------
# Archive coverage
#
# Reducing an empty ImageCollection yields an image with no bands, and every
# operation after that fails with a message about band counts or null inputs:
#
#   Image.gt: If one image has no bands, the other must also have no bands.
#   Image.select: Parameter 'input' is required and may not be null.
#
# Neither mentions dates, which is always the actual problem. The archives these
# scenarios read end on different days -- ERA5-Land about a week behind, FIRMS
# about a day, CAMS ahead because it is a forecast, MODIS burned area months
# behind -- so "the last few days" fails in a different place depending on the
# scenario. These turn that into one message that names a date that would work.
# --------------------------------------------------------------------------

REANALYSIS_HINT = (
    "Reanalysis runs several days behind real time. For the last few days use "
    "smoke-video, which reads live feeds and needs no Earth Engine.")


def collection_span(collection_id):
    """First and last timestamp a collection carries, as UTC datetimes."""
    import datetime as dt

    import ee

    ic = ee.ImageCollection(collection_id)
    span = ee.Dictionary({
        "lo": ee.Date(ic.aggregate_min("system:time_start")).format(
            "yyyy-MM-dd HH:mm"),
        "hi": ee.Date(ic.aggregate_max("system:time_start")).format(
            "yyyy-MM-dd HH:mm"),
    }).getInfo()
    fmt = "%Y-%m-%d %H:%M"
    return (dt.datetime.strptime(span["lo"], fmt).replace(tzinfo=dt.UTC),
            dt.datetime.strptime(span["hi"], fmt).replace(tzinfo=dt.UTC))


def span_message(what, need_lo, need_hi, have_lo, have_hi, hint=""):
    """A window the archive cannot cover end to end.

    Reports what WOULD fit, not only what is missing: the user's next move is to
    pick a date that works, and making them derive it from an end timestamp is
    the part that wastes their time.
    """
    lines = [f"{what} does not cover the whole window.",
             f"  needed:    {need_lo:%Y-%m-%d} to {need_hi:%Y-%m-%d}",
             f"  available: {have_lo:%Y-%m-%d} to {have_hi:%Y-%m-%d}"]
    if need_hi.date() > have_hi.date():
        lines += ["", f"End the window on {have_hi:%Y-%m-%d} or earlier."]
    if need_lo.date() < have_lo.date():
        lines += ["", f"Start the window on {have_lo:%Y-%m-%d} or later."]
    if hint:
        lines += ["", hint]
    return "\n".join(lines)


_PLACEHOLDER_NAMES = ("not available", "unknown", "unnamed", "no data", "n/a")


def is_named(name):
    """Whether an admin name can carry a ranking or a headline.

    GAUL ships placeholder names for polygons it cannot attribute -- most often
    "Administrative unit not available". Those are real land with real people,
    so they belong in the totals. They do not belong in a ranking: a district
    nobody can name is a district nobody can act on, and on a day when only two
    districts have any exposure the placeholder floats into third place and
    lands in the summary sentence.
    """
    s = (name or "").strip().lower()
    if not s or s in {"?", "-", "(unnamed)", "none"}:
        return False
    return not any(p in s for p in _PLACEHOLDER_NAMES)


def last_complete_day(collection_id, before, per_day=24, look_back=12):
    """Most recent day for which the collection holds a full set of hours."""
    import datetime as dt

    import ee

    ic = ee.ImageCollection(collection_id)
    d0 = before.date() if isinstance(before, dt.datetime) else before
    days = [d0 - dt.timedelta(days=i) for i in range(look_back)]
    counts = ee.Dictionary({
        d.isoformat(): ic.filterDate(
            ee.Date(d.isoformat()),
            ee.Date(d.isoformat()).advance(1, "day")).size()
        for d in days}).getInfo()
    for d in days:
        if counts.get(d.isoformat(), 0) >= per_day:
            return d
    return None


def require_hours(collection_id, lo, hi, what, hint=REANALYSIS_HINT):
    """Refuse a window with HOLES, not merely one that runs past the end.

    Comparing against min/max timestamps assumes the archive is contiguous, and
    a near-real-time reanalysis is not: its most recent day arrives piecemeal.
    ERA5 on 2026-08-04 held 2 of 24 hours while its max timestamp read 19:00, so
    a window ending at 00:00 that day passed every range check and then found a
    null image in the middle of the run -- surfacing as a GeoTIFF download
    failure with no mention of dates at all.
    """
    import ee

    have = (ee.ImageCollection(collection_id)
            .filterDate(lo.isoformat(), hi.isoformat()).size().getInfo())
    need = int((hi - lo).total_seconds() // 3600)
    if have >= need:
        return
    good = last_complete_day(collection_id, hi)
    lines = [f"{what} holds {have} hourly images where this run needs {need}.",
             f"  window: {lo:%Y-%m-%d %H:%M} to {hi:%Y-%m-%d %H:%M}",
             "",
             "A near-real-time reanalysis ingests its most recent day a few "
             "hours at a time, so the range looks covered while hours inside "
             "it are missing."]
    if good:
        lines += ["", f"The last complete day is {good}. End the run on or "
                      "before it."]
    lines += ["", hint]
    raise SystemExit("\n".join(lines))


def require_span(collection_id, lo, hi, what, hint=REANALYSIS_HINT):
    """Refuse a window the collection cannot cover, before any computation.

    Compared on dates rather than timestamps: a daily product is stamped at
    midnight, so a window ending later the same day is in fact covered.
    """
    have_lo, have_hi = collection_span(collection_id)
    if have_lo.date() <= lo.date() and hi.date() <= have_hi.date():
        return
    raise SystemExit(span_message(what, lo, hi, have_lo, have_hi, hint))
