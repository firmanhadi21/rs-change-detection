"""Did the paddy get the water it needed? Adequacy, uniformity, reliability.

Definitions follow the Paper 3 reference implementation in
~/GitHub/s1-land-cover-classification (paper3/reference/
irrigation_performance_dynamic.py, Sept 2026) and the Water Adequacy Index
methodology (2026/laporan/WATER_ADEQUACY_INDEX_METHODOLOGY.md). Three results
from that work decide the shape of this module:

  * The season is measured, not assumed. Against farmer truth at BulakBakal
    (29 units, 13 with harvest windows) a fixed 110-day season put harvest
    inside the window 0/13 times; a SAR-measured season length -- median 75
    days, not 110 -- got 12/13. So `season_length` comes from the second
    flood anchor, and Kc is stretched onto it.
  * The planting date is best taken from optical (median error 6 days, 90%
    within 12) and the season length from SAR: the "hybrid" calendar. SAR
    alone dates planting to 12 days, which is simply its repeat interval.
  * Area-based "is it active" cannot see deficit irrigation: a paddy under
    70% of its requirement still looks like paddy to radar. Hence the water
    balance below rather than an area count.

Adequacy is ETa against the crop water requirement Kc x ET0. Everything here
is pure numpy over daily or per-period arrays: no Earth Engine, no I/O.
"""
import numpy as np

# The operational 110-day curve (results_csv/cwr.csv in that repo): flat
# through transplanting shock, up to a mid-season peak, down as the field is
# drained for harvest. Held as breakpoints; `kc_curve110` interpolates.
KC110_DAYS = (1.0, 10.0, 40.0, 80.0, 110.0)
KC110_VALUES = (1.05, 1.05, 1.15, 1.20, 0.95)

# Stage-resolved FAO-56 steps on the S1 stage clock (Paper 1 §4.4, as coded in
# irrigation_performance_dynamic.kc_value). Boundaries scale with the season:
# reproductive starts at max(55, L-30), ripening runs to L.
STAGE_FLOOD_END = 18.0
STAGE_VEG_END = 54.0
STAGE_KC = {"flood": 1.05, "veg_end": 1.20, "repro": 1.20, "ripen_end": 0.90}

SI_CAP = 1.0                  # SI = min(1.2 * ETa / CWR, 1)
SI_FREE_WATER = 1.2           # flooded paddy evaporates beyond Kc x ET0
RELIABILITY_THRESHOLD = 0.80  # weekly SI counted as "supplied" (Paper 3)
CU_TARGET = 85.0              # Christiansen target, per cent
RI_TARGET = 0.75

# Adequacy classes, FAO-33 (Doorenbos & Kassam 1979) yield-response bands for
# paddy, as tabulated in the WAI methodology §3.1. Conventions to be
# calibrated against local yield data -- the map must say so.
ADEQUACY_CLASSES = [
    (0, 1.00, 9.99, {"id": "Cukup", "en": "Adequate"}, "#2c7bb6"),
    (1, 0.85, 1.00, {"id": "Defisit ringan", "en": "Mild deficit"}, "#abd9e9"),
    (2, 0.65, 0.85, {"id": "Defisit sedang", "en": "Moderate deficit"}, "#fdae61"),
    (3, -0.01, 0.65, {"id": "Defisit berat", "en": "Severe deficit"}, "#d7191c"),
]
ADEQUACY_NODATA = 255
EQUITY_FLOOR = 0.65           # 10th-percentile adequacy below this = tail-end stress

# Drought is a departure from normal, and measuring it that way removes a
# problem the absolute bands cannot survive. Over Klambu paddy, WaPOR AETI
# runs about 35% below Kc x reference ET even in a wet season with 13 mm/day
# of rain and the fields plainly supplied (measured by stage: 0.64 initial,
# 0.66 vegetative, 0.77 reproductive). Three ET products agree with each
# other, so this is what satellite ETa does over flooded rice, not a bug --
# and it makes "adequate" unreachable on the FAO-33 scale, which that
# methodology already flags as uncalibrated.
#
# A ratio against the SAME pixel's own earlier seasons cancels that bias:
# whatever the product reads for a healthy crop here, this season is measured
# against it.
ANOMALY_CLASSES = [
    (0, 0.95, 9.99, {"id": "Normal", "en": "Normal"}, "#2c7bb6"),
    (1, 0.85, 0.95, {"id": "Agak kering", "en": "Slightly drier"}, "#abd9e9"),
    (2, 0.70, 0.85, {"id": "Lebih kering", "en": "Drier than normal"}, "#fdae61"),
    (3, -0.01, 0.70, {"id": "Jauh lebih kering",
                      "en": "Much drier than normal"}, "#d7191c"),
]

# Planting lateness against the same fields' own baseline seasons. One S1
# period (12 days) of slip is scheduling; three is a season in trouble.
DELAY_CLASSES = [
    (0, -1e9, 12, {"id": "Tepat waktu", "en": "On time"}, "#1a9850"),
    (1, 12, 24, {"id": "Mundur 12-24 hari", "en": "12-24 days late"}, "#fee08b"),
    (2, 24, 36, {"id": "Mundur 24-36 hari", "en": "24-36 days late"}, "#fc8d59"),
    (3, 36, 1e9, {"id": "Mundur >36 hari", "en": "More than 36 days late"}, "#b2182b"),
    (4, None, None, {"id": "Belum tanam", "en": "Not planted"}, "#6a3d9a"),
]
NOT_PLANTED = 4

PUSO_MIN_GAIN_DB = 3.0        # a canopy that never closed


def kc_curve110(day_of_season, length):
    """The 110-day curve stretched onto a season of `length` days.

    Rescaling rather than truncating is what the reference does: a 75-day
    season passes through the same shape faster, so a short-duration variety
    is not charged for a mid-season it never had.
    """
    d = np.asarray(day_of_season, dtype="float32")
    length = float(np.maximum(length, 1))
    kc = np.interp(d * 110.0 / length, KC110_DAYS, KC110_VALUES)
    return np.where((d >= 1) & (d <= length), kc, 0.0).astype("float32")


def kc_stage(day_of_season, length):
    """Stage-resolved Kc on the S1 stage clock (flood, veg, repro, ripen)."""
    d = np.asarray(day_of_season, dtype="float32")
    length = float(length)
    repro_end = max(55.0, length - 30.0)
    kc = np.zeros_like(d)
    kc = np.where(d < STAGE_FLOOD_END, STAGE_KC["flood"], kc)
    veg = (d >= STAGE_FLOOD_END) & (d < STAGE_VEG_END)
    kc = np.where(veg, STAGE_KC["flood"] + (d - STAGE_FLOOD_END) /
                  (STAGE_VEG_END - STAGE_FLOOD_END) *
                  (STAGE_KC["veg_end"] - STAGE_KC["flood"]), kc)
    kc = np.where((d >= STAGE_VEG_END) & (d < repro_end), STAGE_KC["repro"], kc)
    ripen = (d >= repro_end) & (d < length)
    kc = np.where(ripen, STAGE_KC["repro"] - (d - repro_end) /
                  max(length - repro_end, 1.0) *
                  (STAGE_KC["repro"] - STAGE_KC["ripen_end"]), kc)
    return np.where((d >= 1) & (d < length), kc, 0.0).astype("float32")


def kc(day_of_season, length, mode="curve110"):
    if mode == "stage":
        return kc_stage(day_of_season, length)
    if mode == "curve110":
        return kc_curve110(day_of_season, length)
    raise ValueError(f"unknown Kc mode: {mode!r} (curve110 | stage)")


def extraterrestrial_radiation(lat_deg, doy):
    """Ra at the top of the atmosphere, as equivalent evaporation (mm/day).

    FAO-56 eq. 21-25. Needed because a forecast carries temperature but not
    radiation, and Ra depends only on latitude and the day of the year.
    """
    lat = np.radians(np.asarray(lat_deg, dtype="float64"))
    j = np.asarray(doy, dtype="float64")
    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * j)            # earth-sun distance
    dec = 0.409 * np.sin(2 * np.pi / 365 * j - 1.39)        # solar declination
    x = np.clip(-np.tan(lat) * np.tan(dec), -1.0, 1.0)
    ws = np.arccos(x)                                       # sunset hour angle
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.sin(ws))
    return (ra * 0.408).astype("float32")                   # MJ/m2/day -> mm/day


def et0_hargreaves(tmin_c, tmax_c, lat_deg, doy):
    """Reference ET from temperature alone (FAO-56 eq. 52).

    Used only for the FORECAST leg: a weather forecast carries temperature
    reliably and radiation poorly. Hargreaves runs about 10-15% either side of
    the full Penman-Monteith in humid tropics, which is smaller than the
    rainfall-forecast error it is paired with -- but it is why the outlook is
    reported as risk rather than as millimetres of certainty.
    """
    tmin = np.asarray(tmin_c, dtype="float32")
    tmax = np.asarray(tmax_c, dtype="float32")
    tmean = (tmin + tmax) / 2.0
    ra = extraterrestrial_radiation(lat_deg, doy)
    spread = np.clip(tmax - tmin, 0.0, None)
    return (0.0023 * (tmean + 17.8) * np.sqrt(spread) * ra).astype("float32")


def adequacy(eta, cwr, free_water=SI_FREE_WATER):
    """SI = min(free_water * ETa / CWR, 1); NaN where nothing was required.

    `free_water` is 1.2 in the Paper 3 implementation, standing in for the
    evaporation from the standing water of a paddy that its ETa product does
    not carry. With WaPOR AETI it should be 1.0: that product already
    includes interception and open-water evaporation -- which is why the WAI
    methodology writes the index as plain ETa/ETc -- and applying 1.2 on top
    would credit the same water twice.

    A field with no standing crop has no adequacy to report. Returning 1.0
    there would paint fallow land as well watered, the failure this index
    exists to avoid.
    """
    eta = np.asarray(eta, dtype="float32")
    cwr = np.asarray(cwr, dtype="float32")
    with np.errstate(divide="ignore", invalid="ignore"):
        si = free_water * eta / cwr
    return np.where(cwr > 0, np.minimum(si, SI_CAP), np.nan).astype("float32")


def season_adequacy(eta_periods, et0_periods, plant_period, length_days,
                    period_days=12, upto=None, mode="curve110",
                    free_water=SI_FREE_WATER):
    """Season-to-date adequacy per pixel, each on its own planting date.

    `eta_periods` / `et0_periods` are (period, row, col) cubes in mm per
    period; `plant_period` is the transplanting period index per pixel, NaN
    where the field never flooded; `length_days` is that pixel's season. Only
    the periods when the crop was standing are summed, so a late-transplanted
    field is judged on its own shorter season.
    """
    eta = np.asarray(eta_periods, dtype="float32")
    et0 = np.asarray(et0_periods, dtype="float32")
    plant = np.asarray(plant_period, dtype="float32")
    length = np.asarray(length_days, dtype="float32")
    n = eta.shape[0] if upto is None else min(upto, eta.shape[0])
    supply = np.zeros(plant.shape, dtype="float32")
    demand = np.zeros(plant.shape, dtype="float32")
    length = np.broadcast_to(length, plant.shape).astype("float32")
    scored = np.zeros(plant.shape, dtype="int32")
    for i in range(n):
        dos = (i - plant) * period_days + period_days / 2.0   # mid-period day
        dos = np.where(np.isnan(dos), -1.0, dos)
        k = _kc_per_pixel(dos, length, mode)                  # each its own L
        # Count a period only where BOTH sides were observed. Actual ET lags
        # its reference by about two weeks, so charging demand for a period
        # whose supply has not been published yet reads as a deficit that
        # nobody has measured.
        both = (k > 0) & np.isfinite(eta[i]) & np.isfinite(et0[i])
        demand += np.where(both, et0[i] * k, 0.0)
        supply += np.where(both, eta[i], 0.0)
        scored += both.astype("int32")
    si = adequacy(supply, demand, free_water)
    si = np.where(scored > 0, si, np.nan)          # nothing paired, nothing said
    return np.where(np.isnan(plant), np.nan, si), supply, demand


def _kc_per_pixel(dos, length, mode):
    """Kc where every pixel has its own season length.

    Grouped by length so the curve is evaluated once per distinct season
    rather than once per pixel; lengths come from a 12-day clock, so there
    are only a handful of them.
    """
    out = np.zeros_like(dos, dtype="float32")
    finite = np.isfinite(length)
    for L in np.unique(length[finite]):
        sel = finite & (length == L)
        out[sel] = kc(dos[sel], float(L), mode)
    return out


def classify(value, table, nodata=ADEQUACY_NODATA):
    v = np.asarray(value, dtype="float32")
    out = np.full(v.shape, nodata, dtype="uint8")
    for cid, lo, hi, _, _ in table:
        if lo is None:
            continue
        out = np.where((v > lo) & (v <= hi) & np.isfinite(v), cid, out)
    return out


def adequacy_class(si):
    return classify(si, ADEQUACY_CLASSES)


def anomaly(si_now, si_baseline):
    """This season's adequacy against the same pixels' own earlier seasons.

    1.0 means as well supplied as usual; 0.7 means the crop is getting about
    seven tenths of what these fields normally get at this point. Product
    bias divides out, which the absolute index cannot do.
    """
    now = np.asarray(si_now, dtype="float32")
    base = np.asarray(si_baseline, dtype="float32")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = now / base
    return np.where((base > 0) & np.isfinite(now), out, np.nan).astype("float32")


def anomaly_class(ratio):
    return classify(ratio, ANOMALY_CLASSES)


def christiansen_uniformity(values):
    """CU = 100 * (1 - mean|x - xbar| / xbar), across units within a period.

    Christiansen's coefficient, as the reference computes it weekly. It asks
    whether the water was shared evenly, which a mean adequacy cannot: two
    schemes with the same mean can be uniform or half-starved.
    """
    v = np.asarray(values, dtype="float32")
    v = v[np.isfinite(v)]
    if v.size == 0 or v.mean() <= 0:
        return float("nan")
    return float(100.0 * (1.0 - np.abs(v - v.mean()).mean() / v.mean()))


def reliability(si_by_period, threshold=RELIABILITY_THRESHOLD):
    """Fraction of periods a unit was supplied at or above `threshold`."""
    v = np.asarray(si_by_period, dtype="float32")
    ok = np.isfinite(v)
    if not ok.any():
        return float("nan")
    return float((v[ok] >= threshold).mean())


def equity_percentile(si_values, q=10.0):
    """The 10th percentile of adequacy: how the worst-served pixels fared.

    Head-tail inequity is invisible in a block mean, and it is the tail that
    the performance contract is supposed to protect.
    """
    v = np.asarray(si_values, dtype="float32")
    v = v[np.isfinite(v)]
    return float(np.percentile(v, q)) if v.size else float("nan")


def delay_days(plant_period, baseline_plant_period, period_days=12):
    """Days later than the same pixel's baseline transplanting; NaN if unknown."""
    p = np.asarray(plant_period, dtype="float32")
    b = np.asarray(baseline_plant_period, dtype="float32")
    return (p - b) * period_days


def delay_class(days, planted):
    out = classify(days, DELAY_CLASSES)
    return np.where(planted, out, NOT_PLANTED).astype("uint8")


def puso_candidates(planted, peak_gain_db, si_reproductive,
                    min_gain_db=PUSO_MIN_GAIN_DB, si_floor=0.65):
    """Transplanted but unlikely to yield: fields to visit, not a verdict.

    Two independent failures after transplanting -- the canopy never built
    (radar never rose) or the water ran out while the grain was forming
    (adequacy in the severe FAO-33 band). Neither is proof of crop failure;
    calling it puso from orbit is exactly the overreach this package refuses.
    """
    planted = np.asarray(planted, dtype=bool)
    gain = np.asarray(peak_gain_db, dtype="float32")
    si = np.asarray(si_reproductive, dtype="float32")
    no_canopy = planted & np.isfinite(gain) & (gain < min_gain_db)
    starved = planted & np.isfinite(si) & (si < si_floor)
    return no_canopy | starved, no_canopy, starved
