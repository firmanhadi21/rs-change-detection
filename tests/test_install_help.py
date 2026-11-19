"""Install and first-run failures point the user at the fix (offline)."""

import os
import sys
import tomllib
import types

import pytest

from earthchange import gee_utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _extras():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)["project"]["optional-dependencies"]


def test_all_extra_covers_the_everyday_extras():
    extras = _extras()
    want = set()
    for name in ("gee", "mpc", "maps", "zones", "track", "transit"):
        want |= set(extras[name])
    assert want - set(extras["all"]) == set()


def test_ee_failure_passes_on_the_reason_and_names_set_project(monkeypatch, tmp_path):
    fake = types.ModuleType("ee")

    def boom(*a, **k):
        raise Exception("no project found")
    fake.Initialize = boom
    monkeypatch.setitem(sys.modules, "ee", fake)
    monkeypatch.delenv("EARTHCHANGE_EE_KEY", raising=False)
    monkeypatch.delenv("SATCHANGE_EE_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))       # no ~/.secrets key
    monkeypatch.chdir(tmp_path)                      # no repo-local key
    with pytest.raises(SystemExit) as exc:
        gee_utils.initialize_ee()
    msg = str(exc.value)
    assert "no project found" in msg
    assert "earthengine set_project" in msg
    assert "earthengine authenticate" in msg
