"""The --transit-file loader, against a real stops layer.

transit-access accepts either stops (Points) or routes (LineStrings, sampled
every ~250 m), and the two paths are easy to break independently. The Point path
is checked against the Trans Semarang stops that produced a published figure, so
a change that silently drops or duplicates features shows up as a count that no
longer matches the run it came from.
"""

import json
import os

import pytest

from earthchange.transit import _stops_from_file

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BRT = os.path.join(FIXTURES, "semarang_brt_stops.geojson")

# From run 20260721-141407_transit-access_TransSemarang_7ba18f: n_stops 673.
N_STOPS = 673


def test_brt_fixture_is_a_point_collection():
    with open(BRT) as f:
        gj = json.load(f)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == N_STOPS
    assert {f["geometry"]["type"] for f in gj["features"]} == {"Point"}


def test_loads_every_stop():
    pts = _stops_from_file(BRT)
    assert len(pts) == N_STOPS


def test_stops_are_lon_lat_over_semarang():
    """Reversed coordinates are the classic failure and produce no error at all.

    Semarang sits near 110.4 E, 7.0 S. Latitude in the first slot would still be
    a valid pair of floats, snap to nothing, and report ~0% served.
    """
    for lon, lat in _stops_from_file(BRT):
        assert 110.0 < lon < 111.0, "longitude out of Semarang; coords swapped?"
        assert -7.5 < lat < -6.5, "latitude out of Semarang; coords swapped?"


@pytest.mark.parametrize("geom, want", [
    ({"type": "Point", "coordinates": [110.4, -7.0]}, 1),
    ({"type": "MultiPoint", "coordinates": [[110.4, -7.0], [110.5, -7.1]]}, 2),
])
def test_point_geometries(tmp_path, geom, want):
    p = tmp_path / "g.geojson"
    p.write_text(json.dumps(
        {"type": "FeatureCollection",
         "features": [{"type": "Feature", "properties": {}, "geometry": geom}]}))
    assert len(_stops_from_file(str(p))) == want


@pytest.mark.xfail(strict=True, reason=(
    "_sample_line decimates existing vertices, it never interpolates between "
    "them: a 10 km segment with two vertices yields those two vertices (plus a "
    "duplicated endpoint), not ~40 samples. Sparse routes -- which is what a "
    "corridor exported from GIS looks like -- therefore produce a handful of "
    "stops and a near-zero served percentage, with no error. Remove this "
    "marker when _sample_line interpolates."))
def test_routes_are_sampled_not_taken_as_endpoints(tmp_path):
    """A LineString is a corridor, not two stops.

    ~0.09 deg of longitude at this latitude is ~10 km, which at the ~250 m
    sampling interval the docstring promises has to yield far more than the two
    vertices given.
    """
    p = tmp_path / "route.geojson"
    p.write_text(json.dumps(
        {"type": "FeatureCollection",
         "features": [{"type": "Feature", "properties": {},
                       "geometry": {"type": "LineString",
                                    "coordinates": [[110.40, -7.0],
                                                    [110.49, -7.0]]}}]}))
    assert len(_stops_from_file(str(p))) > 20


def test_bare_geometry_without_a_feature_wrapper(tmp_path):
    """Layers exported straight from GIS are often not FeatureCollections."""
    p = tmp_path / "bare.geojson"
    p.write_text(json.dumps({"type": "Point", "coordinates": [110.4, -7.0]}))
    assert _stops_from_file(str(p)) == [(110.4, -7.0)]
