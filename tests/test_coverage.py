"""Archive-coverage messages.

Every scenario here reads an archive that ends on a different day, and an empty
ImageCollection fails deep inside Earth Engine with a message about band counts
or null inputs -- never about dates, which is always the actual problem. These
tests cover the wording, since that is the whole value of the guard.
"""

import datetime as dt

import pytest

from earthchange.gee_utils import REANALYSIS_HINT, span_message


def _utc(y, m, d):
    return dt.datetime(y, m, d, tzinfo=dt.UTC)


def test_names_both_the_need_and_the_availability():
    msg = span_message("ERA5-Land", _utc(2025, 11, 7), _utc(2026, 8, 4),
                       _utc(1950, 1, 1), _utc(2026, 8, 3))
    assert "2025-11-07" in msg and "2026-08-04" in msg
    assert "2026-08-03" in msg


def test_says_which_end_to_move_when_the_window_runs_past():
    msg = span_message("ERA5-Land", _utc(2025, 11, 7), _utc(2026, 8, 4),
                       _utc(1950, 1, 1), _utc(2026, 8, 3))
    assert "End the window on 2026-08-03 or earlier" in msg
    assert "Start the window" not in msg


def test_says_which_end_to_move_when_the_window_starts_too_early():
    msg = span_message("CAMS", _utc(2015, 1, 1), _utc(2016, 1, 1),
                       _utc(2016, 6, 22), _utc(2026, 8, 12))
    assert "Start the window on 2016-06-22 or later" in msg
    assert "End the window" not in msg


def test_reports_both_ends_when_the_window_overruns_both():
    msg = span_message("MODIS", _utc(1990, 1, 1), _utc(2026, 8, 1),
                       _utc(2000, 11, 1), _utc(2026, 5, 1))
    assert "Start the window on 2000-11-01" in msg
    assert "End the window on 2026-05-01" in msg


def test_hint_is_optional():
    args = ("X", _utc(2026, 8, 4), _utc(2026, 8, 5),
            _utc(2000, 1, 1), _utc(2026, 8, 3))
    assert "smoke-video" in span_message(*args, hint=REANALYSIS_HINT)
    assert "smoke-video" not in span_message(*args)


@pytest.mark.parametrize("what", ["ERA5-Land (Drought Code weather)",
                                  "CAMS PM2.5"])
def test_leads_with_what_is_missing(what):
    msg = span_message(what, _utc(2026, 8, 4), _utc(2026, 8, 5),
                       _utc(2000, 1, 1), _utc(2026, 8, 3))
    assert msg.startswith(what)
