"""Assemble the HyP3 stack inside OpenScienceLab, without the project picker.

ASF's notebook lists one radio button per HyP3 job NAME and downloads a single
"project". earthchange names each interferogram uniquely so resubmission is
idempotent and never pays twice for the same pair -- which is correct, but
makes the stack appear as 705 projects instead of one. Job names are fixed at
submission, so the existing stack cannot be renamed into a single project
without resubmitting all 705 at roughly 7,050 credits.

This selects by NAME PREFIX instead, and sorts jobs into ascending and
descending directories, producing exactly the layout prep_hyp3 expects:

    <out>/insar_asc/hyp3/<job name>/*.tif
    <out>/insar_desc/hyp3/<job name>/*.tif

Disk: the full four-year stack is ~54 GB across both tracks. OpenScienceLab
quotas are frequently smaller than that, so --max-pairs and --start/--end exist
to take a workable subset, and --dry-run reports the size before committing.

    python3 opensciencelab_fetch.py --dry-run
    python3 opensciencelab_fetch.py --track asc --start 2026-01-01
"""

import argparse
import datetime as dt
import os
import re
import sys
import zipfile

PAIR = re.compile(r"earthchange-(\d{8})_(\d{8})")
# Keep what MintPy reads; skipping the rest roughly halves the download.
KEEP = ("_unw_phase.tif", "_corr.tif", "_dem.tif", "_water_mask.tif",
        "_lv_theta.tif", "_lv_phi.tif", "_inc_map.tif", ".txt")


def flight_direction(granule):
    """ASCENDING or DESCENDING for a Sentinel-1 granule.

    Uses asf_search when available, because it is authoritative. Falls back to
    acquisition hour, which separates cleanly for a single AOI -- over Flores
    ascending passes near 10:00 UTC and descending near 21:30 UTC -- but would
    be wrong for a different region, hence the warning.
    """
    try:
        import asf_search as asf
        r = asf.granule_search([granule])
        if r:
            return r[0].properties["flightDirection"].upper()
    except Exception:  # noqa: BLE001
        pass

    m = re.search(r"_(\d{8})T(\d{2})", granule)
    if not m:
        return "UNKNOWN"
    hour = int(m.group(2))
    return "DESCENDING" if hour >= 16 else "ASCENDING"


def _place_look_vectors(job, root, track):
    """Put one lv_theta/lv_phi pair into the FIRST product dir of a track.

    Look vectors describe the track, not a pair, so MintPy wants one file --
    copying them into every product dir would multiply ~90 MB by the number of
    products and, on a 705-product stack, fill the disk (it did, locally).
    Named after the product they sit beside so per-product globs resolve.
    """
    import glob
    import shutil
    import tempfile

    if job is None:
        print(f"  {track}: no look-vector job — stack will have no azimuth "
              f"angle, and ASF's notebook will reject it")
        return

    dirs = sorted(d for d in glob.glob(f"{root}/*") if os.path.isdir(d))
    if not dirs:
        return
    target = dirs[0]
    unw = glob.glob(f"{target}/*_unw_phase.tif")
    if not unw:
        return
    stem = os.path.basename(unw[0])[:-len("_unw_phase.tif")]

    if glob.glob(f"{target}/*_lv_phi.tif"):
        print(f"  {track}: look vectors already present")
        return

    with tempfile.TemporaryDirectory() as tmp:
        try:
            paths = job.download_files(tmp)
        except Exception as e:  # noqa: BLE001
            print(f"  {track}: look-vector download failed {type(e).__name__}")
            return
        for p in map(str, paths):
            if not p.endswith(".zip"):
                continue
            with zipfile.ZipFile(p) as z:
                for member in z.namelist():
                    for suffix in ("_lv_theta.tif", "_lv_phi.tif",
                                   "_inc_map.tif"):
                        if member.endswith(suffix):
                            dst = os.path.join(target, f"{stem}{suffix}")
                            with z.open(member) as src, \
                                 open(dst, "wb") as o:
                                shutil.copyfileobj(src, o)
    print(f"  {track}: look vectors placed in {os.path.basename(target)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefix", default="earthchange-")
    ap.add_argument("--out", default="stack")
    ap.add_argument("--track", choices=("asc", "desc", "both"), default="both")
    ap.add_argument("--start", help="only pairs whose first date is >= this (YYYY-MM-DD)")
    ap.add_argument("--end", help="only pairs whose second date is <= this")
    ap.add_argument("--max-pairs", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3000)
    jobs = [j for j in hyp3.find_jobs(start=since)
            if j.name and j.name.startswith(a.prefix)
            and j.status_code == "SUCCEEDED" and PAIR.search(j.name)]
    print(f"{len(jobs)} SUCCEEDED jobs match {a.prefix!r}")

    def in_window(job):
        m = PAIR.search(job.name)
        d1, d2 = m.group(1), m.group(2)
        if a.start and d1 < a.start.replace("-", ""):
            return False
        if a.end and d2 > a.end.replace("-", ""):
            return False
        return True

    jobs = [j for j in jobs if in_window(j)]
    print(f"{len(jobs)} within the requested window")

    # One lookup per distinct granule, not per job.
    cache, sorted_jobs = {}, {"asc": [], "desc": [], "unknown": []}
    for j in jobs:
        g = (j.job_parameters or {}).get("granules", [None])[0]
        if g is None:
            sorted_jobs["unknown"].append(j)
            continue
        if g not in cache:
            cache[g] = flight_direction(g)
        d = cache[g]
        key = ("asc" if d == "ASCENDING"
               else "desc" if d == "DESCENDING" else "unknown")
        sorted_jobs[key].append(j)

    for k, v in sorted_jobs.items():
        print(f"  {k}: {len(v)}")
    if sorted_jobs["unknown"]:
        print("  WARNING: unknown flight direction — check asf_search is installed")

    # The look-vector jobs carry no date pair, so the filter above drops them --
    # and without lv_theta/lv_phi the stack has no azimuth angle and ASF's own
    # notebook refuses it. They are per-track geometry, so one each is enough.
    lv = {}
    for j in hyp3.find_jobs(start=since):
        if not j.name or not j.name.startswith("earthchange-lookvectors-"):
            continue
        if j.status_code != "SUCCEEDED":
            continue
        lv["asc" if "-asc-" in j.name else "desc"] = j
    print(f"look-vector jobs found: {sorted(lv)}")

    wanted = (["asc", "desc"] if a.track == "both" else [a.track])
    plan = []
    for k in wanted:
        sel = sorted(sorted_jobs[k], key=lambda j: j.name)
        if a.max_pairs:
            sel = sel[:a.max_pairs]
        plan.append((k, sel))
        print(f"{k}: {len(sel)} to fetch  (~{len(sel)*0.075:.1f} GB kept)")

    if a.dry_run:
        print("\ndry run — rerun without --dry-run to download")
        return 0

    for track, sel in plan:
        root = os.path.join(a.out, f"insar_{track}", "hyp3")
        os.makedirs(root, exist_ok=True)
        for i, job in enumerate(sel, 1):
            dest = os.path.join(root, job.name)
            if os.path.isdir(dest) and os.listdir(dest):
                continue
            os.makedirs(dest, exist_ok=True)
            try:
                paths = job.download_files(dest)
            except Exception as e:  # noqa: BLE001
                print(f"  {job.name}: download failed {type(e).__name__}")
                continue
            for p in map(str, paths):
                if not p.endswith(".zip"):
                    continue
                with zipfile.ZipFile(p) as z:
                    for member in z.namelist():
                        if member.endswith(KEEP):
                            with z.open(member) as src, \
                                 open(os.path.join(
                                     dest, os.path.basename(member)), "wb") as o:
                                o.write(src.read())
                os.remove(p)   # before the next fetch, so peak disk stays low
            if i % 25 == 0 or i == len(sel):
                print(f"  {track} {i}/{len(sel)}", flush=True)

        _place_look_vectors(lv.get(track), root, track)

    print(f"\nNext, in OpenScienceLab:\n"
          f"  prep_hyp3.py '{a.out}/insar_asc/hyp3/*/*_unw_phase.tif'\n"
          f"  smallbaselineApp.py <your cfg>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
