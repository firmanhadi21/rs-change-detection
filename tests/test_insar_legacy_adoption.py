"""A changed variant tag must not make paid-for jobs look unsubmitted.

Deriving the job-name variant from the submitted parameters fixed a real bug,
but it renamed every job at the same time. Without adoption, 705 already
SUCCEEDED interferograms read as missing and a rerun repurchases the lot --
about 7,050 credits against a balance of 930. The credit guard would refuse,
so the visible failure is a pipeline that cannot run at all on its own stack.
"""

from earthchange.insar_series import (
    LEGACY_VARIANTS,
    _adopt_legacy,
    job_name,
    variant,
)

PAIRS = [
    ({"date": "2022-08-23", "granule": "S1A_AAA"},
     {"date": "2022-09-04", "granule": "S1A_BBB"}),
    ({"date": "2022-09-04", "granule": "S1A_BBB"},
     {"date": "2022-09-16", "granule": "S1A_CCC"}),
]


def _want():
    return {job_name("n", "ts", p, variant()): p for p in PAIRS}


def test_jobs_under_the_old_tag_are_adopted_not_resubmitted():
    known = {job_name("n", "ts", p, "geom"): f"job-{i}"
             for i, p in enumerate(PAIRS)}
    want = _want()
    assert not set(want) & set(known), "precondition: names must differ"

    adopted = _adopt_legacy("n", want, known)
    assert len(adopted) == len(PAIRS)
    known.update(adopted)
    assert all(jn in known for jn in want), (
        "a rerun would resubmit pairs that already succeeded")


def test_nothing_is_adopted_when_the_job_is_already_current():
    want = _want()
    known = {jn: "current-job" for jn in want}
    assert _adopt_legacy("n", want, known) == {}


def test_unrelated_pairs_are_not_adopted():
    """Adoption must key on the pair, not merely on the tag existing."""
    other = ({"date": "2023-01-01", "granule": "S1A_ZZZ"},
             {"date": "2023-01-13", "granule": "S1A_YYY"})
    known = {job_name("n", "ts", other, "geom"): "unrelated"}
    assert _adopt_legacy("n", _want(), known) == {}


def test_current_variant_is_not_listed_as_legacy():
    """Listing it would make the mapping ambiguous with itself."""
    assert variant() not in LEGACY_VARIANTS
