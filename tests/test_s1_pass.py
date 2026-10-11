"""Sentinel-1 pass selection: every slice of the latest overpass, not the latest slice."""
import datetime as dt
from types import SimpleNamespace

from earthchange.mpc_backend import _latest_pass


def _item(name, t):
    return SimpleNamespace(id=name, datetime=t)


def test_latest_pass_keeps_every_slice_of_the_overpass():
    # Pekalongan, Jan 2026: a descending pass, slices 25 s apart; the latest
    # slice is the southern one and covered 1.3% of the AOI on its own.
    t = dt.datetime(2025, 12, 23, 22, 17, 50, tzinfo=dt.timezone.utc)
    items = [_item("north", t - dt.timedelta(seconds=25)), _item("south", t),
             _item("12 days earlier", t - dt.timedelta(days=12))]
    assert {it.id for it in _latest_pass(items)} == {"north", "south"}


def test_latest_pass_single_slice():
    t = dt.datetime(2026, 1, 16, 22, 17, 36, tzinfo=dt.timezone.utc)
    items = [_item("only", t), _item("old", t - dt.timedelta(days=6))]
    assert [it.id for it in _latest_pass(items)] == ["only"]
