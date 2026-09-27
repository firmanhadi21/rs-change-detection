"""The transplanting dip must be found where it was put, and nowhere else.

Synthetic VH series: a paddy is a dip to about -21 dB (water mirrors the
pulse away), a rise over ~6 periods to a vegetative peak, then harvest. Forest
and town are flat and bright. If these rules cannot tell those apart on clean
synthetic data they cannot be trusted on a real scene.
"""
import numpy as np
import pytest

from earthchange.paddy_phenology import (cycles, heikin_ashi, looks_like_paddy,
                                         median3, planting, stack_planting)

N = 31                       # one year of 12-day periods


def rice(plant=8, floor=-21.0, base=-14.0, peak=-11.0, rise=6, cycle=11,
         n=N, noise=0.0, seed=0):
    """A flood-then-grow series with the transplanting dip at `plant`."""
    s = np.full(n, base, dtype="float32")
    for start in range(plant, n, cycle):
        s[start] = floor
        for k in range(1, rise + 1):
            if start + k < n:
                s[start + k] = floor + (peak - floor) * k / rise
        for k in range(1, 3):                       # harvest, back to bare
            if start + rise + k < n:
                s[start + rise + k] = peak - (peak - base) * k / 2
    if noise:
        s = s + np.random.default_rng(seed).normal(0, noise, n).astype("float32")
    return s


def test_planting_is_found_at_the_dip():
    assert planting(rice(plant=8, cycle=99))[0] == 8        # one season only


def test_with_several_seasons_the_default_is_the_most_recent():
    """The default question is "what is standing now", not "what was biggest"."""
    got = planting(rice(plant=8, cycle=11))                 # 8, 19, 30
    assert got[0] == max(lo for lo, _ in cycles(rice(plant=8, cycle=11)))


@pytest.mark.parametrize("p", [7, 8, 9, 10, 12])
def test_planting_found_wherever_the_dip_is(p):
    assert planting(rice(plant=p, cycle=99))[0] == p


def test_peak_follows_planting_by_the_rise():
    plant, peak = planting(rice(plant=8, rise=6, cycle=99))
    assert peak - plant == 6


def test_survives_speckle_noise_after_filtering():
    s = rice(plant=9, cycle=99, noise=0.8, seed=3)
    got = planting(median3(heikin_ashi(s)))
    assert got is not None and abs(got[0] - 9) <= 1


def test_flat_cover_is_not_rice():
    rng = np.random.default_rng(1)
    for base in (-16.0, -8.0):                       # forest, then town
        flat = base + rng.normal(0, 0.4, N).astype("float32")
        assert not looks_like_paddy(flat)


def test_a_single_dip_without_a_rise_is_not_rice():
    s = np.full(N, -14.0, dtype="float32")
    s[10] = -22.0                                    # a wet field, not a crop
    assert not looks_like_paddy(s)
    assert planting(s) is None


def test_double_cropping_gives_two_cycles():
    got = cycles(rice(plant=6, cycle=12))
    assert len(got) >= 2
    assert got[1][0] - got[0][0] == 12


def test_window_picks_this_season_not_the_last():
    s = rice(plant=6, cycle=12)                      # plantings at 6 and 18
    assert planting(s, first=12)[0] == 18
    assert planting(s, last=12)[0] == 6


def test_a_dip_within_the_window_of_the_edge_cannot_be_seen():
    """Why the scenario pads the stack either side of the season.

    A minimum is only validated against `window_min` periods on BOTH sides, so
    a transplanting in the first (or last) five periods of the series is
    undetectable -- 60 days at 12-day repeat. Fetch a season's stack with no
    padding and the earliest plantings silently read as "not planted", which
    is exactly the drought signal being looked for.
    """
    assert planting(rice(plant=3, cycle=99)) is None
    assert planting(rice(plant=8, cycle=99))[0] == 8   # same series, padded


def test_deepest_dip_wins_when_asked_for_the_main_season():
    s = rice(plant=6, cycle=99)
    s[18] = -18.0                                    # a shallower second dip
    s[19:23] = [-16.0, -14.5, -13.0, -12.0]
    assert planting(s, pick="deepest")[0] == 6


def test_median3_kills_a_spike_and_keeps_the_edge():
    s = np.array([-14, -14, -2, -14, -14, -21, -21], dtype="float32")
    out = median3(s)
    assert out[2] == pytest.approx(-14)              # spike gone
    assert out[-1] == pytest.approx(-21)             # edge kept


def test_heikin_ashi_keeps_length_and_direction():
    s = rice(plant=8, cycle=99)
    ha = heikin_ashi(s)
    assert ha.shape == s.shape
    assert ha[8] < ha[14]                            # still rising after planting


def test_stack_runs_only_where_the_mask_is_true():
    cube = np.stack([rice(plant=7, cycle=99)] * 4, axis=-1).reshape(N, 2, 2)
    mask = np.array([[True, False], [False, True]])
    plant, peak, amp = stack_planting(cube, mask)
    assert plant[0, 0] == 7 and plant[1, 1] == 7
    assert np.isnan(plant[0, 1]) and np.isnan(plant[1, 0])
    assert amp[0, 0] == pytest.approx(10.0, abs=0.01)


# --- the double window: planting date AND the variety's own season length ---

def two_seasons(plant=8, length_days=75, gap_days=0, n=40, period_days=12):
    """Two flood troughs: this season's, then the next one after harvest.

    The second trough is what dates the harvest. Its decline begins
    ANCHOR_TO_HARVEST_DAYS after harvest, so a series built from a known
    season length must return that length.
    """
    import numpy as _np
    from earthchange.paddy_phenology import ANCHOR_TO_HARVEST_DAYS
    s = _np.full(n, -14.0, dtype="float32")
    rise = max(int(round(length_days / period_days)) - 2, 3)
    # The anchor dates harvest from where the next decline BEGINS, which is
    # ANCHOR_TO_HARVEST_DAYS after harvest -- so that index is the last high
    # value, and the trough itself is one period later.
    onset = plant + int(round(
        (length_days + ANCHOR_TO_HARVEST_DAYS + gap_days) / period_days))
    for start in (plant, onset + 1):
        if start >= n:
            break
        s[start] = -21.0
        for k in range(1, rise + 1):
            if start + k < n:
                s[start + k] = -21.0 + 10.0 * k / rise
        for k in range(1, 3):
            if start + rise + k < n:
                s[start + rise + k] = -11.0 - 3.0 * k / 2
    return s


@pytest.mark.parametrize("days", [75, 110, 130])
def test_season_length_is_measured_not_assumed(days):
    """A short variety and a long one must not come back the same length."""
    from earthchange.paddy_phenology import calendar
    s = two_seasons(plant=8, length_days=days, n=44)
    got = calendar(s, first=4, last=14)
    assert got is not None
    plant, length = got
    assert abs(plant - 8) <= 1
    assert abs(length - days) <= 12                  # within one S1 period


def test_season_length_falls_back_when_there_is_no_second_flood():
    """One season in the series: the length is unknown, and says so."""
    from earthchange.paddy_phenology import (SEASON_LENGTH_FALLBACK, calendar,
                                             season_length)
    s = rice(plant=8, cycle=99)
    assert season_length(s, 8) == SEASON_LENGTH_FALLBACK
    assert calendar(s)[1] == SEASON_LENGTH_FALLBACK


def test_season_length_refuses_an_impossible_season():
    """Outside 60-140 days it is not a rice season, so the fallback stands."""
    from earthchange.paddy_phenology import SEASON_LENGTH_FALLBACK, season_length
    s = two_seasons(plant=6, length_days=75, gap_days=200, n=60)
    assert season_length(s, 6) == SEASON_LENGTH_FALLBACK


def test_stack_calendar_reports_length_per_pixel():
    from earthchange.paddy_phenology import stack_calendar
    short, long_ = two_seasons(length_days=75, n=44), two_seasons(length_days=130, n=44)
    cube = np.stack([short, long_], axis=-1).reshape(44, 1, 2)
    mask = np.ones((1, 2), dtype=bool)
    plant, length, amp = stack_calendar(cube, mask, first=4, last=14)
    assert abs(length[0, 0] - 75) <= 12 and abs(length[0, 1] - 130) <= 12
    assert length[0, 0] < length[0, 1]               # the varieties differ


# --- gaps: Sentinel-1 does not acquire every period everywhere ---

def test_short_gaps_are_interpolated_long_ones_are_not():
    from earthchange.paddy_phenology import fill_time_gaps
    s = rice(plant=8, cycle=99).astype("float32")
    cube = np.repeat(s[:, None, None], 2, axis=2).copy()
    cube[12:14, 0, 0] = np.nan                       # a 2-period gap: fill
    cube[3:9, 0, 1] = np.nan                         # a 6-period gap: leave
    filled, valid = fill_time_gaps(cube, max_gap=3)
    assert np.isfinite(filled[12:14, 0, 0]).all()
    assert np.isnan(filled[3:9, 0, 1]).all()
    assert valid[0, 0] and valid[0, 1]               # both still well covered


def test_a_pixel_with_too_little_data_is_not_scored():
    from earthchange.paddy_phenology import fill_time_gaps
    cube = np.full((20, 1, 1), -14.0, dtype="float32")
    cube[:14, 0, 0] = np.nan                         # only 30% observed
    _, valid = fill_time_gaps(cube, min_coverage=0.6)
    assert not valid[0, 0]


def test_interpolation_is_linear_between_real_observations():
    from earthchange.paddy_phenology import fill_time_gaps
    cube = np.full((7, 1, 1), np.nan, dtype="float32")
    cube[0, 0, 0], cube[4, 0, 0], cube[6, 0, 0] = -20.0, -12.0, -12.0
    filled, _ = fill_time_gaps(cube, max_gap=3, min_coverage=0.3)
    assert filled[2, 0, 0] == pytest.approx(-16.0)   # halfway
    assert np.isnan(filled[5, 0, 0]) or np.isfinite(filled[5, 0, 0])


def test_the_edges_are_left_alone_not_extrapolated():
    from earthchange.paddy_phenology import fill_time_gaps
    cube = np.full((10, 1, 1), -14.0, dtype="float32")
    cube[0, 0, 0] = np.nan
    cube[-1, 0, 0] = np.nan
    filled, _ = fill_time_gaps(cube)
    assert np.isnan(filled[0, 0, 0]) and np.isnan(filled[-1, 0, 0])


def test_clamped_ends_cannot_invent_a_planting():
    """The padding may be filled flat, but flat is never a validated trough."""
    from earthchange.paddy_phenology import fill_time_gaps
    s = rice(plant=12, cycle=99).astype("float32")
    s[:4] = np.nan                                   # missing at the start
    cube = s[:, None, None].copy()
    filled, valid = fill_time_gaps(cube, clamp_ends=True)
    assert np.isfinite(filled[:, 0, 0]).all() and valid[0, 0]
    got = cycles(filled[:, 0, 0])
    assert got and got[0][0] == 12                   # the real one, and only it
    assert all(lo >= 4 for lo, _ in got)             # nothing from the flat tail


def test_latest_planting_is_the_crop_standing_now():
    """Two plantings in the window: the current crop is the later one."""
    s = rice(plant=6, cycle=12)                      # plantings at 6 and 18
    s[6] = -24.0                                     # make the FIRST deeper
    assert planting(s, pick="latest")[0] == 18
    assert planting(s, pick="deepest")[0] == 6
