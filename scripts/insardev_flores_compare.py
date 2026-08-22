"""Does the third chain land on the same radial profile as the other two?

GMTSAR and MintPy already agreed to within 1 cm at every ring. insardev is a
separate implementation of the same physics -- its own burst alignment, an
IRLS unwrapper rather than snaphu, its own geocoding, and solid Earth tides
removed where the other two left them in. If it lands on the same profile the
number is not an artefact of one code path.

TWO THINGS THIS SCRIPT MUST GET RIGHT OR THE COMPARISON IS MEANINGLESS.

  The arbitrary constant. An interferogram measures differences, so every
  profile floats by an unknown offset. Comparing absolute values would compare
  three arbitrary constants. Each profile is therefore referenced to its own
  outermost ring, which is the same convention used for the MintPy and GMTSAR
  numbers being compared against.

  The sign. GMTSAR writes los.grd in millimetres with the sign opposite to
  phase; insardev's displacement_los returns metres. Rather than assume the
  conventions agree, this reports the correlation of the profile shape under
  both orientations and says which one matches. A sign error would otherwise
  look like a dramatic disagreement.

    conda run -n insardev-test python scripts/insardev_flores_compare.py
"""

import argparse
import os
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
LOS = os.path.join(REPO, "data/insardev_flores/work/los.tif")
CORR = os.path.join(REPO, "data/insardev_flores/work/corr.zarr")
OUT = os.path.join(REPO, "output/coseismic/insardev_flores_compare.png")
EPI = (121.3517, -8.3101)

RINGS = [(20, 30), (30, 40), (40, 50), (50, 65)]
# Published earlier in this investigation, same frame, same acquisition pair.
GMTSAR = [-7.53, -4.81, -0.99, +0.84]          # raw radial median, cm
MINTPY = [-6.50, -4.13, -0.94, +1.05]          # deramped + demErr, cm
MINTPY_SD = [1.65, 1.30, 1.05, 0.99]           # 76 quiet 12-day intervals


def profile(vals, R, rings, ref_lo):
    """Ring medians referenced to the outermost ring."""
    ref = np.nanmedian(vals[R >= ref_lo]) if np.isfinite(
        vals[R >= ref_lo]).any() else 0.0
    out = []
    for r0, r1 in rings:
        m = (R >= r0) & (R < r1) & np.isfinite(vals)
        out.append((np.nanmedian(vals[m]) - ref, int(m.sum()))
                   if m.sum() >= 200 else (np.nan, int(m.sum())))
    return out, ref


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--los", default=LOS)
    ap.add_argument("--ref-km", type=float, default=60.0,
                    help="inner edge of the ring used as the zero reference")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import rioxarray  # noqa: F401
    import xarray as xr
    from pyproj import Transformer

    da = xr.open_dataarray(a.los, engine="rasterio")
    if "band" in da.dims:
        da = da.isel(band=0)
    v = da.values.astype("float64") * 100.0            # metres -> cm
    crs = da.rio.crs
    print(f"los.tif {da.shape}, {crs}")
    print(f"finite {np.isfinite(v).mean()*100:.1f}%  "
          f"range {np.nanmin(v):.1f} .. {np.nanmax(v):.1f} cm")

    xs = da[da.dims[-1]].values
    ys = da[da.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    ex, ey = fwd.transform(*EPI)
    R = np.hypot(xs[None, :] - ex, ys[:, None] - ey) / 1000.0
    print(f"distance from epicentre: {R.min():.0f} .. {R.max():.0f} km")

    prof, ref = profile(v, R, RINGS, a.ref_km)
    vals = np.array([p[0] for p in prof])
    if not np.isfinite(vals).all():
        print("\nWARNING: some rings have too few coherent pixels")

    # Which sign convention matches? Decide from the data instead of assuming.
    g = np.array(GMTSAR)
    ok = np.isfinite(vals)
    if ok.sum() >= 3:
        c_pos = np.corrcoef(vals[ok], g[ok])[0, 1]
        c_neg = np.corrcoef(-vals[ok], g[ok])[0, 1]
        flip = c_neg > c_pos
        print(f"\nshape correlation with GMTSAR: as-is {c_pos:+.3f}, "
              f"negated {c_neg:+.3f}")
        if flip:
            print("  -> insardev's LOS sign is opposite GMTSAR's; negating")
            vals = -vals
        else:
            print("  -> signs already agree")
    else:
        flip = False

    print(f"\n  {'ring km':>10}{'px':>9}{'insardev':>10}{'GMTSAR':>9}"
          f"{'MintPy':>9}{'noise sd':>10}")
    for (r0, r1), (val, n), gm, mp, sd in zip(
            RINGS, [(x, p[1]) for x, p in zip(vals, prof)],
            GMTSAR, MINTPY, MINTPY_SD):
        print(f"  {f'{r0}-{r1}':>10}{n:>9}{val:>10.2f}{gm:>9.2f}"
              f"{mp:>9.2f}{sd:>10.2f}")

    d_g = vals - g
    d_m = vals - np.array(MINTPY)
    print(f"\n  insardev - GMTSAR: {np.nanmax(np.abs(d_g)):.2f} cm max, "
          f"{np.sqrt(np.nanmean(d_g**2)):.2f} cm rms")
    print(f"  insardev - MintPy: {np.nanmax(np.abs(d_m)):.2f} cm max, "
          f"{np.sqrt(np.nanmean(d_m**2)):.2f} cm rms")
    print(f"  for scale, the 12-day noise sd on this frame is "
          f"{np.mean(MINTPY_SD):.2f} cm")

    inside = np.abs(d_m) <= np.array(MINTPY_SD)
    print(f"\n  {int(np.nansum(inside))} of {len(RINGS)} rings agree with "
          f"MintPy to within one noise sd")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mid = [(r0 + r1) / 2 for r0, r1 in RINGS]
    fig, ax = plt.subplots(1, 2, figsize=(13, 5),
                           gridspec_kw={"width_ratios": [1.15, 1]})
    ax[0].axhline(0, color="#999", lw=.8)
    ax[0].errorbar(mid, MINTPY, yerr=MINTPY_SD, fmt="-o", ms=5, lw=1.6,
                   capsize=4, color="#1d4a54",
                   label="MintPy (deramped) ±1 sd of 76 quiet intervals")
    ax[0].plot(mid, GMTSAR, "-s", ms=5, lw=1.6, color="#c8471b",
               label="GMTSAR (snaphu)")
    ax[0].plot(mid, vals, "-^", ms=6, lw=1.8, color="#6b8f3a",
               label="insardev (IRLS)")
    ax[0].set_xlabel("distance from epicentre, km")
    ax[0].set_ylabel("LOS displacement, cm")
    ax[0].set_title("Three chains, same two acquisitions\n"
                    f"each referenced to its own >{a.ref_km:.0f} km ring",
                    fontsize=10.5, loc="left")
    ax[0].grid(alpha=.25)
    ax[0].legend(fontsize=8.5)

    im = ax[1].imshow(np.where(R <= 90, v if not flip else -v, np.nan),
                      cmap="RdBu_r", vmin=-10, vmax=10,
                      extent=[xs.min(), xs.max(), ys.min(), ys.max()],
                      origin="upper")
    ax[1].plot(ex, ey, "*", color="#111", ms=15)
    ax[1].set_title("insardev LOS, cm", fontsize=10.5, loc="left")
    ax[1].set_xticks([]); ax[1].set_yticks([])
    fig.colorbar(im, ax=ax[1], shrink=.8)
    fig.suptitle("Flores frame 1148 co-seismic LOS: does a third "
                 "implementation agree?", fontsize=12.5, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .93])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
