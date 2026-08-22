"""Build a MintPy stack for Flores frame 1148: 72 quiet pairs + 1 co-event.

WHAT THIS CAN AND CANNOT ANSWER, because the distinction decides how the
result should be read.

Only ONE pair brackets the 14 August rupture (2026-08-06 -> 2026-08-18), since
only one post-event scene exists. Inverting a network does not create a second
independent observation of the step, so this is NOT a second measurement of
the 4-7 cm found in the GMTSAR interferogram.

What the other 72 pairs give is the thing that measurement lacks: an empirical
noise model. They are earthquake-free, on the SAME frame and track, at the
same 12-day cadence, so their scatter is exactly what this scene's atmosphere
and orbit errors do over 12 days. That converts "4-7 cm" into "4-7 cm against
a background of X", which is the difference between a number and a result.

The limit that survives: with one post-event epoch, the atmosphere on 18
August is not separable from the co-seismic step by any inversion. MintPy
shrinks the uncertainty; only more post-event scenes remove the confound.

THREE PRACTICAL OBSTACLES, all handled here.

  Duplicates. 144 product directories hold 73 unique date pairs -- HyP3 was
  asked twice for some. Only one per date pair may enter the stack; feeding
  MintPy the same observation twice would falsely halve its variance.

  Footprints. HyP3 clips each pair to its own overlap, so the 73 differ and 22
  distinct raster sizes are present. MintPy needs one grid. The intersection
  of all of them is 253 x 73 km, which does contain the epicentre and the
  north coast, so clipping to it costs nothing that matters.

  Pixel spacing -- WHICH TURNED OUT NOT TO BE A PROBLEM. I had planned to
  resample the separately-ordered co-event product (INT40, 10x2 looks) onto
  the 80 m grid. The duplicate check above showed why that was wrong: the
  baseline network ALREADY CONTAINS 20260806_20260818 at INT80, processed
  identically to every other pair. Adding the INT40 copy would have entered
  the one observation carrying the signal twice, falsely halving its variance
  in the inversion -- the exact failure the duplicate check exists to prevent,
  arriving by a different door. The stack is therefore homogeneous HyP3 INT80
  throughout, with no resampling anywhere.

    conda run -n mintpy python scripts/mintpy_flores_setup.py --prepare
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
BASE = os.path.join(REPO, "output/coseismic/baseline/hyp3")
COEVENT = os.path.join(REPO, "output/coseismic",
                       "flores-coseismic-2026-asc-f1148-prepost-d2")
WORK = os.path.join(REPO, "data/mintpy_flores")
BANDS = ("unw_phase", "corr", "dem", "inc_map", "water_mask")
EVENT = "20260814"


def gdal_json(path):
    r = subprocess.run(["gdalinfo", "-json", path], capture_output=True,
                       text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


def pair_of(path):
    m = re.search(r"(20\d{6})T\d{6}_(20\d{6})T\d{6}", os.path.basename(path))
    return (m.group(1), m.group(2)) if m else None


def collect():
    """One product directory per unique date pair."""
    by_pair = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(BASE, "*", "*_unw_phase.tif"))):
        p = pair_of(f)
        if p:
            by_pair[p].append(f)
    chosen = {}
    for p, files in by_pair.items():
        # Deterministic pick so a rerun builds the identical stack rather than
        # a different-but-equivalent one, which would make results
        # irreproducible for no reason.
        chosen[p] = sorted(files)[0]
    dupes = sum(len(v) - 1 for v in by_pair.values())
    print(f"{len(by_pair)} unique date pairs from "
          f"{sum(len(v) for v in by_pair.values())} products "
          f"({dupes} duplicates dropped)")
    return chosen


def common_extent(files):
    x0 = y0 = -1e18
    x1 = y1 = 1e18
    for f in files:
        j = gdal_json(f)
        if not j:
            continue
        c = j["cornerCoordinates"]
        x0 = max(x0, c["upperLeft"][0]); y1 = min(y1, c["upperLeft"][1])
        x1 = min(x1, c["lowerRight"][0]); y0 = max(y0, c["lowerRight"][1])
    return x0, y0, x1, y1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prepare", action="store_true",
                    help="clip and stage the products (slow, ~73 pairs)")
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--res", type=int, default=80)
    a = ap.parse_args()

    chosen = collect()
    co = glob.glob(os.path.join(COEVENT, "*_unw_phase.tif"))
    if not co:
        sys.exit(f"no co-event unw_phase in {COEVENT}")
    co_pair = pair_of(co[0])
    print(f"co-event pair: {co_pair[0]} -> {co_pair[1]}")

    spanning = [p for p in list(chosen) + [co_pair]
                if p[0] < EVENT < p[1]]
    print(f"pairs spanning {EVENT}: {len(spanning)}  {spanning}")

    ext = common_extent(list(chosen.values()))
    print(f"\ncommon extent  x {ext[0]:.0f}..{ext[2]:.0f}  "
          f"y {ext[1]:.0f}..{ext[3]:.0f}"
          f"  ({(ext[2]-ext[0])/1000:.0f} x {(ext[3]-ext[1])/1000:.0f} km)")
    if ext[2] <= ext[0] or ext[3] <= ext[1]:
        sys.exit("no common ground across the pairs")

    if not a.prepare:
        print("\nsurvey only — rerun with --prepare to stage the stack")
        return 0

    ifg_dir = os.path.join(a.work, "interferograms")
    os.makedirs(ifg_dir, exist_ok=True)
    te = [str(ext[0]), str(ext[1]), str(ext[2]), str(ext[3])]

    def clip(src, dst):
        if os.path.exists(dst):
            return True
        r = subprocess.run(
            ["gdalwarp", "-q", "-overwrite", "-te", *te,
             "-tr", str(a.res), str(a.res), "-r", "bilinear", src, dst],
            capture_output=True, text=True)
        return r.returncode == 0

    # NOT chosen + co-event: the network already holds 20260806_20260818 at
    # INT80, processed identically. See the header.
    items = list(chosen.items())
    staged = 0
    for i, (pair, unw) in enumerate(items, 1):
        stem = os.path.basename(unw).replace("_unw_phase.tif", "")
        srcdir = os.path.dirname(unw)
        out_stem = stem
        dest = os.path.join(ifg_dir, out_stem)
        os.makedirs(dest, exist_ok=True)
        ok = True
        for band in BANDS:
            src = os.path.join(srcdir, f"{stem}_{band}.tif")
            if not os.path.exists(src):
                if band in ("unw_phase", "corr", "dem"):
                    ok = False           # required by prep_hyp3
                continue
            ok &= clip(src, os.path.join(dest, f"{out_stem}_{band}.tif"))
        txt = os.path.join(srcdir, f"{stem}.txt")
        if os.path.exists(txt):
            shutil.copy(txt, os.path.join(dest, f"{out_stem}.txt"))
        else:
            ok = False                   # prep_hyp3 reads geometry from it
        if ok:
            staged += 1
        else:
            print(f"  incomplete, skipped: {out_stem}")
        if i % 15 == 0:
            print(f"  staged {i}/{len(items)}")

    print(f"\nstaged {staged}/{len(items)} pairs into {ifg_dir}")

    cfg = os.path.join(a.work, "flores1148.txt")
    with open(cfg, "w") as f:
        f.write(f"""# MintPy — Flores frame 1148, ascending path 112
# 72 earthquake-free pairs plus the single pair spanning 14 Aug 2026.
mintpy.load.processor        = hyp3
mintpy.load.unwFile          = {ifg_dir}/*/*_unw_phase.tif
mintpy.load.corFile          = {ifg_dir}/*/*_corr.tif
mintpy.load.demFile          = {ifg_dir}/*/*_dem.tif
mintpy.load.incAngleFile     = {ifg_dir}/*/*_inc_map.tif
mintpy.load.waterMaskFile    = {ifg_dir}/*/*_water_mask.tif

# Reference far from the epicentre so the co-seismic field is not zeroed at
# the point being measured. The epicentre is near 121.35, -8.31; this sits
# ~150 km east, inside the common footprint.
mintpy.reference.lalo        = -8.25, 122.60

# Network: keep everything. The quiet pairs ARE the measurement here -- they
# are what turns the co-seismic step into a number with an uncertainty.
mintpy.network.coherenceBased = no
mintpy.network.excludeDate    = no

# Tropospheric correction is left OFF for now: ERA5 has not published
# 2026-08-18 yet. Turn it on once it has, and compare.
mintpy.troposphericDelay.method = no
mintpy.deramp                   = linear
mintpy.topographicResidual      = yes
""")
    print(f"wrote {cfg}")
    print("\nnext:")
    print(f"  cd {a.work} && conda run -n mintpy smallbaselineApp.py "
          f"{os.path.basename(cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
