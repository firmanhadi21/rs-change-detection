"""The hybrid calendar: optical planting date, radar season length.

Why it exists, in the reference's own numbers (BulakBakal, 29 parcels, 13 with
farmer harvest windows):

    arm       plant |err| med   within 12 d   harvest in window
    fixed110        6 d             90%            0/13
    full_sar       12 d             55%           11/13
    hybrid          6 d             90%           12/13

So the optical date is worth taking when it can be trusted -- and the radar
length is what wins the harvest window. These tests pin the "when it can be
trusted" half, because that is where a wet-season product goes wrong quietly.
"""
import datetime as dt

import numpy as np
import pytest

from earthchange import paddy_phenology as phen


def _grid(n=20, start=dt.date(2026, 1, 1), days=12):
    out = []
    cur = start
    for i in range(n):
        out.append((i, cur, cur + dt.timedelta(days=days - 1)))
        cur += dt.timedelta(days=days)
    return out


def _doy(grid, index):
    _, a, b = grid[index]
    return (a + (b - a) / 2).timetuple().tm_yday


def test_the_optical_date_is_used_when_it_agrees_and_is_well_observed():
    grid = _grid()
    sar = np.array([[5.0]], dtype="float32")
    near = _doy(grid, 5) + 6                      # 6 days from the radar trough
    doy, arm = phen.hybrid_planting(sar, np.array([[near]]), grid,
                                    n_obs=np.array([[8]]))
    assert doy[0, 0] == pytest.approx(near)
    assert arm[0, 0] == 1                         # optical


def test_the_radar_date_stands_when_the_two_sensors_disagree():
    """A wettest-day two months from the trough is a different event."""
    grid = _grid()
    sar = np.array([[5.0]], dtype="float32")
    far = _doy(grid, 5) + 60
    doy, arm = phen.hybrid_planting(sar, np.array([[far]]), grid,
                                    n_obs=np.array([[8]]))
    assert doy[0, 0] == pytest.approx(_doy(grid, 5))
    assert arm[0, 0] == 0                         # fell back to radar


def test_too_few_clear_looks_falls_back():
    """Transplanting is in the wet season; two glimpses are not a date."""
    grid = _grid()
    sar = np.array([[5.0]], dtype="float32")
    near = _doy(grid, 5) + 3
    doy, arm = phen.hybrid_planting(sar, np.array([[near]]), grid,
                                    n_obs=np.array([[2]]))
    assert doy[0, 0] == pytest.approx(_doy(grid, 5))
    assert arm[0, 0] == 0


def test_no_optical_observation_at_all_falls_back():
    grid = _grid()
    sar = np.array([[7.0]], dtype="float32")
    doy, arm = phen.hybrid_planting(sar, np.array([[np.nan]]), grid,
                                    n_obs=np.array([[0]]))
    assert doy[0, 0] == pytest.approx(_doy(grid, 7))
    assert arm[0, 0] == 0


def test_no_planting_at_all_stays_unplanted():
    """The strongest drought signal there is must not be invented by optics."""
    grid = _grid()
    sar = np.array([[np.nan]], dtype="float32")
    doy, arm = phen.hybrid_planting(sar, np.array([[40.0]]), grid,
                                    n_obs=np.array([[9]]))
    assert np.isnan(doy[0, 0])
    assert np.isnan(arm[0, 0])


def test_the_day_of_year_wrap_is_not_a_disagreement():
    """31 December and 2 January are two days apart, not 363."""
    grid = _grid(start=dt.date(2025, 12, 20))
    sar = np.array([[0.0]], dtype="float32")
    sar_doy = _doy(grid, 0)                       # late December
    optical = (sar_doy + 4) % 365 or 365          # just into January
    doy, arm = phen.hybrid_planting(sar, np.array([[optical]]), grid,
                                    n_obs=np.array([[6]]))
    assert arm[0, 0] == 1, "a new-year crossing was read as 360 days of error"
    assert doy[0, 0] == pytest.approx(optical)


def test_a_mixed_field_reports_both_arms():
    grid = _grid()
    sar = np.array([[5.0, 5.0, np.nan]], dtype="float32")
    near, far = _doy(grid, 5) + 2, _doy(grid, 5) + 90
    doy, arm = phen.hybrid_planting(
        sar, np.array([[near, far, near]]), grid,
        n_obs=np.array([[9, 9, 9]]))
    assert list(arm[0][:2]) == [1.0, 0.0]
    assert np.isnan(arm[0, 2])
    assert np.nansum(arm) == 1                    # one pixel on the optical arm


def test_the_arms_and_thresholds_are_the_documented_ones():
    assert phen.CALENDAR_ARMS == ("full_sar", "hybrid", "fixed110")
    assert phen.HYBRID_MAX_DISAGREE_DAYS == 24    # two Sentinel-1 periods
    assert phen.HYBRID_MIN_OBS >= 3
