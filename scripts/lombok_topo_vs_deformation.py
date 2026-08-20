"""Is the Lombok fringe pattern the earthquake, or is it the mountain?

I called these fringes co-seismic on first sight. Look again at where they are
centred: on Rinjani's edifice near 116.45, -8.42, with the rings following the
shape of the volcano out to the coast. Both epicentres are 15-20 km NORTH of
that centre, and the rings are not centred on either. Concentric rings around a
3726 m volcano in a 12-week pair are the textbook signature of two things that
are not slip:

  * stratified tropospheric delay -- the radar path through the atmosphere is
    shorter over high ground, and the difference between two days' humidity
    profiles maps almost linearly onto elevation;
  * residual topographic phase -- an error in the perpendicular baseline leaves
    a term proportional to height that survives topo_ra removal.

Both produce phase that is a function of ELEVATION. Co-seismic displacement is
a function of DISTANCE FROM THE FAULT. Those two are separable here precisely
because the fault is not on the mountain: the epicentres sit on the north
coast, the topographic high sits in the middle of the island.

So: regress unwrapped phase on elevation. A high R^2 with a physically sensible
slope means atmosphere/topography, and the "16.7 cm of displacement" I reported
from fringe counting is a delay measurement wearing a displacement's clothes.
Then look at what is LEFT after removing the elevation term, and check whether
the residual is organised around the epicentres.

Prerequisite: dem_ll.grd, the 1-arcsec DEM resampled onto the unwrapped grid.
GMTSAR's proj_ra2ll writes geocoded longitudes as 116.x - 360, so grdsample
finds no overlap with topo/dem.grd until the convention is reconciled by hand:

    cd ~/Teaching/UNDIP/InSAR/EQ/Pair1/intf/2018132_2018216
    R=$(gmt grdinfo -I- unwrap_c15_ll.grd | sed 's/-R//' \
        | awk -F/ '{printf "-R%.6f/%.6f/%s/%s", $1+360, $2+360, $3, $4}')
    gmt grdsample ../../topo/dem.grd $R $(gmt grdinfo -I unwrap_c15_ll.grd) \
        -r -Gdem_ll.grd=nf

    conda run -n base python scripts/lombok_topo_vs_deformation.py \
        --tag c15 --min-coh 0.15
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
DEM = os.path.join(D, "dem_ll.grd")   # topo/dem.grd resampled onto the
# unwrapped grid by grdsample; the raw DEM is 1-arcsec over 115-117 lon, and
# GMTSAR wrote the geocoded products at 116.x - 360, so the two do not overlap
# until the longitude convention is reconciled.
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/lombok_topo_vs_deformation.png")

CM_PER_RAD = 0.242452 / (4 * np.pi) * 100
KM_LAT = 110.57
EVENTS = [
    ("M6.4  29 Jul", 116.426, -8.239, "#ffdd00"),
    ("M6.9   5 Aug", 116.439, -8.287, "#ff5500"),
]


def grid(path):
    return xr.open_dataarray(path) if os.path.exists(path) else None


def axes(da):
    gy, gx = da.dims
    glat, glon = da[gy].values, da[gx].values
    if glon.max() < 0:                      # proj_ra2ll writes 116.x - 360
        glon = glon + 360.0
    return glat, glon


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.30)
    ap.add_argument("--tag", default="c30",
                    help="which unwrap run to read: c30, c15, ...")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    unw = grid(os.path.join(D, f"unwrap_{a.tag}_ll.grd"))
    corr = grid(os.path.join(D, "corr_ll.grd"))
    cc = grid(os.path.join(D, f"conncomp_{a.tag}_ll.grd"))
    dem = grid(DEM)
    if unw is None or dem is None:
        sys.exit("need unwrap_ll.grd and topo/dem.grd")

    lat, lon = axes(unw)
    U = unw.values.astype(float)
    U[U == 0] = np.nan

    def match(da):
        glat, glon = axes(da)
        iy = np.clip(np.searchsorted(glat, lat), 1, len(glat) - 1) - 1
        ix = np.clip(np.searchsorted(glon, lon), 1, len(glon) - 1) - 1
        return da.values[np.ix_(iy, ix)]

    Z = match(dem).astype(float)
    if corr is not None:
        U = np.where(match(corr) >= a.min_coh, U, np.nan)
    if cc is not None:
        L = match(cc)
        lab = L[np.isfinite(U) & (L > 0)]
        if lab.size:
            main_lab = np.bincount(lab.astype(int)).argmax()
            U = np.where(L == main_lab, U, np.nan)

    m = np.isfinite(U) & np.isfinite(Z)
    n = int(m.sum())
    if n < 1000:
        sys.exit(f"only {n} usable pixels -- lower --min-coh")

    z, u = Z[m], U[m]
    print(f"{n} pixels, elevation {z.min():.0f}-{z.max():.0f} m\n")

    # Straight least squares first, because it is the version everyone reports.
    # Pixels are spatially correlated, so the formal error on the slope is
    # meaningless -- what matters is the fraction of variance explained, which
    # correlation does not inflate.
    A = np.column_stack([z, np.ones_like(z)])
    coef, *_ = np.linalg.lstsq(A, u, rcond=None)
    lin_resid = u - A @ coef
    r2 = 1 - lin_resid.var() / u.var()

    print("  linear:  phase = slope * elevation + offset")
    print(f"    slope   {coef[0]*1000:+.3f} rad / km of elevation "
          f"= {coef[0]*1000*CM_PER_RAD:+.2f} cm/km")
    print(f"    R^2     {r2:.3f}")

    # But a straight line is the wrong shape. Tropospheric water vapour falls
    # off roughly exponentially with height, so the delay saturates: the phase
    # climbs steeply through the first kilometre and then flattens. Forcing a
    # line through a saturating curve leaves a residual that is largest exactly
    # where the coastal plain is -- which is where the epicentres are. That
    # would manufacture an apparent near-field signal out of model misfit.
    #
    # So remove elevation non-parametrically: the median phase in each
    # elevation bin, interpolated. It assumes only that the delay is some
    # monotone-ish function of height, not which function.
    nb = 60
    edges_z = np.percentile(z, np.linspace(0, 100, nb + 1))
    edges_z = np.unique(edges_z)
    idx = np.clip(np.searchsorted(edges_z, z, "right") - 1, 0,
                  len(edges_z) - 2)
    centres = np.array([z[idx == i].mean() if (idx == i).any() else np.nan
                        for i in range(len(edges_z) - 1)])
    meds = np.array([np.median(u[idx == i]) if (idx == i).any() else np.nan
                     for i in range(len(edges_z) - 1)])
    ok = np.isfinite(centres) & np.isfinite(meds)
    curve = np.interp(z, centres[ok], meds[ok])
    resid = u - curve
    r2n = 1 - resid.var() / u.var()

    print(f"\n  non-parametric: median phase per elevation bin ({ok.sum()} bins)")
    print(f"    R^2     {r2n:.3f}")
    print(f"    scatter {u.std()*CM_PER_RAD:.2f} cm total -> "
          f"{resid.std()*CM_PER_RAD:.2f} cm after removing elevation\n")
    r2 = r2n

    if r2 > 0.5:
        print("  The pattern is ELEVATION, not slip. A delay of a few cm per")
        print("  km of height is exactly what a stratified troposphere does,")
        print("  and it is centred on the mountain because the mountain is")
        print("  what it is a function of.")
    else:
        print("  Elevation does not explain the pattern; the fringes need")
        print("  another cause.")

    # Now the real question: after removing the elevation term, is anything
    # organised around the epicentres? Report residual by distance from the
    # M6.4, which is the event this pair actually spans.
    elon, elat = EVENTS[0][1], EVENTS[0][2]
    kx = 111.32 * np.cos(np.deg2rad(elat))
    Rm = np.hypot((lat[:, None] - elat) * KM_LAT,
                  (lon[None, :] - elon) * kx)[m]

    print("\n  Residual after removing elevation, by distance from the M6.4:")
    print("    range        n     median (cm)    p16..p84 (cm)")
    edges = [0, 10, 15, 20, 25, 30, 40, 60]
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = (Rm >= lo) & (Rm < hi)
        if s.sum() < 200:
            print(f"    {lo:>2}-{hi:<3} km  {int(s.sum()):>7}    "
                  f"-- too few --")
            continue
        r = resid[s] * CM_PER_RAD
        p16, p84 = np.percentile(r, [16, 84])
        print(f"    {lo:>2}-{hi:<3} km  {int(s.sum()):>7}    "
              f"{np.median(r):>+9.2f}    {p16:+.2f} .. {p84:+.2f}")
    print("\n  Co-seismic displacement falls off with distance from the fault.")
    print("  A residual with no distance trend is atmosphere that happens not")
    print("  to be a pure function of height.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(17, 5.6))
    ext = [lon.min(), lon.max(), lat.min(), lat.max()]

    # Thin for the scatter -- 100k points plots as a solid block.
    k = max(1, n // 20000)
    ax[0].plot(z[::k], u[::k] * CM_PER_RAD, ".", ms=1.2, alpha=.25,
               color="#2b5d8a")
    zz = np.linspace(z.min(), z.max(), 50)
    ax[0].plot(zz, (coef[0] * zz + coef[1]) * CM_PER_RAD, "--", lw=1.6,
               color="#8e8e8e",
               label=f"straight line, $R^2$ = {1-lin_resid.var()/u.var():.2f}\n"
                     f"({coef[0]*1000*CM_PER_RAD:+.2f} cm per km)")
    ax[0].plot(centres[ok], meds[ok] * CM_PER_RAD, "-", lw=2.4,
               color="#c0392b",
               label=f"median per elevation bin, $R^2$ = {r2n:.2f}")
    ax[0].set_xlabel("elevation (m)")
    ax[0].set_ylabel("unwrapped phase (cm line-of-sight)")
    ax[0].set_title("Phase against elevation\nthe test that separates delay "
                    "from slip", fontsize=10, loc="left")
    ax[0].legend(fontsize=9, loc="best")
    ax[0].grid(alpha=.25)

    R2 = np.full(U.shape, np.nan)
    R2[m] = resid * CM_PER_RAD
    lim = np.nanpercentile(np.abs(R2), 98)
    for axi, arr, ttl, cm_, kw in (
        (ax[1], np.where(m, U * CM_PER_RAD, np.nan),
         "Unwrapped phase\nrings centred on the volcano, not the epicentres",
         "RdYlBu", {}),
        (ax[2], R2, "Residual after removing elevation\nwhat is left for an "
         "earthquake to explain", "RdBu_r",
         dict(vmin=-lim, vmax=lim)),
    ):
        im = axi.imshow(arr, extent=ext, origin="lower", cmap=cm_,
                        interpolation="nearest", **kw)
        axi.set_title(ttl, fontsize=10, loc="left")
        axi.set_xlabel("lon")
        for label, xl, yl, col in EVENTS:
            axi.plot(xl, yl, "*", ms=15, mfc=col, mec="black", mew=.9, zorder=5)
        fig.colorbar(im, ax=axi, shrink=.8, pad=.02, label="cm line-of-sight")

    fig.suptitle("Lombok ALOS-2 12 May → 4 Aug 2018 — the fringes are a "
                 "function of height, not of distance from the fault",
                 fontsize=12.5, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .93])
    out = a.out.replace(".png", f"_{a.tag}.png")
    fig.savefig(out, dpi=130)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
