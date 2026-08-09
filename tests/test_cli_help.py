"""The per-scenario --help flag table.

SCENARIO_FLAGS is maintained by hand, so what is worth testing is not that it
looks right today but that nothing falls through it later. A flag added without
being listed would otherwise vanish from every scenario's help and nobody would
notice.
"""

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from earthchange import detect as d
from earthchange.scenarios import (COMMON_FLAGS, SCENARIOS, SCENARIO_FLAGS,
                                   flags_for, unclaimed_flags)


def _real_option(action, opt):
    """Skip --help and the negation argparse generates for BooleanOptionalAction.

    Only a --no-x sharing an action with --x is generated. A standalone
    store_true like --no-water-mask is a real flag a scenario must claim.
    """
    if opt == "--help" or not opt.startswith("--"):
        return False
    return not (opt.startswith("--no-")
                and "--" + opt[5:] in action.option_strings)


@pytest.fixture(scope="module")
def all_flags():
    """Real option strings off the parser.

    Not scraped from formatted help: that text carries horizontal rules, prose
    mentions of flags and the generated --no-* forms, which is how an earlier
    version of this test reported eleven phantom orphans.
    """
    ap = d.build_parser()
    return sorted({o for a in ap._actions for o in a.option_strings
                   if _real_option(a, o)})


def _help_for(scenario):
    out, err = io.StringIO(), io.StringIO()
    argv = ["earthchange", "-s", scenario, "--help"]
    import sys
    old, sys.argv = sys.argv, argv
    try:
        with redirect_stdout(out), redirect_stderr(err):
            d.main()
    except SystemExit:
        pass
    finally:
        sys.argv = old
    return out.getvalue(), err.getvalue()


def test_no_flag_is_unclaimed(all_flags):
    """Every option is common or belongs to at least one scenario."""
    orphans = unclaimed_flags(all_flags)
    assert not orphans, f"add these to SCENARIO_FLAGS or COMMON_FLAGS: {orphans}"


def test_every_scenario_has_an_entry():
    missing = [s for s in SCENARIOS if s not in SCENARIO_FLAGS]
    assert not missing, missing


def test_table_has_no_typos(all_flags):
    bogus = {s: sorted(set(f) - set(all_flags))
             for s, f in SCENARIO_FLAGS.items() if set(f) - set(all_flags)}
    assert not bogus, bogus


def test_common_flags_have_no_typos(all_flags):
    assert not (set(COMMON_FLAGS) - set(all_flags))


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_scenario_help_is_shorter_and_complete(scenario, all_flags):
    shown = flags_for(scenario)
    assert shown < set(all_flags), f"{scenario} hides nothing"
    out, _ = _help_for(scenario)
    assert f"options that apply to {scenario}" in out
    absent = [f for f in SCENARIO_FLAGS[scenario] if f not in out]
    assert not absent, f"{scenario} claims but does not show: {absent}"


@pytest.mark.parametrize("noise", ["--transect-spacing", "--video-title",
                                   "--hysplit-bin", "--cdi-mask",
                                   "--walk-dist"])
def test_burn_hides_other_scenarios_flags(noise):
    out, _ = _help_for("burn")
    assert noise not in out


def test_unknown_scenario_is_rejected_with_the_real_list():
    _out, err = _help_for("not-a-scenario")
    assert "invalid choice" in err
    assert "smoke-track" in err and "burn" in err
