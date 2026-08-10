"""fire-record: the two ways a season window can quietly produce a wrong record.

Both were found by running the same season two ways and noticing the answers
disagreed, so both are regression tests rather than hypotheticals.
"""

import datetime as dt

import numpy as np
import pytest

from earthchange.fire_record import _crossing_lines, _incomplete, _match_grid


# --------------------------------------------------------------------------
# Weather chunks arriving on different grids
# --------------------------------------------------------------------------

def test_match_grid_is_a_no_op_on_the_same_shape():
    a = np.zeros((2, 34, 43))
    assert _match_grid(a, (34, 43)) is a


@pytest.mark.parametrize("src", [(2, 17, 22), (2, 68, 86), (2, 34, 43)])
def test_match_grid_reaches_the_target_shape(src):
    out = _match_grid(np.arange(np.prod(src), dtype="float64").reshape(src),
                      (34, 43))
    assert out.shape == (2, 34, 43)


def test_match_grid_keeps_corner_values():
    """Nearest, not interpolated: the bounds are identical and only the
    sampling differs, so this undoes an unrequested resample."""
    a = np.arange(2 * 17 * 22, dtype="float64").reshape(2, 17, 22)
    out = _match_grid(a, (34, 43))
    assert out[0, 0, 0] == a[0, 0, 0]
    assert out[0, -1, -1] == a[0, -1, -1]


def test_carried_drought_code_still_broadcasts():
    """download_geotiff coarsens per call, so chunk 3 can come back at half
    chunk 0's resolution and the recursion dies with
    'operands could not be broadcast together with shapes (17,22) (34,43)'."""
    dc = np.full((34, 43), 15.0)
    t = _match_grid(np.ones((17, 22)), (34, 43))
    assert (dc + t).shape == (34, 43)


# --------------------------------------------------------------------------
# A crossing dated to the first snapshot is the window's edge, not a finding
# --------------------------------------------------------------------------

def test_real_crossings_are_reported_as_dates():
    r = {"first_crossed": {"Sedang": "2019-07-18", "Tinggi": "2019-08-17"},
         "first_crossed_censored": {"Sedang": False, "Tinggi": False}}
    out = "\n".join(_crossing_lines(r))
    assert "Pertama mencapai **Sedang**: 2019-07-18" in out
    assert "Pertama mencapai **Tinggi**: 2019-08-17" in out
    assert "Sudah pada kelas" not in out


def test_censored_crossing_is_not_printed_as_a_date():
    r = {"first_crossed": {"Tinggi": "2019-09-01"},
         "first_crossed_censored": {"Tinggi": True}}
    out = "\n".join(_crossing_lines(r))
    assert "Sudah pada kelas **Tinggi**" in out
    assert "lebih awal" in out
    assert "Pertama mencapai" not in out


def test_threshold_never_reached_is_omitted():
    r = {"first_crossed": {"Tinggi": None, "Ekstrem": None},
         "first_crossed_censored": {}}
    assert _crossing_lines(r) == []


# --------------------------------------------------------------------------
# A record missing checkpoints must not be written at all
# --------------------------------------------------------------------------

def test_incomplete_names_the_missing_checkpoints():
    kept = [dt.date(2026, 1, 5) + dt.timedelta(days=15 * i) for i in range(15)]
    missing = kept[9:]
    msg = _incomplete(kept, missing, 60, dt.date(2026, 1, 5),
                      dt.date(2026, 8, 3))
    assert "6 of 15" not in msg          # phrased as how many succeeded
    assert "9 of 15" in msg
    for d in missing:
        assert d.isoformat() in msg


def test_incomplete_explains_why_the_tail_is_what_fails():
    """The lost checkpoints are always the later ones, which for a fire season
    are the dry months -- the only ones the record is about."""
    kept = [dt.date(2026, 1, 5), dt.date(2026, 8, 3)]
    msg = _incomplete(kept, [dt.date(2026, 8, 3)], 60, dt.date(2026, 1, 5),
                      dt.date(2026, 8, 3))
    assert "later checkpoints" in msg
    assert "dry months" in msg
    assert "no record was written" in msg


def test_incomplete_reports_the_chain_length_it_asked_for():
    msg = _incomplete([dt.date(2026, 1, 5)], [dt.date(2026, 1, 5)], 60,
                      dt.date(2026, 1, 5), dt.date(2026, 8, 3))
    assert "271 days" in msg            # 60 spin-up + 210 season + 1


def test_incomplete_names_the_remedy_and_its_cost():
    """Shortening the season is the fix, and it reintroduces the censoring
    problem -- saying only the first half would trade one wrong record for
    another."""
    msg = _incomplete([dt.date(2026, 1, 5)], [dt.date(2026, 1, 5)], 60,
                      dt.date(2026, 1, 5), dt.date(2026, 8, 3))
    assert "Shorten the season" in msg
    assert "180 days" in msg
    assert "spun up" in msg
