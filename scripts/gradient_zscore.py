"""Where does the co-event phase gradient sit among earthquake-free pairs?

Both SNAP and PyGMTSAR find a north-south gradient of ~0.15 cm/km across
western Flores in the 6->18 Aug pair, about 3x the single control pair. Two
processors agreeing means the gradient is in the data rather than in an
unwrapper. It does NOT yet mean it is the earthquake: turbulent troposphere
and residual orbits both produce long-wavelength tilts, and one control pair
being smaller is one draw, not a distribution.

So measure the same gradient in every earthquake-free 12-day pair on the same
ground and ask where the co-event falls. That converts "3x the control" into a
number with a tail probability attached.

    z = (grad_coevent - mean(grad_baseline)) / std(grad_baseline)

WHY THIS WORKS WHERE THE EARLIER TESTS FAILED. My radial-profile test computed
circular means of WRAPPED phase, which cannot represent more than half a
fringe -- it had a hard ceiling at 1.39 cm and the signal here is ~6-18 cm. My
fringe test ran EAST-WEST transects while the gradient is north-south, so it
measured the minor axis. Fitting a plane to UNWRAPPED phase has neither limit.

WHAT IT STILL CANNOT DO. A deformation gradient from an offshore source north
of the island and an orbital/ionospheric ramp are both close to planar over
this footprint. A large z says the co-event pair is unusual against its own
history -- not which of the two made it unusual. Only a second look direction
(descending 163) or GNSS separates them.

    conda run -n base python scripts/gradient_zscore.py --frame 1148
"""

import argparse
import glob
import os
import re
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                    # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

BASE = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/baseline/hyp3")
COEVENT = "20260806_20260818"
FRAME_SECOND = {1148: "1016", 1153: "1017"}
KM_LAT = 110.57
FRINGE_CM = 5.5465 / 2


def products(frame, band):
    """Group products by FOOTPRINT, not by acquisition second.

    The obvious discriminator -- the seconds field of the granule timestamp --
    is wrong, and wrong silently. Frames are ~25 s apart along track, but the
    absolute time depends on the SATELLITE: the S1A baselines sit at 10:16:45
    (1148) and 10:17:10 (1153), while the S1D co-event sits at 10:16:03 and
    10:16:28. A prefix rule calibrated on S1A therefore files BOTH S1D
    co-event products under 1148, which would have compared the northern
    frame's co-event against the southern frame's baselines and reported the
    difference as an earthquake.

    Centre latitude has no such dependence: 1153 is simply north of 1148.
    """
    cands = []
    for d in sorted(glob.glob(f"{BASE}/earthchange-*")):
        if not os.path.isdir(d):
            continue
        tifs = glob.glob(f"{d}/*_{band}.tif")
        if not tifs:
            continue
        k = re.search(r"earthchange-(\d{8}_\d{8})", os.path.basename(d))
        if not k:
            continue
        with rasterio.open(tifs[0]) as src:
            b = src.bounds
            x = (b.left + b.right) / 2
            y = (b.bottom + b.top) / 2
            lon, lat = warp_transform(src.crs, "EPSG:4326", [x], [y])
        cands.append((k.group(1), tifs[0], float(lat[0])))

    if not cands:
        return {}
    lats = np.array([c[2] for c in cands])
    # Two frames, well separated along track; split at the midpoint of the
    # observed range rather than a hardcoded latitude.
    cut = (lats.min() + lats.max()) / 2
    north = frame == 1153
    return {k: p for k, p, la in cands if (la >= cut) == north}


# Frame 1153 is scattered across islands spanning 1.8 deg of latitude, and
# unwrapping resolves each connected component with its own arbitrary integer
# offset -- so a plane fitted over all of it partly measures that bookkeeping.
# Restricting to the contiguous Flores patch is not cherry-picking: it is the
# only region where the unwrapped phase is internally consistent, and the
# anomaly grows rather than shrinks under the restriction (z -8.83 -> -6.52
# against a baseline spread that is 19x wider).
FRAME_LATMAX = {1148: None, 1153: -8.20}


def gradient(path, corr_path, min_coh, lat_max=None):
    """Plane fit to unwrapped phase; returns cm/km east and north."""
    with rasterio.open(path) as src:
        phi = src.read(1).astype("float64")
        tr, crs, H, W = src.transform, src.crs, src.height, src.width
    with rasterio.open(corr_path) as src:
        coh = src.read(1).astype("float32")
    if coh.shape != phi.shape:
        return None

    # HyP3 writes 0 both outside the footprint and where unwrapping produced
    # nothing. Either way it is not a measurement.
    ok = np.isfinite(phi) & (phi != 0) & (coh >= min_coh)
    if ok.sum() < 20000:
        return None

    rows, cols = np.nonzero(ok)
    xs = tr.c + (cols + .5) * tr.a
    ys = tr.f + (rows + .5) * tr.e
    lon, lat = warp_transform(crs, "EPSG:4326", xs, ys)
    lon = np.array(lon); lat = np.array(lat)
    v_all = phi[ok]
    if lat_max is not None:
        keep = lat <= lat_max
        if keep.sum() < 5000:
            return None
        lon, lat, v_all = lon[keep], lat[keep], v_all[keep]
    kx = 111.32 * np.cos(np.deg2rad(float(np.median(lat))))
    X = (lon - np.median(lon)) * kx
    Y = (lat - np.median(lat)) * KM_LAT
    v = v_all

    A = np.column_stack([np.ones_like(X), X, Y])
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    r2 = 1 - (v - A @ coef).var() / v.var() if v.var() > 0 else np.nan
    to_cm = FRINGE_CM / (2 * np.pi)
    return dict(east=coef[1] * to_cm, north=coef[2] * to_cm, r2=r2,
                n=int(len(v)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1148, choices=(1148, 1153))
    ap.add_argument("--min-coh", type=float, default=0.3)
    a = ap.parse_args()

    unw = products(a.frame, "unw_phase")
    corr = products(a.frame, "corr")
    if not unw:
        sys.exit(f"no frame-{a.frame} unw_phase products under {BASE}")

    co_key = COEVENT if COEVENT in unw else None
    print(f"frame {a.frame}: {len(unw)} unwrapped products"
          + ("" if co_key else "   (co-event NOT yet on disk)"))
    print("\n  pair                    east      north    plane R2      n")
    rows = []
    for k in sorted(unw):
        if k not in corr:
            continue
        g = gradient(unw[k], corr[k], a.min_coh, FRAME_LATMAX[a.frame])
        if g is None:
            print(f"  {k[:8]}->{k[9:]}   -- too little unwrapped ground --")
            continue
        tag = "  <- CO-EVENT" if k == co_key else ""
        print(f"  {k[:8]}->{k[9:]}  {g['east']:+8.4f}  {g['north']:+8.4f}"
              f"   {g['r2']:5.2f}  {g['n']:>9,}{tag}")
        if k != co_key:
            rows.append(g)

    if len(rows) < 3:
        sys.exit("\nfewer than 3 baseline pairs; no distribution to speak of")

    for axis in ("east", "north"):
        v = np.array([r[axis] for r in rows])
        mu, sd = float(np.mean(v)), float(np.std(v, ddof=1))
        print(f"\n=== {axis} gradient over {len(v)} earthquake-free pairs ===")
        print(f"  mean {mu:+.4f}  sd {sd:.4f} cm/km   "
              f"range {v.min():+.4f} .. {v.max():+.4f}")
        if co_key:
            # MUST use the same restriction as the baselines. Comparing a
            # whole-frame co-event against patch-restricted baselines measures
            # the difference in footprint, not the difference in ground motion.
            g = gradient(unw[co_key], corr[co_key], a.min_coh,
                         FRAME_LATMAX[a.frame])
            if g:
                z = (g[axis] - mu) / sd if sd > 0 else np.nan
                print(f"  co-event {g[axis]:+.4f}  ->  z = {z:+.2f}")
                if abs(z) >= 3:
                    print("  -> the co-event pair is far outside the normal")
                    print("     spread of this frame. Something happened.")
                elif abs(z) >= 2:
                    print("  -> unusual but not decisive at this sample size.")
                else:
                    print("  -> within ordinary variability. The gradient is")
                    print("     the kind this frame produces anyway.")

    print("\nA large z means the pair is anomalous against its own history.")
    print("It does NOT say the anomaly is tectonic: an offshore source and an")
    print("orbital ramp are both planar here. Descending 163 separates them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
