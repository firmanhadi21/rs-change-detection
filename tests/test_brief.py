"""fire-brief assembly.

The brief's job is to pick the six claims that carry the argument out of
eighteen figures. What can go wrong is picking the wrong thing and stating it
confidently, so that is what these cover.
"""

import json
import os

import pytest

from earthchange import brief


# --------------------------------------------------------------------------
# Zone selection — the bug that put a puddle in the headline
# --------------------------------------------------------------------------

ZONES_DANGER = {
    "AREA PENGGUNAAN LAIN": {"total_ha": 1393456.1,
                             "pct_by_class": {"Sedang": 38.8, "Tinggi": 57.6}},
    "CAGAR ALAM": {"total_ha": 153274.0,
                   "pct_by_class": {"Sedang": 1.3, "Tinggi": 73.7}},
    # 276 ha of water in a 3.4 Mha district, and being a puddle it dries fastest.
    "LAUT/AIR": {"total_ha": 300.0,
                 "pct_by_class": {"Tinggi": 66.7, "Ekstrem": 33.3}},
}


def test_driest_zone_ignores_slivers():
    got = brief._driest_zone({"zones": {"zones": ZONES_DANGER}})
    assert got is not None
    assert got[0] == "CAGAR ALAM", got


def test_driest_zone_reads_pct_by_class():
    """Not `pct` or `class_pct`: guessing the key silently produced no sentence
    at all, which is worse than a wrong one because nobody notices."""
    name, share = brief._driest_zone({"zones": {"zones": ZONES_DANGER}})
    assert share == pytest.approx(73.7)


def test_driest_zone_handles_a_missing_layer():
    assert brief._driest_zone({}) is None
    assert brief._driest_zone({"zones": {"zones": []}}) is None


def test_material_keeps_everything_when_all_zones_are_large():
    entries = {"a": {"area_ha": 100.0}, "b": {"area_ha": 100.0}}
    assert set(brief._material(entries, "area_ha")) == {"a", "b"}


def test_material_drops_below_one_percent():
    entries = {"big": {"area_ha": 1_000_000.0}, "sliver": {"area_ha": 100.0}}
    assert set(brief._material(entries, "area_ha")) == {"big"}


# --------------------------------------------------------------------------
# Claims
# --------------------------------------------------------------------------

def test_record_claim_picks_a_material_zone_not_the_driest_sliver():
    s = {"zones": {
        "CAGAR ALAM": {"area_ha": 153164.0, "dc_peak": 317.7,
                       "dc_class_at_peak": "Tinggi",
                       "first_crossed": {"Sedang": "2026-07-17",
                                         "Tinggi": "2026-08-01"},
                       "hotspots_total": 284},
        "LAUT/AIR": {"area_ha": 276.0, "dc_peak": 323.6,
                     "dc_class_at_peak": "Tinggi", "first_crossed": {}},
    }}
    out = brief._claim_record(s, "en")
    assert "CAGAR ALAM" in out and "LAUT/AIR" not in out


def test_record_claim_marks_a_censored_crossing():
    s = {"zones": {"Z": {"area_ha": 1000.0, "dc_peak": 300,
                         "dc_class_at_peak": "Tinggi",
                         "first_crossed": {"Tinggi": "2026-01-05"},
                         "first_crossed_censored": {"Tinggi": True}}}}
    assert "sebelum" in brief._claim_record(s, "en")


def test_exposure_claim_omits_classes_nobody_was_in():
    s = {"totals": {"population": 100, "under5": 5, "over65": 3,
                    "person_days_unhealthy": 42,
                    "person_days_by_class": {"Baik": 900, "Tidak Sehat": 42,
                                             "Berbahaya": 0}},
         "districts": {}}
    out = brief._claim_exposure(s, "en")
    assert "Berbahaya" not in out and "Tidak Sehat" in out


def test_track_claim_distinguishes_the_two_directions():
    fwd = {"direction": "forward", "day": "2026-08-01", "hours": 48,
           "engine": "kinematic", "median_path_km": 414.4,
           "districts_crossed": {"Ketapang": 25}}
    back = dict(fwd, direction="backward", engine="hysplit",
                receptors=[{"name": "Kuching", "pm25": 51.8}])
    assert "from the fires" in brief._claim_track(fwd, "en")
    assert "Receptors" in brief._claim_track(back, "en")


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def _write_step(root, folder, stats, figure="x.png"):
    d = os.path.join(root, folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "stats.json"), "w") as f:
        json.dump(stats, f)
    if figure:
        # A 1x1 PNG, enough for the inliner to find and encode.
        with open(os.path.join(d, figure), "wb") as f:
            f.write(bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000"
                "001f15c4890000000a49444154789c6300010000050001"
                "0d0a2db40000000049454e44ae426082"))
    return d


def test_load_keys_smoke_track_by_direction(tmp_path):
    root = str(tmp_path)
    _write_step(root, "3_fwd", {"scenario": "smoke-track",
                                "direction": "forward"}, "a_smoke_track.png")
    _write_step(root, "5_back", {"scenario": "smoke-track",
                                 "direction": "backward"}, "b_smoke_track.png")
    steps = brief.load(root)
    assert set(steps) == {"smoke-track:forward", "smoke-track:backward"}


def test_run_writes_both_outputs_and_skips_absent_steps(tmp_path, capsys):
    root = str(tmp_path)
    _write_step(root, "2_fire_danger",
                {"scenario": "fire-danger", "name": "Ketapang",
                 "date": "2026-08-02", "indices": {"DC": 258.8},
                 "dc_class_pct": {"Tinggi": 47.0},
                 "note": "DC and BUI lead here."}, "k_dc.png")
    md, html = brief.run(root, lang="en")
    assert os.path.exists(md) and os.path.exists(html)
    text = open(md).read()
    assert "Ketapang" in text and "258.8" in text
    assert "How dangerous" in text
    assert "Who breathed it" not in text          # step not present
    assert "DC and BUI lead here." in text        # the note is carried
    out = capsys.readouterr().out
    assert "1/6 steps found" in out


def test_html_is_self_contained(tmp_path):
    root = str(tmp_path)
    _write_step(root, "2_fire_danger",
                {"scenario": "fire-danger", "name": "K", "indices": {"DC": 1}},
                "k_dc.png")
    _md, html = brief.run(root, lang="en")
    body = open(html).read()
    assert "data:image/png;base64," in body       # inlined, not linked
    assert "k_dc.png" not in body


def test_run_refuses_an_empty_directory(tmp_path):
    with pytest.raises(SystemExit, match="No chain output"):
        brief.run(str(tmp_path))
