"""The national roll-up across islands.

The point of these: a national figure must never imply coverage it does not
have. An island that has not run is named, with the hectares the index says it
holds -- not silently counted as zero paddy or zero drought.
"""
import json
import os

import numpy as np
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
def test_the_provisional_share_of_planting_is_rolled_up(tmp_path):
    """The weakest joint in the not-planted headline, made weighable.

    The SC rules cannot confirm a planting from the last ~60 days, so part of
    "planted" is a flood awaiting validation. The caveat was in the text; the
    number was nowhere.
    """
    run = str(tmp_path / "run")
    rows = _rows("Jawa", 2, 100.0)
    ids = [r["tile_id"] for r in rows]
    _tile_stats_for(run, ids[0], paddy_ha=1000.0, planted_ha=400.0,
                    not_planted_ha=600.0, planted_confirmed_ha=300.0,
                    planted_provisional_ha=100.0)
    _tile_stats_for(run, ids[1], paddy_ha=500.0, planted_ha=200.0,
                    not_planted_ha=300.0, planted_confirmed_ha=120.0,
                    planted_provisional_ha=80.0)
    got = pisl.roll_up(rows, run, "Jawa", "2026-09-27", 2)
    assert got["planted_confirmed_ha"] == 420.0
    assert got["planted_provisional_ha"] == 180.0
    assert got["planted_confirmed_ha"] + got["planted_provisional_ha"] == \
        got["planted_ha"]
    assert got["planted_provisional_pct"] == 30.0


def _tile_stats_for(run_dir, tid, **fields):
    import os as _os
    d = pisl.tile_dir(run_dir, tid)
    _os.makedirs(d, exist_ok=True)
    with open(_os.path.join(d, "stats.json"), "w") as f:
        json.dump(fields, f)


def test_class_hectares_never_exceed_the_paddy_they_describe(tmp_path):
    """The bug this guards: delay_class marks every unplanted pixel NOT_PLANTED,
    including everything that is not a field, so summing it per tile reported
    four times the island's paddy as "belum tanam" -- 13.8 M ha against 3.35 M.
    Taken from the mosaic, masked to paddy, it cannot happen.
    """
    import numpy as np
    import rasterio
    from earthchange import paddy_water as pw

    n = 40
    prof = {"driver": "GTiff", "height": n, "width": n, "count": 1,
            "dtype": "uint8", "crs": rasterio.crs.CRS.from_epsg(4326),
            "transform": rasterio.Affine(0.0005, 0, 110.0, 0, -0.0005, -7.0)}
    # a quarter of the scene is paddy; the rest is not a field at all
    paddy = np.zeros((n, n), dtype="uint8")
    paddy[:20, :20] = 1
    delay = np.full((n, n), 255, dtype="uint8")
    delay[:20, :20] = pw.NOT_PLANTED           # all of the paddy unplanted
    written = {}
    for name, arr in (("paddy", paddy), ("delay_class", delay),
                      ("adequacy_class", np.full((n, n), 255, "uint8")),
                      ("anomaly_class", np.full((n, n), 255, "uint8")),
                      ("outlook_class", np.full((n, n), 255, "uint8")),
                      ("puso", np.zeros((n, n), "uint8"))):
        p = str(tmp_path / f"{name}.tif")
        with rasterio.open(p, "w", **prof) as dst:
            dst.write(arr, 1)
        written[name] = p

    got = pisl.admin_totals(written, None, "id")
    assert got["paddy_ha"] > 0
    belum = got["planting_delay_ha"]["Belum tanam"]
    assert belum == pytest.approx(got["paddy_ha"], rel=1e-6)
    assert belum <= got["paddy_ha"] * 1.000001, "more 'not planted' than paddy"
    assert got["not_planted_ha"] == pytest.approx(got["paddy_ha"], rel=1e-6)


def test_row_areas_match_the_drought_sites_own_formula():
    """Two area formulas that drift are how a wrong headline reaches a page.

    drought.ownmap.id recomputes every published hectare from the pixels with an
    exact spherical per-row area. Its figure for West Java sat 0.5% above this
    package's, because this one used a single pixel area for a whole province.
    This pins the formula, constant included.
    """
    import math

    import rasterio
    t = rasterio.transform.from_origin(106.0, -5.0, 0.0005, 0.0005)
    got = pisl.row_areas_ha(t, 4000)

    R = 6371008.8
    lat_top = -5.0 - np.arange(4000) * 0.0005
    lat_bot = lat_top - 0.0005
    want = (R ** 2 * math.radians(0.0005)
            * (np.sin(np.radians(lat_top)) - np.sin(np.radians(lat_bot))) / 1e4)
    assert np.allclose(got, want, rtol=1e-12)
    # and it really does shrink away from the equator
    assert got[0] > got[-1]
    assert got[0] == pytest.approx(0.3095, abs=0.002)


def test_the_spherical_formula_is_what_differed_from_the_drought_site():
    """Locating the 0.5%: it was the formula, not the latitude spread.

    A mid-latitude pixel area times the row count is accurate to 0.005% over two
    degrees, because the error is symmetric about the midpoint -- so per-row
    variation was never the explanation. pixel_area_ha multiplies planar
    constants (111320 m per degree of longitude by 110540 per degree of
    latitude); the spherical area is R^2 * dlon * d(sin lat). Those differ by
    about half a per cent, which is exactly the gap the drought site's
    independent recount reported.
    """
    from earthchange import paddy_drought as pdr
    import rasterio
    t = rasterio.transform.from_origin(107.0, -6.0, 0.0005, 0.0005)
    n = 4000                                       # two degrees of latitude
    rows = pisl.row_areas_ha(t, n)

    # per-row variation is NOT the issue
    mid = rows[n // 2] * n
    assert abs(mid - rows.sum()) / rows.sum() < 0.001

    # the formula is
    profile = {"transform": t, "crs": "EPSG:4326"}
    planar = pdr.pixel_area_ha(profile, -7.0) * n
    gap = abs(planar - rows.sum()) / rows.sum()
    assert 0.002 < gap < 0.01, f"expected ~0.5%, got {gap:.4%}"


def test_clipping_makes_a_recount_agree_with_the_published_figure(tmp_path):
    """A province mosaic is the union of tile BOXES and spills over the border.

    Unclipped, West Java's raster carried Banten and Central Java paddy: the map
    showed a neighbour's fields, and the drought site's independent pixel
    recount came out 6.3% above the published figure. After clipping, counting
    every pixel gives the same answer as masking by the boundary.
    """
    import numpy as np
    import rasterio
    from shapely.geometry import box

    n = 40
    prof = {"driver": "GTiff", "height": n, "width": n, "count": 1,
            "dtype": "uint8", "crs": rasterio.crs.CRS.from_epsg(4326),
            "transform": rasterio.Affine(0.001, 0, 110.0, 0, -0.001, -7.0)}
    written = {}
    for name in ("paddy", "delay_class", "adequacy_class", "anomaly_class",
                 "outlook_class", "puso"):
        arr = (np.ones((n, n), dtype="uint8") if name == "paddy"
               else np.full((n, n), 255, dtype="uint8"))
        p = str(tmp_path / f"{name}.tif")
        with rasterio.open(p, "w", **prof) as dst:
            dst.write(arr, 1)
        written[name] = p

    # the "province" is the western half of the raster
    geom = box(110.0, -7.04, 110.02, -7.0)
    whole = pisl.admin_totals(written, None, "id")["paddy_ha"]
    masked = pisl.admin_totals(written, geom, "id")["paddy_ha"]
    assert masked < whole * 0.75, "the fixture must actually straddle the edge"

    pisl.clip_to(written, geom)
    after_whole = pisl.admin_totals(written, None, "id")["paddy_ha"]
    after_masked = pisl.admin_totals(written, geom, "id")["paddy_ha"]
    assert after_whole == pytest.approx(masked, rel=1e-9)
    assert after_masked == pytest.approx(masked, rel=1e-9)


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
