"""Submit ONE job per track that actually carries look vectors.

The 705 existing jobs all recorded include_look_vectors=False, so *_lv_phi.tif
and *_lv_theta.tif were never produced and cannot be recovered by re-download.
Resubmitting all of them would cost ~7,050 credits against a balance of 950.

It is not necessary. Look vectors, like incidence angle, describe the TRACK
geometry rather than an individual pair, and MintPy wants one geometry file per
track -- so two jobs suffice, at roughly 20 credits.

Reuses a real granule pair from each existing stack, so the geometry lands on
the same orbit and frame as the data it will describe.

    python3 scripts/submit_lookvectors.py            # show the plan, submit nothing
    python3 scripts/submit_lookvectors.py --submit
"""

import argparse
import glob
import os
import re
import sys

# An older earthchange is pip-installed into site-packages and would shadow the
# working tree. The variant tag must come from the code being edited, or the
# submitted parameters and the job name drift apart -- which is the exact bug
# this script exists to repair.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earthchange.insar_series import FIXED_JOB_PARAMETERS, variant  # noqa: E402

OUT = "output"
TRACKS = ("insar_geom_desc", "insar_geom_asc")
GRANULE = re.compile(r"(S1[AB]_[A-Z0-9_]+)")


def granules_for(track):
    """A granule pair from this track, read from a delivered product's metadata."""
    for txt in sorted(glob.glob(f"{OUT}/{track}/hyp3/*/*.txt")):
        names = []
        for line in open(txt, errors="ignore"):
            if "Reference Granule:" in line or "Secondary Granule:" in line:
                names.append(line.split(":", 1)[1].strip())
        if len(names) == 2:
            return names, txt
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true",
                    help="actually submit; without it, only print the plan")
    a = ap.parse_args()

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()

    plan = []
    for track in TRACKS:
        names, src = granules_for(track)
        if not names:
            print(f"{track}: could not read a granule pair from any .txt")
            continue
        tag = f"earthchange-lookvectors-{track.split('_')[-1]}-{variant()}"
        plan.append((track, tag, names))
        print(f"{track}")
        print(f"  from {os.path.basename(src)}")
        for n in names:
            print(f"    {n}")
        print(f"  job name: {tag}")

    have = hyp3.check_credits()
    print(f"\n{len(plan)} jobs to submit, credits available: {have}")
    print(f"parameters: {FIXED_JOB_PARAMETERS}")

    if not a.submit:
        print("\ndry run — pass --submit to send these")
        return 0

    # Don't resubmit if a job with this exact name already succeeded.
    import datetime as dt
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    existing = {j.name for j in hyp3.find_jobs(start=since) if j.name}

    prepared = [{
        "job_type": "INSAR_GAMMA",
        "name": tag,
        "job_parameters": {"granules": names, **FIXED_JOB_PARAMETERS},
    } for _, tag, names in plan if tag not in existing]

    if not prepared:
        print("all already submitted under these names — nothing to do")
        return 0

    jobs = hyp3.submit_prepared_jobs(prepared)
    for j in jobs:
        print(f"submitted {j.name}  id={j.job_id}  status={j.status_code}")
    print(f"\n{len(jobs)} submitted. Credits now: {hyp3.check_credits()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
