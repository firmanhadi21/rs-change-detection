"""Alert polygons: small enough to open, honest about their own areas.

What went wrong without this: one West Java province wrote a 26.7 MB
alerts.geojson. 24.3 MB of that was vertices, because the simplification
tolerance was 25 m on a 55.66 m grid -- below one pixel, so it removed nothing
from polygons that trace pixel edges. And 22 MB of it was "not planted", which
across a dry-season province is the state of two thirds of the land and is
already carried exactly by the delay_class raster.
"""
import json

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from earthchange import paddy_publish as ppub
from earthchange import paddy_water as pw

DEG = 0.0005            # the analysis grid: 55.66 m


def _profile(n=200):
    return {"driver": "GTiff", "height": n, "width": n, "count": 1,
            "dtype": "uint8", "crs": rasterio.crs.CRS.from_epsg(4326),
            "transform": rasterio.Affine(DEG, 0, 110.0, 0, -DEG, -7.0)}


def _rasters(tmp_path, severe=None, not_planted=None, puso=None, n=200):
    """Write the three rasters alerts_geojson reads."""
    prof = _profile(n)
    paths = {}
    for key, arr, fill in (("adequacy_class", severe, 255),
                           ("delay_class", not_planted, 0),
                           ("puso", puso, 0)):
        data = np.full((n, n), fill, dtype="uint8")
        if arr is not None:
            data[arr] = {"adequacy_class": 3,
                         "delay_class": pw.NOT_PLANTED,
                         "puso": 1}[key]
        p = str(tmp_path / f"{key}.tif")
        with rasterio.open(p, "w", **prof) as dst:
            dst.write(data, 1)
        paths[key] = p
    return paths, prof


def _blob(n, r0, c0, size):
    m = np.zeros((n, n), dtype=bool)
    m[r0:r0 + size, c0:c0 + size] = True
    return m


def test_the_tolerance_is_bigger_than_a_pixel():
    """The bug: 25 m on a 55.66 m grid simplified nothing at all."""
    px_m = DEG * 111320.0
    assert ppub.ALERT_SIMPLIFY_PX >= 1.0
    assert ppub.ALERT_SIMPLIFY_PX * px_m > px_m


def _disc(n, r0, c0, radius):
    """A rasterised circle: its boundary is a staircase, which is what a real
    field edge looks like and what the tolerance has to eat. An axis-aligned
    rectangle is NOT a test of this -- rasterio merges collinear pixel edges,
    so a square already comes back with nine vertices."""
    rr, cc = np.ogrid[:n, :n]
    return ((rr - r0) ** 2 + (cc - c0) ** 2) <= radius ** 2


def test_simplification_reduces_vertices_without_dropping_patches(tmp_path):
    n = 200
    mask = _disc(n, 70, 70, 45)
    paths, prof = _rasters(tmp_path, severe=mask, n=n)
    plain = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0, simplify_px=0)
    slim = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0, simplify_px=2.0)

    def verts(coll):
        return sum(sum(len(r) for r in f["geometry"]["coordinates"])
                   for f in coll["features"])

    assert len(slim["features"]) == len(plain["features"]) > 0
    assert verts(slim) < verts(plain)


def test_the_area_is_measured_before_simplifying(tmp_path):
    """A coarser tolerance must not move the hectares it reports."""
    n = 200
    mask = _disc(n, 70, 70, 40)       # ragged, so the tolerance really bites
    paths, prof = _rasters(tmp_path, severe=mask, n=n)
    plain = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0, simplify_px=0)
    slim = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0, simplify_px=3.0)
    a = plain["features"][0]["properties"]["area_ha"]
    b = slim["features"][0]["properties"]["area_ha"]
    assert a == pytest.approx(b, rel=1e-6)
    # and it is the real area of the disc, not of its simplified outline
    assert a == pytest.approx(np.pi * 40 ** 2 * 0.3098, rel=0.05)


def test_no_leftover_internal_property_ships(tmp_path):
    paths, prof = _rasters(tmp_path, severe=_blob(200, 10, 10, 40))
    coll = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0)
    props = coll["features"][0]["properties"]
    assert set(props) == {"kind", "area_ha"}
    assert "area_deg2" not in props


def test_labels_are_not_repeated_on_every_feature(tmp_path):
    """Repeating them cost 1.4 MB over one province."""
    paths, prof = _rasters(tmp_path, severe=_blob(200, 10, 10, 40))
    coll = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0)
    assert "label" not in coll["features"][0]["properties"]
    assert coll["kinds"]["severe_deficit"]["label"]["id"] == "Defisit berat"
    assert coll["kinds"]["severe_deficit"]["label"]["en"] == "Severe deficit"


def test_a_floor_per_kind_is_applied(tmp_path):
    """not_planted gets a higher floor than the kinds someone is sent to."""
    n = 200
    small = _blob(n, 10, 10, 20)      # 20x20 px ~ 124 ha
    tiny = _blob(n, 60, 60, 6)        # 6x6 px ~ 11 ha
    paths, prof = _rasters(tmp_path, severe=tiny, not_planted=tiny, n=n)
    coll = ppub.alerts_geojson(paths, prof, 0.31, min_ha=5.0,
                               per_kind_min_ha={"not_planted": 25.0},
                               by_kind=True)
    assert len(coll["severe_deficit"]["features"]) == 1   # 11 ha >= 5
    assert len(coll["not_planted"]["features"]) == 0      # 11 ha < 25
    assert coll["not_planted"]["min_ha"] == 25.0
    assert small.any()                                    # keep the fixture used


def test_the_shipped_floors_treat_not_planted_differently():
    assert ppub.ALERT_MIN_HA["not_planted"] > ppub.ALERT_MIN_HA["severe_deficit"]
    assert ppub.ALERT_MIN_HA["puso_candidate"] == ppub.ALERT_MIN_HA["severe_deficit"]


def test_by_kind_splits_into_one_collection_per_kind(tmp_path):
    paths, prof = _rasters(tmp_path, severe=_blob(200, 10, 10, 40),
                           not_planted=_blob(200, 100, 100, 40),
                           puso=_blob(200, 150, 20, 30))
    per = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0, by_kind=True)
    assert set(per) == {"severe_deficit", "not_planted", "puso_candidate"}
    for kind, coll in per.items():
        assert coll["kind"] == kind
        assert coll["type"] == "FeatureCollection"
        assert all(f["properties"]["kind"] == kind for f in coll["features"])
        assert coll["features"], kind


def test_one_collection_still_carries_everything(tmp_path):
    paths, prof = _rasters(tmp_path, severe=_blob(200, 10, 10, 40),
                           not_planted=_blob(200, 100, 100, 40),
                           puso=_blob(200, 150, 20, 30))
    per = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0, by_kind=True)
    one = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0)
    assert len(one["features"]) == sum(len(c["features"]) for c in per.values())


def test_a_collection_is_valid_geojson(tmp_path):
    paths, prof = _rasters(tmp_path, severe=_blob(200, 10, 10, 40))
    coll = ppub.alerts_geojson(paths, prof, 0.31, min_ha=0.0)
    text = json.dumps(coll)              # must serialise
    back = json.loads(text)
    assert back["type"] == "FeatureCollection"
    ring = back["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]           # closed
