"""Prepare a HyP3 stack for MintPy and run the small-baseline workflow.

prep_hyp3.py writes a ROI_PAC .rsc sidecar next to each raster, which is how
MintPy learns the geometry and dates. It is run per product rather than with one
huge argument list: 354 products is over a thousand paths, past what the shell
will take, and a per-product loop also survives one bad product instead of
losing the batch.

Only the rasters are passed. The .txt is found by prep_hyp3 itself; handing it
in makes prep_hyp3 try to open it with GDAL and abort the run.

    python3 scripts/run_mintpy.py output/insar_geom_desc --prep
    python3 scripts/run_mintpy.py output/insar_geom_desc --run
"""

import argparse
import glob
import os
import subprocess
import sys

MINTPY = "/Users/firmanhadi/miniforge3/envs/mintpy/bin"

# An OTB install exports PROJ_LIB pointing at a PROJ 1.2 database, which breaks
# every CRS lookup GDAL makes. MintPy is entirely CRS operations.
ENV = {k: v for k, v in os.environ.items()
       if not (k in ("PROJ_LIB", "GDAL_DATA") and "OTB" in v)}


def prep(run_dir):
    dirs = sorted(d for d in glob.glob(f"{run_dir}/hyp3/*") if os.path.isdir(d))
    print(f"{len(dirs)} products in {run_dir}")

    ok = failed = skipped = 0
    for i, d in enumerate(dirs, 1):
        rasters = (glob.glob(f"{d}/*_unw_phase.tif")
                   + glob.glob(f"{d}/*_corr.tif")
                   + glob.glob(f"{d}/*_dem.tif")
                   + glob.glob(f"{d}/*_lv_theta.tif")
                   + glob.glob(f"{d}/*_inc_map.tif"))
        if not rasters:
            skipped += 1
            continue
        if len(glob.glob(f"{d}/*.rsc")) >= 2:      # already prepared
            ok += 1
            continue

        r = subprocess.run([f"{MINTPY}/prep_hyp3.py"] + rasters,
                           capture_output=True, text=True, env=ENV, timeout=600)
        if r.returncode == 0 or glob.glob(f"{d}/*.rsc"):
            ok += 1
        else:
            failed += 1
            if failed <= 3:
                print(f"  FAILED {os.path.basename(d)}: "
                      f"{(r.stderr or r.stdout).strip()[-200:]}")
        if i % 50 == 0 or i == len(dirs):
            print(f"  {i}/{len(dirs)}  ok {ok}, failed {failed}", flush=True)

    print(f"\nprepared {ok}, failed {failed}, no rasters {skipped}")
    return failed == 0


def run(run_dir):
    cfg = os.path.join(run_dir, "mintpy", "earthchange.cfg")
    if not os.path.exists(cfg):
        raise SystemExit(f"no config at {cfg} — the run never wrote one")
    work = os.path.join(run_dir, "mintpy")
    print(f"smallbaselineApp.py {cfg}")
    r = subprocess.run([f"{MINTPY}/smallbaselineApp.py", cfg],
                       cwd=work, env=ENV)
    print(f"exit {r.returncode}")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--prep", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()

    if a.prep or not a.run:
        if not prep(a.run_dir) and not a.run:
            return 1
    if a.run:
        return 0 if run(a.run_dir) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
