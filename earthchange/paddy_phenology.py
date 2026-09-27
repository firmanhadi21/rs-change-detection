"""Rice planting dates from a Sentinel-1 VH time series, per pixel.

A flooded paddy is a mirror to radar: the water reflects the pulse away and VH
collapses to about -20 dB. The canopy then grows back into the beam, so the
series dips at transplanting and peaks in the vegetative stage. Finding that
dip IS finding the planting date, and a planting date that arrives late, or
not at all, is what drought looks like in irrigated rice before any index
moves.

The rules here are the SC ("Standing Crops") deterministic algorithm used in
~/GitHub/rice-growth-stage-mapping (SC_ALGORITHM_DOCUMENTATION.md): median and
Heikin-Ashi filtering, window extrema, then validation on threshold, spacing
and min-max pairing. Its published parameters are kept, and named after the
quantity rather than transliterated.

What is deliberately NOT ported: the 1-11 growth-stage assignment. That repo
measures it at 47-78% against its own training data, well below its CNN
ensemble's 92%, and this module needs only the transplanting dip and the
following peak. Stage labels would be the least reliable part of the answer
and are better taken from that project's models.

Pure numpy: no Earth Engine, no I/O, so the rules can be tested against
synthetic series whose planting date is known.
"""
import numpy as np

# One Sentinel-1 repeat over Java; 31 periods span a year.
PERIOD_DAYS = 12

# SC defaults (SC_ALGORITHM_DOCUMENTATION.md, "Algorithm Parameters"), in
# periods. At 12 days: a cycle is >= 108 days, and transplanting to peak is
# 48-120 days, which is the agronomy of a 110-day variety.
SC = {
    "window_min": 5,          # per_eks_min
    "window_max": 5,          # per_eks_max
    "min_sigma": 0.0,         # batas_tanam: minima must fall below the mean
    "max_sigma": 0.0,         # batas_max: maxima must rise above the mean
    "cycle_periods": 9,       # per1sikluspadi
    "max_spacing": 6,         # bedawaktuemax
    "amplitude_sigma": 1.0,   # bedaspektralmaxmin
    "rise_min": 4,            # jaraktemporalmineminemax
    "rise_max": 10,           # jaraktemporalmaxeminemax
}


def median3(a, axis=-1):
    """3-point median filter along `axis`; endpoints keep their value.

    Removes the single-date spikes speckle leaves behind without moving an
    edge, which a mean filter would.
    """
    a = np.asarray(a, dtype="float32")
    out = a.copy()
    if a.shape[axis] < 3:
        return out
    a = np.moveaxis(a, axis, -1)
    out = np.moveaxis(out, axis, -1)
    out[..., 1:-1] = np.median(
        np.stack([a[..., :-2], a[..., 1:-1], a[..., 2:]], axis=-1), axis=-1)
    return np.moveaxis(out, -1, axis)


def heikin_ashi(a, axis=-1):
    """Heikin-Ashi smoothing, as SC applies it before looking for extrema.

    Borrowed from candlestick charting: each step is the midpoint of a range
    built from the two previous smoothed values, so a trend survives and a
    jitter does not. Sequential by construction -- vectorised across pixels,
    looped over time.
    """
    a = np.moveaxis(np.asarray(a, dtype="float32"), axis, -1)
    out = np.empty_like(a)
    n = a.shape[-1]
    for i in range(n):
        cl = a[..., i]
        if i == 0:
            ha2 = ha3 = cl
        elif i == 1:
            ha2, ha3 = cl, out[..., 0]
        else:
            ha2, ha3 = out[..., i - 1], out[..., i - 2]
        dha = np.abs(ha3 - ha2)
        hi2, lo2 = ha2 + dha, ha2 - dha
        op1 = (hi2 + lo2) / 2.0
        up = op1 < cl
        hi1 = np.where(up, np.maximum(np.where(hi2 < cl, cl, hi2), hi2), op1)
        lo1 = np.where(up, op1, np.minimum(np.where(lo2 > cl, cl, lo2), lo2))
        out[..., i] = (hi1 + lo1) / 2.0
    return np.moveaxis(out, -1, axis)


def fill_time_gaps(stack, max_gap=3, min_coverage=0.6, clamp_ends=False):
    """Interpolate short gaps along time; leave long ones as NaN.

    Sentinel-1 does not acquire every 12-day period over every place: at
    Klambu 15 of 80 periods were empty, and requiring every period to be
    present rejects every pixel. A gap of one to three periods sits well
    inside a rice cycle and interpolates safely; a longer one is a hole, and
    a pixel with less than `min_coverage` real observations is not scored at
    all rather than invented.

    Returns (filled stack, valid mask).
    """
    stack = np.asarray(stack, dtype="float32")
    p, rows, cols = stack.shape
    flat = stack.reshape(p, -1)
    ok = np.isfinite(flat)
    coverage = ok.mean(axis=0)
    out = flat.copy()
    idx = np.arange(p)
    for j in np.nonzero(coverage >= min_coverage)[0]:
        col = flat[:, j]
        good = ok[:, j]
        if good.all():
            continue
        # Only fill runs no longer than max_gap, and only between real
        # observations -- the ends are left to the caller's padding.
        filled = np.interp(idx, idx[good], col[good])
        gaps = _gap_lengths(good)
        take = (~good) & (gaps <= max_gap) & (idx > idx[good][0]) & (idx < idx[good][-1])
        col = col.copy()
        col[take] = filled[take]
        if clamp_ends:
            # Hold the first and last real values out to the ends. A flat tail
            # cannot invent a planting: a validated minimum has to be strictly
            # lower than its neighbours, and a constant never is.
            col[:idx[good][0]] = col[idx[good][0]]
            col[idx[good][-1] + 1:] = col[idx[good][-1]]
        out[:, j] = col
    filled_stack = out.reshape(p, rows, cols)
    valid = (np.isfinite(filled_stack).mean(axis=0) >= min_coverage)
    return filled_stack, valid


def _gap_lengths(good):
    """For each missing sample, the length of the run of misses it belongs to."""
    n = len(good)
    out = np.zeros(n, dtype=int)
    i = 0
    while i < n:
        if good[i]:
            i += 1
            continue
        j = i
        while j < n and not good[j]:
            j += 1
        out[i:j] = j - i
        i = j
    return out


def _window_minima(s, w):
    """Indices strictly lower than every value within w periods either side."""
    n = len(s)
    out = []
    for i in range(w, n - w):
        if s[i - w:i].min() <= s[i]:
            continue
        if s[i] > s[i + 1:i + w + 1].min():
            continue
        out.append(i)
    return out


def _window_maxima(s, w):
    n = len(s)
    out = []
    for i in range(w, n - w):
        if s[i - w:i].max() > s[i]:
            continue
        if s[i] <= s[i + 1:i + w + 1].max():
            continue
        out.append(i)
    return out


def _thin(idx, s, spacing, keep="low"):
    """Drop events closer than `spacing`, keeping the deeper (or higher) one."""
    kept = []
    for i in idx:
        if kept and i - kept[-1] < spacing:
            better = s[i] < s[kept[-1]] if keep == "low" else s[i] > s[kept[-1]]
            if better:
                kept[-1] = i
            continue
        kept.append(i)
    return kept


def cycles(series, params=None):
    """Planting/peak pairs in one VH series (dB), oldest first.

    Returns a list of (plant, peak) index pairs. A pair must satisfy every SC
    validation: the dip below the series mean, the rise above it, at least
    `cycle_periods` between plantings, an amplitude of `amplitude_sigma`
    standard deviations, and a rise lasting `rise_min`..`rise_max` periods --
    the last of which is what separates a rice cycle from a random dip.
    """
    p = {**SC, **(params or {})}
    s = np.asarray(series, dtype="float32")
    if s.size < 2 * p["window_min"] + 2 or not np.isfinite(s).all():
        return []
    mu, sd = float(s.mean()), float(s.std())
    if sd == 0:
        return []

    mins = [i for i in _window_minima(s, p["window_min"])
            if s[i] <= mu - p["min_sigma"] * sd]
    maxs = [i for i in _window_maxima(s, p["window_max"])
            if s[i] >= mu + p["max_sigma"] * sd]
    mins = _thin(mins, s, p["cycle_periods"], keep="low")
    maxs = _thin(maxs, s, p["max_spacing"], keep="high")

    out = []
    for lo in mins:
        after = [hi for hi in maxs
                 if p["rise_min"] <= hi - lo <= p["rise_max"]]
        if not after:
            continue
        hi = after[0]
        if s[hi] - s[lo] < p["amplitude_sigma"] * sd:
            continue
        out.append((lo, hi))
    return out


def planting(series, params=None, first=None, last=None, pick="latest",
             found=None):
    """The planting in a window: (plant, peak), or None.

    `first`/`last` bound the planting index, so a season's own transplanting
    is picked out of a multi-year series rather than the previous season's.

    `pick` decides between several inside the window:
      latest   the most recent -- the crop standing NOW, which is what a
               current-season question is about
      deepest  the deepest flood, i.e. the main season of a double-crop year

    `found` passes in an already-computed `cycles(series)`. The detection is
    the expensive part -- 95 us a pixel against 84 for everything else -- and a
    stack asks for the planting and then the calendar of the same pixel, which
    would otherwise run it twice for the same answer.
    """
    found = cycles(series, params) if found is None else found
    s = np.asarray(series, dtype="float32")
    lo = 0 if first is None else first
    hi = len(s) if last is None else last
    inside = [(a, b) for a, b in found if lo <= a < hi]
    if not inside:
        return None
    if pick == "deepest":
        return min(inside, key=lambda ab: s[ab[0]])
    return max(inside, key=lambda ab: ab[0])


def looks_like_paddy(series, params=None, min_amplitude_db=3.0):
    """Does this pixel behave like rice at all?

    Rice is a flood-then-grow cycle of a given depth and duration; a forest,
    a town or a dryland field is not. Used only when no paddy layer is
    supplied -- an official one beats this every time.
    """
    found = cycles(series, params)
    if not found:
        return False
    s = np.asarray(series, dtype="float32")
    return any(s[hi] - s[lo] >= min_amplitude_db for lo, hi in found)


# ---------------------------------------------------------------------------
# The double window: when was it planted, and how long is ITS season?
#
# Rice season length is a property of the variety and the water, not of the
# calendar: Indonesian varieties run from about 90 days to 130+, and the
# measured median at BulakBakal was 75 days from transplanting to harvest --
# nothing like the 110 days the older pipeline assumed. Assuming a length put
# harvest inside the farmers' window 0 times out of 13; measuring it with a
# second window got 12 of 13 (paper3/reference/s1_hybrid_calendar.py).
#
# So two windows are searched, not one:
#   window 1  the season's own flood trough  -> transplanting date
#   window 2  the NEXT flood trough, 85-200 days later -> harvest, at the
#             point its decline begins, less 21 days of drain and land prep
# ---------------------------------------------------------------------------
ANCHOR_SEARCH_DAYS = (85, 200)
ANCHOR_TO_HARVEST_DAYS = 21
SEASON_LENGTH_RANGE = (60, 140)
SEASON_LENGTH_FALLBACK = 86


def _savgol(series, window=5, order=2):
    """Savitzky-Golay smoothing, as the Paper 3 calendar uses before argmin.

    scipy is an optional dependency of this package; without it the series is
    returned unsmoothed rather than failing, since the SC filters have already
    removed the spikes that matter.
    """
    s = np.asarray(series, dtype="float32")
    if s.size < window:
        return s
    try:
        from scipy.signal import savgol_filter
    except ImportError:
        return s
    return savgol_filter(s, window, order).astype("float32")


def season_length(series, plant_index, period_days=PERIOD_DAYS,
                  search=ANCHOR_SEARCH_DAYS, fallback=SEASON_LENGTH_FALLBACK):
    """Days from transplanting to harvest, from the second flood trough.

    Walks back up the decline into the next season's trough: the fall begins
    when the field is drained and prepared, so harvest sits
    ANCHOR_TO_HARVEST_DAYS before it. A result outside 60-140 days is not a
    rice season and the fallback stands in (prototype_double_anchor.py).
    """
    s = np.asarray(series, dtype="float32")
    lo = int(np.ceil(search[0] / period_days))
    hi = int(np.floor(search[1] / period_days))
    window = [i for i in range(plant_index + lo, plant_index + hi + 1)
              if 0 <= i < len(s) and np.isfinite(s[i])]
    if len(window) < 3:
        return float(fallback)
    bottom = min(window, key=lambda i: s[i])
    onset = bottom
    while onset - 1 in window and s[onset - 1] > s[onset]:
        onset -= 1
    if onset == window[0]:
        return float(fallback)
    length = (onset - plant_index) * period_days - ANCHOR_TO_HARVEST_DAYS
    lo_d, hi_d = SEASON_LENGTH_RANGE
    return float(length) if lo_d <= length <= hi_d else float(fallback)


def calendar(series, params=None, first=None, last=None,
             period_days=PERIOD_DAYS, refine=True, pick="latest", found=None):
    """The pixel's own crop calendar: (plant index, season length in days).

    Planting is the validated SC trough inside the window -- validated, so a
    field that was never flooded returns None rather than the lowest point of
    a flat series. The date is then refined on a Savitzky-Golay smoothing of
    the series, matching the Paper 3 calendar, and the length comes from the
    second window. Returns None when the field did not plant.
    """
    got = planting(series, params, first, last, pick, found)
    if got is None:
        return None
    lo, _ = got
    if refine:
        s = _savgol(series)
        near = [i for i in (lo - 1, lo, lo + 1) if 0 <= i < len(s)]
        lo = min(near, key=lambda i: s[i])
    return lo, season_length(series, lo, period_days)


def flood_signature(series, first, last, drop_db=3.0, floor_db=-17.0):
    """A recent flood that cannot be confirmed yet: provisional planting.

    The SC rules validate a trough against the five periods either side, so a
    transplanting in the last ~60 days is invisible to them -- the crop has
    not grown back into the beam yet. For a product about NOW that would
    report the newest plantings as "not planted", which is precisely the
    drought signal being looked for, so the tail is searched for the flood
    alone: a dip of `drop_db` below the pixel's own median and below an
    absolute floor. Provisional, and labelled as such.
    """
    s = np.asarray(series, dtype="float32")
    lo, hi = max(0, first), min(len(s), last)
    if hi <= lo or not np.isfinite(s).any():
        return None
    med = float(np.nanmedian(s))
    window = s[lo:hi]
    cand = [i for i in range(lo, hi)
            if np.isfinite(s[i]) and s[i] <= med - drop_db and s[i] <= floor_db]
    if not cand:
        return None
    return min(cand, key=lambda i: s[i])


def stack_flood(stack, mask, first, last, progress=None):
    """`flood_signature` over a cube: the period of a recent, unconfirmed flood."""
    stack = np.asarray(stack, dtype="float32")
    _, rows, cols = stack.shape
    out = np.full((rows, cols), np.nan, dtype="float32")
    ys, xs = np.nonzero(mask)
    for n, (y, x) in enumerate(zip(ys, xs)):
        if progress and n % 20000 == 0:
            progress(n, len(ys))
        got = flood_signature(stack[:, y, x], first, last)
        if got is not None:
            out[y, x] = got
    return out


def stack_calendar(stack, mask, params=None, first=None, last=None,
                   period_days=PERIOD_DAYS, progress=None, pick="latest"):
    """`calendar` over a (period, row, col) cube where `mask` is True.

    Returns (plant_idx, length_days, amplitude_db) as (row, col) float32 with
    NaN where no season was found -- which is itself the answer to "was this
    field planted at all".
    """
    stack = np.asarray(stack, dtype="float32")
    _, rows, cols = stack.shape
    plant = np.full((rows, cols), np.nan, dtype="float32")
    length = np.full((rows, cols), np.nan, dtype="float32")
    amp = np.full((rows, cols), np.nan, dtype="float32")
    ys, xs = np.nonzero(mask)
    for n, (y, x) in enumerate(zip(ys, xs)):
        if progress and n % 20000 == 0:
            progress(n, len(ys))
        s = stack[:, y, x]
        if not np.isfinite(s).all():
            continue
        # Detect once, then read both answers off it: the detection is the
        # expensive half, and planting and calendar want the same cycles.
        found = cycles(s, params)
        if not found:
            continue
        got = planting(s, params, first, last, pick, found)
        if got is None:
            continue
        lo, hi = got
        cal = calendar(s, params, first, last, period_days, pick=pick,
                       found=found)
        plant[y, x] = cal[0]
        length[y, x] = cal[1]
        amp[y, x] = s[hi] - s[lo]
    return plant, length, amp


def stack_planting(stack, mask, params=None, first=None, last=None,
                   progress=None):
    """Run `planting` over a (period, row, col) cube where `mask` is True.

    Returns (plant_idx, peak_idx, amplitude_db), each (row, col) float32 with
    NaN where no cycle was found. Looped per pixel: the SC validation is
    sequential, and the loop only visits paddy pixels.
    """
    stack = np.asarray(stack, dtype="float32")
    _, rows, cols = stack.shape
    plant = np.full((rows, cols), np.nan, dtype="float32")
    peak = np.full((rows, cols), np.nan, dtype="float32")
    amp = np.full((rows, cols), np.nan, dtype="float32")
    ys, xs = np.nonzero(mask)
    for n, (y, x) in enumerate(zip(ys, xs)):
        if progress and n % 20000 == 0:
            progress(n, len(ys))
        s = stack[:, y, x]
        if not np.isfinite(s).all():
            continue
        got = planting(s, params, first, last)
        if got is None:
            continue
        lo, hi = got
        plant[y, x], peak[y, x] = lo, hi
        amp[y, x] = s[hi] - s[lo]
    return plant, peak, amp
