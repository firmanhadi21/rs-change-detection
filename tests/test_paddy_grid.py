"""The analysis grid, and the per-layer resolution that travels with it.

The point of these: a supplied paddy layer must never be resampled, and a
300 m water balance drawn on a 56 m grid must not be publishable as a
field-level measurement.
"""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from earthchange import paddy_data as pdata
from earthchange import paddy_drought as pd
from earthchange import paddy_publish as pub


# --- the transform ---------------------------------------------------------
def test_transform_shape_and_sign():
    t = pdata.grid_transform(0.0005, (0.0, 0.0002))
    assert t == [0.0005, 0.0, 0.0, 0.0, -0.0005, 0.0002]


def test_anchor_is_taken_modulo_the_step():
    """An anchor only names which global grid the pixels fall on."""
    a = pdata.grid_transform(0.0005, (94.9995, 6.0007))
    b = pdata.grid_transform(0.0005, (0.0, 0.0002))
    assert a[2] == pytest.approx(b[2], abs=1e-12)
    assert a[5] == pytest.approx(b[5], abs=1e-12)


def test_float_dust_reads_as_zero():
    """6.0007 % 0.0005 lands a hair under the step; that is not a 55 m shift."""
    assert pdata._snap(0.0005 - 1e-15, 0.0005) == 0.0
    assert pdata._snap(1e-15, 0.0005) == 0.0
    assert pdata._snap(0.0002, 0.0005) == pytest.approx(0.0002)


def test_lbs_default_matches_the_national_raster_grid():
    """The constants are the LBS raster's own grid, not a round number."""
    assert pdata.LBS_GRID_DEG == 0.0005
    assert pdata.grid_metres() == pytest.approx(55.66, abs=0.01)
    # 6.0007, the raster's latitude origin, is NOT on a zero-anchored grid:
    # this offset is the whole reason the anchor exists.
    assert (6.0007 / 0.0005) % 1 == pytest.approx(0.4, abs=1e-6)
    assert pdata.LBS_GRID_ANCHOR[1] == pytest.approx(0.0002)


# --- reading a grid off a raster -------------------------------------------
def _write(path, transform, crs="EPSG:4326", n=8):
    prof = {"driver": "GTiff", "height": n, "width": n, "count": 1,
            "dtype": "uint8", "crs": crs, "transform": transform}
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(np.ones((n, n), dtype="uint8"), 1)
    return str(path)


def test_grid_from_raster_reads_step_and_origin(tmp_path):
    t = rasterio.Affine(0.0005, 0, 110.8412, 0, -0.0005, -6.9408)
    got = pdata.grid_from_raster(_write(tmp_path / "a.tif", t))
    assert got[0] == pytest.approx(0.0005)
    assert got[1] == (pytest.approx(110.8412), pytest.approx(-6.9408))


def test_grid_from_raster_refuses_a_projected_layer(tmp_path):
    t = rasterio.Affine(50, 0, 400000, 0, -50, 9200000)
    assert pdata.grid_from_raster(
        _write(tmp_path / "utm.tif", t, crs="EPSG:32749")) is None


def test_grid_from_raster_refuses_rotation_and_oblong_pixels(tmp_path):
    rot = rasterio.Affine(0.0005, 0.0001, 110.0, 0.0001, -0.0005, -7.0)
    assert pdata.grid_from_raster(_write(tmp_path / "rot.tif", rot)) is None
    oblong = rasterio.Affine(0.0005, 0, 110.0, 0, -0.001, -7.0)
    assert pdata.grid_from_raster(_write(tmp_path / "ob.tif", oblong)) is None


# --- resolve_grid ----------------------------------------------------------
def test_a_supplied_raster_layer_defines_the_grid(tmp_path):
    t = rasterio.Affine(0.0005, 0, 110.8412, 0, -0.0005, -6.9408)
    p = _write(tmp_path / "lbs.tif", t)
    deg, anchor, metres, source = pd.resolve_grid("lbs", p)
    assert deg == pytest.approx(0.0005)
    assert metres == pytest.approx(55.66, abs=0.01)
    assert source == "lbs.tif"
    # and it is the layer's own anchor, so reading it needs no resampling
    x = pdata.grid_transform(deg, anchor)
    assert (110.8412 - x[2]) / deg == pytest.approx(
        round((110.8412 - x[2]) / deg), abs=1e-6)


def test_lbs_is_the_default_when_no_layer_is_given():
    deg, anchor, metres, source = pd.resolve_grid("lbs", None)
    assert (deg, anchor) == (pdata.LBS_GRID_DEG, pdata.LBS_GRID_ANCHOR)
    assert "Lahan Baku Sawah" in source


def test_an_explicit_metre_grid_beats_the_paddy_layer(tmp_path):
    """The flag exists to be used.

    The layer used to win unconditionally, so asking for 150 m over a 50 km
    irrigation scheme ran at 55.66 m, exceeded the request limit, and the
    download's own fallback coarsened it to ~222 m and off-grid -- worse than
    either choice, and visible only in a log line.
    """
    t = rasterio.Affine(0.0005, 0, 110.8412, 0, -0.0005, -6.9408)
    p = _write(tmp_path / "lbs.tif", t)
    deg, anchor, metres, source = pd.resolve_grid(150.0, p)
    assert metres == 150.0
    assert deg == pytest.approx(150.0 / pdata.DEG_M)
    assert "150 m" in source
    # and with the default spec the layer still wins
    deg2, _, metres2, source2 = pd.resolve_grid("lbs", p)
    assert metres2 == pytest.approx(55.66, abs=0.01)
    assert source2 == "lbs.tif"


def test_a_metre_value_still_gets_one_shared_grid():
    """Anchored at zero: two AOIs at 20 m still share their pixel edges."""
    deg, anchor, metres, source = pd.resolve_grid(20.0, None)
    assert metres == 20.0
    assert anchor == (0.0, 0.0)
    assert deg == pytest.approx(20.0 / pdata.DEG_M)
    assert "20 m" in source


def test_a_vector_layer_does_not_override_the_grid(tmp_path):
    p = str(tmp_path / "petak.gpkg")
    deg, _, metres, source = pd.resolve_grid("lbs", p)
    assert deg == pdata.LBS_GRID_DEG          # vectors have no grid to inherit
    assert "Lahan Baku Sawah" in source


# --- the resolution that travels with the data -----------------------------
def test_water_layers_declare_wapor_not_the_grid():
    for key in ("adequacy", "adequacy_class", "anomaly", "anomaly_class",
                "supply_mm", "demand_mm"):
        assert pd.NATIVE_M[key] == pd.WAPOR_PIXEL_M == 300
    for key in ("planting_doy", "delay_days", "delay_class", "plant_period"):
        assert pd.NATIVE_M[key] == pd.S1_EFFECTIVE_M == 90
    assert pd.NATIVE_M["outlook_class"] == pd.GFS_PIXEL_M > 20000


def test_legend_carries_grid_and_native_per_layer():
    leg = pub.legend("id", grid_m=55.66, native_m=pd.NATIVE_M)
    assert leg["anomaly_class"]["grid_m"] == 55.66
    assert leg["anomaly_class"]["native_m"] == 300
    assert leg["delay_class"]["native_m"] == 90
    # every published layer says something about its own resolution
    assert all("native_m" in v and "grid_m" in v for v in leg.values())


def test_legend_without_a_grid_says_nothing_rather_than_guessing():
    leg = pub.legend("id")
    assert leg["anomaly_class"]["grid_m"] is None
    assert leg["anomaly_class"]["native_m"] is None


@pytest.mark.parametrize("lang,mark,grid,cells", [
    ("id", "piksel menutupi", 55.66, 29),
    ("en", "pixel covers", 50.0, 36),
])
def test_the_wapor_caveat_counts_cells_of_the_grid_in_use(lang, mark, grid, cells):
    line = [c for c in pub.caveats(lang, grid) if mark in c]
    assert len(line) == 1
    assert str(cells) in line[0]
    assert f"{grid:.0f} m" in line[0]
    assert "{" not in line[0]                 # no unformatted placeholder ships


def test_caveats_keep_the_puso_and_forecast_limits():
    got = " ".join(pub.caveats("en", 55.66))
    assert "not a verdict" in got
    assert "irrigation deliveries cannot be forecast" in got.lower()
