"""The forecast leg, when the GFS run is still being written.

A run is published forecast hour by hour, so a request for 14 days made
minutes after 00Z comes back with the later days empty. Counting demand over
days whose rain is missing would manufacture a deficit, so both sides must
cover the same days -- and the report must say how many days that was.
"""
import datetime as dt

import numpy as np
import pytest

from earthchange import paddy_drought as pd


def _forecast(days, lat=-6.95, published=None):
    """Synthetic daily rain/tmin/tmax; `published` days are real, rest masked."""
    published = days if published is None else published
    shape = (days, 4, 4)
    rain = np.full(shape, 6.0, dtype="float32")
    tmin = np.full(shape, 24.0, dtype="float32")
    tmax = np.full(shape, 32.0, dtype="float32")
    rain[published:] = np.nan
    tmin[published:] = np.nan
    tmax[published:] = np.nan
    lat_grid = np.full((4, 4), lat, dtype="float32")
    doy = np.full((4, 4), 200.0, dtype="float32")     # planted, mid-season
    length = np.full((4, 4), 95.0, dtype="float32")
    return rain, tmin, tmax, doy, length, lat_grid


def test_a_complete_run_uses_every_lead_day():
    rain, tmin, tmax, doy, length, lat_grid = _forecast(14)
    si, r, d, used = pd.outlook(rain, tmin, tmax, doy, length, lat_grid,
                                dt.date(2026, 9, 27), lead_days=7)
    assert used == 7
    assert r[0, 0] == pytest.approx(7 * 6.0)          # 7 days of rain
    assert d[0, 0] > 0 and np.isfinite(si).all()


def test_unpublished_days_are_dropped_from_both_sides():
    """Three days published: 3 days of rain against 3 days of demand."""
    rain, tmin, tmax, doy, length, lat_grid = _forecast(14, published=3)
    si, r, d, used = pd.outlook(rain, tmin, tmax, doy, length, lat_grid,
                                dt.date(2026, 9, 27), lead_days=7)
    full = pd.outlook(*_forecast(14), dt.date(2026, 9, 27), lead_days=7)
    assert used == 3
    assert r[0, 0] == pytest.approx(3 * 6.0)
    # demand covers 3 days too, so adequacy is not dragged down by the gap
    assert d[0, 0] == pytest.approx(full[2][0, 0] * 3 / 7, rel=0.1)
    assert si[0, 0] == pytest.approx(full[0][0, 0], rel=0.1)


def test_an_empty_run_returns_nothing_rather_than_zero():
    """No published day means no outlook -- not a total deficit."""
    rain, tmin, tmax, doy, length, lat_grid = _forecast(14, published=0)
    si, r, d, used = pd.outlook(rain, tmin, tmax, doy, length, lat_grid,
                                dt.date(2026, 9, 27), lead_days=7)
    assert used == 0
    assert np.isnan(si).all() and np.isnan(r).all() and np.isnan(d).all()


def test_a_short_run_never_reports_more_days_than_it_used():
    rain, tmin, tmax, doy, length, lat_grid = _forecast(4)
    _, _, _, used = pd.outlook(rain, tmin, tmax, doy, length, lat_grid,
                               dt.date(2026, 9, 27), lead_days=7)
    assert used == 4
