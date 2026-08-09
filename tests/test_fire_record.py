"""fire-record: the two ways a season window can quietly produce a wrong record.

Both were found by running the same season two ways and noticing the answers
disagreed, so both are regression tests rather than hypotheticals.
"""

import datetime as dt

from earthchange.fire_record import _crossing_lines, _incomplete


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
