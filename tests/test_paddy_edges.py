"""Edges. The place where a tiled product goes wrong quietly.

Two things are pinned here. A coarse field fetched for local upsampling must be
padded, so the analysis grid's outer ring interpolates from real neighbours
rather than from nothing. And the ring must carry data at all: the old path
asked Earth Engine to upsample WaPOR to the analysis grid, and clipping at that
resolution returned a one-pixel ring of ZEROS around every window -- which a
water balance reads as total failure, on the border of every tile and of every
single-AOI run.
"""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from earthchange import paddy_data as pdata
from earthchange import paddy_drought as pdr


def _coarse(path, value=40.0, n=10, deg=0.0027, origin=(110.0, -7.0), bands=2):
    """A WaPOR-like coarse raster of a constant value."""
    t = rasterio.Affine(deg, 0, origin[0], 0, -deg, origin[1])
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n,
                       count=bands, dtype="float32", crs="EPSG:4326",
                       transform=t) as dst:
        for b in range(bands):
            dst.write(np.full((n, n), value, dtype="float32"), b + 1)
    return str(path)


def _fine_profile(origin, n=48, deg=0.0005):
    return {"driver": "GTiff", "height": n, "width": n, "count": 1,
            "dtype": "float32", "crs": rasterio.crs.CRS.from_epsg(4326),
            "transform": rasterio.Affine(deg, 0, origin[0], 0, -deg, origin[1])}


def test_upsampling_inside_a_padded_window_has_no_dead_ring(tmp_path):
    """The destination sits well inside the source, so every cell has neighbours."""
    src = _coarse(tmp_path / "coarse.tif", value=40.0, n=12)
    # start 3 coarse cells in, which is what WAPOR_PAD_CELLS buys
    prof = _fine_profile((110.0 + 3 * 0.0027, -7.0 - 3 * 0.0027))
    got = pdr.resample_stack(src, prof)
    assert np.isfinite(got).all()
    assert got.min() == pytest.approx(40.0, abs=1e-3)
    assert got[0, 0, 0] == pytest.approx(40.0, abs=1e-3)      # the ring too
    assert got[0, -1, -1] == pytest.approx(40.0, abs=1e-3)


def test_the_pad_is_wide_enough_to_matter():
    """Three cells of 300 m is ~900 m, comfortably more than one analysis cell."""
    assert pdr.WAPOR_PAD_CELLS >= 1
    pad_deg = pdr.WAPOR_PAD_CELLS * pdr.WAPOR_PIXEL_M / pdata.DEG_M
    assert pad_deg > pdata.LBS_GRID_DEG * 4


def test_a_zero_ring_would_read_as_total_failure():
    """Why the ring matters: adequacy of zero supply is the worst class there is.

    This is what the old WaPOR path produced on every window's border.
    """
    from earthchange import paddy_water as pw
    demand = np.full((3, 3), 40.0, dtype="float32")
    supply = np.full((3, 3), 40.0, dtype="float32")
    supply[0, :] = 0.0                       # the ring
    si = pw.adequacy(supply, demand)
    cls = pw.adequacy_class(si)
    assert cls[0, 0] == 3                    # severe
    assert cls[1, 1] != 3                    # the interior is fine
    assert si[0, 0] == 0.0


def test_resample_keeps_the_analysis_grid_exactly(tmp_path):
    """Upsampling must not shift the grid: the products are mosaicked by window."""
    src = _coarse(tmp_path / "c.tif", n=12)
    prof = _fine_profile((110.0 + 3 * 0.0027, -7.0 - 3 * 0.0027), n=32)
    got = pdr.resample_stack(src, prof)
    assert got.shape == (2, 32, 32)


def test_nodata_in_the_source_stays_nodata(tmp_path):
    """A masked dekad must not be upsampled into plausible-looking numbers."""
    p = str(tmp_path / "masked.tif")
    t = rasterio.Affine(0.0027, 0, 110.0, 0, -0.0027, -7.0)
    with rasterio.open(p, "w", driver="GTiff", height=12, width=12, count=1,
                       dtype="float32", crs="EPSG:4326", transform=t,
                       nodata=float("nan")) as dst:
        dst.write(np.full((12, 12), np.nan, dtype="float32"), 1)
    prof = _fine_profile((110.0 + 3 * 0.0027, -7.0 - 3 * 0.0027))
    got = pdr.resample_stack(p, prof)
    assert np.isnan(got).all()
