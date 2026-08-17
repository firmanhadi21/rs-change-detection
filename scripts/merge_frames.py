"""Mosaic two along-track HyP3 frames into one raster.

Frames 1148 and 1153 are consecutive along ascending path 112 and overlap by a
few kilometres. Merging gives a single coherence map covering Flores plus the
sea north of it, which is what a report figure needs.

Overlap handling is the only real decision here. The default in most tools is
"last one wins", which puts an arbitrary seam through the overlap. Coherence
from two frames of the SAME acquisition pair should agree there, so averaging
is both defensible and a check: if the two disagree in the overlap, something
is wrong with one of them, and this prints that difference rather than hiding
it under a seam.

    python3 scripts/merge_frames.py a.tif b.tif -o merged.tif
"""

import argparse
import os
import sys

for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.merge import merge  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    srcs = []
    for p in a.inputs:
        if not os.path.exists(p):
            raise SystemExit(f"not found: {p}")
        srcs.append(rasterio.open(p))

    crs = {s.crs for s in srcs}
    res = {(round(s.res[0], 6), round(s.res[1], 6)) for s in srcs}
    print(f"{len(srcs)} inputs")
    for s in srcs:
        b = s.bounds
        print(f"  {os.path.basename(s.name)[:46]}")
        print(f"      {s.width} x {s.height}  {s.crs}  res {s.res[0]:.1f} m")
        print(f"      N {b.top:.0f}  S {b.bottom:.0f}  "
              f"W {b.left:.0f}  E {b.right:.0f}")

    if len(crs) > 1:
        raise SystemExit(f"inputs have different CRS: {crs} — reproject first")
    if len(res) > 1:
        raise SystemExit(f"inputs have different resolution: {res}")

    # Average where frames overlap, rather than letting one overwrite the
    # other. Both come from the same acquisition pair, so they should agree;
    # a seam would be an artefact of merge order, not of the data.
    def mean_overlap(merged_data, new_data, merged_mask, new_mask, **kwargs):
        both = ~merged_mask & ~new_mask
        only_new = merged_mask & ~new_mask
        merged_data[both] = (merged_data[both] + new_data[both]) / 2.0
        merged_data[only_new] = new_data[only_new]
        merged_mask[only_new] = False

    mosaic, transform = merge(srcs, method=mean_overlap, nodata=np.nan)

    prof = srcs[0].profile.copy()
    prof.update(height=mosaic.shape[1], width=mosaic.shape[2],
                transform=transform, dtype="float32", nodata=np.nan,
                compress="deflate", tiled=True, blockxsize=512,
                blockysize=512)

    with rasterio.open(a.out, "w", **prof) as dst:
        dst.write(mosaic[0].astype("float32"), 1)

    print(f"\nwrote {a.out}")
    print(f"  {mosaic.shape[2]} x {mosaic.shape[1]}")

    v = mosaic[0]
    valid = np.isfinite(v) & (v > 0)
    print(f"  valid pixels: {int(valid.sum()):,} "
          f"({100*valid.mean():.1f}% of mosaic)")
    if valid.any():
        x = v[valid]
        for q in (25, 50, 75, 95):
            print(f"    p{q:<3} {np.percentile(x, q):.3f}")
        print(f"    mean {x.mean():.3f}")

    # Do the two frames agree where they overlap? Read each onto the mosaic
    # grid and compare. Disagreement means one of them is wrong.
    if len(srcs) == 2:
        from rasterio.warp import reproject, Resampling
        planes = []
        for s in srcs:
            dest = np.full((mosaic.shape[1], mosaic.shape[2]), np.nan,
                           dtype="float32")
            reproject(source=rasterio.band(s, 1), destination=dest,
                      dst_transform=transform, dst_crs=prof["crs"],
                      src_nodata=np.nan, dst_nodata=np.nan,
                      resampling=Resampling.nearest)
            planes.append(dest)
        ov = (np.isfinite(planes[0]) & (planes[0] > 0)
              & np.isfinite(planes[1]) & (planes[1] > 0))
        n = int(ov.sum())
        print(f"\n=== overlap between the two frames ===")
        print(f"  {n:,} pixels")
        if n:
            d = planes[0][ov] - planes[1][ov]
            print(f"  difference: median {np.median(d):+.4f}  "
                  f"mean {d.mean():+.4f}  RMS {np.sqrt((d**2).mean()):.4f}")
            if abs(np.median(d)) < 0.05:
                print("  the frames agree — averaging the overlap is safe")
            else:
                print("  the frames DISAGREE materially; check calibration "
                      "before trusting the mosaic")

    for s in srcs:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
