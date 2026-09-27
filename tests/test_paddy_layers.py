"""A national layer must be windowed to the AOI, never thumbnailed into it.

Lahan Baku Sawah covers 95E-141E. Read with `out_shape` it would be
resampled whole, so a 8 km study area would receive a postage stamp of
Indonesia -- paddy in roughly the right proportion, in entirely the wrong
places, and nothing downstream would look obviously wrong.
"""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from affine import Affine                                       # noqa: E402

from earthchange.paddy_drought import (pixel_area_ha,           # noqa: E402
                                       rasterize_layer)


def _national_raster(path):
    """A country-sized 0/1 layer: paddy ONLY in one small eastern block."""
    west, north, res = 95.0, 6.0, 0.01                 # ~1 km cells
    width, height = 4600, 1700                         # 95-141E, 11S-6N
    data = np.zeros((height, width), dtype="uint8")
    # A 0.2 x 0.2 degree block of paddy centred on (110.85, -6.95)
    col = int((110.85 - west) / res)
    row = int((north - (-6.95)) / res)
    data[row - 10:row + 10, col - 10:col + 10] = 1
    profile = {"driver": "GTiff", "height": height, "width": width, "count": 1,
               "dtype": "uint8", "crs": "EPSG:4326",
               "transform": Affine(res, 0, west, 0, -res, north)}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return path


def _aoi_profile(lon=110.85, lat=-6.95, half_deg=0.04, n=161):
    res = 2 * half_deg / n
    return {"driver": "GTiff", "height": n, "width": n, "count": 1,
            "dtype": "float32", "crs": "EPSG:4326",
            "transform": Affine(res, 0, lon - half_deg, 0, -res, lat + half_deg)}


def test_a_national_layer_lands_on_the_right_ground(tmp_path):
    path = _national_raster(str(tmp_path / "lbs.tif"))
    got = rasterize_layer(path, _aoi_profile())
    assert got.shape == (161, 161)
    # The AOI sits inside the paddy block, so it should be almost all paddy.
    assert got.mean() > 0.95, "AOI inside the block should be paddy"


def test_an_aoi_outside_the_paddy_block_gets_nothing(tmp_path):
    """The thumbnail bug would sprinkle paddy here too."""
    path = _national_raster(str(tmp_path / "lbs.tif"))
    far = _aoi_profile(lon=120.0, lat=-2.0)            # Sulawesi, no paddy drawn
    got = rasterize_layer(path, far)
    assert got.sum() == 0


def test_pixel_area_shrinks_with_latitude_in_degrees():
    prof = _aoi_profile()
    equator = pixel_area_ha(prof, 0.0)
    high = pixel_area_ha(prof, 60.0)
    assert high < equator / 1.9                        # cos(60) = 0.5
