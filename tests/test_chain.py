"""earthchain — the step list and the date arithmetic.

The chain's whole value is getting the order and the dates right, so those are
what is tested. Nothing here runs a scenario.
"""

import argparse
import datetime as dt

import pytest

from earthchange import chain


def _args(**kw):
    base = dict(end="2026-08-01", admin="Ketapang", bbox=None, name="Ketapang",
                zones=None, zone_field=None, wide=None, out="out",
                steps=chain.DEFAULT_STEPS, lang="id", dry_run=True)
    base.update(kw)
    return argparse.Namespace(**base)


def _argv_for(step_no, **kw):
    return next(argv for n, _l, argv in chain._steps(_args(**kw))
                if n == step_no)


# --------------------------------------------------------------------------
# Dates, all derived from --end so there is one number to change
# --------------------------------------------------------------------------

def test_exposure_window_is_the_ninety_days_before_end():
    argv = _argv_for(4)
    assert "--season" in argv
    assert argv[argv.index("--season") + 1] == "2026-05-03:2026-08-01"


def test_record_gets_a_longer_run_up_than_the_rest():
    """DC has a ~52-day lag and the build-up precedes the burning by months, so
    a 90-day window opens after every zone has already crossed."""
    argv = _argv_for(7, zones="z.gpkg", zone_field="F")
    season = argv[argv.index("--season") + 1]
    assert season == "2026-01-03:2026-08-01"
    start = dt.date.fromisoformat(season.split(":")[0])
    assert (dt.date(2026, 8, 1) - start).days == chain.RECORD_DAYS


def test_backward_step_runs_later_because_gdas1_is_fresher():
    argv = _argv_for(5)
    assert argv[argv.index("--date") + 1] == "2026-08-05"
    assert "--engine" in argv and argv[argv.index("--engine") + 1] == "hysplit"
    assert argv[argv.index("--direction") + 1] == "backward"


def test_forward_step_uses_end_itself():
    assert _argv_for(3)[_argv_for(3).index("--date") + 1] == "2026-08-01"


# --------------------------------------------------------------------------
# Area handling
# --------------------------------------------------------------------------

def test_wide_box_applies_only_to_the_two_smoke_steps():
    kw = dict(wide="107,-4,115,3")
    for n in (4, 5):
        assert "107,-4,115,3" in _argv_for(n, **kw)
    for n in (1, 2, 3, 6):
        assert "107,-4,115,3" not in _argv_for(n, **kw)


def test_wide_steps_are_labelled_regional():
    """Naming a wide-box step after the province produced "Di mana penduduk
    terpapar — Kalteng" over a map whose only shaded districts were in Kalbar.
    The analysis was right; the title said it was about somewhere else."""
    kw = dict(wide="107,-4,115,3")
    for n in (4, 5):
        argv = _argv_for(n, **kw)
        assert argv[argv.index("-n") + 1] == "Ketapang-regional"
    for n in (1, 2, 3, 6, 7):
        argv = _argv_for(n, zones="z.gpkg", zone_field="F", **kw)
        assert argv[argv.index("-n") + 1] == "Ketapang"


def test_without_wide_the_smoke_steps_use_the_plain_area():
    argv = _argv_for(5)
    assert "--admin" in argv
    assert argv[argv.index("-n") + 1] == "Ketapang"


def test_bbox_area_is_passed_through():
    argv = _argv_for(1, admin=None, bbox="1,2,3,4")
    assert argv[argv.index("--bbox") + 1] == "1,2,3,4"


def test_zones_reach_only_the_two_steps_that_use_them():
    kw = dict(zones="z.gpkg", zone_field="FUNGSI_HTN")
    for n in (2, 7):
        assert "--zone-field" in _argv_for(n, **kw)
    for n in (1, 3, 4, 5, 6):
        assert "--zone-field" not in _argv_for(n, **kw)


def test_every_step_writes_to_its_own_folder():
    seen = set()
    for n, _l, argv in chain._steps(_args()):
        out = argv[argv.index("-o") + 1]
        assert out.startswith("out/")
        seen.add(out)
    assert len(seen) == 7


# --------------------------------------------------------------------------
# Step selection
# --------------------------------------------------------------------------

def test_record_is_not_in_the_default_steps():
    """MODIS burned area lags ~100 days, so a current-season record would report
    near-zero hectares and read as good news."""
    assert "7" not in chain.DEFAULT_STEPS.split(",")


def test_brief_is_in_the_default_steps():
    assert "8" in chain.DEFAULT_STEPS.split(",")


def test_all_seven_data_steps_are_defined():
    assert [n for n, _l, _a in chain._steps(_args())] == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize("bad", ["2026-13-01", "01-08-2026", "soon"])
def test_bad_end_date_is_rejected(bad, monkeypatch):
    monkeypatch.setattr("sys.argv",
                        ["earthchain", "--end", bad, "--admin", "X"])
    with pytest.raises(SystemExit):
        chain.main()


def test_zones_without_zone_field_is_rejected(monkeypatch):
    monkeypatch.setattr("sys.argv", ["earthchain", "--end", "2026-08-01",
                                     "--admin", "X", "--zones", "z.gpkg"])
    with pytest.raises(SystemExit):
        chain.main()
