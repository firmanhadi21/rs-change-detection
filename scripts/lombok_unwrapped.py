"""Is a Lombok unwrapped grid trustworthy? Check whether its relief converges.

An unwrapped interferogram can be arithmetically fine and still meaningless,
because two things inflate it and neither is ground movement:

  1. Disconnected components. Coherent ground here comes in islands separated
     by decorrelated terrain, and snaphu gives each island its own arbitrary
     multiple of 2-pi. Comparing across islands is comparing two numbers on
     different scales -- the same trap that produced the frame-1153 gradient
     on Flores, where a whole-frame plane fit spanned two of them.
  2. Error propagation. An unwrapping mistake in a low-coherence corridor is
     carried forward into everything downstream along the integration path, so
     one bad bridge shifts a whole region.

Absolute unwrapped phase has no meaning anyway -- there is no reference pixel
-- so what is measurable is RELIEF within one connected component. This script
reports relief in growing windows around a chosen centre. Relief that keeps
climbing with window size is stitched-together ground; relief that plateaus is
at least internally consistent. That is a test of the UNWRAPPING, not of the
cause -- see the caveats below.

It caught exactly that. The first snaphu run, with the zero-byte config
described in lombok_unwrap.sh, gave relief growing 84 -> 309 cm from a 5 km to
a 45 km window and never settling. After the config fix the same measurement
plateaus: on the 0.30 mask by 15 km at ~4.5 cm, on the wider 0.15 mask by
20-30 km at ~18 cm. It distinguishes the two without needing to know in advance
which one is broken.

Two things this does NOT establish, and both matter:

  * That converged relief is an earthquake. In this pair it is not -- 81% of
    the variance is a function of elevation. See lombok_topo_vs_deformation.py.
  * That the plateau value is a displacement. The 0.15 mask plateaus four
    times higher than the 0.30 mask because it reaches further down Rinjani's
    flanks and so spans more of the topographic delay. The plateau tracks how
    much elevation range the window contains, which is the giveaway.

    conda run -n base python scripts/lombok_unwrapped.py --grid unwrap_c15_ll.grd
"""

import argparse
import os
import sys

import numpy as np

try:
    import xarray as xr
except ImportError:                                   # pragma: no cover
    sys.exit("needs xarray + matplotlib: run under `conda run -n base`")

D = os.path.expanduser(
    "~/Teaching/UNDIP/InSAR/EQ/Pair1/intf/2018132_2018216")
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/lombok_unwrapped.png")

WAVELENGTH_M = 0.242452
CM_PER_RAD = WAVELENGTH_M / (4 * np.pi) * 100     # 1.930 cm per radian
KM_LAT = 110.57

CENTRE = (116.40, -8.38)
EVENTS = [
    ("M6.4  29 Jul", 116.426, -8.239, "#ffdd00"),
    ("M6.9   5 Aug", 116.439, -8.287, "#ff5500"),
]


def load(name):
    p = os.path.join(D, name)
    return xr.open_dataarray(p) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.15)
    ap.add_argument("--grid", default="unwrap_c15_ll.grd")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    unw = load(a.grid)
    corr = load("corr_ll.grd")
    cc = load(a.grid.replace("unwrap_", "conncomp_"))
    if unw is None:
        sys.exit(f"no {a.grid} -- run scripts/lombok_unwrap.sh first")

    ydim, xdim = unw.dims
    lat = unw[ydim].values
    lon = unw[xdim].values
    # GMTSAR's proj_ra2ll wrote longitude as -243.x, i.e. 116.x - 360.
    if lon.max() < 0:
        lon = lon + 360.0
    U = unw.values.astype(float)
    U[U == 0] = np.nan                    # masked pixels come back as 0

    # Every geocoded grid here was resampled independently by proj_ra2ll.csh,
    # so they do NOT share a lon/lat grid -- each unwrap_c*_ll differs from the
    # next AND from corr_ll (1810x1850). Anything sampled onto it has to be
    # matched by nearest neighbour; assuming alignment masks the wrong pixels
    # and would do it silently.
    def match(da):
        gy, gx = da.dims
        glat, glon = da[gy].values, da[gx].values
        if glon.max() < 0:
            glon = glon + 360.0
        iy = np.clip(np.searchsorted(glat, lat), 1, len(glat) - 1) - 1
        ix = np.clip(np.searchsorted(glon, lon), 1, len(glon) - 1) - 1
        return da.values[np.ix_(iy, ix)]

    if corr is not None:
        U = np.where(match(corr) >= a.min_coh, U, np.nan)

    # Restrict to the connected component that contains the deformation centre.
    # This is the whole point of keeping the labels: unwrapped phase is only
    # comparable WITHIN one component, because snaphu gives each its own
    # arbitrary multiple of 2-pi. Comparing across components is the mistake
    # that produced the frame-1153 gradient on Flores.
    kx = 111.32 * np.cos(np.deg2rad(CENTRE[1]))
    dlat = (lat - CENTRE[1]) * KM_LAT
    dlon = (lon - CENTRE[0]) * kx
    R = np.hypot(dlat[:, None], dlon[None, :])

    if cc is not None:
        L = match(cc)
        near = (R <= 3) & np.isfinite(U) & (L > 0)
        if near.any():
            labs, counts = np.unique(L[near], return_counts=True)
            main = labs[np.argmax(counts)]
            frac = 100 * np.mean(L[np.isfinite(U)] == main)
            print(f"connected components: {int(np.nanmax(L))}; the centre sits "
                  f"on #{int(main)}, which covers {frac:.1f}% of usable pixels")
            U = np.where(L == main, U, np.nan)
        else:
            print("no labelled pixels within 3 km of the centre")
    else:
        print("no conncomp_ll.grd -- cannot separate components; "
              "cross-component comparisons below are NOT safe")

    finite = np.isfinite(U)
    print(f"1 radian = {CM_PER_RAD:.3f} cm line-of-sight  (ALOS-2 L-band)")
    print(f"grid {U.shape}, {100*finite.mean():.1f}% usable at coherence "
          f">= {a.min_coh}")
    span = (np.nanmax(U) - np.nanmin(U)) * CM_PER_RAD
    print(f"range on this component {np.nanmin(U):+.1f} .. {np.nanmax(U):+.1f} "
          f"rad = {span:.0f} cm span\n")

    # Does the relief converge as the window grows? If it keeps climbing, the
    # grid is still stitching unrelated ground together.
    print("  window   n usable    p2 .. p98 (rad)    relief (cm)   median")
    for rad_km in (5, 10, 15, 20, 30, 45):
        m = finite & (R <= rad_km)
        n = int(m.sum())
        if n < 500:
            print(f"  {rad_km:>3} km    {n:>8}    -- too few pixels --")
            continue
        v = U[m]
        lo, hi = np.percentile(v, [2, 98])
        print(f"  {rad_km:>3} km    {n:>8}    {lo:+8.1f} .. {hi:+7.1f}   "
              f"{(hi-lo)*CM_PER_RAD:>9.1f}   {np.median(v):+8.1f}")

    print("\n  A relief that plateaus is at least self-consistent; one that")
    print("  keeps growing means stranded components. Neither result tells you\n"
          "  the cause -- run lombok_topo_vs_deformation.py for that.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 6.6))

    # Left: the whole grid, on a percentile stretch so one bad island does not
    # flatten everything else to a single colour.
    v = U[finite]
    lo, hi = np.percentile(v, [2, 98])
    im = ax[0].imshow(U * CM_PER_RAD, extent=ext, origin="lower", cmap="RdYlBu",
                      vmin=lo * CM_PER_RAD, vmax=hi * CM_PER_RAD,
                      interpolation="nearest")
    ax[0].set_title("Unwrapped phase, whole scene\n"
                    "2-98 percentile stretch; large-scale pattern is "
                    "unwrapping, not ground", fontsize=10, loc="left")
    fig.colorbar(im, ax=ax[0], shrink=.82, pad=.02, label="cm line-of-sight")

    # Right: a 25 km box, referenced to its own median so the arbitrary
    # component offset is removed rather than pretended away.
    box = R <= 25
    ref = np.nanmedian(U[finite & box])
    Ub = np.where(box, U - ref, np.nan)
    b = Ub[np.isfinite(Ub)]
    blo, bhi = np.percentile(b, [1, 99])
    im = ax[1].imshow(Ub * CM_PER_RAD, extent=ext, origin="lower",
                      cmap="RdYlBu", vmin=blo * CM_PER_RAD,
                      vmax=bhi * CM_PER_RAD, interpolation="nearest")
    ax[1].set_xlim(CENTRE[0] - .30, CENTRE[0] + .30)
    ax[1].set_ylim(CENTRE[1] - .28, CENTRE[1] + .28)
    ax[1].set_title("25 km around the deformation centre\n"
                    "referenced to its own median (the absolute level is "
                    "arbitrary)", fontsize=10, loc="left")
    fig.colorbar(im, ax=ax[1], shrink=.82, pad=.02, label="cm line-of-sight")

    for axi in ax:
        for label, elon, elat, col in EVENTS:
            axi.plot(elon, elat, "*", ms=15, mfc=col, mec="black", mew=.9,
                     zorder=5)
        axi.set_xlabel("lon")
    ax[0].set_ylabel("lat")

    fig.suptitle("Lombok ALOS-2 12 May → 4 Aug 2018, unwrapped with snaphu — "
                 "spans the M6.4 foreshock only", fontsize=12.5, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .95])
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
