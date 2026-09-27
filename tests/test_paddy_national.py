"""The national roll-up across islands.

The point of these: a national figure must never imply coverage it does not
have. An island that has not run is named, with the hectares the index says it
holds -- not silently counted as zero paddy or zero drought.
"""
import json
import os

import pytest

from earthchange import paddy_island as pisl
from earthchange import paddy_tiles as ptiles


def _island(base, name, **fields):
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "stats.json"), "w") as f:
        json.dump({"island": name, "as_of": "2026-09-27", **fields}, f)


def _index(base, rows):
    ptiles.write_csv(rows, os.path.join(base, "tile_index_all.csv"))


def _rows(island, n, ha):
    return [{"tile_id": f"t{i:04d}_0000", "island": island, "paddy_ha": ha,
             "lon_min": 110.0, "lon_max": 110.125, "lat_min": -7.0,
             "lat_max": -6.875, "lon_c": 110.06, "lat_c": -6.94}
            for i in range(n)]


def test_national_adds_the_islands_that_ran(tmp_path):
    base = str(tmp_path)
    _island(base, "Jawa", paddy_ha=3000.0, planted_ha=1200.0,
            not_planted_ha=1800.0, anomaly_ha={"Normal": 800.0},
            puso_candidates_ha=50.0)
    _island(base, "Sulawesi", paddy_ha=1000.0, planted_ha=600.0,
            not_planted_ha=400.0, anomaly_ha={"Normal": 300.0},
            puso_candidates_ha=10.0)
    got = pisl.national(base)
    assert got["headline"]["paddy_ha"] == 4000.0
    assert got["headline"]["planted_ha"] == 1800.0
    assert got["headline"]["anomaly_ha"]["Normal"] == 1100.0
    assert got["headline"]["puso_candidates_ha"] == 60.0
    assert got["headline"]["not_planted_pct"] == pytest.approx(55.0)
    assert set(got["islands"]) == {"Jawa", "Sulawesi"}


def test_islands_that_did_not_run_are_named_not_zeroed(tmp_path):
    base = str(tmp_path)
    _index(base, _rows("Jawa", 2, 1500.0) + _rows("Sumatera", 3, 500.0))
    _island(base, "Jawa", paddy_ha=3000.0, planted_ha=1000.0,
            not_planted_ha=2000.0)
    got = pisl.national(base)
    assert "Sumatera" in got["islands_not_run"]
    assert got["islands_not_run"]["Sumatera"]["index_paddy_ha"] == 1500.0
    assert got["coverage"]["paddy_ha_scored"] == 3000.0
    assert got["coverage"]["paddy_ha_not_run"] >= 1500.0
    # the national total is NOT presented as the country's paddy
    assert "only the islands that have run" in got["coverage"]["note"]["en"]


def test_national_summary_is_written_and_points_at_each_island(tmp_path):
    base = str(tmp_path)
    _island(base, "Jawa", paddy_ha=10.0)
    pisl.national(base)
    p = os.path.join(base, "national_summary.json")
    assert os.path.exists(p)
    s = json.load(open(p))
    assert s["islands"]["Jawa"]["web"] == "Jawa/web/"
    assert s["scope"] == "national"
    assert s["caveats"]


def test_national_carries_the_scenario_caveats(tmp_path):
    base = str(tmp_path)
    _island(base, "Jawa", paddy_ha=10.0)
    got = pisl.national(base)
    joined = " ".join(got["caveats"])
    assert "puso" in joined.lower()
    assert "WaPOR" in joined


def test_an_empty_base_is_not_a_national_figure_of_zero(tmp_path):
    got = pisl.national(str(tmp_path))
    assert got["islands"] == {}
    assert got["headline"].get("paddy_ha") is None
    assert len(got["islands_not_run"]) == len(ptiles.ISLANDS)


# --- island-specific caveats ----------------------------------------------
def test_kalimantan_says_its_rice_is_tidal_or_rainfed():
    got = pisl.island_caveats("Kalimantan", "en", 55.66)
    assert "tidal or rainfed" in got[0]
    # and it comes first, before the generic scenario limits
    assert "WaPOR" in " ".join(got[1:])


def test_an_island_without_a_note_gets_the_plain_caveats():
    plain = pisl.island_caveats("Jawa", "en", 55.66)
    from earthchange import paddy_publish as ppub
    assert plain == ppub.caveats("en", 55.66)


def test_island_notes_exist_in_both_languages():
    for name, note in pisl.ISLAND_NOTES.items():
        assert set(note) == {"id", "en"}, name
        assert note["id"] and note["en"]
