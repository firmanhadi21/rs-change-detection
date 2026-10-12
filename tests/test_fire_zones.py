"""Zone accounting over the province rasters.

The thing worth protecting is the overlap. The 38 province rasters are each
clipped to their own boundary but their bounding boxes are not disjoint, and a
zone summed naively across two of them counts the shared ground twice -- the
provinces' own land areas already add up about 1% over Indonesia for exactly
that reason. Everything here exists to keep one ground pixel counted once.
"""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
gpd = pytest.importorskip("geopandas")
from rasterio.transform import from_origin                      # noqa: E402
from shapely.geometry import box                                # noqa: E402

from earthchange import fire_zones as fz                        # noqa: E402
from earthchange.fire_national import GRID_DEG                  # noqa: E402

YEARS = [2015, 2016]
KEYS = ["soc"]
D = GRID_DEG


def _province(dirpath, inside, peat, bits, west, north):
    """One province raster, on the global lattice like fire-national writes."""
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "recurrence.tif"
    h, w = inside.shape
    prof = {"driver": "GTiff", "width": w, "height": h, "count": 3,
            "dtype": "uint16", "crs": "EPSG:4326",
            "transform": from_origin(west, north, D, D)}
    with rasterio.open(path, "w", **prof) as ds:
        for i, a in enumerate((inside, peat, bits), start=1):
            ds.write(a.astype("uint16"), i)
    return str(path)


def _zones(geoms, codes, field="code", label=None, labels=None):
    data = {field: codes}
    if label:
        data[label] = labels
    return gpd.GeoDataFrame(data, geometry=geoms, crs="EPSG:4326")


# --- the overlap, which is the whole point ---------------------------------
def test_two_provinces_claiming_one_pixel_count_it_once(tmp_path):
    """The same ground in two rasters is one hectare, not two."""
    on = np.ones((1, 2), dtype="uint16")
    # A covers lattice columns 0-1; B covers columns 1-2 -- they share col 1.
    _province(tmp_path / "A", on, on * 0, on, west=0.0, north=0.0)
    _province(tmp_path / "B", on, on * 0, on, west=D, north=0.0)
    z = _zones([box(-D, -D, 3 * D, D)], ["all"])
    rows = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS, progress=None)
    one = rows[0]["land_ha"] / 3
    # three distinct lattice columns were covered, not four
    assert rows[0]["land_ha"] == pytest.approx(3 * one)
    assert rows[0]["burned_ha"] == pytest.approx(3 * one)


def test_a_pixel_only_one_province_claims_is_still_counted(tmp_path):
    """The deduplication must not also drop the non-overlapping ground."""
    on = np.ones((1, 2), dtype="uint16")
    _province(tmp_path / "A", on, on * 0, on, west=0.0, north=0.0)
    _province(tmp_path / "B", on, on * 0, on, west=10 * D, north=0.0)
    z = _zones([box(-D, -D, 20 * D, D)], ["all"])
    rows = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS, progress=None)
    assert rows[0]["burned_ha"] > 0
    per = rows[0]["land_ha"] / 4
    assert rows[0]["land_ha"] == pytest.approx(4 * per)


def test_outside_a_province_boundary_is_not_land(tmp_path):
    """inside=0 is bounding-box padding, not ground the zone can claim."""
    inside = np.array([[1, 0]], dtype="uint16")
    bits = np.array([[1, 1]], dtype="uint16")
    _province(tmp_path / "A", inside, np.zeros((1, 2), "uint16"), bits,
              west=0.0, north=0.0)
    z = _zones([box(-D, -D, 3 * D, D)], ["all"])
    rows = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS, progress=None)
    assert rows[0]["burned_ha"] == pytest.approx(rows[0]["land_ha"])
    assert rows[0]["max_times"] == 1


# --- zones -----------------------------------------------------------------
def test_each_zone_gets_only_its_own_pixels(tmp_path):
    on = np.ones((1, 4), dtype="uint16")
    bits = np.array([[1, 1, 0, 0]], dtype="uint16")
    _province(tmp_path / "A", on, np.zeros((1, 4), "uint16"), bits,
              west=0.0, north=0.0)
    west = _zones([box(0, -D, 2 * D, 0)], ["W"])
    east = _zones([box(2 * D, -D, 4 * D, 0)], ["E"])
    rw = fz.zone_stats(str(tmp_path), west, "code", YEARS, KEYS, progress=None)
    re = fz.zone_stats(str(tmp_path), east, "code", YEARS, KEYS, progress=None)
    assert rw[0]["burned_ha"] > 0
    assert re[0]["burned_ha"] == 0
    assert re[0]["land_ha"] > 0          # the zone exists, it just did not burn


def test_a_zone_spanning_two_provinces_is_summed_not_split(tmp_path):
    on = np.ones((1, 2), dtype="uint16")
    _province(tmp_path / "A", on, on * 0, on, west=0.0, north=0.0)
    _province(tmp_path / "B", on, on * 0, on, west=10 * D, north=0.0)
    whole = _zones([box(-D, -D, 20 * D, D)], ["all"])
    rows = fz.zone_stats(str(tmp_path), whole, "code", YEARS, KEYS,
                         progress=None)
    just_a = fz.zone_stats(str(tmp_path), _zones([box(-D, -D, 3 * D, D)],
                                                 ["a"]),
                           "code", YEARS, KEYS, progress=None)
    assert rows[0]["land_ha"] > just_a[0]["land_ha"]


def test_the_year_bits_survive_the_composite(tmp_path):
    """Bit i must still mean years[i] after band-by-band compositing."""
    on = np.ones((1, 2), dtype="uint16")
    bits = np.array([[1, 2]], dtype="uint16")      # one pixel per year
    _province(tmp_path / "A", on, on * 0, bits, west=0.0, north=0.0)
    z = _zones([box(-D, -D, 3 * D, D)], ["all"])
    rows = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS, progress=None)
    by = rows[0]["burned_ha_by_year"]
    assert set(by) == set(YEARS)
    assert all(v > 0 for v in by.values())
    assert rows[0]["repeat_ha"] == 0               # neither pixel burned twice


def test_a_band_boundary_does_not_lose_or_double_a_row(tmp_path):
    """Compositing happens in bands; a zone must not see the seam."""
    h = 7
    on = np.ones((h, 2), dtype="uint16")
    _province(tmp_path / "A", on, on * 0, on, west=0.0, north=0.0)
    z = _zones([box(-D, -h * D - D, 3 * D, D)], ["all"])
    whole = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS,
                          band_rows=64, progress=None)[0]["land_ha"]
    split = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS,
                          band_rows=2, progress=None)[0]["land_ha"]
    assert whole == pytest.approx(split, abs=0.2)


# --- peat ------------------------------------------------------------------
def test_peat_columns_are_named_after_their_definition(tmp_path):
    on = np.ones((1, 2), dtype="uint16")
    peat = np.array([[1, 0]], dtype="uint16")
    _province(tmp_path / "A", on, peat, on, west=0.0, north=0.0)
    z = _zones([box(-D, -D, 3 * D, D)], ["all"])
    r = fz.zone_stats(str(tmp_path), z, "code", YEARS, KEYS,
                      progress=None)[0]
    assert "peat_ha_soc" in r and "burned_peat_ha_soc" in r
    assert "peat_ha" not in r and "burned_peat_ha" not in r
    assert r["peat_share_of_burned_pct_soc"] == pytest.approx(50.0)


# --- inputs ----------------------------------------------------------------
def test_a_missing_run_directory_says_to_run_fire_national(tmp_path):
    with pytest.raises(SystemExit) as e:
        fz._raster_frames(str(tmp_path))
    assert "fire-national" in str(e.value)


def test_rasters_with_different_band_counts_are_refused(tmp_path):
    on = np.ones((1, 2), dtype="uint16")
    _province(tmp_path / "A", on, on * 0, on, west=0.0, north=0.0)
    p = tmp_path / "B"
    p.mkdir()
    with rasterio.open(p / "recurrence.tif", "w", driver="GTiff", width=2,
                       height=1, count=4, dtype="uint16", crs="EPSG:4326",
                       transform=from_origin(0.0, 0.0, D, D)) as ds:
        for i in range(1, 5):
            ds.write(on, i)
    with pytest.raises(SystemExit) as e:
        fz._raster_frames(str(tmp_path))
    assert "band counts" in str(e.value)


def test_a_zone_field_that_is_not_there_lists_what_is(tmp_path):
    z = _zones([box(0, 0, 1, 1)], ["x"], field="kode")
    f = tmp_path / "z.gpkg"
    z.to_file(f, driver="GPKG")
    with pytest.raises(SystemExit) as e:
        fz._read_zones(str(f), "nope")
    assert "kode" in str(e.value)


def test_the_label_rides_along_with_the_key(tmp_path):
    """KHG is keyed by a code; the chart needs the name."""
    z = _zones([box(0, 0, 1, 1), box(2, 0, 3, 1)], ["K1", "K2"],
               label="nama", labels=["Sungai Satu", "Sungai Dua"])
    f = tmp_path / "z.gpkg"
    z.to_file(f, driver="GPKG")
    got = fz._read_zones(str(f), "code", label="nama")
    assert list(got["nama"]) == ["Sungai Satu", "Sungai Dua"]


def test_parts_sharing_a_code_dissolve_to_one_zone(tmp_path):
    """KHG arrives as 6,405 parts making up 865 units."""
    z = _zones([box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)],
               ["K1", "K1", "K2"])
    f = tmp_path / "z.gpkg"
    z.to_file(f, driver="GPKG")
    got = fz._read_zones(str(f), "code")
    assert len(got) == 2
    assert sorted(got["code"]) == ["K1", "K2"]


# --- what ships with the numbers -------------------------------------------
def test_the_attribution_caveat_is_not_optional():
    """A table of burned hectares per concession is read as an accusation.

    Checks the caveat that actually ships in stats.json, not just the
    docstring: the reader of the table never sees the docstring.
    """
    import inspect
    src = inspect.getsource(fz.run)
    assert "not evidence about who lit it" in src
    assert "say nothing\nabout who lit it" in (fz.__doc__ or "")
