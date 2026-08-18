"""Collect the look-vector jobs and place *_lv_*.tif into both stacks.

The 705 original jobs recorded include_look_vectors=False, so these two jobs
are the only source of *_lv_theta.tif and *_lv_phi.tif. Look vectors describe
the track geometry rather than an individual pair, so one file per track is
what MintPy wants -- the same reasoning that made the incidence-angle recovery
two downloads instead of 705.

Copies into EVERY product dir on the track, because the ASF notebook globs
across the stack and checks the count, not just presence.

    python3 scripts/fetch_lookvectors.py            # status only
    python3 scripts/fetch_lookvectors.py --place    # download and distribute
"""

import argparse
import datetime as dt
import glob
import os
import shutil
import sys
import tempfile
import zipfile

WANT = ("_lv_theta.tif", "_lv_phi.tif", "_inc_map.tif", "_inc_map_ell.tif")
JOBS = {
    "insar_geom_desc": "earthchange-lookvectors-desc-",
    "insar_geom_asc": "earthchange-lookvectors-asc-",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--place", action="store_true",
                    help="download and copy into every product dir")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    jobs = [j for j in hyp3.find_jobs(start=since)
            if j.name and j.name.startswith("earthchange-lookvectors-")]

    if not jobs:
        print("no look-vector jobs found")
        return 1

    for j in jobs:
        print(f"{j.name}: {j.status_code}")

    pending = [j for j in jobs if j.status_code != "SUCCEEDED"]
    if pending:
        print(f"\n{len(pending)} still processing — HyP3 INSAR_GAMMA takes "
              f"20-40 min. Rerun with --place once both say SUCCEEDED.")
        return 1
    if not a.place:
        print("\nboth ready — rerun with --place to download and distribute")
        return 0

    for track, prefix in JOBS.items():
        job = next((j for j in jobs if j.name.startswith(prefix)), None)
        if job is None:
            print(f"{track}: no job matching {prefix}")
            continue

        dirs = [d for d in glob.glob(f"{a.out}/{track}/hyp3/*")
                if os.path.isdir(d)]
        if not dirs:
            print(f"{track}: no product dirs")
            continue

        with tempfile.TemporaryDirectory() as tmp:
            extracted = {}
            for p in job.download_files(tmp):
                p = str(p)
                if not p.endswith(".zip"):
                    continue
                with zipfile.ZipFile(p) as z:
                    for member in z.namelist():
                        if member.endswith(WANT):
                            suffix = next(w for w in WANT
                                          if member.endswith(w))
                            dest = os.path.join(tmp, os.path.basename(member))
                            with z.open(member) as src, \
                                    open(dest, "wb") as out:
                                shutil.copyfileobj(src, out)
                            extracted[suffix] = dest

            if not extracted:
                print(f"{track}: job produced none of {WANT}")
                continue
            print(f"{track}: got {sorted(extracted)}")

            # ONE product dir, not all of them. Look vectors describe the
            # track, so MintPy wants a single geometry file and the notebook
            # only checks that at least one exists. Copying all four bands into
            # all 705 dirs writes ~127 GB and fills the disk -- the same
            # reasoning that made the incidence-angle recovery two downloads
            # rather than 705.
            target = sorted(dirs)[0]
            unw = glob.glob(f"{target}/*_unw_phase.tif")
            if not unw:
                print(f"{track}: {target} has no _unw_phase.tif to name after")
                continue
            stem = os.path.basename(unw[0])[:-len("_unw_phase.tif")]

            copied = []
            for suffix, src in sorted(extracted.items()):
                dst = os.path.join(target, f"{stem}{suffix}")
                if not os.path.exists(dst):
                    shutil.copyfile(src, dst)
                    copied.append(os.path.basename(dst))
            print(f"{track}: placed {len(copied)} files in "
                  f"{os.path.basename(target)}")
            for c in copied:
                print(f"    {c}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
