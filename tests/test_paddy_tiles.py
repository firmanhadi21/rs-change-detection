"""The tile index and the island machinery.

What these protect: tiles must tessellate and share one grid (or the mosaic is
a lie), the order must be richest-first (or stopping early loses rice), and an
empty tile must be recorded with its reason (or "the radar left a hole here"
becomes indistinguishable from "there is no paddy here").
"""
import json
import os

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from earthchange import paddy_data as pdata
from earthchange import paddy_island as pisl
from earthchange import paddy_tiles as ptiles


# --- islands ---------------------------------------------------------------
def test_island_lookup_covers_the_rice_islands():
    assert ptiles.island_of(110.85, -6.95) == "Jawa"
    assert ptiles.island_of(98.7, 3.6) == "Sumatera"
    assert ptiles.island_of(119.5, -4.0) == "Sulawesi"
    assert ptiles.island_of(115.2, -8.5) == "Bali-NusaTenggara"
    assert ptiles.island_of(114.5, -2.2) == "Kalimantan"
    assert ptiles.island_of(140.0, -4.0) == "Papua"
    assert ptiles.island_of(0.0, 0.0) == "lain"


def test_overlaps_resolve_by_priority_not_by_accident():
    """The Sunda strait sliver is Jawa, because Jawa is checked first."""
    assert ptiles.island_of(105.5, -6.0) == "Jawa"
    # ... and a point clearly on Sumatera still reads Sumatera
    assert ptiles.island_of(104.0, -4.0) == "Sumatera"


# --- the index -------------------------------------------------------------
def _paddy_raster(path, blocks, deg=0.0005, origin=(110.0, -7.0), n=400):
    """A small WGS84 paddy raster: `blocks` is a list of (row0, col0, size)."""
    arr = np.zeros((n, n), dtype="uint8")
    for r0, c0, size in blocks:
        arr[r0:r0 + size, c0:c0 + size] = 1
    t = rasterio.Affine(deg, 0, origin[0], 0, -deg, origin[1])
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="uint8", crs="EPSG:4326", transform=t) as dst:
        dst.write(arr, 1)
    return str(path)


def test_index_finds_only_tiles_holding_paddy(tmp_path):
    # 400 px at 0.0005 deg = 0.2 deg across: two 0.125 deg tiles per axis
    p = _paddy_raster(tmp_path / "p.tif", [(10, 10, 40)])
    rows = ptiles.index(p, tile_deg=0.125, cell_deg=0.01)
    assert len(rows) == 1
    assert rows[0]["paddy_ha"] > 0
    assert rows[0]["lon_min"] <= 110.005 <= rows[0]["lon_max"]


def test_index_is_ordered_richest_first(tmp_path):
    p = _paddy_raster(tmp_path / "p.tif",
                      [(10, 10, 20), (10, 300, 60), (300, 10, 40)])
    rows = ptiles.index(p, tile_deg=0.125, cell_deg=0.01)
    areas = [r["paddy_ha"] for r in rows]
    assert areas == sorted(areas, reverse=True)
    assert len(rows) >= 2


def test_tile_ids_are_stable_and_bounds_tessellate(tmp_path):
    p = _paddy_raster(tmp_path / "p.tif", [(10, 10, 20), (10, 300, 60)])
    a = ptiles.index(p, tile_deg=0.125, cell_deg=0.01)
    b = ptiles.index(p, tile_deg=0.125, cell_deg=0.01)
    assert [r["tile_id"] for r in a] == [r["tile_id"] for r in b]
    for r in a:                        # every tile is exactly one tile wide
        assert r["lon_max"] - r["lon_min"] == pytest.approx(0.125)
        assert r["lat_max"] - r["lat_min"] == pytest.approx(0.125)
        # and sits on the tile lattice measured from the layer's own corner
        assert ((r["lon_min"] - 110.0) / 0.125) % 1 == pytest.approx(0, abs=1e-9)


def test_min_ha_drops_the_slivers(tmp_path):
    p = _paddy_raster(tmp_path / "p.tif", [(10, 10, 40), (300, 300, 1)])
    everything = ptiles.index(p, tile_deg=0.125, cell_deg=0.01, min_ha=0.0)
    trimmed = ptiles.index(p, tile_deg=0.125, cell_deg=0.01, min_ha=10.0)
    assert len(trimmed) < len(everything)


def test_index_refuses_a_layer_coarser_than_its_own_grid(tmp_path):
    p = _paddy_raster(tmp_path / "coarse.tif", [(1, 1, 3)], deg=0.05, n=20)
    with pytest.raises(SystemExit):
        ptiles.index(p, tile_deg=0.125, cell_deg=0.01)


# --- select ----------------------------------------------------------------
def _rows(*areas, island="Jawa"):
    return [{"tile_id": f"t{i:04d}_0000", "island": island, "paddy_ha": a,
             "lon_min": 110.0 + i * 0.125, "lon_max": 110.125 + i * 0.125,
             "lat_min": -7.0, "lat_max": -6.875,
             "lon_c": 110.06 + i * 0.125, "lat_c": -6.94}
            for i, a in enumerate(sorted(areas, reverse=True))]


def test_coverage_keeps_the_richest_tiles_only():
    rows = _rows(100, 50, 20, 20, 10)          # 200 ha total
    keep = ptiles.select(rows, coverage=0.75)
    assert [r["paddy_ha"] for r in keep] == [100, 50]      # 150/200 >= 0.75


def test_coverage_of_one_keeps_everything():
    rows = _rows(100, 50, 20)
    assert len(ptiles.select(rows, coverage=1.0)) == 3


def test_island_and_limit_filters():
    rows = _rows(100, 50) + _rows(80, 40, island="Sumatera")
    assert len(ptiles.select(rows, islands=["sumatera"])) == 2
    assert len(ptiles.select(rows, limit=3)) == 3


def test_summarise_totals_per_island():
    rows = _rows(100, 50) + _rows(80, island="Papua")
    got = ptiles.summarise(rows)
    assert got["Jawa"] == {"tiles": 2, "paddy_ha": 150.0}
    assert list(got) == ["Jawa", "Papua"]      # richest island first


def test_csv_round_trip_keeps_types(tmp_path):
    rows = _rows(100, 50)
    p = ptiles.write_csv(rows, str(tmp_path / "i.csv"))
    back = ptiles.read_csv(p)
    assert back[0]["tile_id"] == rows[0]["tile_id"]
    assert isinstance(back[0]["paddy_ha"], float)
    assert back[0]["lon_min"] == pytest.approx(rows[0]["lon_min"])


def test_geojson_polygons_close(tmp_path):
    p = ptiles.write_geojson(_rows(100), str(tmp_path / "i.geojson"))
    gj = json.load(open(p))
    ring = gj["features"][0]["geometry"]["coordinates"][0]
    assert len(ring) == 5 and ring[0] == ring[-1]


# --- orbit choice ----------------------------------------------------------
def test_gaps_counts_holes_and_the_longest_run():
    assert pdata.gaps([1, 1, 1]) == (0, 0)
    assert pdata.gaps([1, 0, 1, 0, 0, 0, 1]) == (4, 3)
    assert pdata.gaps([0, 0]) == (2, 2)


def test_orbit_choice_prefers_the_shorter_hole(monkeypatch):
    """East Java, measured: descending 42 empty with a run of 23; ascending 1."""
    series = {"DESCENDING": [1] * 40 + [0] * 23 + [1] * 22,
              "ASCENDING": [1] * 50 + [0] + [1] * 34}
    monkeypatch.setattr(pdata, "s1_acquisitions",
                        lambda aoi, grid, p: series[p])
    chosen, counts, g = pdata.pick_orbit(None, [None] * 85)
    assert chosen == "ASCENDING"
    assert g == (1, 1)


def test_orbit_choice_can_pick_descending(monkeypatch):
    """It is not a new constant: one sampled tile really does prefer descending."""
    series = {"DESCENDING": [1] * 80 + [0] * 3 + [1, 1],
              "ASCENDING": [1] * 70 + [0] * 4 + [1] * 11}
    monkeypatch.setattr(pdata, "s1_acquisitions",
                        lambda aoi, grid, p: series[p])
    chosen, _, g = pdata.pick_orbit(None, [None] * 85)
    assert chosen == "DESCENDING"
    assert g == (3, 3)


# --- the mosaic ------------------------------------------------------------
def _tile(path, value, origin, n=10, deg=0.0005, dtype="uint8"):
    t = rasterio.Affine(deg, 0, origin[0], 0, -deg, origin[1])
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=1,
                       dtype=dtype, crs="EPSG:4326", transform=t) as dst:
        dst.write(np.full((n, n), value, dtype=dtype), 1)
    return str(path)


def test_mosaic_places_aligned_tiles_without_resampling(tmp_path):
    """Two tiles side by side land whole, with their own values intact."""
    a = _tile(tmp_path / "a.tif", 1, (110.0, -7.0))
    b = _tile(tmp_path / "b.tif", 2, (110.005, -7.0))   # 10 px to the east
    out = pisl.mosaic_aligned([a, b], str(tmp_path / "m.tif"), "uint8")
    with rasterio.open(out) as ds:
        arr = ds.read(1)
        assert ds.width == 20 and ds.height == 10
        assert ds.transform.c == pytest.approx(110.0)
        assert set(np.unique(arr[:, :10])) == {1}
        assert set(np.unique(arr[:, 10:])) == {2}


def test_mosaic_leaves_gaps_as_nodata_not_zero_paddy(tmp_path):
    a = _tile(tmp_path / "a.tif", 3, (110.0, -7.0))
    b = _tile(tmp_path / "b.tif", 4, (110.02, -7.0))    # a hole between them
    out = pisl.mosaic_aligned([a, b], str(tmp_path / "m.tif"), "uint8",
                              nodata=255)
    with rasterio.open(out) as ds:
        arr = ds.read(1)
        assert ds.nodata == 255
        assert arr[0, 20] == 255                        # inside the hole
        assert arr[0, 0] == 3 and arr[0, -1] == 4


def test_mosaic_of_floats_keeps_nan_outside_the_tiles(tmp_path):
    a = _tile(tmp_path / "a.tif", 1.5, (110.0, -7.0), dtype="float32")
    b = _tile(tmp_path / "b.tif", 2.5, (110.02, -7.0), dtype="float32")
    out = pisl.mosaic_aligned([a, b], str(tmp_path / "m.tif"), "float32")
    with rasterio.open(out) as ds:
        arr = ds.read(1)
        assert np.isnan(arr[0, 20])
        assert arr[0, 0] == pytest.approx(1.5)


def test_mosaic_of_nothing_is_nothing(tmp_path):
    assert pisl.mosaic_aligned([], str(tmp_path / "m.tif"), "uint8") is None


# --- the roll-up -----------------------------------------------------------
def _tile_stats(run_dir, tid, **fields):
    d = pisl.tile_dir(run_dir, tid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "stats.json"), "w") as f:
        json.dump(fields, f)


def test_roll_up_adds_hectares_and_flags_what_it_could_not_score(tmp_path):
    run = str(tmp_path / "run")
    rows = _rows(100, 60, 40)
    ids = [r["tile_id"] for r in rows]
    _tile_stats(run, ids[0], paddy_ha=100.0, planted_ha=60.0,
                not_planted_ha=40.0, adequacy_ha={"Cukup": 10.0},
                season_length_days_median=90.0, median_delay_days=6.0,
                orbit_pass="ASCENDING",
                radar_coverage={"empty_periods": 1, "longest_gap": 1})
    _tile_stats(run, ids[1], paddy_ha=60.0, planted_ha=30.0,
                not_planted_ha=30.0, adequacy_ha={"Cukup": 5.0},
                season_length_days_median=100.0, median_delay_days=12.0,
                orbit_pass="ASCENDING",
                radar_coverage={"empty_periods": 2, "longest_gap": 2})
    _tile_stats(run, ids[2], empty=True, reason="radar coverage",
                longest_gap=7, paddy_ha=0.0)

    got = pisl.roll_up(rows, run, "Jawa", "2026-09-27", len(rows))
    assert got["paddy_ha"] == 160.0
    assert got["planted_ha"] == 90.0
    assert got["adequacy_ha"]["Cukup"] == 15.0
    assert got["not_planted_pct"] == pytest.approx(43.8, abs=0.1)
    assert got["tiles"]["with_products"] == 2
    assert got["tiles"]["empty"] == 1
    # the third tile's 40 ha are NOT silently dropped from the picture
    assert got["tiles"]["unscored_paddy_ha"] == 40.0
    assert got["tiles"]["orbit_pass"] == {"ASCENDING": 2}
    # medians of medians are labelled as such, never passed off as pixel medians
    assert "note" in got["season_length_note"] or got["season_length_note"]
    assert got["median_delay_days"] == 9.0


def test_roll_up_weights_season_length_by_area(tmp_path):
    """A tile with most of the rice should dominate the island's season length."""
    run = str(tmp_path / "run")
    rows = _rows(1000, 10)
    ids = [r["tile_id"] for r in rows]
    _tile_stats(run, ids[0], paddy_ha=1000.0, season_length_days_median=95.0)
    _tile_stats(run, ids[1], paddy_ha=10.0, season_length_days_median=130.0)
    got = pisl.roll_up(rows, run, "Jawa", "2026-09-27", 2)
    assert got["season_length_days_median"] == 95.0


def test_a_finished_tile_is_not_run_again(tmp_path):
    run = str(tmp_path / "run")
    _tile_stats(run, "t0001_0001", paddy_ha=1.0)
    assert pisl.tile_done(run, "t0001_0001")
    assert not pisl.tile_done(run, "t0002_0002")


def test_island_bbox_is_the_union_of_its_tiles():
    rows = _rows(100, 50)
    bbox = pisl.island_bbox(rows)
    assert bbox[0] == min(r["lon_min"] for r in rows)
    assert bbox[2] == max(r["lon_max"] for r in rows)
