"""A resumable run reuses what it downloaded -- so it must not reuse rubbish.

What broke without this: a national run was interrupted mid-download, leaving a
truncated GeoTIFF. Every later attempt saw a file of the right name, trusted it,
and failed with "Read failed" -- poisoning that tile permanently.
"""
import os

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from earthchange import paddy_drought as pdr


def _raster(path, bands=3, n=16):
    t = rasterio.Affine(0.0005, 0, 110.0, 0, -0.0005, -7.0)
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n,
                       count=bands, dtype="float32", crs="EPSG:4326",
                       transform=t) as dst:
        for b in range(bands):
            dst.write(np.full((n, n), float(b), dtype="float32"), b + 1)
    return str(path)


def test_a_complete_raster_is_usable(tmp_path):
    p = _raster(tmp_path / "ok.tif", bands=3)
    assert pdr.usable_raster(p)
    assert pdr.usable_raster(p, bands=3)


def test_a_missing_file_is_not_usable(tmp_path):
    assert not pdr.usable_raster(str(tmp_path / "nope.tif"))


def test_a_truncated_download_is_not_usable(tmp_path):
    """The actual failure: a file cut off mid-write."""
    p = _raster(tmp_path / "cut.tif", bands=8, n=64)
    full = os.path.getsize(p)
    with open(p, "r+b") as f:
        f.truncate(full // 3)
    assert not pdr.usable_raster(p)


def test_an_empty_file_is_not_usable(tmp_path):
    p = tmp_path / "empty.tif"
    p.write_bytes(b"")
    assert not pdr.usable_raster(str(p))


def test_garbage_with_the_right_name_is_not_usable(tmp_path):
    p = tmp_path / "junk.tif"
    p.write_bytes(b"not a geotiff at all")
    assert not pdr.usable_raster(str(p))


def test_the_wrong_band_count_is_not_usable(tmp_path):
    """A stack cached for a different window must not be reused for this one."""
    p = _raster(tmp_path / "short.tif", bands=5)
    assert pdr.usable_raster(p, bands=5)
    assert not pdr.usable_raster(p, bands=85)


def test_a_part_file_is_not_mistaken_for_the_real_one(tmp_path):
    """Downloads land on `.part` and are renamed, so this name is never read."""
    p = _raster(tmp_path / "x.tif.part", bands=2)
    assert not pdr.usable_raster(str(tmp_path / "x.tif"))
    assert os.path.exists(p)
