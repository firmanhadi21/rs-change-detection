"""Geometry bands must survive pruning, whichever flag produced them.

705 jobs were resubmitted for one reason: to obtain the geometry rasters that
make an ascending/descending decomposition possible. The keep-list named only
_lv_theta.tif, so the _inc_map.tif those jobs actually returned was deleted
during unpacking -- the pruning step silently undid the reprocessing, and it
only came to light when MintPy was ready to run.
"""

import os

import pytest

from earthchange.insar import KEEP_SUFFIXES, prune

STEM = "S1AA_20220823T212849_20220904T212850_VVP012_INT80_G_weF_455D"

GEOMETRY = ("_dem.tif", "_lv_theta.tif", "_lv_phi.tif", "_inc_map.tif",
            "_inc_map_ell.tif")
ANALYSIS = ("_unw_phase.tif", "_corr.tif")
DISPOSABLE = ("_amp.tif", "_color_phase.kmz", "_color_phase.png",
              "_unw_phase.png", "_rgb.tif")


def build(tmp_path):
    d = tmp_path / "product"
    d.mkdir()
    for suffix in GEOMETRY + ANALYSIS + DISPOSABLE:
        (d / f"{STEM}{suffix}").write_bytes(b"\0" * 2048)
    (d / f"{STEM}.txt").write_text("Baseline: -95.6839\n")
    return str(d)


@pytest.mark.parametrize("suffix", GEOMETRY)
def test_every_geometry_band_is_kept(tmp_path, suffix):
    """Any of these may be the one a downstream tool wants."""
    d = build(tmp_path)
    prune(d)
    assert f"{STEM}{suffix}" in os.listdir(d), (
        f"{suffix} was pruned; a resubmission that requested it would be wasted")


@pytest.mark.parametrize("suffix", ANALYSIS)
def test_analysis_bands_are_kept(tmp_path, suffix):
    d = build(tmp_path)
    prune(d)
    assert f"{STEM}{suffix}" in os.listdir(d)


def test_bulk_is_still_dropped(tmp_path):
    """The point of pruning survives: _amp.tif is 30 MB and never read."""
    d = build(tmp_path)
    prune(d)
    left = os.listdir(d)
    for suffix in DISPOSABLE:
        assert f"{STEM}{suffix}" not in left


def test_keep_list_covers_what_hyp3_can_emit():
    """A band HyP3 produces but the list omits is deleted without warning."""
    for suffix in GEOMETRY + ANALYSIS:
        assert suffix in KEEP_SUFFIXES, f"{suffix} missing from KEEP_SUFFIXES"
