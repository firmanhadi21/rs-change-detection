"""Settle the sign convention empirically, inside one HyP3 product.

Everything downstream depends on one question: does POSITIVE unwrapped phase
mean the ground moved TOWARD the satellite or AWAY from it? Getting it
backwards inverts uplift and subsidence, and the error is invisible because
both readings produce a plausible map.

The textbook relation is dphi = -(4*pi/lambda) * d_range, so positive phase is
a range DECREASE, i.e. motion TOWARD the satellite. But conventions differ
between processors, and an argument from a textbook is not a measurement.

HyP3 ships both bands for the same pair, so the relation can be read off
directly: regress los_displacement against unw_phase over coherent pixels. The
slope carries the answer, and its magnitude also confirms the wavelength
scaling. No assumptions, no textbook.

    conda run -n base python scripts/check_los_sign.py
"""

import argparse
import glob
import os
import sys

import numpy as np

try:
    import rasterio
except ImportError:                                    # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

WAVELENGTH_M = 0.055465
ROOT = os.path.expanduser("~/GitHub/rs-change-detection/output/coseismic")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.4)
    a = ap.parse_args()

    pairs = []
    for unw in sorted(glob.glob(f"{ROOT}/**/*_unw_phase.tif", recursive=True)):
        los = unw.replace("_unw_phase.tif", "_los_disp.tif")
        corr = unw.replace("_unw_phase.tif", "_corr.tif")
        if os.path.exists(los) and os.path.exists(corr):
            pairs.append((unw, los, corr))
    if not pairs:
        sys.exit("no product carrying BOTH _unw_phase and _los_displacement.\n"
                 "The 20x4 baseline products omit los_displacement; the 10x2\n"
                 "co-seismic products include it. Fetch those first.")

    print(f"{len(pairs)} product(s) carry both bands\n")
    for unw_p, los_p, corr_p in pairs[:3]:
        with rasterio.open(unw_p) as s:
            phi = s.read(1).astype("float64")
        with rasterio.open(los_p) as s:
            los = s.read(1).astype("float64")
        with rasterio.open(corr_p) as s:
            coh = s.read(1)
        if not (phi.shape == los.shape == coh.shape):
            print(f"  {os.path.basename(unw_p)[:44]}: shapes differ, skipped")
            continue
        ok = (np.isfinite(phi) & np.isfinite(los) & (phi != 0) & (los != 0)
              & (coh >= a.min_coh))
        if ok.sum() < 5000:
            continue
        x, y = phi[ok], los[ok]
        slope = float(np.polyfit(x, y, 1)[0])
        r = float(np.corrcoef(x, y)[0, 1])
        expect = WAVELENGTH_M / (4 * np.pi)

        print(f"  {os.path.basename(unw_p)[:52]}")
        print(f"    n={int(ok.sum()):,}  slope={slope:+.6e} m/rad  r={r:+.4f}")
        print(f"    |lambda/4pi| = {expect:.6e} m/rad   "
              f"ratio = {abs(slope)/expect:.3f}")
        if slope > 0:
            print("    -> los_displacement = +phase * lambda/(4pi)")
            print("       POSITIVE PHASE AND POSITIVE los_displacement AGREE.")
        else:
            print("    -> los_displacement = -phase * lambda/(4pi)")
            print("       POSITIVE PHASE MEANS THE OPPOSITE OF POSITIVE")
            print("       los_displacement.")
        print()

    print("=== what to do with this ===")
    print("  HyP3 documents los_displacement as POSITIVE = motion TOWARD the")
    print("  satellite (range decrease). Combine that with the slope sign")
    print("  above to fix what positive unwrapped phase means, then check any")
    print("  figure captions against it. A caption asserting the wrong")
    print("  direction inverts uplift and subsidence everywhere on the map,")
    print("  while leaving the map itself looking entirely reasonable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
