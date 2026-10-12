"""The national fire-recurrence accounting, on rasters built by hand.

Two things are worth protecting here. The year-per-bit packing is the only
copy of the annual record once the download is done, so a bit read at the
wrong offset would silently reassign a fire to another year. And "burned area"
has two meanings that differ by a factor of several in Riau -- the distinct
area that burned at least once, and the sum of the annual figures -- so the
module must not quietly return one when the reader expects the other.
"""
import json
import math

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin                      # noqa: E402

from earthchange import fire_national as fn                     # noqa: E402


YEARS = [2015, 2016, 2017, 2018]


KEYS = ["soc"]


def _write(tmp_path, inside, peat, bits, west=110.0, north=-2.0, deg=0.0045,
           extra_peat=None):
    """A uint16 stack shaped exactly like a downloaded province.

    inside, one band per peat definition, then bits -- always last.
    """
    path = tmp_path / "recurrence.tif"
    h, w = inside.shape
    peats = [peat] if extra_peat is None else [peat, extra_peat]
    bands = [inside, *peats, bits]
    prof = {"driver": "GTiff", "width": w, "height": h, "count": len(bands),
            "dtype": "uint16", "crs": "EPSG:4326",
            "transform": from_origin(west, north, deg, deg)}
    with rasterio.open(path, "w", **prof) as ds:
        for i, a in enumerate(bands, start=1):
            ds.write(a.astype("uint16"), i)
    return str(path)


# --- the bitmask -----------------------------------------------------------
def test_popcount_table_covers_every_uint16():
    t = fn._popcount()
    assert len(t) == 1 << fn.MAX_YEARS
    assert t[0] == 0 and t[1] == 1 and t[0b1011] == 3
    assert t[(1 << fn.MAX_YEARS) - 1] == fn.MAX_YEARS


def test_each_year_is_read_from_its_own_bit(tmp_path):
    """Bit i must mean years[i], not years[i] off by one."""
    inside = np.ones((1, 4), dtype="uint16")
    bits = np.array([[1, 2, 4, 8]], dtype="uint16")   # one pixel per year
    tif = _write(tmp_path, inside, np.zeros((1, 4), "uint16"), bits)
    st = fn.province_stats(tif, YEARS, KEYS)
    by = st["burned_ha_by_year"]
    assert sorted(by) == YEARS
    # every year burned exactly one pixel, and they are all the same size
    assert len({round(v, 3) for v in by.values()}) == 1
    assert all(v > 0 for v in by.values())
    assert st["max_times"] == 1
    assert st["repeat_ha"] == 0


def test_a_pixel_burning_four_times_is_one_hectare_not_four(tmp_path):
    """The distinction the note in stats.json exists to make."""
    inside = np.ones((1, 1), dtype="uint16")
    bits = np.array([[0b1111]], dtype="uint16")
    tif = _write(tmp_path, inside, np.zeros((1, 1), "uint16"), bits)
    st = fn.province_stats(tif, YEARS, KEYS)
    annual = sum(st["burned_ha_by_year"].values())
    assert st["burned_ha"] == pytest.approx(annual / 4, rel=1e-9)
    assert st["max_times"] == 4
    assert st["repeat_ha"] == pytest.approx(st["burned_ha"])
    assert st["repeat3_ha"] == pytest.approx(st["burned_ha"])


def test_recurrence_histogram_partitions_the_burned_area(tmp_path):
    inside = np.ones((1, 4), dtype="uint16")
    bits = np.array([[0b1, 0b11, 0b111, 0]], dtype="uint16")
    tif = _write(tmp_path, inside, np.zeros((1, 4), "uint16"), bits)
    st = fn.province_stats(tif, YEARS, KEYS)
    assert sorted(st["recurrence_ha"]) == [1, 2, 3]
    assert sum(st["recurrence_ha"].values()) == pytest.approx(st["burned_ha"],
                                                              abs=0.15)


# --- what counts as inside -------------------------------------------------
def test_outside_the_province_counts_for_nothing(tmp_path):
    """A clipped download pads the bounding box with zeros, not with land."""
    inside = np.array([[1, 1, 0, 0]], dtype="uint16")
    peat = np.ones((1, 4), dtype="uint16")
    bits = np.array([[1, 0, 1, 1]], dtype="uint16")
    tif = _write(tmp_path, inside, peat, bits)
    st = fn.province_stats(tif, YEARS, KEYS)
    one = st["land_ha"] / 2
    assert st["land_ha"] == pytest.approx(2 * one)
    assert st["peat_ha_soc"] == pytest.approx(2 * one)   # peat clipped to inside
    # the two burned pixels outside the province are not counted as peat burn
    assert st["burned_peat_ha_soc"] == pytest.approx(one)


def test_peat_share_is_of_burned_area_not_of_land(tmp_path):
    inside = np.ones((1, 4), dtype="uint16")
    peat = np.array([[1, 1, 0, 0]], dtype="uint16")
    bits = np.array([[1, 0, 1, 0]], dtype="uint16")
    tif = _write(tmp_path, inside, peat, bits)
    st = fn.province_stats(tif, YEARS, KEYS)
    assert st["peat_share_of_burned_pct_soc"] == pytest.approx(50.0)
    assert st["burned_pct_of_land"] == pytest.approx(50.0)


# --- two peat definitions, carried rather than chosen between ---------------
def test_both_peat_definitions_survive_to_a_range(tmp_path):
    """Riau: soc gives 3.9 Mha and peatgrids 5.8. Neither may be hidden."""
    inside = np.ones((1, 4), dtype="uint16")
    soc = np.array([[1, 0, 0, 0]], dtype="uint16")
    pg = np.array([[1, 1, 1, 0]], dtype="uint16")
    bits = np.ones((1, 4), dtype="uint16")
    tif = _write(tmp_path, inside, soc, bits, extra_peat=pg)
    st = fn.province_stats(tif, YEARS, ["soc", "peatgrids"])
    assert st["burned_peat_ha_soc"] < st["burned_peat_ha_peatgrids"]
    lo, hi = st["burned_peat_ha_range"]
    assert lo == st["burned_peat_ha_soc"] and hi == st["burned_peat_ha_peatgrids"]
    assert st["peat_share_of_burned_pct_range"] == [25.0, 75.0]
    # and no unqualified figure exists for a reader to quote by mistake
    assert "burned_peat_ha" not in st and "peat_ha" not in st


def test_one_definition_collapses_the_range_rather_than_dropping_it(tmp_path):
    inside = np.ones((1, 2), dtype="uint16")
    peat = np.array([[1, 0]], dtype="uint16")
    tif = _write(tmp_path, inside, peat, np.ones((1, 2), "uint16"))
    st = fn.province_stats(tif, YEARS, KEYS)
    lo, hi = st["burned_peat_ha_range"]
    assert lo == hi == st["burned_peat_ha_soc"]


def test_a_supplied_peat_map_leads_and_the_proxies_survive(tmp_path):
    """Gumbricht is the citable number; the spread it sits in still ships."""
    one = np.ones((1, 4), dtype="uint16")
    tif = _write(tmp_path, one,
                 np.zeros((1, 4), "uint16"),            # the file band: zeros
                 one)
    # rebuild with four peat bands by hand: file, soc, peatgrids, then bits
    with rasterio.open(tif) as ds:
        tr, crs = ds.transform, ds.crs
    bands = [one, np.zeros((1, 4), "uint16"),
             np.array([[1, 1, 0, 0]], "uint16"),
             np.array([[1, 1, 1, 0]], "uint16"), one]
    with rasterio.open(tif, "w", driver="GTiff", width=4, height=1,
                       count=len(bands), dtype="uint16", crs=crs,
                       transform=tr) as ds:
        for i, a in enumerate(bands, start=1):
            ds.write(a, i)
    peat = tmp_path / "peat.tif"
    with rasterio.open(peat, "w", driver="GTiff", width=4, height=1, count=1,
                       dtype="uint8", crs=crs, transform=tr) as ds:
        ds.write(np.array([[1, 0, 0, 0]], "uint8"), 1)
    st = fn.province_stats(tif, [2015], ["file", "soc", "peatgrids"],
                           peat_file=str(peat))
    assert (st["burned_peat_ha_file"] < st["burned_peat_ha_soc"]
            < st["burned_peat_ha_peatgrids"])
    assert st["burned_peat_ha_range"][0] == st["burned_peat_ha_file"]


# --- a supplied raster finer than the fire grid ----------------------------
def _peat_raster(path, arr, west, north, deg, nodata=None, dtype="float32"):
    h, w = arr.shape
    prof = {"driver": "GTiff", "width": w, "height": h, "count": 1,
            "dtype": dtype, "crs": "EPSG:4326",
            "transform": from_origin(west, north, deg, deg)}
    if nodata is not None:
        prof["nodata"] = nodata
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(arr.astype(dtype), 1)
    return str(path)


def test_a_finer_peat_raster_becomes_a_fraction_not_a_coin_flip(tmp_path):
    """Half a cell of peat must read as half, not as all or nothing."""
    one = np.ones((1, 1), dtype="uint16")
    tif = _write(tmp_path, one, np.zeros((1, 1), "uint16"), one,
                 west=110.0, north=-2.0)
    # ten sub-pixels across one fire cell; four of them are peat
    sub = np.zeros((10, 10), dtype="float32")
    sub[:, :4] = 1.0
    peat = _peat_raster(tmp_path / "p.tif", sub, 110.0, -2.0, 0.0045 / 10)
    frac, cov = fn._local_peat(peat, tif)
    assert cov.all()
    assert frac[0, 0] == pytest.approx(0.4, abs=0.02)


def test_nodata_averages_in_as_not_peat(tmp_path):
    """Declared to GDAL, average skips nodata and one peat pixel reads 1.0."""
    one = np.ones((1, 1), dtype="uint16")
    tif = _write(tmp_path, one, np.zeros((1, 1), "uint16"), one,
                 west=110.0, north=-2.0)
    sub = np.full((10, 10), -99999.0, dtype="float32")
    sub[0, 0] = 1.0                       # exactly one peat pixel in a hundred
    peat = _peat_raster(tmp_path / "p.tif", sub, 110.0, -2.0, 0.0045 / 10,
                        nodata=-99999.0)
    frac, _ = fn._local_peat(peat, tif)
    assert frac[0, 0] == pytest.approx(0.01, abs=0.005)


def test_a_threshold_turns_a_thickness_grid_into_peat(tmp_path):
    """Indonesia's official definition cuts at 50 cm, not at any depth."""
    one = np.ones((1, 1), dtype="uint16")
    tif = _write(tmp_path, one, np.zeros((1, 1), "uint16"), one,
                 west=110.0, north=-2.0)
    sub = np.zeros((10, 10), dtype="float32")
    sub[:, :5] = 20.0                      # shallow, below the cut
    sub[:, 5:] = 80.0                      # deep
    peat = _peat_raster(tmp_path / "p.tif", sub, 110.0, -2.0, 0.0045 / 10)
    assert fn._local_peat(peat, tif)[0][0, 0] == pytest.approx(1.0, abs=0.02)
    deep = fn._local_peat(peat, tif, thr=50.0)[0][0, 0]
    assert deep == pytest.approx(0.5, abs=0.02)


def test_where_the_supplied_map_does_not_reach_is_unknown_not_zero(tmp_path):
    """A one-island map must not report the mainland as having no peat."""
    one = np.ones((1, 2), dtype="uint16")
    tif = _write(tmp_path, one, np.zeros((1, 2), "uint16"), one,
                 west=110.0, north=-2.0)
    far = _peat_raster(tmp_path / "p.tif", np.ones((4, 4), "float32"),
                       130.0, -2.0, 0.0045)
    st = fn.province_stats(tif, YEARS, ["file"], peat_file=far)
    assert st["peat_coverage_pct_file"] == 0.0
    assert st["burned_peat_ha_file"] is None
    assert st["peat_share_of_burned_pct_file"] is None
    assert st["burned_peat_ha_range"] is None


def test_an_uncovered_definition_does_not_drag_the_range_to_zero(tmp_path):
    """Riau's soc/peatgrids range must survive a Kalimantan-only raster."""
    one = np.ones((1, 2), dtype="uint16")
    tif = _write(tmp_path, one, np.zeros((1, 2), "uint16"), one,
                 west=110.0, north=-2.0)
    with rasterio.open(tif) as ds:
        tr, crs = ds.transform, ds.crs
    bands = [one, np.zeros((1, 2), "uint16"),
             np.array([[1, 0]], "uint16"), np.array([[1, 1]], "uint16"), one]
    with rasterio.open(tif, "w", driver="GTiff", width=2, height=1,
                       count=len(bands), dtype="uint16", crs=crs,
                       transform=tr) as ds:
        for i, a in enumerate(bands, start=1):
            ds.write(a, i)
    far = _peat_raster(tmp_path / "p.tif", np.ones((4, 4), "float32"),
                       130.0, -2.0, 0.0045)
    st = fn.province_stats(tif, YEARS, ["file", "soc", "peatgrids"],
                           peat_file=far)
    assert st["burned_peat_ha_file"] is None
    lo, hi = st["peat_share_of_burned_pct_range"]
    assert lo == pytest.approx(50.0) and hi == pytest.approx(100.0)


def test_a_stack_whose_bands_do_not_match_the_keys_is_refused(tmp_path):
    """A cache written under one set of peat definitions, read under another."""
    inside = np.ones((1, 2), dtype="uint16")
    tif = _write(tmp_path, inside, inside, inside)        # 3 bands, one peat
    with pytest.raises(SystemExit):
        fn.province_stats(tif, YEARS, ["soc", "peatgrids"])


# --- areas -----------------------------------------------------------------
def test_rows_shrink_towards_the_pole(tmp_path):
    """The same pixel is smaller at 10 degrees than on the equator."""
    inside = np.ones((3, 1), dtype="uint16")
    z = np.zeros((3, 1), dtype="uint16")
    for sub in ("a", "b"):
        (tmp_path / sub).mkdir()
    eq = fn.province_stats(_write(tmp_path / "a", inside, z, z + 1, north=0.5),
                           YEARS, KEYS)["land_ha"]
    hi = fn.province_stats(_write(tmp_path / "b", inside, z, z + 1, north=-10.0),
                           YEARS, KEYS)["land_ha"]
    assert hi < eq
    assert hi / eq == pytest.approx(math.cos(math.radians(10.0)), abs=2e-3)


def test_area_matches_the_drought_repo_formula(tmp_path):
    """The same spherical formula paddy_island uses, so two products agree."""
    from earthchange.paddy_island import row_areas_ha
    inside = np.ones((4, 5), dtype="uint16")
    z = np.zeros((4, 5), dtype="uint16")
    tif = _write(tmp_path, inside, z, z)
    with rasterio.open(tif) as ds:
        want = float(row_areas_ha(ds.transform, ds.height).sum() * ds.width)
    # equal to the 0.1 ha the figures are published at, not merely close
    assert fn.province_stats(tif, YEARS, KEYS)["land_ha"] == round(want, 1)


def test_the_national_extent_comes_from_the_rasters_not_earth_engine(tmp_path):
    """GAUL's Indonesia unions to 2.49 M edges and Earth Engine refuses it."""
    one = np.ones((2, 2), dtype="uint16")
    for sub, west, north in (("A", 95.0, 6.0), ("B", 140.0, -9.0)):
        (tmp_path / sub).mkdir()
        _write(tmp_path / sub, one, one, one, west=west, north=north)
    w, s, e, n = fn.mosaic_bounds(str(tmp_path))
    assert w == pytest.approx(95.0)
    assert n == pytest.approx(6.0)
    assert e > 140.0 and s < -9.0


def test_an_empty_run_directory_says_so_rather_than_mapping_nothing(tmp_path):
    with pytest.raises(SystemExit):
        fn.mosaic_bounds(str(tmp_path))


# --- the grid --------------------------------------------------------------
def test_every_province_lands_on_one_global_lattice():
    """Anchored at zero, so 38 rasters mosaic without being resampled."""
    t = fn.grid_transform()
    assert t == [fn.GRID_DEG, 0.0, 0.0, 0.0, -fn.GRID_DEG, 0.0]
    assert 490 < fn.GRID_DEG * 111320 < 510


def test_years_beyond_the_bitmask_are_refused():
    with pytest.raises(SystemExit):
        fn.burn_bits(list(range(2000, 2000 + fn.MAX_YEARS + 1)))


# --- resumability ----------------------------------------------------------
def test_a_truncated_download_is_not_treated_as_cached(tmp_path):
    """An interrupted fetch leaves a readable header over missing pixels."""
    inside = np.ones((8, 8), dtype="uint16")
    tif = _write(tmp_path, inside, inside * 0, inside)
    assert fn._usable(tif, 3)
    with open(tif, "r+b") as f:        # lop off the tail, keep the header
        f.truncate(int(f.seek(0, 2) * 0.4))
    assert not fn._usable(tif, 3)


def test_a_cache_from_other_peat_definitions_is_refetched(tmp_path):
    """Three bands held one peat layer; a two-peat run needs four."""
    inside = np.ones((4, 4), dtype="uint16")
    tif = _write(tmp_path, inside, inside, inside)
    assert fn._usable(tif, 3)
    assert not fn._usable(tif, 4)


# --- the season ------------------------------------------------------------
def test_hotspot_ratio_excludes_the_current_year_from_its_own_baseline():
    series = {2023: {"Riau": 100}, 2024: {"Riau": 200}, 2025: {"Riau": 900}}
    out = fn._hotspot_summary(series, 2025)["Riau"]
    assert out["hotspots_baseline"] == pytest.approx(150.0)
    assert out["hotspots_ratio"] == pytest.approx(6.0)


def test_a_province_with_no_history_gets_no_ratio_rather_than_infinity():
    series = {2024: {"Papua Selatan": 0}, 2025: {"Papua Selatan": 500}}
    out = fn._hotspot_summary(series, 2025)["Papua Selatan"]
    assert out["hotspots_ratio"] is None


# --- what ships with the numbers -------------------------------------------
def test_slug_survives_a_province_with_spaces():
    assert fn.slug("Kalimantan Tengah") == "Kalimantan_Tengah"
    assert fn.slug("Daerah Istimewa Yogyakarta") == "Daerah_Istimewa_Yogyakarta"


def test_csv_header_and_stats_keys_agree(tmp_path):
    """Every CSV column is something province_stats or the hotspots produce."""
    inside = np.ones((2, 2), dtype="uint16")
    keys = ["soc", "peatgrids"]
    tif = _write(tmp_path, inside, inside, inside, extra_peat=inside)
    st = fn.province_stats(tif, YEARS, keys)
    st["province"] = "Test"
    produced = set(st) | {"hotspots_season", "hotspots_baseline", "hotspots_ratio"}
    assert set(fn.csv_fields(keys)) <= produced


def test_the_csv_names_its_peat_columns_after_the_definition():
    """A column called peat_ha would not say which peat map it came from."""
    cols = fn.csv_fields(["soc", "peatgrids"])
    assert "peat_ha" not in cols
    assert "peat_ha_soc" in cols and "peat_ha_peatgrids" in cols
    assert len(cols) == len(set(cols))


def test_the_attribution_caveat_is_not_optional():
    """A map of burn scars inside concessions is read as an accusation."""
    src = (fn.__doc__ or "") + json.dumps(fn.run.__doc__ or "")
    assert "not evidence" in src
