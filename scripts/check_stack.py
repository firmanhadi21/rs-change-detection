"""Assert MintPy loaded every interferogram that exists on disk.

Three times now MintPy has discarded data with no error and no warning in the
summary -- an all-zero unwrap-error dataset it preferred over the good raw
phase, 189 ascending pairs, 198 descending pairs -- and each time the only
symptom was a stack that came back shorter than it should have been. The
earthquake measurement gets one chance, so this turns that silent failure into
a loud one.

Exit code is non-zero when the stack is short, so it can gate a pipeline.

    python3 scripts/check_stack.py output/insar_geom_desc
"""

import argparse
import datetime as dt
import glob
import os
import re
import sys

import h5py

PAIR = re.compile(r"earthchange-(\d{8})_(\d{8})")
NEEDED = ("_unw_phase.tif", "_corr.tif")


def check(run_dir, max_days=None):
    on_disk = set()
    for d in glob.glob(f"{run_dir}/hyp3/*"):
        if not os.path.isdir(d):
            continue
        m = PAIR.search(os.path.basename(d))
        if not m or not all(glob.glob(f"{d}/*{s}") for s in NEEDED):
            continue
        d1, d2 = m.group(1), m.group(2)
        if max_days:
            span = (dt.datetime.strptime(d2, "%Y%m%d")
                    - dt.datetime.strptime(d1, "%Y%m%d")).days
            if span > max_days:
                continue
        on_disk.add((d1, d2))

    stack = f"{run_dir}/mintpy/inputs/ifgramStack.h5"
    if not os.path.exists(stack):
        print(f"FAIL {run_dir}: no ifgramStack.h5")
        return 1
    with h5py.File(stack, "r") as f:
        loaded = {tuple(p) for p in f["date"][:].astype(str).tolist()}
        shape = f["unwrapPhase"].shape

    missing = sorted(on_disk - loaded)
    extra = sorted(loaded - on_disk)
    name = os.path.basename(run_dir)
    print(f"{name}: {len(on_disk)} complete on disk, {len(loaded)} loaded, "
          f"grid {shape[1]}x{shape[2]}")

    if missing:
        by_year = {}
        for d1, _ in missing:
            by_year[d1[:4]] = by_year.get(d1[:4], 0) + 1
        print(f"  FAIL {len(missing)} on disk but NOT loaded — "
              f"by year {dict(sorted(by_year.items()))}")
        for p in missing[:5]:
            print(f"      {p[0]}_{p[1]}")
    if extra:
        print(f"  note: {len(extra)} loaded pairs have no product dir")

    if not missing:
        dates = sorted({x for p in loaded for x in p})
        print(f"  OK  full stack, {dates[0]} -> {dates[-1]}")
    return 1 if missing else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", nargs="+")
    ap.add_argument("--max-days", type=int, default=None,
                    help="ignore pairs longer than this, matching the network filter")
    a = ap.parse_args()
    return max(check(r, a.max_days) for r in a.run_dir)


if __name__ == "__main__":
    sys.exit(main())
