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
    """Return a list of problems with one product directory."""
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

    # prep_hyp3 writes a .rsc beside each raster; absence means it did not run
    # or it failed on this product.
    unw = glob.glob(f"{d}/*_unw_phase.tif")
    if unw and not os.path.exists(unw[0] + ".rsc"):
        problems.append("no .rsc (prep_hyp3 did not succeed)")

    return problems


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

    broken = {}
    empty = []
    for d in dirs:
        if not glob.glob(f"{d}/*"):
            empty.append(d)
            continue
        p = inspect(d)
        if p:
            broken[d] = p

    print(f"{len(dirs)} products, {len(broken)} with problems, "
          f"{len(empty)} empty")

    for d, probs in sorted(broken.items()):
        print(f"\n  {os.path.basename(d)}")
        for p in probs[:4]:
            print(f"      {p}")

    for d in empty:
        print(f"\n  {os.path.basename(d)}\n      EMPTY directory")

    victims = list(broken) + empty
    if not victims:
        print("\nnothing to repair")
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
