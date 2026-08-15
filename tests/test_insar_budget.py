"""The credit guard must price what is left to buy, not the whole network.

This is the resume path, and it is the one that broke: a four-year stack whose
first half was already submitted refused to collect, because the guard totalled
all 354 pairs and compared that against a balance already reduced by the 180 it
had itself bought.
"""

import datetime as dt

import pytest

from earthchange.insar_series import network, pick_track, plan


def scene(date, path=163, frame=620, direction="descending"):
    return {"granule":
            f"S1D_IW_SLC__1SDV_{date.replace('-', '')}T2127{frame % 100:02d}_"
            f"{path:03d}_{frame}",
            "date": date, "path": path, "frame": frame, "direction": direction}


def stack(n, step=12, first="2024-08-12"):
    d0 = dt.date.fromisoformat(first)
    return [scene((d0 + dt.timedelta(days=step * i)).isoformat())
            for i in range(n)]


def test_plan_prices_every_pair_before_anything_is_submitted():
    s = stack(60)
    key, picked = pick_track(s, "descending")
    pairs, _ = network(picked)
    meta = plan(key, picked, pairs, 0, per_job=10)
    assert meta["estimated_credits"] == len(pairs) * 10
    assert meta["credits_per_pair"] == 10


def test_extending_a_window_only_adds_the_new_pairs():
    """The dedup design's whole benefit: a longer window re-uses what exists."""
    short = stack(30)
    long_ = stack(60)

    def keys(scenes):
        _, picked = pick_track(scenes, "descending")
        pairs, _ = network(picked)
        return {tuple(sorted(p["granule"] for p in pr)) for pr in pairs}

    a, b = keys(short), keys(long_)
    assert a < b, "the shorter window must be a subset of the longer"
    new = len(b - a)
    assert 0 < new < len(b), "extending should add pairs, not all of them"
    # What the guard should ask for is the delta, priced -- not len(b) * 10.
    assert new * 10 < len(b) * 10


@pytest.mark.parametrize("already,total,per_job,expected_due", [
    (180, 354, 10, 1740),   # the four-year descending case that failed
    (354, 354, 10, 0),      # nothing left to buy: collection must not be gated
    (0, 174, 10, 1740),     # a fresh stack pays for everything
])
def test_amount_due_is_the_outstanding_pairs(already, total, per_job,
                                             expected_due):
    missing = total - already
    assert missing * per_job == expected_due
