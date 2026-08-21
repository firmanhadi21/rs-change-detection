"""Did the alignment survive into the geocoded stack?

Both dates are projected onto the SAME map grid, so if the alignment was
applied correctly their amplitude images must sit on top of each other: the
cross-correlation peak belongs at (0, 0). A peak at tens of pixels means the
bilinear offset model never reached the resampler, and the pair is
misregistered on the ground -- which is exactly the control that collapsed
coherence to the noise floor in alos2_radar_coherence.py.

Correlating AMPLITUDE, not phase, on purpose. Amplitude survives whatever is
happening to the phase, so this isolates registration from every other
candidate.

    conda run -n insardev-test python scripts/alos2_check_geocoded_shift.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STACK = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/alos2_lombok_stack.zarr")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=STACK)
    ap.add_argument("--size", type=int, default=1024)
    a = ap.parse_args()

    import cv2
    import xarray as xr

    scenes = []
    for g in sorted(os.listdir(a.stack)):
        gp = os.path.join(a.stack, g)
        if not os.path.isdir(gp):
            continue
        for s in sorted(os.listdir(gp)):
            if os.path.exists(os.path.join(gp, s, "re")):
                scenes.append(os.path.join(gp, s))

    def amp(path):
        ds = xr.open_zarr(path, consolidated=False)
        fill = ds["re"].attrs.get("_FillValue", 32767)
        r, m = ds["re"].values, ds["im"].values
        v = np.where((r == fill) | (m == fill), np.nan,
                     np.hypot(r.astype(np.float32), m.astype(np.float32)))
        return v

    a0, a1 = amp(scenes[0]), amp(scenes[1])
    print(f"geocoded grids {a0.shape} and {a1.shape}")

    # Take a window from the middle where both have data.
    cy, cx = a0.shape[0] // 2, a0.shape[1] // 2
    h = a.size // 2
    p0 = a0[cy - h:cy + h, cx - h:cx + h]
    p1 = a1[cy - h:cy + h, cx - h:cx + h]
    good = np.isfinite(p0) & np.isfinite(p1)
    print(f"window {p0.shape}, {100*good.mean():.1f}% valid in both")
    if good.mean() < 0.3:
        sys.exit("too little overlap in this window")

    p0 = np.nan_to_num(p0, nan=0.0)
    p1 = np.nan_to_num(p1, nan=0.0)
    p0 = (p0 - p0.mean()) / (p0.std() + 1e-10)
    p1 = (p1 - p1.mean()) / (p1.std() + 1e-10)
    hann = np.outer(np.hanning(p0.shape[0]),
                    np.hanning(p0.shape[1])).astype(np.float32)
    (dx, dy), resp = cv2.phaseCorrelate((p0 * hann).astype(np.float32),
                                        (p1 * hann).astype(np.float32))
    print(f"\n  amplitude peak at dx={dx:+.3f}, dy={dy:+.3f} px "
          f"(response {resp:.4f})")
    ok = abs(dx) < 1.0 and abs(dy) < 1.0
    print(f"  [{'PASS' if ok else 'FAIL'}] the two dates are registered on "
          f"the map grid")
    if not ok:
        print("  -> the alignment did not reach the resampler; the pair is "
              "misregistered on the ground")
    else:
        print("  -> registration is fine, so the decorrelation is in the "
              "phase, not the geometry")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
