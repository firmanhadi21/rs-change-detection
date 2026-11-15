"""Planetary Computer flood: speckle filter (offline)."""

import numpy as np
import pytest

pytest.importorskip("scipy")
from earthchange import mpc_backend  # noqa: E402


def test_median_removes_single_dark_pixel_and_keeps_nodata():
    db = np.full((20, 20), -8.0)
    db[10, 10] = -25.0            # one speckle pixel reading as water
    db[0, :] = np.nan              # no-data edge
    out = mpc_backend._median50(db)
    assert out[10, 10] == pytest.approx(-8.0)
    assert np.isnan(out[0]).all()


class _Item:
    def __init__(self, day, cloud, tile):
        import datetime as dt
        self.datetime = dt.datetime(2025, 1, day, 3, 0)
        self.properties = {"eo:cloud_cover": cloud}
        self.tile = tile


def test_clearest_days_keep_all_tiles_of_a_day():
    items = [_Item(1, 5, "A"), _Item(1, 15, "B"),     # day 1: mean 10
             _Item(2, 80, "A"), _Item(2, 90, "B"),     # day 2: mean 85
             _Item(3, 1, "A"), _Item(3, 3, "B")]       # day 3: mean 2
    kept = mpc_backend.clearest(items, 2)
    assert sorted({it.datetime.day for it in kept}) == [1, 3]
    assert len(kept) == 4                               # both tiles of each day


def test_clearest_with_fewer_days_than_cap():
    items = [_Item(1, 50, "A")]
    assert mpc_backend.clearest(items, 12) == items


def test_median_keeps_a_real_water_body():
    db = np.full((30, 30), -8.0)
    db[5:25, 5:25] = -22.0        # a 200 m pond
    out = mpc_backend._median50(db)
    assert (out[8:22, 8:22] < -16).all()
