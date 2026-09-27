"""Drought in paddy fields: planted late, not planted, or not watered.

Three questions, each answered by a different physics, on the fields
themselves rather than on a district average:

  1. Was it planted, and when?   The flood-then-grow cycle in Sentinel-1 VH.
     A transplanting that slips by three periods is a drought signal weeks
     before any vegetation index moves, and one that never arrives is the
     strongest signal there is.
  2. Is it getting the water it needs?   WaPOR actual ET against the crop's
     own requirement, Kc x reference ET, where Kc follows the season THIS
     field is having -- measured with the double window, not assumed.
  3. What happens over the next fortnight?   The demand side is nearly
     deterministic once the calendar is known; the supply side is a GFS
     rainfall forecast, and is treated as risk, not as a promise.

Method credit, and where each rule comes from, in the companion modules:
paddy_phenology (SC deterministic rules, double-window calendar) and
paddy_water (Paper 3 adequacy, Christiansen uniformity, reliability, FAO-33
bands, Hargreaves for the forecast leg).

Honest limits, stated here because they belong on the map too:
  * Irrigation deliveries cannot be forecast. The outlook is a rainfall-only
    water balance: it says where rain alone will not cover demand, which is
    where the canals must, not what the canals will do.
  * Tropical rainfall forecasts are useful to about 5-7 days and marginal at
    14, so the 7-day outlook leads and the 14-day is marked indicative.
  * WaPOR AETI is 300 m: one pixel covers about 30 cells of the 55.66 m grid.
    Block means are meaningful; sub-block variation is not. The grid is not the
    resolution, so every layer ships its own `native_m` (see NATIVE_M).
  * A paddy layer the user supplies always beats detection from radar -- and it
    defines the grid too, so the official extent is never resampled.
"""
import datetime as dt
import json
import os

import numpy as np

from . import paddy_data as pdata
from . import paddy_phenology as phen
from . import paddy_water as pw

# "lbs" = take the grid from the supplied paddy layer, or failing that the
# national Lahan Baku Sawah grid (0.0005 deg = 55.66 m). A number is read as
# metres, on a grid anchored at zero so tiles still mosaic.
DEFAULT_GRID = "lbs"
# A rice cycle plus its lead time. Shorter and the crop standing now may have
# been transplanted before the window opens, which reads as "not planted".
DEFAULT_SEASON_DAYS = 210
DEFAULT_SEASONS_BACK = 2
DEFAULT_OUTLOOK_DAYS = 14
LEAD_ACTIONABLE_DAYS = 7          # beyond this the rainfall forecast is thin

T = {
    "id": {
        "planted": "Sudah tanam", "not_planted": "Belum tanam",
        "delay": "Kemunduran tanam (hari)", "si": "Kecukupan air (SI)",
        "outlook": "Risiko 7 hari (hujan saja)",
        "puso": "Kandidat gagal tanam (puso)",
        "anomaly": "Dibanding musim biasanya",
        "paddy": "Sawah", "season": "Musim",
    },
    "en": {
        "planted": "Planted", "not_planted": "Not planted",
        "delay": "Planting delay (days)", "si": "Water adequacy (SI)",
        "outlook": "7-day risk (rainfall only)",
        "puso": "Crop-failure candidates (puso)",
        "anomaly": "Against this field's normal",
        "paddy": "Paddy", "season": "Season",
    },
}


# ---------------------------------------------------------------------------
# dates and windows
# ---------------------------------------------------------------------------
def season_windows(as_of, season_days=DEFAULT_SEASON_DAYS,
                   seasons_back=DEFAULT_SEASONS_BACK):
    """The current season, then the same window in each previous year.

    Previous years are the baseline a delay is measured against: the same
    fields, the same part of the calendar, the same irrigation scheme.
    """
    cur = (as_of - dt.timedelta(days=season_days), as_of)
    out = [cur]
    for k in range(1, seasons_back + 1):
        out.append((cur[0] - dt.timedelta(days=365 * k),
                    cur[1] - dt.timedelta(days=365 * k)))
    return out


def stack_span(windows, pad_periods=pdata.PAD_PERIODS,
               period_days=pdata.PERIOD_DAYS):
    """Dates the VH stack must cover: padded, and long enough for anchor 2.

    Padding matters at both ends: a dip within 5 periods of an edge cannot be
    validated at all, so an unpadded stack reports the earliest transplantings
    as "not planted" -- the very signal being looked for.
    """
    start = min(w[0] for w in windows) - dt.timedelta(
        days=pad_periods * period_days)
    end = max(w[1] for w in windows)
    return start, end


def window_periods(grid, window):
    """Indices of the periods whose midpoint falls inside `window`."""
    lo, hi = window
    out = [i for i, a, b in grid if lo <= a + (b - a) / 2 <= hi]
    return (out[0], out[-1] + 1) if out else (0, 0)


def doy_delay(current_doy, baseline_doy):
    """Days later than the baseline, the short way round the year.

    A crop planted on 5 January against a baseline of 20 December is 16 days
    late, not 349 days early.
    """
    d = np.asarray(current_doy, dtype="float32") - np.asarray(
        baseline_doy, dtype="float32")
    return np.where(np.isnan(d), np.nan, (d + 182.5) % 365.0 - 182.5)


# ---------------------------------------------------------------------------
# rasters in and out
# ---------------------------------------------------------------------------
def read_stack(path):
    """(bands, rows, cols) float32 with nodata as NaN, plus the profile."""
    import rasterio
    with rasterio.open(path) as src:
        arr = src.read(masked=True).astype("float32").filled(np.nan)
        return arr, src.profile.copy(), src.bounds


def write_raster(path, data, profile, dtype="float32", nodata=None):
    """One band out, with a nodata value the dtype can actually hold.

    The profile is inherited from the VH stack, whose nodata is -inf; carried
    onto a uint8 class raster that is not a value, it is an error.
    """
    import rasterio
    prof = profile.copy()
    prof.update(count=1, dtype=dtype, compress="lzw", tiled=True)
    if nodata is None:
        nodata = float("nan") if dtype.startswith("float") else None
    if nodata is None:
        prof.pop("nodata", None)
    else:
        prof.update(nodata=nodata)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(np.asarray(data).astype(dtype), 1)
    return path


def rasterize_layer(path, profile, field=None):
    """A vector or raster layer burned onto the analysis grid.

    Vectors are rasterised with `all_touched`, so a narrow bund or a sliver of
    a block still counts -- paddy blocks are small against a 50 m cell.
    """
    import rasterio
    from rasterio.enums import Resampling
    if str(path).lower().endswith((".tif", ".tiff")):
        # Reproject the AOI's window onto the analysis grid. Reading with
        # out_shape would resample the WHOLE file -- and a national layer like
        # Lahan Baku Sawah covers 95E to 141E, so the AOI would be filled with
        # a thumbnail of Indonesia.
        from rasterio.warp import reproject
        out = np.zeros((profile["height"], profile["width"]), dtype="float32")
        with rasterio.open(path) as src:
            reproject(source=rasterio.band(src, 1), destination=out,
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=profile["transform"],
                      dst_crs=profile["crs"], resampling=Resampling.nearest,
                      src_nodata=src.nodata, dst_nodata=0)
        return out
    import geopandas as gpd
    from rasterio.features import rasterize
    gdf = gpd.read_file(path)
    if gdf.crs and profile.get("crs") and gdf.crs != profile["crs"]:
        gdf = gdf.to_crs(profile["crs"])
    if field and field in gdf.columns:
        shapes = [(g, int(v)) for g, v in zip(gdf.geometry, gdf[field])
                  if g is not None]
    else:
        shapes = [(g, i + 1) for i, g in enumerate(gdf.geometry) if g is not None]
    return rasterize(shapes, out_shape=(profile["height"], profile["width"]),
                     transform=profile["transform"], fill=0, all_touched=True,
                     dtype="int32")


def resample_stack(path, profile, resampling="bilinear"):
    """A multi-band raster covering more than this AOI, onto the analysis grid.

    For fields shared across a whole island -- the GFS forecast, at 27 km --
    where one download serves hundreds of tiles. Bilinear, because these are
    continuous fields; it adds no information, only the common shape.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject
    how = getattr(Resampling, resampling)
    with rasterio.open(path) as src:
        out = np.full((src.count, profile["height"], profile["width"]),
                      np.nan, dtype="float32")
        for b in range(src.count):
            reproject(source=rasterio.band(src, b + 1), destination=out[b],
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=profile["transform"],
                      dst_crs=profile["crs"], resampling=how,
                      src_nodata=src.nodata, dst_nodata=float("nan"))
    return out


def pixel_area_ha(profile, lat):
    """Cell area in hectares; degrees shrink with latitude, hectares do not."""
    t = profile["transform"]
    if str(profile.get("crs", "")).upper().endswith("4326"):
        dx = abs(t.a) * 111320.0 * float(np.cos(np.radians(lat)))
        dy = abs(t.e) * 110540.0
    else:
        dx, dy = abs(t.a), abs(t.e)
    return dx * dy / 10000.0


# ---------------------------------------------------------------------------
# the paddy extent
# ---------------------------------------------------------------------------
def detect_paddy(stack, covered=None, min_amplitude_db=3.0, progress=None):
    """Pixels whose VH series behaves like rice: flood, grow, harvest.

    Screened first on dynamic range, because most of a scene is obviously not
    paddy and the per-pixel rule is the expensive part. Only used when no
    layer is supplied; an official extent is always better than this.
    """
    finite = np.isfinite(stack).all(axis=0)
    if covered is not None:
        finite &= covered
    with np.errstate(invalid="ignore"):
        spread = np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)
        floor = np.nanmin(stack, axis=0)
    candidate = finite & (spread >= min_amplitude_db + 2.0) & (floor <= -15.0)
    out = np.zeros(candidate.shape, dtype=bool)
    ys, xs = np.nonzero(candidate)
    for n, (y, x) in enumerate(zip(ys, xs)):
        if progress and n % 20000 == 0:
            progress(n, len(ys))
        out[y, x] = phen.looks_like_paddy(stack[:, y, x],
                                          min_amplitude_db=min_amplitude_db)
    return out


# ---------------------------------------------------------------------------
# the season, per pixel
# ---------------------------------------------------------------------------
def confirmable_until(grid, window_min=None):
    """Last period whose trough can still be validated, and the date it ends.

    A validated planting needs `window_min` periods of growth after it. The
    newest periods therefore cannot be confirmed at all -- not a defect, just
    the crop not having grown yet -- so they are handled provisionally.
    """
    w = window_min or phen.SC["window_min"]
    idx = max(0, len(grid) - w)
    return idx, grid[idx][1] if idx < len(grid) else grid[-1][2]


def season_calendars(stack, mask, grid, windows, confirm_last=None,
                     progress=None):
    """Planting index, season length and cycle amplitude, per season.

    The current season cannot measure its own length: the second flood has
    not happened yet. So its length is the median of the same pixel's
    baseline seasons -- the field's own variety and water habit -- and the
    package-level fallback only where there is no history either.
    """
    out = []
    for n, w in enumerate(windows):
        first, last = window_periods(grid, w)
        search_last = min(last, confirm_last) if (n == 0 and confirm_last) else last
        plant, length, amp = phen.stack_calendar(
            stack, mask, first=first, last=search_last, progress=progress)
        out.append({"window": w, "first": first, "last": last,
                    "search_last": search_last,
                    "plant": plant, "length": length, "amp": amp})
    if len(out) > 1:
        hist = np.stack([s["length"] for s in out[1:]])
        with np.errstate(invalid="ignore"):
            med = np.nanmedian(hist, axis=0)
        out[0]["length"] = np.where(np.isfinite(med), med,
                                    phen.SEASON_LENGTH_FALLBACK)
        out[0]["length_source"] = np.where(np.isfinite(med), 1, 0)
    return out


def planting_doy(plant_index, grid):
    """Transplanting as a day of the year, from the period it happened in."""
    doy = np.full(plant_index.shape, np.nan, dtype="float32")
    mid = {i: (a + (b - a) / 2) for i, a, b in grid}
    for i, when in mid.items():
        sel = plant_index == i
        if sel.any():
            doy[sel] = when.timetuple().tm_yday
    return doy


# ---------------------------------------------------------------------------
# water, now and ahead
# ---------------------------------------------------------------------------
# Paper 3's 1.2, kept after measuring rather than on the argument that WaPOR
# already carries interception. Over the Klambu paddies three independent ET
# products agree closely (wet season: WaPOR 3.32, MOD16 3.32, ERA5-Land 3.98
# mm/day; dry: 2.49, 2.16, 2.55) and all cap out at ETa/ET0 ~ 0.90 in the
# wettest months. With Kc ~1.1 that makes a fully watered paddy score 0.82 and
# "adequate" unreachable. The 1.2 puts the wet season at 0.98 -- the mean SI
# the Klambu study measured -- and the dry season at 0.63.
WAPOR_FREE_WATER = pw.SI_FREE_WATER


def adequacy_now(aeti, ret, plant_rel, length, kc_mode="curve110",
                 period_days=pdata.PERIOD_DAYS, free_water=WAPOR_FREE_WATER):
    """Season-to-date adequacy, and adequacy per period for reliability."""
    si, supply, demand = pw.season_adequacy(
        aeti, ret, plant_rel, length, period_days=period_days, mode=kc_mode,
        free_water=free_water)
    per_period = np.full(aeti.shape, np.nan, dtype="float32")
    for i in range(aeti.shape[0]):
        dos = (i - plant_rel) * period_days + period_days / 2.0
        dos = np.where(np.isnan(dos), -1.0, dos)
        k = pw._kc_per_pixel(dos, np.broadcast_to(
            length, plant_rel.shape).astype("float32"), kc_mode)
        per_period[i] = pw.adequacy(aeti[i], ret[i] * k, free_water)
    return si, per_period, supply, demand


def outlook(rain_daily, tmin_daily, tmax_daily, plant_doy, length, lat_grid,
            start_date, kc_mode="curve110", lead_days=LEAD_ACTIONABLE_DAYS):
    """Rainfall-only adequacy over the next `lead_days`.

    Demand is what the crop will need, which its own calendar already fixes.
    Supply is forecast rain alone: irrigation cannot be forecast, so this
    says where rain will not cover the crop, i.e. where the canals have to.

    Only days the run has actually published are counted, and they are counted
    on both sides: comparing seven days of demand with five days of rain would
    manufacture a deficit out of a run still being written. Returns the number
    of days used, because a 3-day outlook must not be reported as a 7-day one.
    """
    n = min(lead_days, rain_daily.shape[0])
    rain = np.zeros(plant_doy.shape, dtype="float32")
    demand = np.zeros(plant_doy.shape, dtype="float32")
    used = 0
    for d in range(n):
        if not (np.isfinite(tmin_daily[d]).any() and
                np.isfinite(tmax_daily[d]).any()):
            continue                       # this forecast day is not out yet
        when = start_date + dt.timedelta(days=d)
        doy = when.timetuple().tm_yday
        et0 = pw.et0_hargreaves(tmin_daily[d], tmax_daily[d], lat_grid, doy)
        dos = doy_delay(np.full(plant_doy.shape, float(doy)), plant_doy)
        dos = np.where(dos < 0, dos + 365.0, dos)      # days since planting
        k = pw._kc_per_pixel(np.where(np.isnan(dos), -1.0, dos),
                             np.broadcast_to(length, plant_doy.shape
                                             ).astype("float32"), kc_mode)
        demand += np.where(k > 0, et0 * k, 0.0)
        rain += np.nan_to_num(rain_daily[d], nan=0.0)
        used += 1
    if not used:
        nan = np.full(plant_doy.shape, np.nan, dtype="float32")
        return nan, nan.copy(), nan.copy(), 0
    si = pw.adequacy(rain, demand)
    return si, rain, demand, used


# ---------------------------------------------------------------------------
# the grid, and what each layer actually resolves on it
# ---------------------------------------------------------------------------
WAPOR_PIXEL_M = 300
PURE_ENOUGH = 0.6         # planted share of a WaPOR cell before it is scored


def wapor_cell_purity(planted, grid_m, cell_m=WAPOR_PIXEL_M):
    """Share of each WaPOR cell that is planted paddy, spread back to the grid.

    WaPOR AETI is 300 m: one value covers about 30 cells of the 55.66 m grid.
    Where that footprint is half fallow, the ET it reports is not the crop's, and
    adequacy computed from it says more about the neighbours than the field.
    The methodology makes the same point (section 7.1): the honest spatial
    unit is the WaPOR pixel.
    """
    k = max(1, int(round(cell_m / max(grid_m, 1))))
    rows, cols = planted.shape
    pad_r = (-rows) % k
    pad_c = (-cols) % k
    padded = np.pad(planted.astype("float32"), ((0, pad_r), (0, pad_c)),
                    constant_values=np.nan)
    blocks = padded.reshape(padded.shape[0] // k, k, padded.shape[1] // k, k)
    with np.errstate(invalid="ignore"):
        share = np.nanmean(blocks, axis=(1, 3))
    back = np.repeat(np.repeat(share, k, axis=0), k, axis=1)
    return back[:rows, :cols]


def zone_table(zones, paddy, si_now, si_period, area_ha):
    """Per-zone adequacy, equity and reliability; Christiansen across zones."""
    rows = []
    for zid in sorted(int(z) for z in np.unique(zones) if z > 0):
        sel = (zones == zid) & paddy
        n = int(sel.sum())
        if not n:
            continue
        vals = si_now[sel]
        weekly = [float(np.nanmean(si_period[i][sel]))
                  for i in range(si_period.shape[0])]
        rows.append({
            "zone": zid, "paddy_px": n, "paddy_ha": round(n * area_ha, 1),
            "si_mean": _r(np.nanmean(vals)), "si_p10": _r(pw.equity_percentile(vals)),
            "reliability": _r(pw.reliability(weekly)),
            "equity_flag": bool(pw.equity_percentile(vals) < pw.EQUITY_FLOOR),
        })
    cu = pw.christiansen_uniformity([r["si_mean"] for r in rows]) if rows else float("nan")
    return rows, cu


def _r(v, nd=3):
    v = float(v)
    return None if not np.isfinite(v) else round(v, nd)


# Every layer is written on the analysis grid, and for some of them the grid is
# finer than the information. Stated per layer, so nobody reads a 300 m water
# balance as a field-level one. The radar figure is the speckle filter's own
# radius (paddy_data.s1_vh_stack speckle_m): the dip is located on the grid, but
# its footprint is the filter's.
S1_EFFECTIVE_M = 90
GFS_PIXEL_M = 27750          # 0.25 deg, bilinearly upsampled to the grid
NATIVE_M = {
    "paddy": None,                          # the extent source's own, set at run time
    "planting_doy": S1_EFFECTIVE_M,
    "plant_period": S1_EFFECTIVE_M,
    "delay_days": S1_EFFECTIVE_M,
    "delay_class": S1_EFFECTIVE_M,
    "adequacy": WAPOR_PIXEL_M,
    "adequacy_class": WAPOR_PIXEL_M,
    "anomaly": WAPOR_PIXEL_M,
    "anomaly_class": WAPOR_PIXEL_M,
    "supply_mm": WAPOR_PIXEL_M,
    "demand_mm": WAPOR_PIXEL_M,
    "outlook_class": GFS_PIXEL_M,
    "puso": WAPOR_PIXEL_M,                  # the starved half binds it
}


def resolve_grid(spec=DEFAULT_GRID, paddy_file=None):
    """Which grid to compute on: (deg, anchor, metres, what it is aligned to).

    A supplied paddy layer wins, because the official extent is the thing that
    must not be resampled. Failing that, `spec` is "lbs" (the national Lahan
    Baku Sawah grid) or a pixel size in metres.
    """
    if paddy_file:
        got = pdata.grid_from_raster(paddy_file) if _is_raster(paddy_file) else None
        if got:
            deg, anchor = got
            return deg, anchor, pdata.grid_metres(deg), os.path.basename(paddy_file)
    if str(spec).lower() in ("lbs", "auto"):
        return (pdata.LBS_GRID_DEG, pdata.LBS_GRID_ANCHOR,
                pdata.grid_metres(pdata.LBS_GRID_DEG), "Lahan Baku Sawah grid")
    deg = float(spec) / pdata.DEG_M
    return deg, (0.0, 0.0), float(spec), f"{float(spec):.0f} m, anchored at zero"


def _is_raster(path):
    return os.path.splitext(path)[1].lower() in (".tif", ".tiff", ".vrt", ".img")


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
_QUIET = False


def _say(msg):
    if not _QUIET:
        print(msg, flush=True)


def _progress(label):
    def cb(n, total):
        if total:
            _say(f"    {label}: {n:,}/{total:,} pixels")
    return cb


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        as_of=None, season_days=DEFAULT_SEASON_DAYS,
        seasons_back=DEFAULT_SEASONS_BACK, grid_spec=DEFAULT_GRID,
        paddy_file=None, zones_file=None, zone_field=None,
        kc_mode="curve110", outlook_days=DEFAULT_OUTLOOK_DAYS,
        orbit_pass="DESCENDING", lang="id", do_map=True, publish=False,
        bbox=None, gfs_file=None, gfs_run=None, on_empty="raise"):
    """Fetch, measure and write the paddy-drought products for one AOI.

    `bbox` (lon_min, lat_min, lon_max, lat_max) replaces the square AOI, which
    is what a national tile run needs: tiles must tessellate, and a square in
    kilometres does not. `gfs_file` reuses a forecast already downloaded for a
    wider area -- GFS is a 27 km field, so fetching it per tile is thousands of
    requests for one field. `on_empty="skip"` returns None instead of exiting
    when a tile turns out to hold no scorable paddy.
    """
    if backend != "gee":
        raise SystemExit(
            "drought-paddy runs on the Earth Engine backend: the water balance "
            "needs WaPOR AETI/RET and CHIRPS, and the outlook needs GFS, none "
            "of which the Planetary Computer serves. Use --backend gee.")
    from .gee_utils import download_geotiff, initialize_ee, square_aoi

    t = T.get(lang, T["id"])
    as_of = as_of or dt.date.today()
    initialize_ee(config_key)
    if bbox:
        import ee
        aoi = ee.Geometry.Rectangle(list(bbox))
        lat = (bbox[1] + bbox[3]) / 2.0
        lon = (bbox[0] + bbox[2]) / 2.0
    else:
        aoi = square_aoi(lon, lat, radius)
    os.makedirs(run_dir, exist_ok=True)

    grid_deg, grid_anchor, grid_m, grid_source = resolve_grid(grid_spec, paddy_file)
    xform = pdata.grid_transform(grid_deg, grid_anchor)
    windows = season_windows(as_of, season_days, seasons_back)
    start, end = stack_span(windows)
    grid = pdata.period_grid(start, end)
    _say(f"Paddy drought at {lat:.4f}, {lon:.4f} (radius {radius} km), as of "
         f"{as_of}")
    _say(f"  season {windows[0][0]} -> {windows[0][1]}, {seasons_back} baseline "
         f"season(s); VH stack {start} -> {end} ({len(grid)} periods of 12 days)")
    _say(f"  grid {grid_deg:.7f} deg (~{grid_m:.2f} m), aligned to {grid_source}")

    # --- which pass actually covers this AOI -------------------------------
    # Not a constant. Measured across Java, descending leaves up to 42 of 85
    # periods empty with a run of 23 -- which discards the tile -- where
    # ascending leaves one. The reverse happens too, so it is chosen per AOI
    # and recorded. Mixing passes inside one stack is not an option: the
    # geometry moves backscatter by more than the crop does.
    orbit_gaps = None
    if str(orbit_pass).lower() in ("auto", "none", "") or orbit_pass is None:
        orbit_pass, _counts, orbit_gaps = pdata.pick_orbit(aoi, grid)
        _say(f"  orbit {orbit_pass.lower()} chosen: {orbit_gaps[0]} of "
             f"{len(grid)} periods empty, longest gap {orbit_gaps[1]}")

    # --- Sentinel-1: the flood-then-grow cycle -----------------------------
    vh_path = os.path.join(run_dir, f"paddy_vh_{name}.tif")
    if not os.path.exists(vh_path):
        _say("  fetching Sentinel-1 VH periods...")
        got = download_geotiff(pdata.s1_vh_stack(aoi, grid, orbit_pass),
                               aoi, vh_path, scale=grid_m, crs_transform=xform)
        if not got:
            raise SystemExit("could not download the VH stack; reduce --radius "
                             "or coarsen --paddy-grid")
    raw, profile, bounds = read_stack(vh_path)
    empty = int((np.isnan(raw).mean(axis=(1, 2)) == 1).sum())
    stack, covered = phen.fill_time_gaps(raw, clamp_ends=True)
    _say(f"  VH stack {raw.shape[0]} periods, {raw.shape[1]}x{raw.shape[2]} "
         f"pixels at ~{grid_m} m")
    _say(f"    {empty} periods had no {orbit_pass.lower()} acquisition; short "
         f"gaps interpolated, {int(covered.sum()):,} pixels well enough covered "
         f"to score")

    # --- where the paddy is ------------------------------------------------
    native_m = dict(NATIVE_M)
    if paddy_file:
        paddy = (rasterize_layer(paddy_file, profile) > 0) & covered
        extent_source = os.path.basename(paddy_file)
        src_grid = pdata.grid_from_raster(paddy_file) if _is_raster(paddy_file) else None
        # A vector layer is a boundary, exact at whatever grid it is drawn on;
        # a raster layer resolves no finer than its own pixel.
        native_m["paddy"] = (round(pdata.grid_metres(src_grid[0]), 2) if src_grid
                             else round(grid_m, 2))
    else:
        _say("  no --paddy-file: detecting rice from the VH cycle "
             "(an official layer would be better)")
        paddy = detect_paddy(stack, covered=covered,
                             progress=_progress("detecting paddy"))
        extent_source = "detected from Sentinel-1 phenology"
        native_m["paddy"] = S1_EFFECTIVE_M
    area_ha = pixel_area_ha(profile, lat)
    _say(f"  paddy: {int(paddy.sum()):,} pixels "
         f"({paddy.sum() * area_ha:,.0f} ha) — {extent_source}")
    if not paddy.any():
        # A tile can hold paddy on the layer and still have none the radar
        # covers. In a national run that is a tile to note and move past, not
        # a reason to stop the country.
        if on_empty == "skip":
            gap = f", longest gap {orbit_gaps[1]} periods" if orbit_gaps else ""
            _say(f"  no paddy pixels the radar covers ({empty} empty periods"
                 f"{gap}): nothing to score here")
            return {"empty": True, "reason": "radar coverage",
                    "empty_periods": empty,
                    "orbit_pass": orbit_pass,
                    "longest_gap": orbit_gaps[1] if orbit_gaps else None}
        raise SystemExit("no paddy pixels in this AOI: supply --paddy-file, or "
                         "check the location")

    # --- each field's own calendar ----------------------------------------
    _say("  measuring crop calendars (double window: planting, then season "
         "length from the next flood)...")
    confirm_idx, confirm_date = confirmable_until(grid)
    seasons = season_calendars(stack, paddy, grid, windows,
                               confirm_last=confirm_idx,
                               progress=_progress("calendars"))
    cur = seasons[0]
    confirmed = np.isfinite(cur["plant"])
    _say(f"    plantings after {confirm_date} cannot be confirmed yet (the "
         f"crop has not grown back into the beam); searching the tail for the "
         f"flood alone")
    prov_idx = phen.stack_flood(stack, paddy & ~confirmed, confirm_idx,
                                cur["last"], progress=_progress("recent floods"))
    provisional = np.isfinite(prov_idx)
    cur["plant"] = np.where(confirmed, cur["plant"], prov_idx)
    planted = confirmed | provisional
    doy_now = planting_doy(cur["plant"], grid)
    base_doy = np.nanmedian(
        np.stack([planting_doy(s["plant"], grid) for s in seasons[1:]]), axis=0
    ) if len(seasons) > 1 else np.full(doy_now.shape, np.nan, dtype="float32")
    delay = doy_delay(doy_now, base_doy)
    delay_cls = pw.delay_class(delay, planted & paddy)
    _say(f"    planted this season: {int((planted & paddy).sum()):,} of "
         f"{int(paddy.sum()):,} paddy pixels "
         f"({int((confirmed & paddy).sum()):,} confirmed, "
         f"{int((provisional & paddy).sum()):,} provisional)")

    # --- water, this season and the ones before ----------------------------
    def season_water(season, tag):
        """Adequacy for one season window, on that season's own calendar."""
        f, l = season["first"], season["last"]
        sgrid = [(i - f, a, b) for i, a, b in grid[f:l]]
        ap = os.path.join(run_dir, f"paddy_aeti_{tag}_{name}.tif")
        rp = os.path.join(run_dir, f"paddy_ret_{tag}_{name}.tif")
        if not (os.path.exists(ap) and os.path.exists(rp)):
            _say(f"  fetching WaPOR actual and reference ET ({tag})...")
            a_img, r_img = pdata.wapor_periods(aoi, sgrid)
            download_geotiff(a_img, aoi, ap, scale=grid_m, crs_transform=xform)
            download_geotiff(r_img, aoi, rp, scale=grid_m, crs_transform=xform)
        a_arr, _, _ = read_stack(ap)
        r_arr, _, _ = read_stack(rp)
        return adequacy_now(a_arr, r_arr, season["plant"] - f,
                            season["length"], kc_mode) + (a_arr, r_arr)

    first, last = cur["first"], cur["last"]
    si_now, si_period, supply, demand, aeti, ret = season_water(cur, "now")
    plant_rel = cur["plant"] - first

    # Drought is a departure from normal, and a ratio against the same
    # pixels' earlier seasons divides out the product bias that makes the
    # absolute scale unusable here (see paddy_water.ANOMALY_CLASSES).
    base_si = []
    for n, season in enumerate(seasons[1:], start=1):
        si_b, _, _, _, _, _ = season_water(season, f"base{n}")
        base_si.append(si_b)
    if base_si:
        with np.errstate(invalid="ignore"):
            si_baseline = np.nanmedian(np.stack(base_si), axis=0)
    else:
        si_baseline = np.full(si_now.shape, np.nan, dtype="float32")
    purity = wapor_cell_purity(paddy & planted, grid_m)
    pure = purity >= PURE_ENOUGH
    si_now = np.where(pure, si_now, np.nan)
    si_cls = pw.adequacy_class(si_now)
    si_cls[~(paddy & planted & pure)] = pw.ADEQUACY_NODATA

    anomaly = pw.anomaly(si_now, si_baseline)
    anomaly_cls = pw.anomaly_class(anomaly)
    anomaly_cls[~(paddy & planted & pure)] = pw.ADEQUACY_NODATA
    got = np.isfinite(anomaly)
    if got.any():
        _say(f"  against the same fields' own {len(base_si)} earlier season(s): "
             f"median {float(np.nanmedian(anomaly[got])):.2f} of normal "
             f"({int(got.sum()):,} pixels with a baseline)")
    _say(f"  water balance scored on {int((paddy & planted & pure).sum()):,} of "
         f"{int((paddy & planted).sum()):,} planted pixels — the rest share a "
         f"300 m WaPOR cell with fallow land, whose ET is not the crop's")

    # --- puso candidates ---------------------------------------------------
    puso, no_canopy, starved = pw.puso_candidates(
        paddy & planted, cur["amp"], si_now)

    # --- the fortnight ahead ----------------------------------------------
    outlook_cls = np.full(paddy.shape, pw.ADEQUACY_NODATA, dtype="uint8")
    out_si = np.full(paddy.shape, np.nan, dtype="float32")
    lead_used = 0
    if gfs_file:
        # One 27 km forecast field, downloaded once for the whole island and
        # resampled here. Fetching it per tile would be thousands of requests
        # for the same numbers.
        run_time, gfs_path = gfs_run, gfs_file
    else:
        run_time = pdata.latest_gfs_run()
        gfs_path = os.path.join(run_dir, f"paddy_gfs_{name}.tif")
    if run_time is not None and not os.path.exists(gfs_path):
        _say(f"  fetching GFS run {run_time:%Y-%m-%d %H:%M} UTC for the next "
             f"{outlook_days} days...")
        # On the analysis grid, like every other layer: GFS is a 0.25 deg field
        # bilinearly upsampled, which adds no information but keeps every array
        # the same shape as the paddy mask.
        if not download_geotiff(pdata.gfs_daily(aoi, run_time, outlook_days),
                                aoi, gfs_path, scale=grid_m,
                                crs_transform=xform):
            # The outlook is the one leg that can be missing without voiding
            # the rest: the season measured so far is already the answer to two
            # of the three questions.
            _say("  GFS download failed: reporting the season without an outlook")
            run_time = None
    if run_time is None:
        _say("  no outlook this run")
    else:
        # A shared field covers more than this tile, so it is resampled onto
        # the tile's own grid; a tile's own download already is that grid.
        gfs = (resample_stack(gfs_path, profile) if gfs_file
               else read_stack(gfs_path)[0])
        rain = gfs[0::3]
        # Earth Engine serves GFS 2 m temperature in degrees Celsius, not
        # Kelvin (checked: 24.8 over Klambu). Converting anyway would put the
        # crop at -248 C and hand back a negative water demand.
        tmin, tmax = gfs[1::3], gfs[2::3]
        if np.nanmedian(tmax) > 100:                  # a Kelvin feed, one day
            tmin, tmax = tmin - 273.15, tmax - 273.15
        rows = np.linspace(bounds.top, bounds.bottom, paddy.shape[0])
        lat_grid = np.repeat(rows[:, None], paddy.shape[1], axis=1)
        out_si, out_rain, out_demand, lead_used = outlook(
            rain, tmin, tmax, doy_now, cur["length"], lat_grid,
            run_time.date(), kc_mode, LEAD_ACTIONABLE_DAYS)
        outlook_cls = pw.adequacy_class(out_si)
        outlook_cls[~(paddy & planted)] = pw.ADEQUACY_NODATA
        if not lead_used:
            _say("    this run has not published any of the forecast days yet: "
                 "no outlook")
        else:
            short = ("" if lead_used == LEAD_ACTIONABLE_DAYS else
                     f" (only {lead_used} of {LEAD_ACTIONABLE_DAYS} days are "
                     f"published in this run)")
            # Only where the crop is still asking for water: a field past
            # harvest has demand 0, and averaging those in halves the figure
            # and makes it disagree with the map drawn beside it.
            standing = paddy & planted & (out_demand > 0)
            _say(f"    next {lead_used} days: rain "
                 f"{np.nanmean(out_rain[standing]):.0f} mm vs demand "
                 f"{np.nanmean(out_demand[standing]):.0f} mm "
                 f"(mean over {int(standing.sum()):,} pixels still in "
                 f"season){short}")

    # --- write the rasters -------------------------------------------------
    products = {
        "paddy": (paddy.astype("uint8"), "uint8", None),
        "planting_doy": (np.where(paddy, doy_now, np.nan), "float32", None),
        "delay_days": (np.where(paddy & planted, delay, np.nan), "float32", None),
        "delay_class": (np.where(paddy, delay_cls, 255), "uint8", 255),
        "adequacy": (np.where(paddy & planted, si_now, np.nan), "float32", None),
        # Kept as products, not just intermediates: an adequacy figure that
        # cannot be taken apart into the water supplied and the water the crop
        # asked for is not auditable.
        "plant_period": (np.where(paddy & planted, plant_rel, np.nan),
                         "float32", None),
        "supply_mm": (np.where(paddy & planted, supply, np.nan), "float32", None),
        "demand_mm": (np.where(paddy & planted, demand, np.nan), "float32", None),
        "adequacy_class": (si_cls, "uint8", pw.ADEQUACY_NODATA),
        "anomaly": (np.where(paddy & planted, anomaly, np.nan), "float32", None),
        "anomaly_class": (anomaly_cls, "uint8", pw.ADEQUACY_NODATA),
        "outlook_class": (outlook_cls, "uint8", pw.ADEQUACY_NODATA),
        "puso": (np.where(paddy, puso.astype("uint8"), 0), "uint8", None),
    }
    written = {}
    for key, (data, dtype, nodata) in products.items():
        path = os.path.join(run_dir, f"paddy_{key}_{name}.tif")
        write_raster(path, data, profile, dtype, nodata)
        written[key] = path
    _say(f"  wrote {len(written)} rasters")

    # --- zones, if given ---------------------------------------------------
    zones_rows, cu = [], float("nan")
    if zones_file:
        zones = rasterize_layer(zones_file, profile, zone_field)
        zones_rows, cu = zone_table(zones, paddy, si_now, si_period, area_ha)
        _say(f"  {len(zones_rows)} zones; Christiansen uniformity "
             f"{cu:.1f}% (target {pw.CU_TARGET:.0f}%)")

    # --- the numbers -------------------------------------------------------
    stats = summarise(paddy, planted, delay, delay_cls, si_cls, anomaly_cls,
                      outlook_cls, puso, no_canopy, starved, cur, area_ha, lang)
    stats.update({
        "run_id": run_id, "scenario": "drought-paddy", "as_of": str(as_of),
        "location": {"lat": lat, "lon": lon}, "radius_km": radius,
        "season": {"start": str(windows[0][0]), "end": str(windows[0][1]),
                   "baseline_seasons": seasons_back},
        "paddy_extent_source": extent_source, "kc_mode": kc_mode,
        "grid_m": round(grid_m, 3), "orbit_pass": orbit_pass,
        "radar_coverage": {"periods": len(grid), "empty_periods": empty,
                           "longest_gap": orbit_gaps[1] if orbit_gaps else None,
                           "chosen": "auto" if orbit_gaps else "fixed"},
        "grid": {"deg": grid_deg, "m": round(grid_m, 3),
                 "anchor": [round(v, 9) for v in xform[2::3]],
                 "aligned_to": grid_source, "crs": "EPSG:4326"},
        # The grid is not the resolution. Per layer, what the information
        # behind it actually resolves -- so a 300 m water balance drawn on a
        # 56 m grid is not read as a field-level measurement.
        "native_m": native_m,
        "outlook": {"lead_days": lead_used,
                    "lead_days_wanted": LEAD_ACTIONABLE_DAYS,
                    "gfs_run": run_time.isoformat() if run_time else None,
                    "basis": "rainfall only; irrigation deliveries not forecast"},
        "zones": {"n": len(zones_rows), "christiansen_uniformity_pct": _r(cu),
                  "rows": zones_rows} if zones_file else None,
        "sources": {"radar": "Sentinel-1 GRD VH " + orbit_pass,
                    "eta": pdata.WAPOR_AETI[0], "et0": pdata.WAPOR_RET[0],
                    "forecast": pdata.GFS},
    })
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    _print_summary(stats, t)

    if publish:
        from . import paddy_publish
        _say("\n  building the web bundle (COG, GeoJSON, legend, summary)...")
        web = paddy_publish.publish(run_dir, written, stats, profile, area_ha,
                                    zones_file=zones_file,
                                    zone_field=zone_field, lang=lang)
        _say(f"  web/: {len(web['cog'])} COG layers, "
             f"{os.path.basename(web['alerts'])}, legend.json, summary.json")

    return {"rasters": written, "stats": stats, "profile": profile}


def summarise(paddy, planted, delay, delay_cls, si_cls, anomaly_cls,
              outlook_cls, puso, no_canopy, starved, cur, area_ha, lang="id"):
    """Hectares per class: the form an irrigation office can act on."""
    def ha(mask):
        return round(float(np.count_nonzero(mask)) * area_ha, 1)

    def by_class(cls, table):
        out = {}
        for cid, _, _, labels, _ in table:
            out[labels[lang if lang in labels else "en"]] = ha(cls == cid)
        return out

    total = ha(paddy)
    return {
        "paddy_ha": total,
        "planted_ha": ha(paddy & planted),
        "not_planted_ha": ha(paddy & ~planted),
        "not_planted_pct": round(100.0 * ha(paddy & ~planted) / total, 1)
        if total else None,
        "planting_delay_ha": by_class(delay_cls, pw.DELAY_CLASSES),
        "median_delay_days": _r(np.nanmedian(delay[paddy & planted])
                                if (paddy & planted).any() else np.nan, 1),
        "adequacy_ha": by_class(si_cls, pw.ADEQUACY_CLASSES),
        "anomaly_ha": by_class(anomaly_cls, pw.ANOMALY_CLASSES),
        "outlook_ha": by_class(outlook_cls, pw.ADEQUACY_CLASSES),
        "puso_candidates_ha": ha(puso),
        "puso_no_canopy_ha": ha(no_canopy),
        "puso_starved_ha": ha(starved),
        "season_length_days_median": _r(np.nanmedian(cur["length"][paddy])),
    }


def _print_summary(stats, t):
    _say("\n=== " + t["paddy"] + " ===")
    _say(f"  {t['paddy']}: {stats['paddy_ha']:,.0f} ha  |  "
         f"{t['planted']}: {stats['planted_ha']:,.0f} ha  |  "
         f"{t['not_planted']}: {stats['not_planted_ha']:,.0f} ha "
         f"({stats['not_planted_pct']}%)")
    _say(f"  {t['season']}: median {stats['season_length_days_median']} days")
    for label, value in stats["adequacy_ha"].items():
        _say(f"    {t['si']:<24s} {label:<28s} {value:>10,.0f} ha")
    for label, value in stats["anomaly_ha"].items():
        _say(f"    {t['anomaly']:<24s} {label:<28s} {value:>10,.0f} ha")
    for label, value in stats["outlook_ha"].items():
        _say(f"    {t['outlook']:<24s} {label:<28s} {value:>10,.0f} ha")
    _say(f"  {t['puso']}: {stats['puso_candidates_ha']:,.0f} ha "
         f"(no canopy {stats['puso_no_canopy_ha']:,.0f}, "
         f"starved {stats['puso_starved_ha']:,.0f}) — candidates for a field "
         f"check, not a verdict")
