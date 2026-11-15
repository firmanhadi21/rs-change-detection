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


def test_median_keeps_a_real_water_body():
    db = np.full((30, 30), -8.0)
    db[5:25, 5:25] = -22.0        # a 200 m pond
    out = mpc_backend._median50(db)
    assert (out[8:22, 8:22] < -16).all()
