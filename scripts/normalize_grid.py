"""Warp a track's rasters onto one common grid so MintPy stops excluding them.

HyP3 sizes each geocoded product to its own granule footprint, so the raster
size drifts by a pixel or two between acquisitions. MintPy's load_data keeps
only products matching the MODAL size and silently drops the rest -- on the
descending track that discarded 198 of 354 paid interferograms, and truncated
the record 41 days short of the event.

Fixing it is a resample onto the modal grid, not a re-download: nearest
neighbour, so unwrapped phase is never interpolated across a fringe
discontinuity, and the geolocation shift is at most one 80 m pixel.

Rewrites in place. Products are re-downloadable from ASF for free if a run is
interrupted, and DEFLATE keeps the result no larger than the original.

    python3 scripts/normalize_grid.py output/insar_geom_desc
"""

import argparse
import glob
import os
import sys
from collections import Counter

# OTB 8.1.2 exports a PROJ 1.2-layout database that shadows rasterio's own and
# breaks every EPSG lookup. Drop it before rasterio initialises PROJ.
for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402

# _lv_theta and _lv_phi belong here as much as the rest. They arrive from a
# separate look-vector job at that job's own footprint, so leaving them out
# left the geometry two pixels narrower than the stack and correct_SET died
# with "operands could not be broadcast together with shapes (2995,3673)
# (2995,3671)" -- hours in, after ERA5 had already run.
BANDS = ("_unw_phase.tif", "_corr.tif", "_dem.tif",
         "_inc_map.tif", "_water_mask.tif",
         "_lv_theta.tif", "_lv_phi.tif")


def modal_grid(run_dir):
    """The grid most products already use -- warping toward it moves the fewest."""
    grids = Counter()
    for p in glob.glob(f"{run_dir}/hyp3/*/*_unw_phase.tif"):
        with rasterio.open(p) as src:
            grids[(src.width, src.height, src.transform.to_gdal(),
                   src.crs.to_string())] += 1
    if not grids:
        raise SystemExit(f"no *_unw_phase.tif under {run_dir}/hyp3/")
    (w, h, gt, crs), n = grids.most_common(1)[0]
    print(f"{sum(grids.values())} products, {len(grids)} distinct grids")
    print(f"modal grid: {w}x{h} used by {n} products")
    return w, h, rasterio.Affine.from_gdal(*gt), rasterio.crs.CRS.from_string(crs)


def conform(path, w, h, transform, crs):
    """Return True if the file was rewritten, False if it already conformed."""
    with rasterio.open(path) as src:
        if (src.width, src.height) == (w, h) and src.transform == transform:
            return False
        prof = src.profile.copy()
        data = src.read(1)
        src_transform, src_crs, nodata = src.transform, src.crs, src.nodata

    dst = np.full((h, w), nodata if nodata is not None else 0,
                  dtype=data.dtype)
    reproject(
        source=data, destination=dst,
        src_transform=src_transform, src_crs=src_crs,
        dst_transform=transform, dst_crs=crs,
        # Nearest only: unwrapped phase must not be averaged across fringes.
        resampling=Resampling.nearest,
        src_nodata=nodata, dst_nodata=nodata,
    )

    # HyP3 writes striped TIFFs whose block size is not a multiple of 16, which
    # GDAL rejects when re-emitting as tiled. Drop the inherited blocking and
    # let GDAL choose.
    for key in ("blockxsize", "blockysize", "tiled", "interleave"):
        prof.pop(key, None)
    prof.update(width=w, height=h, transform=transform, crs=crs,
                compress="deflate")
    tmp = path + ".tmp"
    with rasterio.open(tmp, "w", **prof) as out:
        out.write(dst, 1)
    os.replace(tmp, path)          # atomic; a kill cannot leave a half file
    for side in (".rsc", ".aux.xml"):
        # Stale metadata would describe the OLD size; prep_hyp3 regenerates it.
        if os.path.exists(path + side):
            os.remove(path + side)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    w, h, transform, crs = modal_grid(a.run_dir)

    dirs = sorted(d for d in glob.glob(f"{a.run_dir}/hyp3/*") if os.path.isdir(d))
    if a.limit:
        dirs = dirs[:a.limit]

    changed = skipped = failed = 0
    for i, d in enumerate(dirs, 1):
        for suffix in BANDS:
            for p in glob.glob(f"{d}/*{suffix}"):
                try:
                    if conform(p, w, h, transform, crs):
                        changed += 1
                    else:
                        skipped += 1
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    if failed <= 5:
                        print(f"  FAILED {os.path.basename(p)}: "
                              f"{type(e).__name__}: {e}")
        if i % 25 == 0 or i == len(dirs):
            print(f"  {i}/{len(dirs)} dirs  rewrote {changed}, "
                  f"already ok {skipped}, failed {failed}", flush=True)

    print(f"\nrewrote {changed}, already conformed {skipped}, failed {failed}")

    # Verify rather than assume. A band left at a different size does not fail
    # here -- it fails hours later inside correct_SET, as a numpy broadcast
    # error naming two shapes and no filename.
    odd = []
    for d in dirs:
        for suffix in BANDS:
            for p in glob.glob(f"{d}/*{suffix}"):
                try:
                    with rasterio.open(p) as src:
                        if (src.width, src.height) != (w, h):
                            odd.append((p, src.width, src.height))
                except Exception:  # noqa: BLE001
                    odd.append((p, None, None))

    if odd:
        print(f"\nWARNING: {len(odd)} file(s) still off the modal {w}x{h} grid:")
        for p, pw, ph in odd[:8]:
            print(f"    {pw}x{ph}  {os.path.basename(p)}")
        return 1

    print(f"all bands on the {w}x{h} grid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
