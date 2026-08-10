"""Placeholder admin names must not reach a ranking or a headline.

GAUL ships names for polygons it cannot attribute. Those are real land with real
people, so they stay in totals -- but a Sumatera Selatan brief listed
"Administrative unit not available (0.0M)" as the third heaviest burden, because
only two districts had any exposure and the placeholder floated up into the
sentence.
"""

import pytest

from earthchange.brief import _worst_districts
from earthchange.gee_utils import is_named


@pytest.mark.parametrize("name", [
    "Administrative unit not available",
    "administrative unit NOT AVAILABLE",
    "Name Unknown",
    "(unnamed)",
    "n/a",
    "?",
    "-",
    "",
    "   ",
    None,
])
def test_placeholders_are_not_names(name):
    assert not is_named(name)


@pytest.mark.parametrize("name", [
    "Lampung Selatan", "Kota Bandarlampung", "Ogan Komering Ulu Timur",
    "Kapuas Hulu", "Bau", "Kota Pontianak",
])
def test_real_districts_are_names(name):
    assert is_named(name)


def test_a_real_name_containing_a_placeholder_word_is_not_rejected():
    """The check is substring-based, so guard against over-matching."""
    assert is_named("Bandar Lampung")
    assert is_named("Nagan Raya")


DISTRICTS = {
    "Lampung Selatan": {"person_days_unhealthy": 1_540_071},
    "Kota Bandarlampung": {"person_days_unhealthy": 1_191_870},
    "Administrative unit not available": {"person_days_unhealthy": 0},
    "Musirawas": {"person_days_unhealthy": 0},
}


def test_worst_districts_drops_the_placeholder():
    out = _worst_districts(DISTRICTS, "en")
    assert "Administrative unit" not in out
    assert "Lampung Selatan" in out and "Kota Bandarlampung" in out


def test_worst_districts_drops_zero_exposure():
    """A district with no exposure is not a 'heaviest burden' either."""
    assert "Musirawas" not in _worst_districts(DISTRICTS, "en")


def test_worst_districts_is_ordered_and_capped():
    many = {f"D{i}": {"person_days_unhealthy": i} for i in range(1, 9)}
    out = _worst_districts(many, "en")
    assert out.startswith("D8")
    assert out.count(",") == 2          # three entries


def test_worst_districts_survives_an_empty_result():
    assert _worst_districts({}, "en") == ""
    assert _worst_districts({"X": {"person_days_unhealthy": 0}}, "id") == ""
