"""Pair selection for InSAR.

Everything here is offline. The parts worth testing are the ones that decide
WHICH scenes get interfered, because a wrong pair still produces a plausible
map: scenes from different tracks cannot be interfered at all, a coherence
change needs three scenes rather than two, and a pair that straddles the event
too loosely decorrelates for reasons that have nothing to do with the event.
"""

import datetime as dt

import pytest

from earthchange.insar import (MAX_PAIR_DAYS, _next_pass, choose_pairs,
                               job_name, tracks)


def scene(date, path=112, frame=1148, direction="ascending"):
    return {"granule": f"S1D_IW_SLC__1SDV_{date.replace('-', '')}T101603_{path}",
            "date": date, "path": path, "frame": frame, "direction": direction}


# The real Flores stack: ascending path 112 and descending 163, 12-day repeat.
ASC = [scene(d) for d in ("2026-07-13", "2026-07-25", "2026-08-06", "2026-08-18")]
DESC = [scene(d, path=163, frame=620, direction="descending")
        for d in ("2026-07-16", "2026-07-28", "2026-08-09", "2026-08-21")]
EVENT = "2026-08-14"


def test_tracks_never_mix_paths():
    """Two scenes from different relative orbits cannot be interfered."""
    grouped = tracks(ASC + DESC)
    assert len(grouped) == 2
    for (path, _frame, _drn), stack in grouped.items():
        assert {s["path"] for s in stack} == {path}


def test_coherence_takes_two_before_and_one_after():
    pick, _ = choose_pairs(ASC, EVENT, "coherence")
    assert pick is not None
    assert [s["date"] for s in pick["pre_pair"]] == ["2026-07-25", "2026-08-06"]
    assert [s["date"] for s in pick["co_pair"]] == ["2026-08-06", "2026-08-18"]
    assert pick["co_days"] == 12


def test_displacement_needs_only_the_straddling_pair():
    """One pre-event scene is enough for displacement, and not for coherence."""
    one_before = [scene("2026-08-06"), scene("2026-08-18")]

    pick, _ = choose_pairs(one_before, EVENT, "displacement")
    assert pick is not None and "pre_pair" not in pick

    pick, why = choose_pairs(one_before, EVENT, "coherence")
    assert pick is None
    assert any("needs two" in w for w in why)


def test_refuses_when_no_post_event_scene_and_says_when():
    """The pre-event-only case, which is where Flores actually stood."""
    pick, why = choose_pairs([s for s in ASC if s["date"] < EVENT],
                             EVENT, "coherence")
    assert pick is None
    assert any("no post-event scene" in w for w in why)
    # The next pass is 12 days after the last one, and saying so is the
    # difference between a refusal and a useful refusal.
    assert any("2026-08-18" in w for w in why)


def test_rejects_a_pair_that_straddles_too_loosely():
    far = [scene("2026-06-01"), scene("2026-08-06"),
           scene("2026-11-30")]           # 116 days after the last pre-event
    pick, why = choose_pairs(far, EVENT, "displacement")
    assert pick is None
    assert any(str(MAX_PAIR_DAYS) in w for w in why)


def test_orbit_pass_filter_is_honoured():
    pick, _ = choose_pairs(ASC + DESC, EVENT, "displacement", "descending")
    assert pick["direction"] == "descending"
    assert pick["path"] == 163


def test_prefers_the_tightest_straddle_across_tracks():
    """Descending straddles 2026-08-09→08-21 (12 d) and ascending 08-06→08-18
    (12 d); ascending is listed first, so a tie must not silently reorder."""
    pick, _ = choose_pairs(ASC + DESC, EVENT, "displacement")
    assert pick["co_days"] == 12


def test_next_pass_is_always_in_the_future():
    """A stale frame must not be told to wait for a date that has gone.

    The AOI can clip a neighbouring frame whose stack ended weeks earlier;
    adding one 12-day cycle to that lands in the past.
    """
    today = dt.date(2026, 8, 15)
    stale = [scene("2026-07-16", path=163, frame=622, direction="descending")]
    assert _next_pass(stale, today) > today
    assert _next_pass(stale, today) == dt.date(2026, 8, 21)

    current = [scene("2026-08-06")]
    assert _next_pass(current, today) == dt.date(2026, 8, 18)


@pytest.mark.parametrize("name", ["Ende", "Kota Ende / Flores", "a" * 60])
def test_job_name_is_deterministic_and_safe(name):
    """The job name is the only handle that survives between invocations, so
    it must be stable and must not carry characters HyP3 would reject."""
    pair = (scene("2026-08-06"), scene("2026-08-18"))
    a = job_name(name, "co", pair)
    assert a == job_name(name, "co", pair)
    assert a != job_name(name, "pre", pair)
    assert all(c.isalnum() or c in "-_" for c in a)
    assert "20260806_20260818" in a
    # HyP3 caps a job name at 100 characters, and a name that gets truncated
    # server-side stops matching on the next find_jobs -- which would silently
    # resubmit rather than resume.
    assert len(a) <= 100
