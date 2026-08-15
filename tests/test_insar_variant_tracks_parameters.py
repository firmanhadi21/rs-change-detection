"""The job-name variant must change whenever the submitted parameters change.

When the tag was the hand-maintained string "geom", adding include_look_vectors
did not change it. The submitter matched 705 pre-existing jobs by name and
reused them with the OLD parameters, so include_look_vectors stayed False on
every job and no *_lv_phi.tif was ever produced. Nothing errored: reusing a job
by name is also the behaviour that stops us paying twice for the same pair.

These pin the property that made the bug impossible to see -- name and
parameters moving together.
"""

from earthchange import insar_series


def test_variant_changes_when_a_parameter_changes(monkeypatch):
    before = insar_series.variant()
    monkeypatch.setitem(insar_series.FIXED_JOB_PARAMETERS,
                        "include_look_vectors", False)
    assert insar_series.variant() != before, (
        "flipping include_look_vectors left the job name unchanged, so a "
        "resubmission would silently reuse jobs with the old parameters")


def test_variant_changes_when_a_parameter_is_added(monkeypatch):
    before = insar_series.variant()
    monkeypatch.setitem(insar_series.FIXED_JOB_PARAMETERS,
                        "include_wrapped_phase", True)
    assert insar_series.variant() != before


def test_variant_is_stable_for_unchanged_parameters():
    """Idempotency still has to hold, or every run repays for the same pairs."""
    assert insar_series.variant() == insar_series.variant()


def test_look_vectors_are_requested():
    """The azimuth angle in *_lv_phi.tif is what a rigorous asc/desc
    decomposition needs; without it the split into vertical and east-west
    assumes a heading instead of reading one."""
    assert insar_series.FIXED_JOB_PARAMETERS["include_look_vectors"] is True
    assert insar_series.FIXED_JOB_PARAMETERS["include_inc_map"] is True
    assert insar_series.FIXED_JOB_PARAMETERS["include_dem"] is True


def test_job_name_embeds_the_variant():
    pair = ({"date": "2022-08-23", "granule": "S1A_AAA"},
            {"date": "2022-09-04", "granule": "S1A_BBB"})
    name = insar_series.job_name("ignored", "ts", pair, insar_series.variant())
    assert insar_series.variant() in name
    # Same pair, different parameters => different job, not a silent reuse.
    other = insar_series.job_name("ignored", "ts", pair, "geomdeadbe")
    assert other != name
