"""fire-history --vs-baseline asks Earth Engine for a few years at a time (offline)."""

import sys
import types

from earthchange import fire_history


class _Img:
    def __init__(self, year):
        self.year = year

    def filterDate(self, start, end):
        return _Img(int(start[:4]))

    def select(self, *_):
        return self

    def map(self, fn):
        return self

    def sum(self):
        return self

    def unmask(self, _):
        return self

    def reduceRegion(self, *a, **k):
        return {"T21": self.year}


def _fake_ee(calls):
    ee = types.ModuleType("ee")
    ee.ImageCollection = lambda _id: _Img(0)
    ee.Reducer = types.SimpleNamespace(sum=lambda: None)

    class _List:
        def __init__(self, items):
            self.items = items

        def getInfo(self):
            calls.append(len(self.items))
            return list(self.items)

    ee.List = _List
    return ee


def test_hotspots_to_date_batches_years(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "ee", _fake_ee(calls))
    years = list(range(2001, 2027))                      # 26 years
    vals = fire_history._hotspots_to_date(None, years, "11-17")
    assert vals == years                                 # order kept
    assert max(calls) <= fire_history.BASELINE_BATCH
    assert sum(calls) == len(years)
