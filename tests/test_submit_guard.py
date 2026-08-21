"""The submit guard decides whether to spend credits, so it gets a test.

The bug this covers: submit_coseismic.py checked only hyp3.find_jobs() for
already-submitted names. That listing has returned other projects' jobs and
none of this project's for the whole campaign, so the check silently passed
and the planner offered to re-buy two frame-1148 pairs for ~30 credits while
both sat extracted in output/coseismic.
"""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "submit_coseismic.py")


def _load(monkeypatch, product_dir):
    """Import the script with PRODUCT_DIR pointed at a temporary tree."""
    spec = importlib.util.spec_from_file_location("submit_coseismic", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["submit_coseismic"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "PRODUCT_DIR", str(product_dir))
    return mod


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="script not present")
def test_fetched_product_is_recognised(tmp_path, monkeypatch):
    mod = _load(monkeypatch, tmp_path)
    d = tmp_path / "flores-coseismic-2026-asc-f1148-prepost-d2"
    d.mkdir()
    (d / "S1DD_x_corr.tif").write_bytes(b"")
    assert mod.already_fetched("flores-coseismic-2026-asc-f1148-prepost-d2")


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="script not present")
def test_unknown_name_is_not_fetched(tmp_path, monkeypatch):
    mod = _load(monkeypatch, tmp_path)
    assert not mod.already_fetched("flores-coseismic-2026-asc-f1153-prepre-d2")


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="script not present")
def test_empty_directory_does_not_count_as_done(tmp_path, monkeypatch):
    """An interrupted fetch leaves the directory but no bands.

    fetch_coseismic.py creates the output directory before extracting into it,
    so treating a bare directory as proof of completion would skip a job whose
    product never arrived -- turning a transient network failure into silently
    missing data.
    """
    mod = _load(monkeypatch, tmp_path)
    (tmp_path / "flores-coseismic-2026-asc-f1148-prepre-d2").mkdir()
    assert not mod.already_fetched("flores-coseismic-2026-asc-f1148-prepre-d2")


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="script not present")
def test_param_tag_distinguishes_reprocessed_jobs(tmp_path, monkeypatch):
    """A d2 product must not satisfy the guard for the un-suffixed name.

    PARAM_TAG exists because these jobs are hand-named, so a parameter change
    does not alter the name by itself. The tag is what makes a reprocessed
    pair a different job; the guard has to respect that in both directions.
    """
    mod = _load(monkeypatch, tmp_path)
    d = tmp_path / "flores-coseismic-2026-asc-f1148-prepost-d2"
    d.mkdir()
    (d / "S1DD_x_corr.tif").write_bytes(b"")
    assert mod.already_fetched("flores-coseismic-2026-asc-f1148-prepost-d2")
    assert not mod.already_fetched("flores-coseismic-2026-asc-f1148-prepost")
