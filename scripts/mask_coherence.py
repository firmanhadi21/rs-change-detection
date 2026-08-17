"""Mask a HyP3 coherence raster with its water mask, and describe what is left.

The epicentre is offshore, so a large part of every frame is Flores Sea. Water
returns near-zero coherence always, which drags every summary statistic down
and makes the land distribution unreadable -- the median coherence of the full
frame says more about how much sea is in it than about the ground.

Masking also matters for what comes next. The damage proxy is
coherence(pre-post) minus coherence(pre-pre), and pixels with low BASELINE
coherence have no room to drop, so their difference is not interpretable. This
prints the distribution needed to choose that threshold from the data rather
than from habit.

    python3 scripts/mask_coherence.py <corr.tif> [water_mask.tif]
"""

import argparse
import os
import sys

for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

import numpy as np  # noqa: E402
import rasterio  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corr")
    ap.add_argument("water_mask", nargs="?", default=None)
    ap.add_argument("-o", "--out", default=None,
                    help="output path (default: alongside, *_corr_masked.tif)")
    a = ap.parse_args()

    corr_path = a.corr
    mask_path = a.water_mask or corr_path.replace("_corr.tif", "_water_mask.tif")
    out_path = a.out or corr_path.replace(".tif", "_masked.tif")

    for p in (corr_path, mask_path):
        if not os.path.exists(p):
            raise SystemExit(f"not found: {p}")

    with rasterio.open(corr_path) as src:
        corr = src.read(1).astype("float32")
        prof = src.profile.copy()
        corr_shape, corr_tf = src.shape, src.transform
    with rasterio.open(mask_path) as src:
        water = src.read(1)
        mask_shape, mask_tf = src.shape, src.transform

    print(f"coherence : {os.path.basename(corr_path)}  {corr_shape}")
    print(f"water mask: {os.path.basename(mask_path)}  {mask_shape}")

    if corr_shape != mask_shape:
        raise SystemExit(
            f"grids differ ({corr_shape} vs {mask_shape}); they must match — "
            f"both come from the same HyP3 product, so this should not happen")
    if corr_tf != mask_tf:
        print("  WARNING: same shape but different transform")

    # HyP3 water mask: 1 = land, 0 = water. Checked rather than assumed,
    # because getting it backwards keeps the sea and throws away the island.
    #
    # The comparison MUST ignore zeros. A HyP3 frame is a bounding box around a
    # slanted SAR swath, so large areas inside it have coherence exactly 0
    # simply for being outside the footprint -- and on this frame 81.5% of land
    # pixels are zero that way against 32.2% of sea. Averaging over all pixels
    # therefore made land look LESS coherent than water and inverted the mask.
    vals = np.unique(water)
    print(f"\nwater mask values: {vals[:6]}{' ...' if vals.size > 6 else ''}")
    land = water == 1
    print(f"  pixels where mask == 1: {100*land.mean():.1f}%")

    def median_observed(sel):
        v = corr[sel]
        v = v[np.isfinite(v) & (v > 0)]
        return float(np.median(v)) if v.size else float("nan")

    med_in, med_out = median_observed(land), median_observed(~land)
    print(f"  median coherence, mask==1, non-zero only: {med_in:.3f}")
    print(f"  median coherence, mask==0, non-zero only: {med_out:.3f}")

    if np.isfinite(med_in) and np.isfinite(med_out) and med_out > med_in:
        print("  POLARITY INVERTED — mask==0 is the more coherent class. "
              "Treating 0 as land.")
        land = ~land
    else:
        print("  mask==1 is land, as expected")

    masked = np.where(land, corr, np.nan)

    prof.update(dtype="float32", nodata=np.nan, compress="deflate")
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(masked, 1)
    print(f"\nwrote {out_path}")

    v = masked[np.isfinite(masked) & (masked > 0)]
    print(f"\n=== coherence over land ===")
    print(f"  valid pixels: {v.size:,} of {masked.size:,} "
          f"({100*v.size/masked.size:.1f}% of frame)")
    if v.size == 0:
        print("  nothing left — check the mask polarity")
        return 1

    for q in (5, 25, 50, 75, 95):
        print(f"    p{q:<3} {np.percentile(v, q):.3f}")
    print(f"    mean {v.mean():.3f}")

    print("\n=== how much ground can support a damage measurement ===")
    for t in (0.2, 0.3, 0.4, 0.5, 0.6):
        n = int((v >= t).sum())
        print(f"    baseline coherence >= {t:.1f}: {n:>9,} px "
              f"({100*n/v.size:5.1f}% of land)")
    print("\n  Pixels below ~0.3 have little room to drop, so their coherence")
    print("  CHANGE will not be interpretable. The figure at 0.3 above is")
    print("  roughly the area where damage could actually be detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
