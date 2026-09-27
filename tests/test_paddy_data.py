"""The 12-day grid and the WaPOR dekad weighting.

Both are pure date arithmetic, and both are easy to get quietly wrong: a
period that slips by a day misaligns every band in the stack, and a dekad
weighted by the wrong overlap silently rescales the water balance.
"""
import datetime as dt

import pytest

from earthchange.paddy_data import (_dekad_bounds, _dekads_overlapping,
                                    band_name, period_grid)

D = dt.date


def test_periods_are_12_days_and_contiguous():
    grid = period_grid(D(2026, 1, 1), D(2026, 3, 31))
    assert grid[0][1] == D(2026, 1, 1) and grid[0][2] == D(2026, 1, 12)
    for (_, _, end), (_, nxt, _) in zip(grid, grid[1:]):
        assert nxt == end + dt.timedelta(days=1)          # no gap, no overlap
    assert grid[-1][2] == D(2026, 3, 31)                  # last one is clipped


def test_period_indices_and_band_names_line_up():
    grid = period_grid(D(2026, 1, 1), D(2026, 2, 1))
    assert [i for i, _, _ in grid] == list(range(len(grid)))
    assert band_name(0) == "p000" and band_name(12) == "p012"


def test_dekads_are_1_10_11_20_and_21_to_month_end():
    assert _dekad_bounds(D(2026, 3, 5)) == (D(2026, 3, 1), D(2026, 3, 10))
    assert _dekad_bounds(D(2026, 3, 15)) == (D(2026, 3, 11), D(2026, 3, 20))
    assert _dekad_bounds(D(2026, 3, 25)) == (D(2026, 3, 21), D(2026, 3, 31))
    assert _dekad_bounds(D(2026, 2, 25)) == (D(2026, 2, 21), D(2026, 2, 28))
    assert _dekad_bounds(D(2024, 2, 25)) == (D(2024, 2, 21), D(2024, 2, 29))


def test_overlap_days_sum_to_the_period_length():
    """Every day of the period is counted once, across the dekads it spans."""
    for start in (D(2026, 1, 1), D(2026, 1, 8), D(2026, 2, 20), D(2026, 12, 25)):
        end = start + dt.timedelta(days=11)
        got = _dekads_overlapping(start, end)
        assert sum(days for _, _, days in got) == 12


def test_a_period_inside_one_dekad_has_a_single_weight():
    got = _dekads_overlapping(D(2026, 3, 2), D(2026, 3, 8))
    assert len(got) == 1 and got[0][2] == 7


def test_a_period_straddling_two_dekads_splits_by_days():
    got = _dekads_overlapping(D(2026, 3, 6), D(2026, 3, 17))
    assert [days for _, _, days in got] == [5, 7]          # 6-10, then 11-17


@pytest.mark.parametrize("day", [D(2026, 1, 31), D(2026, 4, 30), D(2024, 2, 29)])
def test_month_ends_do_not_lose_a_day(day):
    ds, de = _dekad_bounds(day)
    assert ds <= day <= de
    assert de.month == day.month
