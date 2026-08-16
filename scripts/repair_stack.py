"""Find products that will not load, and optionally clear them for re-fetching.

prep_hyp3 failing on a product means that interferogram is absent from the
stack. The usual cause is a truncated download -- a GeoTIFF that exists, has a
plausible size, and cannot be opened. Counting failures is not enough: you need
to know WHICH, because the fix (delete and re-fetch, free) is per product.

Checks each product for the bands MintPy reads, that each opens, and that
prep_hyp3 left its .rsc sidecar. --clean removes the broken directories so
opensciencelab_fetch.py downloads them again -- it skips directories that
already exist and are non-empty, so a broken one is never retried otherwise.

    python3 repair_stack.py stack/insar_asc
    python3 repair_stack.py stack/insar_asc --clean
    python3 opensciencelab_fetch.py --track asc      # re-fetch the cleaned ones
"""

import argparse
import glob
import os
import shutil
import sys

for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

REQUIRED = ("_unw_phase.tif", "_corr.tif")
NICE = ("_dem.tif",)


def inspect(d):
    """Return (damage, pending) for one product directory.

    The distinction decides whether deleting is right. `damage` means the files
    on disk are missing or unusable, so the product must be downloaded again.
    `pending` means the files are fine and only prep_hyp3 has not succeeded --
    which is routinely an UPSTREAM problem, not a data problem: an older MintPy
    rejecting Sentinel-1C/D names leaves 21 intact products with no .rsc.
    Deleting those would discard good data and re-download it for nothing.
    """
    problems = []

    for suffix in REQUIRED + NICE:
        hits = glob.glob(f"{d}/*{suffix}")
        if not hits:
            problems.append(f"missing {suffix}")
            continue
        for p in hits:
            if os.path.getsize(p) == 0:
                problems.append(f"zero-byte {os.path.basename(p)}")

    if not glob.glob(f"{d}/*.txt"):
        # prep_hyp3 reads the HyP3 metadata text file for dates and baseline.
        problems.append("missing .txt metadata")

    # A truncated GeoTIFF opens as a file but not as a raster.
    try:
        import rasterio
        for p in glob.glob(f"{d}/*_unw_phase.tif") + glob.glob(f"{d}/*_corr.tif"):
            try:
                with rasterio.open(p) as src:
                    if src.width == 0 or src.height == 0:
                        problems.append(f"empty raster {os.path.basename(p)}")
            except Exception as e:  # noqa: BLE001
                problems.append(f"unreadable {os.path.basename(p)}: "
                                f"{type(e).__name__}")
    except ImportError:
        pass

    # Reported separately, and never a reason to delete: the rasters are intact
    # and rerunning prep_hyp3 is enough.
    pending = []
    unw = glob.glob(f"{d}/*_unw_phase.tif")
    if unw and not os.path.exists(unw[0] + ".rsc"):
        pending.append("no .rsc — rerun prep_hyp3 (data is fine)")

    return problems, pending


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stack")
    ap.add_argument("--clean", action="store_true",
                    help="delete broken product dirs so they can be re-fetched")
    a = ap.parse_args()

    root = os.path.join(a.stack, "hyp3")
    dirs = sorted(d for d in glob.glob(f"{root}/*") if os.path.isdir(d))
    if not dirs:
        raise SystemExit(f"no product dirs under {root}")

    broken, waiting = {}, {}
    empty = []
    for d in dirs:
        if not glob.glob(f"{d}/*"):
            empty.append(d)
            continue
        dmg, pend = inspect(d)
        if dmg:
            broken[d] = dmg
        elif pend:
            waiting[d] = pend

    print(f"{len(dirs)} products: {len(broken)} damaged, {len(empty)} empty, "
          f"{len(waiting)} awaiting prep_hyp3")

    if broken or empty:
        print("\n=== need re-downloading ===")
        for d, probs in sorted(broken.items()):
            print(f"  {os.path.basename(d)}")
            for p in probs[:4]:
                print(f"      {p}")
        for d in empty:
            print(f"  {os.path.basename(d)}\n      EMPTY directory")

    if waiting:
        print(f"\n=== intact, only missing .rsc ===")
        print("  Data is fine. Rerun prep_hyp3 (opensciencelab_run.py); do NOT"
              "\n  delete these. Commonly an older MintPy that cannot parse"
              "\n  Sentinel-1C/D names — fix that instead.")
        for d in sorted(waiting)[:8]:
            print(f"      {os.path.basename(d)}")
        if len(waiting) > 8:
            print(f"      ... and {len(waiting) - 8} more")

    victims = list(broken) + empty
    if not victims:
        print("\nnothing to re-download")
        return 0

    if not a.clean:
        print(f"\n{len(victims)} to clear — rerun with --clean, then "
              f"opensciencelab_fetch.py to download them again (free)")
        return 1

    for d in victims:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\nremoved {len(victims)} directories; "
          f"rerun opensciencelab_fetch.py to re-download them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
