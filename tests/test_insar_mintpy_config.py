"""The generated MintPy config must not reintroduce the silent-failure settings.

Each assertion here corresponds to a failure that already happened on the
Flores stack and cost hours, and every one of them failed QUIETLY -- the run
carried on and produced a shorter or emptier result instead of stopping. A
config generator is exactly where those should be pinned, because by the time
the symptom appears the cause is a config line nobody is looking at any more.
"""

import os

from earthchange.insar_series import export_mintpy


def _config(tmp_path, bands=("_unw_phase.tif", "_corr.tif", "_dem.tif",
                             "_inc_map.tif")):
    """Build a stack of fake products and return the generated config text."""
    products = []
    for d1, d2 in (("20220823", "20220904"), ("20220904", "20220916")):
        pdir = tmp_path / "hyp3" / f"earthchange-{d1}_{d2}-geom-abc123"
        pdir.mkdir(parents=True)
        for suffix in bands:
            (pdir / f"S1AA_{d1}_{d2}_VVP012_INT80_G_weF_0000{suffix}").touch()
        products.append((str(pdir), (d1, d2)))

    export_mintpy(products, str(tmp_path), "descending")
    return open(os.path.join(tmp_path, "mintpy", "earthchange.cfg")).read()


def test_unwrap_error_correction_is_off(tmp_path):
    """Both methods need connectComponent, which HyP3 GAMMA does not produce.

    bridging raises; phase_closure writes an all-zero dataset instead, which is
    far worse -- the inversion then reports 0 pixels of 1.6 million and the run
    looks like it merely found bad data.
    """
    cfg = _config(tmp_path)
    # Check the SETTING, not the file text: the comment above it names both
    # rejected methods on purpose, so a substring search would match the
    # explanation of the bug rather than the bug.
    settings = [l for l in cfg.splitlines()
                if l.startswith("mintpy.unwrapError.method")]
    assert settings, "unwrapError.method must be set explicitly"
    assert all(l.split("=")[1].strip() == "no" for l in settings)


def test_observed_dataset_is_pinned_to_raw_phase(tmp_path):
    """Turning the method off is not enough on a stack that already has one.

    obsDatasetName=auto prefers any unwrapPhase_* variant present, including a
    zeroed one left behind by an earlier run.
    """
    cfg = _config(tmp_path)
    assert "mintpy.networkInversion.obsDatasetName = unwrapPhase" in cfg


def test_temporal_coherence_gate_allows_the_run_to_reach_the_correction(tmp_path):
    """MintPy builds the reliable-pixel mask BEFORE correct_troposphere.

    At the 0.7 default, uncorrected tropical atmosphere passes a single pixel
    and aborts the run ahead of the correction that would have fixed it.
    """
    cfg = _config(tmp_path)
    line = [l for l in cfg.splitlines()
            if l.startswith("mintpy.networkInversion.minTempCoh")]
    assert line, "minTempCoh must be set explicitly, not left at auto"
    assert float(line[0].split("=")[1].strip()) <= 0.2


def test_incidence_angle_comes_from_inc_map_not_lv_theta(tmp_path):
    """lv_theta is a look-vector component; MintPy wants an incidence angle."""
    cfg = _config(tmp_path)
    assert "_inc_map.tif" in cfg
    assert "_lv_theta.tif" not in cfg


def test_geometry_lines_are_omitted_when_the_bands_are_absent(tmp_path):
    """A config naming files that do not exist fails at load, hours later."""
    cfg = _config(tmp_path, bands=("_unw_phase.tif", "_corr.tif"))
    assert "incAngleFile" not in cfg
    assert "demFile" not in cfg
    # Without a DEM these corrections cannot run, and must not be requested.
    assert "mintpy.troposphericDelay.method   = no" in cfg
