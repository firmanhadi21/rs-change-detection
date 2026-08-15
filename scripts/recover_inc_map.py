"""Recover the geometry bands that pruning deleted, without re-storing 58 GB.

HyP3 produced *_inc_map.tif for all 705 jobs; prune() removed the local copies
because the keep-list named only _lv_theta.tif. The bands still exist inside the
product zips on ASF, so this is a re-download, not a reprocessing -- no credits.

Downloading all 705 products again would cost ~58 GB. Instead each zip is
fetched, the wanted bands extracted straight into the existing product
directory, and the zip deleted before the next one starts. Peak extra disk is
one product, about 70 MB.

Safe to run while MintPy is working on the same directories: it only ADDS files,
and MintPy enumerated its inputs at load time.

    python3 scripts/recover_inc_map.py output/insar_geom_desc
"""

import argparse
import glob
import os
import sys
import tempfile
import zipfile

WANT = ("_inc_map.tif", "_inc_map_ell.tif", "_lv_theta.tif", "_lv_phi.tif")


def client():
    try:
        import hyp3_sdk
    except ImportError:
        raise SystemExit("pip install hyp3_sdk")
    return hyp3_sdk.HyP3()


def recover(run_dir, limit=None):
    import datetime as dt

    hyp3 = client()
    dirs = {os.path.basename(d): d
            for d in glob.glob(f"{run_dir}/hyp3/*") if os.path.isdir(d)}
    todo = {name: d for name, d in dirs.items()
            if not any(glob.glob(f"{d}/*{s}") for s in WANT)}
    print(f"{len(dirs)} products, {len(todo)} missing every geometry band")
    if not todo:
        print("nothing to do")
        return 0

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    jobs = {j.name: j for j in hyp3.find_jobs(start=since)
            if j.name and j.name in todo}
    print(f"matched {len(jobs)} jobs by name")

    done = failed = 0
    names = sorted(jobs)[:limit] if limit else sorted(jobs)
    for i, name in enumerate(names, 1):
        job, dest = jobs[name], todo[name]
        with tempfile.TemporaryDirectory() as tmp:
            try:
                paths = job.download_files(tmp)
            except Exception as e:  # noqa: BLE001
                failed += 1
                if failed <= 3:
                    print(f"  download failed {name}: {type(e).__name__}")
                continue

            got = 0
            for p in paths:
                p = str(p)
                if not p.endswith(".zip"):
                    continue
                with zipfile.ZipFile(p) as z:
                    for member in z.namelist():
                        if member.endswith(WANT):
                            target = os.path.join(dest,
                                                  os.path.basename(member))
                            with z.open(member) as src, \
                                    open(target, "wb") as out:
                                out.write(src.read())
                            got += 1
            # TemporaryDirectory removes the zip here, before the next fetch.
            done += 1 if got else 0
            if not got and failed <= 3:
                print(f"  no geometry band inside {name}")

        if i % 25 == 0 or i == len(names):
            print(f"  {i}/{len(names)}  recovered {done}, failed {failed}",
                  flush=True)

    print(f"\nrecovered {done}, failed {failed}")
    return 0 if failed == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N products, for a trial run")
    a = ap.parse_args()
    return recover(a.run_dir, a.limit)


if __name__ == "__main__":
    sys.exit(main())
