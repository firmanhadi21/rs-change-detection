"""The published data specification must match the code that produces it.

docs/drought_data_spec.md is a contract with whoever builds the map. A class
value, a colour or a nodata that drifts from the code turns that contract into
a lie, and the map would mis-colour real drought. These tests read the document
and check its tables against the tables the products are written from.
"""
import os
import re

import pytest

from earthchange import paddy_island as pisl
from earthchange import paddy_publish as ppub
from earthchange import paddy_water as pw

SPEC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "drought_data_spec.md")


@pytest.fixture(scope="module")
def spec():
    if not os.path.exists(SPEC):
        pytest.skip("data spec not present")
    with open(SPEC, encoding="utf-8") as f:
        return f.read()


def test_every_published_layer_is_documented(spec):
    for key in ppub.LAYERS:
        assert f"`{key}`" in spec, f"{key} missing from the data spec"


def test_the_spec_documents_no_layer_that_is_not_published(spec):
    """A COG named in the spec but absent from LAYERS would 404 on the site."""
    named = set(re.findall(r"cog/(\w+)\.tif", spec))
    assert named <= set(ppub.LAYERS), named - set(ppub.LAYERS)


@pytest.mark.parametrize("table,layer", [
    (pw.ANOMALY_CLASSES, "anomaly_class"),
    (pw.ADEQUACY_CLASSES, "adequacy_class"),
    (pw.DELAY_CLASSES, "delay_class"),
])
def test_class_values_labels_and_colours_match_the_code(spec, table, layer):
    for value, _lo, _hi, labels, colour in table:
        # the Indonesian label and the colour must both appear
        assert labels["id"] in spec, f"{layer} label {labels['id']!r} missing"
        assert colour.lower() in spec.lower(), f"{layer} colour {colour} missing"
        assert f"| {value} |" in spec or f"| **{value}** |" in spec


def test_nodata_values_are_stated_correctly(spec):
    assert str(pw.ADEQUACY_NODATA) in spec          # 255
    assert "255" in spec
    # the two mask layers genuinely have no nodata, and the spec must say so
    for key in ("paddy", "puso"):
        assert ppub.LAYERS[key]["nodata"] is None
    assert "Tanpa nodata" in spec


def test_not_planted_code_is_documented(spec):
    assert f"| **{pw.NOT_PLANTED}** |" in spec or f"| {pw.NOT_PLANTED} |" in spec
    assert "Belum tanam" in spec


def test_the_grid_is_stated_as_the_code_computes_it(spec):
    from earthchange import paddy_data as pdata
    assert "0,0005" in spec or "0.0005" in spec
    assert f"{pdata.grid_metres():.2f}".replace(".", ",") in spec


def test_island_names_in_the_spec_are_the_real_ones(spec):
    for name, _ in pisl.ptiles.ISLANDS:
        assert f"`{name}`" in spec, f"island {name} missing"


def test_alert_kinds_match_what_is_written(spec):
    for kind in ("severe_deficit", "not_planted", "puso_candidate"):
        assert f"`{kind}`" in spec


def test_the_island_alert_floor_is_the_documented_one(spec):
    assert f"{pisl.ISLAND_ALERT_MIN_HA:.0f} ha" in spec


def test_web_crs_and_analysis_crs_are_both_named(spec):
    assert ppub.WEB_CRS in spec              # EPSG:3857
    assert "EPSG:4326" in spec


def test_the_mandatory_disclosures_are_in_the_spec(spec):
    """The caveats exist in the data; the spec must require showing them."""
    assert "caveats" in spec
    for must in ("kandidat", "provisional", "native_m", "unscored_paddy_ha"):
        assert must in spec.lower() or must in spec


def test_summary_headline_keys_are_all_documented(spec):
    for key in ("paddy_ha", "planted_ha", "not_planted_pct", "anomaly_ha",
                "adequacy_ha", "outlook_ha", "puso_candidates_ha",
                "median_delay_days", "season_length_days_median"):
        assert key in spec, f"headline key {key} missing from the spec"


def test_every_calendar_arm_is_documented(spec):
    from earthchange import paddy_phenology as phen
    for arm in phen.CALENDAR_ARMS:
        assert f"`{arm}`" in spec, f"calendar arm {arm} missing from the spec"
    assert "optical_share" in spec
    assert "calendar_arm" in spec


def test_the_default_calendar_is_named_as_the_default(spec):
    from earthchange import paddy_drought as pdr
    line = [ln for ln in spec.splitlines()
            if f"`{pdr.DEFAULT_CALENDAR}`" in ln and "baku" in ln]
    assert line, f"the spec does not mark {pdr.DEFAULT_CALENDAR} as the default"


def test_province_totals_are_documented_as_boundary_masked(spec):
    """The whole point: a border tile must not be counted in both provinces."""
    assert "per_tile_totals" in spec
    assert "batas" in spec
    from earthchange import paddy_tiles as ptiles
    assert ptiles.GAUL1 in spec


def test_anomaly_leads_and_absolute_scale_is_marked_uncalibrated(spec):
    assert "belum dikalibrasi" in spec
    head = spec[:spec.index("## 2.")] if "## 2." in spec else spec
    assert "anomaly_class" in head, "the headline layer must be named up front"
