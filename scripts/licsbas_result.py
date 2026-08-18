"""Read the LiCSBAS velocity field and say whether it shows a signal.

This is the independent test of the HyP3/MintPy negative result: a different
processing chain (LiCSAR interferograms, different unwrapper, LiCSBAS
inversion) over eleven years instead of four. If a coherent interseismic
velocity field exists over Flores, this is where it should appear.

LiCSBAS writes plain float32 binaries, dimensions taken from EQA.dem_par.
Velocity is mm/yr in line of sight.
"""

import os
import sys

import numpy as np

TS = os.path.expanduser(
    sys.argv[1] if len(sys.argv) > 1
    else "~/GitHub/rs-change-detection/output/licsbas/TS_GEOCml10")


def par(path):
    d = {}
    for line in open(path, errors="ignore"):
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return d


def read(name, shape):
    p = f"{TS}/results/{name}"
    if not os.path.exists(p):
        return None
    a = np.fromfile(p, dtype=np.float32)
    if a.size != shape[0] * shape[1]:
        print(f"  {name}: size {a.size} != {shape[0]*shape[1]}, skipped")
        return None
    return a.reshape(shape)


def main():
    dem = par(f"{TS}/info/EQA.dem_par")
    w = int(dem["width"].split()[0])
    h = int(dem["nlines"].split()[0])
    lat0 = float(dem["corner_lat"].split()[0])
    lon0 = float(dem["corner_lon"].split()[0])
    dlat = float(dem["post_lat"].split()[0])
    dlon = float(dem["post_lon"].split()[0])
    print(f"grid {w} x {h}   "
          f"N {lat0:.3f} S {lat0+dlat*h:.3f} "
          f"W {lon0:.3f} E {lon0+dlon*w:.3f}")

    vel = read("vel.filt.mskd", (h, w))
    if vel is None:
        vel = read("vel.mskd", (h, w))
    if vel is None:
        raise SystemExit("no masked velocity found in results/")

    valid = np.isfinite(vel)
    v = vel[valid]
    print(f"\n=== velocity (mm/yr, LOS) ===")
    print(f"  valid pixels: {valid.sum():,} of {vel.size:,} "
          f"({100*valid.mean():.1f}%)")
    if v.size == 0:
        raise SystemExit("no valid pixels — nothing was resolved")
    for q in (1, 5, 25, 50, 75, 95, 99):
        print(f"    p{q:<3} {np.percentile(v, q):+8.2f}")
    print(f"  mean {v.mean():+.2f}   std {v.std():.2f}   "
          f"range {v.min():+.1f} .. {v.max():+.1f}")

    # Velocity uncertainty is what decides whether the field means anything.
    vstd = read("vstd", (h, w))
    if vstd is not None:
        s = vstd[valid & np.isfinite(vstd)]
        if s.size:
            print(f"\n=== velocity std (mm/yr) ===")
            print(f"  median {np.median(s):.2f}   p95 {np.percentile(s,95):.2f}")
            both = valid & np.isfinite(vstd) & (vstd > 0)
            snr = np.abs(vel[both]) / vstd[both]
            print(f"  |vel| / std:  median {np.median(snr):.2f}   "
                  f"p95 {np.percentile(snr,95):.2f}")
            print(f"  pixels with |vel| > 2*std: "
                  f"{100*(snr > 2).mean():.1f}%")
            print(f"  pixels with |vel| > 3*std: "
                  f"{100*(snr > 3).mean():.1f}%")

    for name, label in (("coh_avg", "average coherence"),
                        ("n_unw", "unwrapped ifgs per pixel"),
                        ("resid_rms", "residual RMS (mm)"),
                        ("maxTlen", "max temporal length (yr)")):
        a = read(name, (h, w))
        if a is not None:
            x = a[np.isfinite(a) & (a != 0)]
            if x.size:
                print(f"\n{label}: median {np.median(x):.2f}  "
                      f"p5 {np.percentile(x,5):.2f}  p95 {np.percentile(x,95):.2f}")

    # How much of the NETWORK survived. A velocity fitted from a handful of
    # interferograms over a few months is not an eleven-year measurement,
    # however confident its formal uncertainty looks.
    p13 = par(f"{TS}/info/13parameters.txt")
    n_ifg = int(p13.get("n_ifg", 0) or 0)
    n_ifg_all = int(p13.get("n_ifg_all", 0) or 0)
    n_im = int(p13.get("n_im", 0) or 0)
    n_im_all = int(p13.get("n_im_all", 0) or 0)
    if n_ifg_all:
        print(f"\n=== network actually used ===")
        print(f"  interferograms: {n_ifg} of {n_ifg_all} "
              f"({100*n_ifg/n_ifg_all:.1f}%)")
        print(f"  epochs:         {n_im} of {n_im_all} "
              f"({100*n_im/n_im_all:.1f}%)")

    print("\n=== reading ===")
    coverage = float(valid.mean())
    print(f"  spatial coverage: {100*coverage:.2f}% of the frame")

    # Judge coverage FIRST. Scoring signal-to-noise over surviving pixels alone
    # divides by a denominator the mask already chose, and will call 63 pixels
    # out of 49,087 "a coherent velocity field".
    if coverage < 0.02:
        print("  Coverage is negligible: whatever passed the mask is a handful")
        print("  of pixels, not a velocity field. Formal uncertainties computed")
        print("  on survivors say nothing about the frame.")
    if n_ifg_all and n_ifg / n_ifg_all < 0.3:
        print(f"  {100*(1-n_ifg/n_ifg_all):.0f}% of interferograms were rejected,")
        print("  overwhelmingly by loop closure — the unwrapped phase is not")
        print("  internally consistent. That is an independent measurement of")
        print("  the same problem the asc/desc disagreement showed.")
    if coverage >= 0.02 and n_ifg_all and n_ifg / n_ifg_all >= 0.3:
        both = valid & np.isfinite(vstd) & (vstd > 0) if vstd is not None else None
        frac = (float((np.abs(vel[both]) / vstd[both] > 2).mean())
                if both is not None and both.sum() else 0.0)
        print(f"  {100*frac:.0f}% of covered pixels exceed 2x their uncertainty.")
        print("  Check the PATTERN against tectonics before calling it strain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
