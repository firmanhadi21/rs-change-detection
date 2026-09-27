"""Earth Engine inputs for the paddy-drought scenario, on one 12-day grid.

Everything the scenario needs arrives as a multi-band GeoTIFF on the same
grid, one band per 12-day Sentinel-1 period, so the temporal reasoning can
happen locally per pixel where each field has its own planting date.

Sources, and why these:

  Sentinel-1 GRD VH, descending, 12-day periods   the flood-then-grow cycle
      Mirrors the stack built in ~/GitHub/s1-land-cover-classification
      (gee_stack_generator.py): IW, VH, one orbit direction, speckle filtered.
      One direction only -- mixing geometries changes backscatter by more than
      the crop does.

  WaPOR 3.0 L1 AETI_D (300 m, dekadal) + RET_E (~9 km, daily)
      The pair the Water Adequacy methodology prescribes, because both rest on
      the same reanalysis, so ETa/ET0 means something. NOTE the asset ids use
      underscores (FAO/WAPOR/3/L1_AETI_D), not the slashes printed in that
      document. Scale factor 0.1; checked over Klambu in July 2024, RET came
      to 4.0 mm/day and AETI 2.8, which is the right range for the Java dry
      season. AETI runs ~2 weeks behind, RET ~3 days.

  CHIRPS daily                                    rainfall actually delivered
  GFS 0.25 deg, out to 16 days                    the forecast leg
  ERA5-Land                                       root-zone soil water now

Rejected for the water balance, following that methodology: MOD16 (low over
flooded paddy) and SSEBop (tuned to rainfed). PML-V2 and WaPOR 2 are on GEE
but end in 2023, so they cannot cross-check a current season.
"""
import datetime as dt

PERIOD_DAYS = 12

S1_GRD = "COPERNICUS/S1_GRD"
WAPOR_AETI = ("FAO/WAPOR/3/L1_AETI_D", "L1-AETI-D")     # dekadal mean mm/day
WAPOR_RET = ("FAO/WAPOR/3/L1_RET_E", "L1-RET-E")        # daily mm/day
WAPOR_SCALE = 0.1
CHIRPS = "UCSB-CHG/CHIRPS/DAILY"
GFS = "NOAA/GFS0P25"
ERA5_DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"
ROOT_ZONE = "volumetric_soil_water_layer_2"             # 7-28 cm, crop roots

# A Sentinel-1 dip cannot be validated within 5 periods of either end of the
# series (paddy_phenology.SC["window_min"]), so every stack is padded.
PAD_PERIODS = 6

# --- the analysis grid ------------------------------------------------------
# Every layer is downloaded onto one grid, and which grid is not cosmetic. The
# national Lahan Baku Sawah raster sits on a 0.0005 deg step (55.66 m) whose
# LATITUDE origin, 6.0007, is not a multiple of that step. A grid anchored at
# zero therefore misses the official layer by 0.4 pixel -- about 22 m of shift
# at every field edge, invented paddy on one side and lost paddy on the other.
# Anchored on the layer's own grid instead, reading it is a windowed copy:
# checked over Klambu, 882 paddy pixels either way, arrays identical.
LBS_GRID_DEG = 0.0005
LBS_GRID_ANCHOR = (0.0, 0.0002)
# Earth Engine's metres per degree for EPSG:4326. Asking for `scale` in metres
# cannot land on the grid: 55.66 m comes back as 0.00050000228 deg, close
# enough to look right and wrong enough to resample every tile.
DEG_M = 111319.49079327358


def grid_transform(deg=LBS_GRID_DEG, anchor=LBS_GRID_ANCHOR):
    """A CRS transform for a WGS84 grid of step `deg` anchored at `anchor`.

    Only the anchor's remainder modulo the step matters -- it names which
    global grid the pixels fall on. Two AOIs sharing a transform share their
    pixel edges, which is what lets tiles mosaic without resampling.
    """
    ax, ay = (_snap(anchor[0], deg), _snap(anchor[1], deg))
    return [float(deg), 0.0, ax, 0.0, -float(deg), ay]


def _snap(value, deg, eps=1e-9):
    """`value` modulo `deg`, with float dust at either end read as zero."""
    r = float(value) % deg
    return 0.0 if (r < eps or deg - r < eps) else r


def grid_metres(deg=LBS_GRID_DEG):
    """The step in metres, for the code that reasons in metres (WaPOR purity)."""
    return float(deg) * DEG_M


def grid_from_profile(profile):
    """(deg, anchor) of a rasterio profile's grid, for re-requesting on it."""
    t = profile["transform"]
    return float(t.a), (float(t.c), float(t.f))


def grid_from_raster(path):
    """(deg, anchor) of an existing raster's grid, or None if it has no usable one.

    Used so that a supplied paddy layer defines the analysis grid: the official
    extent should never be resampled to suit us.
    """
    import rasterio
    with rasterio.open(path) as ds:
        epsg = ds.crs.to_epsg() if ds.crs else None
        if epsg != 4326:
            return None                       # projected: cannot share a grid
        t = ds.transform
        if abs(t.b) > 1e-12 or abs(t.d) > 1e-12:
            return None                       # rotated
        if abs(t.a + t.e) > 1e-12:
            return None                       # non-square pixels
        return float(t.a), (float(t.c), float(t.f))


def period_grid(start, end, days=PERIOD_DAYS):
    """12-day periods covering [start, end], as (index, start, end) triples."""
    out, i, cur = [], 0, start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=days - 1), end)
        out.append((i, cur, stop))
        cur = stop + dt.timedelta(days=1)
        i += 1
    return out


def band_name(i):
    return f"p{i:03d}"


def _to_db(img):
    import ee
    return ee.Image(img)


def s1_vh_stack(aoi, grid, orbit_pass="DESCENDING", speckle_m=90):
    """VH in dB, one band per period, speckle filtered, single orbit direction.

    The filter is a focal mean in linear power (dB is logarithmic, so
    averaging dB would bias the mean low). Periods with no acquisition come
    back masked and are left for the caller to see rather than interpolated
    away.
    """
    import ee
    base = (ee.ImageCollection(S1_GRD)
            .filterBounds(aoi)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains(
                "transmitterReceiverPolarisation", "VH"))
            .filter(ee.Filter.eq("orbitProperties_pass", orbit_pass))
            .select("VH"))

    # A period with no acquisition would otherwise reduce to a zero-band
    # image and break the composite. Merging a fully masked image keeps the
    # band present and the mean untouched: masked pixels do not contribute,
    # so such a period comes back empty, which is the truth about it.
    blank = (ee.Image.constant(0).updateMask(ee.Image.constant(0))
             .rename("VH").toFloat())

    def one(period):
        i, a, b = period
        ic = base.filterDate(a.isoformat(),
                             (b + dt.timedelta(days=1)).isoformat())
        # dB -> linear power is 10^(dB/10); averaging dB itself would bias the
        # mean low, because dB is logarithmic.
        linear = ic.map(lambda im: ee.Image(10).pow(ee.Image(im).divide(10))
                        .rename("VH").toFloat())      # same name and type as
                                                      # the blank, or mean() trips
        linear = linear.merge(ee.ImageCollection([blank]))
        smooth = linear.mean().focal_mean(speckle_m, "circle", "meters")
        return smooth.log10().multiply(10).rename(band_name(i)).toFloat()

    return ee.Image.cat([one(p) for p in grid]).clip(aoi)


def s1_period_counts(aoi, grid, orbit_pass="DESCENDING"):
    """Scenes per period: a stack is only as honest as its thinnest period."""
    import ee
    base = (ee.ImageCollection(S1_GRD).filterBounds(aoi)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains(
                "transmitterReceiverPolarisation", "VH"))
            .filter(ee.Filter.eq("orbitProperties_pass", orbit_pass)))
    return [int(base.filterDate(a.isoformat(),
                                (b + dt.timedelta(days=1)).isoformat())
                .size().getInfo()) for _, a, b in grid]


def s1_acquisitions(aoi, grid, orbit_pass="DESCENDING"):
    """Scenes per period, in ONE request.

    s1_period_counts asks once per period, which is 85 round trips for a single
    stack -- fine for one AOI, hopeless for a thousand tiles. This asks for the
    acquisition times once and buckets them here.
    """
    import ee
    start, end = grid[0][1], grid[-1][2]
    ic = (ee.ImageCollection(S1_GRD).filterBounds(aoi)
          .filterDate(start.isoformat(),
                      (end + dt.timedelta(days=1)).isoformat())
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains(
              "transmitterReceiverPolarisation", "VH"))
          .filter(ee.Filter.eq("orbitProperties_pass", orbit_pass)))
    millis = ic.aggregate_array("system:time_start").getInfo() or []
    times = sorted(dt.datetime.fromtimestamp(m / 1000, dt.UTC).date()
                   for m in millis)
    counts = []
    for _, a, b in grid:
        counts.append(sum(1 for t in times if a <= t <= b))
    return counts


def gaps(counts):
    """(periods with nothing, longest run of them) -- how holed a stack is."""
    longest = cur = 0
    for c in counts:
        cur = cur + 1 if not c else 0
        longest = max(longest, cur)
    return sum(1 for c in counts if not c), longest


def pick_orbit(aoi, grid, passes=("DESCENDING", "ASCENDING")):
    """The pass with the least holed 12-day series over this AOI.

    The orbit cannot be a constant for a national run. One direction covers a
    given footprint on its own repeat cycle, so a tile that is well served
    descending can be badly served ascending and the reverse -- measured over
    East Java, descending left 42 of 85 periods empty with a run of 23, which
    discards the tile, while the other pass covers it. Mixing passes WITHIN a
    stack is not allowed (the geometry changes the backscatter by more than the
    crop does), so the choice is per tile, and recorded with the tile.

    Returns (orbit_pass, counts, (empty, longest)).
    """
    best = None
    for p in passes:
        counts = s1_acquisitions(aoi, grid, p)
        empty, longest = gaps(counts)
        # A long hole is what kills a season; total holes break the tie.
        score = (longest, empty)
        if best is None or score < best[0]:
            best = (score, p, counts, (empty, longest))
    return best[1], best[2], best[3]


def _dekad_bounds(day):
    """WaPOR dekads: 1-10, 11-20, 21-end of month."""
    if day.day <= 10:
        return day.replace(day=1), day.replace(day=10)
    if day.day <= 20:
        return day.replace(day=11), day.replace(day=20)
    nxt = (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return day.replace(day=21), nxt - dt.timedelta(days=1)


def _dekads_overlapping(a, b):
    """(dekad start, dekad end, days overlapping [a, b]) for each dekad."""
    out, cur = [], a
    while cur <= b:
        ds, de = _dekad_bounds(cur)
        lo, hi = max(ds, a), min(de, b)
        out.append((ds, de, (hi - lo).days + 1))
        cur = de + dt.timedelta(days=1)
    return out


def wapor_periods(aoi, grid):
    """(AETI, RET) in mm per period, both on the S1 period grid.

    AETI is a dekadal mean in mm/day, and a 12-day period usually straddles
    two dekads, so it is weighted by the days of overlap -- the weighting the
    WAI methodology sets out in section 7.2. RET is daily and simply summed.
    """
    import ee
    aeti_id, aeti_band = WAPOR_AETI
    ret_id, ret_band = WAPOR_RET

    def blank(name):
        # AETI runs about two weeks behind, so the newest periods have no
        # dekad at all. A masked stand-in keeps the band present; the period
        # then reads as missing rather than as zero evapotranspiration, which
        # would look like a total crop failure.
        return (ee.Image.constant(0).updateMask(ee.Image.constant(0))
                .rename(name).toFloat())

    def aeti_one(period):
        i, a, b = period
        total = ee.Image.constant(0).toFloat()
        seen = ee.Image.constant(0).toFloat()
        for ds, de, days in _dekads_overlapping(a, b):
            ic = (ee.ImageCollection(aeti_id)
                  .filterDate(ds.isoformat(),
                              (de + dt.timedelta(days=1)).isoformat())
                  .select(aeti_band).map(lambda im: ee.Image(im).toFloat()))
            img = ic.merge(ee.ImageCollection([blank(aeti_band)])).mean()
            img = img.multiply(WAPOR_SCALE)
            total = total.add(img.unmask(0).multiply(days))    # mm/day -> mm
            seen = seen.add(img.mask().multiply(days))
        # Mask the period if no dekad contributed: absent is not zero.
        return total.updateMask(seen.gt(0)).rename(band_name(i)).toFloat()

    def ret_one(period):
        i, a, b = period
        ic = (ee.ImageCollection(ret_id)
              .filterDate(a.isoformat(), (b + dt.timedelta(days=1)).isoformat())
              .select(ret_band).map(lambda im: ee.Image(im).toFloat()))
        img = ic.merge(ee.ImageCollection([blank(ret_band)])).sum()
        return img.multiply(WAPOR_SCALE).rename(band_name(i)).toFloat()

    aeti = ee.Image.cat([aeti_one(p) for p in grid]).resample("bilinear")
    ret = ee.Image.cat([ret_one(p) for p in grid]).resample("bilinear")
    return aeti.clip(aoi), ret.clip(aoi)


S2_SR = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD_PROB = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S2_CLEAR_MIN = 0.60          # cs+ "cs" band: 1 is clear, 0 is opaque


def ndwi_max_doy(aoi, start, end, clear_min=S2_CLEAR_MIN):
    """When each pixel was wettest: (ndwi, doy, n_obs) from Sentinel-2.

    The optical half of the hybrid calendar. Paper 3's `optical_calendar` takes
    the planting date from the date of MAXIMUM NDWI -- the same physical event
    the radar trough sees, standing water in a puddled field, measured by a
    different sensor. It is twice as accurate on the date: at BulakBakal the
    optical planting date was 6 days off the farmers' own records at the median
    against 12 for the SAR trough, and inside 12 days for 90% of parcels
    against 55%.

    One image out, not a series: `qualityMosaic` picks, per pixel, the scene
    with the highest NDWI and carries that scene's day-of-year with it. So the
    whole optical leg costs one small download per season, not another stack.

    `n_obs` counts the clear observations behind the answer, because a maximum
    over two cloudy glimpses of a wet season is not a planting date. Cloud
    Score+ is the mask: it is trained for exactly this, and over the tropics it
    beats the QA60 bitmask it replaces.
    """
    import ee
    s2 = (ee.ImageCollection(S2_SR)
          .filterBounds(aoi)
          .filterDate(start.isoformat(), (end + dt.timedelta(days=1)).isoformat())
          .linkCollection(ee.ImageCollection(S2_CLOUD_PROB), ["cs"]))

    def prep(img):
        img = ee.Image(img)
        clear = img.select("cs").gte(clear_min)
        # Green and NIR: NDWI = (G - NIR) / (G + NIR), McFeeters 1996. Water is
        # positive, vegetation and soil negative.
        ndwi = img.normalizedDifference(["B3", "B8"]).rename("ndwi")
        doy = ee.Image.constant(
            ee.Date(img.get("system:time_start")).getRelative("day", "year")
        ).add(1).rename("doy").toFloat()
        return (ndwi.addBands(doy).updateMask(clear)
                .copyProperties(img, ["system:time_start"]))

    prepped = s2.map(prep)
    n_obs = prepped.select("ndwi").count().rename("n_obs").toFloat()
    # An empty collection would reduce to a band-less image; a masked blank
    # keeps the bands present and the answer honestly empty.
    blank = (ee.Image.constant([0, 0]).rename(["ndwi", "doy"])
             .updateMask(ee.Image.constant(0)).toFloat())
    best = prepped.map(lambda i: ee.Image(i).toFloat()).merge(
        ee.ImageCollection([blank])).qualityMosaic("ndwi")
    return (best.select(["ndwi", "doy"])
            .addBands(n_obs.unmask(0))
            .clip(aoi).toFloat())


def chirps_periods(aoi, grid):
    """Rainfall in mm per period."""
    import ee

    def one(period):
        i, a, b = period
        return (ee.ImageCollection(CHIRPS)
                .filterDate(a.isoformat(), (b + dt.timedelta(days=1)).isoformat())
                .select("precipitation").sum().rename(band_name(i)))

    return ee.Image.cat([one(p) for p in grid]).resample("bilinear").clip(aoi)


def latest_gfs_run(before=None):
    """Creation time of the newest GFS run, as a date-time."""
    import ee
    end = (before or dt.datetime.now(dt.UTC)) + dt.timedelta(days=1)
    ic = (ee.ImageCollection(GFS)
          .filterDate((end - dt.timedelta(days=3)).strftime("%Y-%m-%d"),
                      end.strftime("%Y-%m-%d")))
    millis = ic.aggregate_max("creation_time").getInfo()
    if millis is None:
        return None
    return dt.datetime.fromtimestamp(millis / 1000, dt.UTC)


def gfs_daily(aoi, run_time, days):
    """Per-day rain (mm), Tmin and Tmax (degC) for the next `days` days.

    One GFS run only, so the forecast is internally consistent. Rain comes
    from total_precipitation_surface, which is an accumulation within each
    3-hourly step, and temperature from the 2 m field.

    A run is published forecast hour by forecast hour, so asking for 14 days
    shortly after it starts leaves the last days with no steps at all. As in
    s1_vh_stack, a fully masked image is merged in so the band still exists and
    comes back empty: a day the run has not reached yet is missing, not dry.
    """
    import ee
    ic = (ee.ImageCollection(GFS)
          .filter(ee.Filter.eq("creation_time",
                               int(run_time.timestamp() * 1000))))

    def blank(name):
        return (ee.Image.constant(0).updateMask(ee.Image.constant(0))
                .rename(name).toFloat())

    def band(day, name):
        return (day.select(name).map(lambda im: ee.Image(im).toFloat())
                .merge(ee.ImageCollection([blank(name)])))

    out = []
    for d in range(days):
        a = run_time + dt.timedelta(days=d)
        b = a + dt.timedelta(days=1)
        day = ic.filter(ee.Filter.rangeContains(
            "forecast_time", int(a.timestamp() * 1000), int(b.timestamp() * 1000)))
        # precipitation_rate (kg/m2/s = mm/s) is defined at every step,
        # including hour 0, where the accumulated field does not exist.
        rain = (band(day, "precipitation_rate").mean().multiply(86400)
                .rename(f"rain{d:02d}").toFloat())
        t = band(day, "temperature_2m_above_ground")
        out += [rain, t.min().rename(f"tmin{d:02d}").toFloat(),
                t.max().rename(f"tmax{d:02d}").toFloat()]
    return ee.Image.cat(out).resample("bilinear").clip(aoi)


def soil_water_now(aoi, as_of, window_days=10):
    """Root-zone soil water (m3/m3) averaged over the last `window_days`.

    The state the forecast starts from. ERA5-Land runs about a week behind,
    which is why this is a recent mean rather than a single day.
    """
    import ee
    a = as_of - dt.timedelta(days=window_days)
    return (ee.ImageCollection(ERA5_DAILY)
            .filterDate(a.isoformat(), as_of.isoformat())
            .select(ROOT_ZONE).mean().resample("bilinear")
            .rename("soil_water").clip(aoi))
