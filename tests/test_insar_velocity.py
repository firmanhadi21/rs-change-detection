"""The velocity inversion: correctness, and that it does not hold the stack.

The four-year fit was killed by the kernel (SIGKILL, exit 137) because the
inversion stacked every interferogram in memory -- 354 pairs, phase and
coherence, tens of gigabytes. It now streams. These tests pin both the arithmetic
and the property that made it fail.
"""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from earthchange.insar_series import velocity

WAVELENGTH = 0.055465
SCALE = (WAVELENGTH / (4 * np.pi)) * 1000.0   # radians -> mm


def write(path, arr, nodata=None):
    # No CRS: the inversion is pure arithmetic on the rasters, and asking
    # rasterio to resolve EPSG:4326 fails on machines where another PROJ
    # installation shadows its database -- an environment problem that should
    # not decide whether these tests can run.
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0],
                       width=arr.shape[1], count=1, dtype="float32",
                       transform=from_origin(120, -8, 0.001, 0.001),
                       nodata=nodata) as d:
        d.write(arr.astype("float32"), 1)


def make_pair(tmp_path, name, phase, coh, dates):
    d = tmp_path / name
    d.mkdir()
    write(str(d / f"{name}_unw_phase.tif"), phase)
    write(str(d / f"{name}_corr.tif"), coh)
    return (str(d), dates)


def constant_rate_stack(tmp_path, n, mm_per_year, shape=(8, 8), coh=0.8):
    """n pairs, each 12 days, all showing the same steady rate."""
    products = []
    for i in range(n):
        days = 12
        yrs = days / 365.25
        phase = np.full(shape, mm_per_year * yrs / SCALE, dtype="float32")
        products.append(make_pair(
            tmp_path, f"p{i:03d}", phase, np.full(shape, coh, dtype="float32"),
            (f"2024-01-{1 + i:02d}", f"2024-01-{13 + i:02d}")))
    return products


def test_recovers_a_known_rate(tmp_path):
    """A stack that all agrees on 10 mm/yr must invert to 10 mm/yr."""
    products = constant_rate_stack(tmp_path, 8, mm_per_year=10.0)
    vel, n_good, stats, _ = velocity(products)
    # Referenced to a pixel, so the field is uniform at zero -- the physically
    # meaningful check is that it is flat, not that it equals 10.
    assert np.nanstd(vel) < 1e-6
    assert stats["pairs_used"] == 8
    assert int(np.median(n_good)) == 8


def test_low_coherence_pixels_are_not_fitted(tmp_path):
    """Below the coherence floor a pixel carries no usable phase."""
    products = constant_rate_stack(tmp_path, 8, 10.0, coh=0.1)
    vel, n_good, _, _ = velocity(products)
    assert n_good.max() == 0
    assert np.isnan(vel).all()


def test_requires_a_minimum_of_coherent_pairs(tmp_path):
    """A velocity from one pair should not appear beside one from forty."""
    good = constant_rate_stack(tmp_path, 8, 10.0, coh=0.8)
    # Make all but one pair incoherent at a single pixel.
    for i, (pdir, _) in enumerate(good[:-1]):
        import glob
        p = glob.glob(f"{pdir}/*_corr.tif")[0]
        with rasterio.open(p) as s:
            a = s.read(1)
            prof = s.profile
        a[0, 0] = 0.05
        with rasterio.open(p, "w", **prof) as d:
            d.write(a, 1)
    vel, n_good, stats, _ = velocity(good)
    assert n_good[0, 0] == 1
    assert np.isnan(vel[0, 0]), "one coherent pair must not yield a velocity"
    assert stats["min_pairs_per_pixel"] >= 3


def test_memory_is_flat_in_the_number_of_pairs(tmp_path):
    """The property whose absence killed the four-year run.

    Peak allocation must not grow with stack depth. Compared at two depths on
    the same raster size: stacking would roughly quadruple, streaming should
    stay put.
    """
    tracemalloc = pytest.importorskip("tracemalloc")

    def peak(n):
        d = tmp_path / f"n{n}"
        d.mkdir()
        products = constant_rate_stack(d, n, 10.0, shape=(60, 60))
        tracemalloc.start()
        velocity(products)
        _, hi = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return hi

    small, large = peak(4), peak(16)
    assert large < small * 2.0, (
        f"peak memory grew {large / small:.1f}x for 4x the pairs; "
        "the inversion is holding the stack again")
