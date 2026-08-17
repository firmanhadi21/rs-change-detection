"""Download the finished Flores co-seismic HyP3 products.

Keeps only the bands the analysis needs, and deletes each zip as soon as it is
unpacked, so peak disk stays around one product rather than the full download.

Which bands, and why each is here:

  _los_displacement  displacement in METRES, computed by HyP3 from the
                     unwrapped phase. Using it avoids doing the phase-to-range
                     conversion by hand, which is one fewer place to lose a
                     factor of 2 or a sign.
  _corr              coherence. Needed from BOTH pairs -- the damage proxy is
                     coherence(pre-post) minus coherence(pre-pre), and a
                     difference needs both terms.
  _unw_phase         the unwrapped phase itself, for checking the displacement
                     against something independent.
  _wrapped_phase     fringes. The clearest evidence that a pattern is real
                     deformation rather than atmosphere or noise -- real
                     deformation makes concentric, continuous fringes.
  _dem, _inc_map,    geometry, for projecting line-of-sight into vertical and
  _lv_theta/_lv_phi  east-west later.
  _water_mask        the epicentre is offshore; without this the sea is full
                     of meaningless phase.

    python3 scripts/fetch_coseismic.py            # status, download nothing
    python3 scripts/fetch_coseismic.py --get
"""

import argparse
import datetime as dt
import glob
import os
import sys
import tempfile
import zipfile

PROJECT = "flores-coseismic-2026"
OUT = os.path.expanduser("~/GitHub/rs-change-detection/output/coseismic")

KEEP = ("_los_displacement.tif", "_corr.tif", "_unw_phase.tif",
        "_wrapped_phase.tif", "_dem.tif", "_inc_map.tif",
        "_lv_theta.tif", "_lv_phi.tif", "_water_mask.tif", ".txt")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--get", action="store_true",
                    help="actually download; without it, status only")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    jobs = [j for j in hyp3.find_jobs(start=since)
            if j.name and j.name.startswith(PROJECT)]
    if not jobs:
        print(f"no jobs named {PROJECT}* found")
        return 1

    ready = [j for j in jobs if j.status_code == "SUCCEEDED"]
    print(f"{len(jobs)} job(s), {len(ready)} finished")
    for j in sorted(jobs, key=lambda x: x.name):
        dest = os.path.join(a.out, j.name)
        got = len(glob.glob(f"{dest}/*.tif")) if os.path.isdir(dest) else 0
        print(f"  {j.name:44} {j.status_code:10} "
              f"{'downloaded (' + str(got) + ' tif)' if got else ''}")

    if not ready:
        # Exit 0: "still processing" is a normal state, not a failure. Exiting
        # non-zero here made `conda run` print an alarming ERROR line for what
        # is simply the answer to the question that was asked.
        print("\nnothing finished yet — HyP3 usually takes 20-40 min")
        return 0
    if not a.get:
        print("\nstatus only — rerun with --get to download")
        return 0

    os.makedirs(a.out, exist_ok=True)
    done = failed = 0

    for job in ready:
        dest = os.path.join(a.out, job.name)
        if os.path.isdir(dest) and glob.glob(f"{dest}/*_corr.tif"):
            print(f"  {job.name}: already downloaded, skipping")
            continue
        os.makedirs(dest, exist_ok=True)

        # Fetch into a temp dir and unpack across, so a failed download never
        # leaves a half-populated product directory that looks complete.
        with tempfile.TemporaryDirectory() as tmp:
            try:
                paths = job.download_files(tmp)
            except Exception as e:  # noqa: BLE001
                print(f"  {job.name}: download FAILED {type(e).__name__}")
                failed += 1
                continue

            kept = 0
            for p in map(str, paths):
                if not p.endswith(".zip"):
                    continue
                with zipfile.ZipFile(p) as z:
                    for member in z.namelist():
                        if member.endswith(KEEP):
                            target = os.path.join(dest,
                                                  os.path.basename(member))
                            with z.open(member) as src, \
                                 open(target, "wb") as out:
                                out.write(src.read())
                            kept += 1
            print(f"  {job.name}: kept {kept} files")
            done += 1

    print(f"\ndownloaded {done}, failed {failed}")
    print(f"in {a.out}")

    # The analysis needs both pairs; say plainly if only one is present.
    have = {os.path.basename(d).rsplit("-", 1)[-1]
            for d in glob.glob(f"{a.out}/*") if os.path.isdir(d)}
    if "prepre" in have and "prepost" in have:
        print("\nboth pairs present — coherence change can be computed")
    else:
        missing = {"prepre", "prepost"} - have
        print(f"\nstill missing: {', '.join(sorted(missing))}")
        if "prepost" in missing:
            print("  the co-event pair needs the post-event scene "
                  "(ascending, ~18 Aug 10:16 UTC)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
