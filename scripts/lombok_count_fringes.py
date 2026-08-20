"""RETRACTED. Counts fringes along profiles; the number is not displacement.

Kept because the failure is more instructive than the script. This reported
1.38 cycles = 16.7 cm of line-of-sight motion, with monotonicity 1.00 due
north -- the phase climbing outward and never returning, which is supposed to
be the signature that separates a real fringe pattern from atmosphere.

It was atmosphere. lombok_topo_vs_deformation.py shows that 81% of the phase
variance in this pair is a function of ELEVATION, and the profiles run up and
down Rinjani's flanks. Climbing a volcano monotonically scores 1.00 on a
monotonicity test just as cleanly as walking away from a fault does. The test
cannot tell those apart, because it never looks at what the phase is a
function of -- only at how tidily it changes along a line I chose.

What was missing: the rings are centred on the summit, not on either epicentre
15-20 km north. I picked CENTRE by eye from the map and called it "the
deformation centre", which assumed the conclusion. The residual after removing
elevation is flat from 0 to 30 km out from the M6.4 -- no bullseye, nothing
above about 2 cm.

The monotonicity idea is still sound for a pair where topography has been
dealt with first. It is not sound as a standalone detector.

Profiles are smoothed on the COMPLEX phase before unwrapping, never on the
angle: the mean of +3.0 and -3.0 rad is 0 when the two are 0.28 rad apart.
That part was right.

    conda run -n base python scripts/lombok_count_fringes.py
"""

import argparse
import os
import sys

import numpy as np

try:
    import xarray as xr
except ImportError:                                   # pragma: no cover
    sys.exit("needs xarray: run under `conda run -n base`")

D = os.path.expanduser(
    "~/Teaching/UNDIP/InSAR/EQ/Pair1/intf/2018132_2018216")
FRINGE_CM = 0.242452 / 2 * 100
KM_LAT = 110.57

# Visual centre of the concentric pattern, read off the map -- deliberately
# NOT the epicentre, which is where rupture nucleated rather than where the
# surface moved most.
CENTRE = (116.40, -8.38)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.25)
    ap.add_argument("--smooth", type=int, default=9)
    ap.add_argument("--length-km", type=float, default=45.0)
    ap.add_argument("--min-samples", type=int, default=60)
    ap.add_argument("--max-gap", type=int, default=8,
                    help="samples; gaps shorter than this are bridged")
    a = ap.parse_args()

    ph = xr.open_dataarray(os.path.join(D, "phasefilt_mask_ll.grd"))
    corr = xr.open_dataarray(os.path.join(D, "corr_ll.grd"))
    ydim, xdim = ph.dims
    lat, lon = ph[ydim].values, ph[xdim].values
    P, C = ph.values, corr.values

    kx = 111.32 * np.cos(np.deg2rad(CENTRE[1]))
    print(f"one fringe = {FRINGE_CM:.2f} cm  (ALOS-2 L-band)")
    print(f"profiles from {CENTRE[1]:.3f}, {CENTRE[0]:.3f}, "
          f"{a.length_km:.0f} km long\n")

    print("  bearing        n   net cycles   net cm   |monotonicity|")
    nets = []
    for bearing in range(0, 360, 45):
        br = np.deg2rad(bearing)
        d = np.linspace(0, a.length_km, 400)
        plat = CENTRE[1] + (d * np.cos(br)) / KM_LAT
        plon = CENTRE[0] + (d * np.sin(br)) / kx

        iy = np.searchsorted(lat, plat)
        ix = np.searchsorted(lon, plon)
        ok = ((iy > 0) & (iy < len(lat)) & (ix > 0) & (ix < len(lon)))
        if ok.sum() < 100:
            continue
        vals = np.full(d.size, np.nan)
        coh = np.full(d.size, np.nan)
        vals[ok] = P[iy[ok] - 1, ix[ok] - 1]
        coh[ok] = C[iy[ok] - 1, ix[ok] - 1]

        good = np.isfinite(vals) & (coh >= a.min_coh)
        if good.sum() < a.min_samples:
            print(f"   {bearing:>3} deg    {int(good.sum()):>5}   "
                  f"-- too little coherent ground --")
            continue

        # Take the longest run of coherent samples, but allow small gaps to be
        # bridged. Demanding a strictly unbroken run rejected every profile
        # here: median coherence is 0.094, so coherent samples come in short
        # bursts even where the fringes are perfectly clear. Bridging gaps
        # shorter than the smoothing window cannot invent a fringe -- a wrap
        # needs half a cycle within the gap, which at this fringe spacing is
        # far wider than the bridge.
        idx = np.flatnonzero(good)
        breaks = np.flatnonzero(np.diff(idx) > a.max_gap)
        runs = np.split(idx, breaks + 1)
        seg = max(runs, key=len)
        if len(seg) < a.min_samples:
            print(f"   {bearing:>3} deg    {len(seg):>5}   "
                  f"-- longest usable run too short --")
            continue
        # Fill the bridged gaps so the profile is evenly sampled.
        seg = np.arange(seg[0], seg[-1] + 1)
        vals = np.interp(seg, np.flatnonzero(good), vals[good])

        z = np.exp(1j * vals)
        k = np.ones(a.smooth) / a.smooth
        zs = (np.convolve(z.real, k, "same") + 1j * np.convolve(z.imag, k,
                                                                "same"))
        phi = np.unwrap(np.angle(zs))[a.smooth:-a.smooth]
        if phi.size < 50:
            continue
        net = (phi[-1] - phi[0]) / (2 * np.pi)
        steps = np.diff(phi)
        mono = abs(np.sign(steps).sum()) / len(steps)
        nets.append(abs(net))
        print(f"   {bearing:>3} deg    {len(phi):>5}   {net:+8.2f}   "
              f"{net*FRINGE_CM:+7.1f}   {mono:>8.2f}")

    if nets:
        print(f"\n  largest |net| across profiles: {max(nets):.2f} cycles "
              f"= {max(nets)*FRINGE_CM:.1f} cm line-of-sight")
        print(f"  median |net|: {np.median(nets):.2f} cycles "
              f"= {np.median(nets)*FRINGE_CM:.1f} cm")
    print("\n  DO NOT READ THESE AS DISPLACEMENT. Monotonicity near 1 means")
    print("  the phase climbs and never returns, which a fringe pattern does")
    print("  -- and so does a profile walking up a volcano. In this pair 81%")
    print("  of the phase variance is a function of elevation, so what these")
    print("  profiles measure is tropospheric delay. See")
    print("  scripts/lombok_topo_vs_deformation.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
