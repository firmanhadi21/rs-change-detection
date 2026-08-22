"""Ascending path 112: coherence change as a damage proxy, plus the evidence
that the displacement pattern is deformation rather than atmosphere.

Coherence change is a DIFFERENCE, and that is the whole point:

    change = coherence(2026-08-06 -> 08-18, spans the rupture)
           - coherence(2026-07-25 -> 08-06, quiet)

Both pairs are 12 days on the same track and mission, so temporal
decorrelation, vegetation and slope affect both and largely cancel. Low
coherence in the co-event pair means nothing on its own -- much of Flores
decorrelates over 12 days regardless. What indicates change is coherence that
was high before and collapsed across the event.

MASKING TO BASELINE COHERENCE, NOT TO CO-EVENT COHERENCE. A pixel whose
pre-pre coherence was already 0.15 cannot drop meaningfully; its difference is
noise around zero and including it dilutes everything. The threshold is 0.3,
chosen from the measured distribution -- 63% of land on frame 1148 sits above
it. Masking on the CO-EVENT pair instead would be circular: it would discard
exactly the pixels that lost coherence, which are the ones being looked for.

WHAT THIS SCRIPT WILL NOT DO. It will not call the result damage. Coherence
falls for many reasons -- harvest, landslides, water, and the deformation
gradient itself where fringes are too dense to correlate. On this project a
tidy four-block cluster of the largest coherence drops in the scene turned out
to be the shoreline at 0 m elevation, so a coastline buffer is applied here
too.

    conda run -n insardev-test python scripts/asc_damage_map.py
"""

import argparse
import glob
import os
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
OUT = os.path.join(REPO, "output/coseismic")
POST = os.path.join(OUT, "asc_prepost_corr_otb.tif")
PRE = os.path.join(OUT, "asc_prepre_corr_otb.tif")
# LOS displacement exists only on frame 1148: the frame-1153 job predates the
# parameter fix and used include_los_displacement, which HyP3 accepts and
# silently ignores in favour of include_displacement_maps. Frame 1148 covers
# all of Flores, so the near field is not lost -- only the north-coast strip
# beyond it.
F1148 = os.path.join(OUT, "flores-coseismic-2026-asc-f1148-prepost-d2")
EPI = (121.3517, -8.3101)


def read(path):
    import rioxarray  # noqa: F401
    import xarray as xr
    da = xr.open_dataarray(path, engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def band(d, name):
    hits = glob.glob(os.path.join(d, f"*_{name}.tif"))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-baseline", type=float, default=0.3)
    ap.add_argument("--coast-px", type=int, default=10)
    ap.add_argument("--out", default=os.path.join(OUT, "asc_damage_map.png"))
    a = ap.parse_args()

    import xarray as xr
    from pyproj import Transformer
    from scipy import ndimage

    post, pre = xr.align(read(POST), read(PRE), join="inner")
    p2 = post.values.astype("float64")
    p1 = pre.values.astype("float64")
    print(f"mosaics aligned to {p2.shape}")

    valid = np.isfinite(p1) & np.isfinite(p2) & (p1 > 0) & (p2 > 0)
    base_ok = valid & (p1 >= a.min_baseline)
    print(f"valid in both        : {int(valid.sum()):,}")
    print(f"baseline >= {a.min_baseline}      : {int(base_ok.sum()):,} "
          f"({100*base_ok.sum()/max(1, valid.sum()):.0f}% of valid)")

    if a.coast_px:
        inland = ndimage.binary_erosion(valid, np.ones((3, 3)),
                                        iterations=a.coast_px,
                                        border_value=0)
        lost = int(base_ok.sum() - (base_ok & inland).sum())
        base_ok &= inland
        print(f"coastline buffer     : dropped {lost:,} px within "
              f"{a.coast_px} px of the frame/water edge")

    change = np.where(base_ok, p2 - p1, np.nan)
    ch = change[np.isfinite(change)]
    print(f"\ncoherence change over {len(ch):,} qualifying pixels")
    print(f"  mean {ch.mean():+.4f}   median {np.median(ch):+.4f}")
    for q in (1, 5, 25, 50, 75, 95, 99):
        print(f"  p{q:<3} {np.percentile(ch, q):+.4f}")
    lost_frac = float((ch < -0.2).mean())
    print(f"\n  pixels losing more than 0.2 coherence: "
          f"{100*lost_frac:.2f}%  ({int((ch < -0.2).sum()):,})")
    print(f"  pixels GAINING more than 0.2         : "
          f"{100*float((ch > 0.2).mean()):.2f}%")
    print("\n  The gain figure is the control that matters. Coherence cannot")
    print("  genuinely improve because of an earthquake, so the gaining")
    print("  fraction measures how much of the losing fraction is noise.")

    # Radial structure: does the loss concentrate near the source?
    xs = post[post.dims[-1]].values
    ys = post[post.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", post.rio.crs, always_xy=True)
    ex, ey = fwd.transform(*EPI)
    R = np.hypot(xs[None, :] - ex, ys[:, None] - ey) / 1000.0
    print(f"\n  {'ring km':>10}{'px':>10}{'median change':>16}"
          f"{'% below -0.2':>14}")
    for r0, r1 in [(0, 20), (20, 30), (30, 40), (40, 50), (50, 65),
                   (65, 90), (90, 130)]:
        m = base_ok & (R >= r0) & (R < r1)
        if m.sum() < 500:
            print(f"  {f'{r0}-{r1}':>10}{int(m.sum()):>10}"
                  f"{'too few':>16}")
            continue
        v = change[m]
        print(f"  {f'{r0}-{r1}':>10}{int(m.sum()):>10}"
              f"{np.median(v):>16.4f}{100*float((v < -0.2).mean()):>13.2f}%")

    los_p = band(F1148, "los_disp")
    wrap_p = band(F1148, "wrapped_phase")
    print()
    if los_p:
        los = read(los_p).values.astype("float64") * 100.0
        fin = np.isfinite(los) & (los != 0)
        print(f"LOS displacement (frame 1148 only): {int(fin.sum()):,} px, "
              f"{np.nanpercentile(los[fin], 1):+.1f} to "
              f"{np.nanpercentile(los[fin], 99):+.1f} cm (1-99 pct)")
    else:
        print("LOS displacement: ABSENT. Frame 1153's job used the deprecated")
        print("  include_los_displacement, which HyP3 ignores.")
    print(f"wrapped phase: {'present' if wrap_p else 'ABSENT'} "
          f"-- fringes are the evidence the pattern is deformation, not "
          f"atmosphere")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5),
                           gridspec_kw={"width_ratios": [1, 1.1]})
    ax[0].hist(ch, bins=120, range=(-0.6, 0.6), color="#8fa8a0",
               edgecolor="none")
    ax[0].axvline(0, color="#444", lw=1)
    ax[0].axvline(np.median(ch), color="#c8471b", lw=2,
                  label=f"median {np.median(ch):+.3f}")
    ax[0].set_xlabel("coherence change, co-event minus quiet")
    ax[0].set_ylabel("pixels")
    ax[0].set_title(f"Ascending p112, baseline ≥ {a.min_baseline}\n"
                    f"{len(ch):,} qualifying pixels", fontsize=10.5,
                    loc="left")
    ax[0].legend(fontsize=9)

    sub = slice(None, None, 4)
    im = ax[1].imshow(change[sub, sub], cmap="RdBu", vmin=-0.4, vmax=0.4,
                      extent=[xs.min(), xs.max(), ys.min(), ys.max()],
                      origin="upper")
    ax[1].plot(ex, ey, "*", color="#111", ms=15)
    ax[1].set_xticks([]); ax[1].set_yticks([])
    # RdBu maps LOW values to red, so loss is red. The first version of this
    # label said blue, which inverts the reading of a damage map.
    ax[1].set_title("red = coherence lost across the rupture",
                    fontsize=10.5, loc="left")
    fig.colorbar(im, ax=ax[1], shrink=.8)
    fig.suptitle("Flores M7.7 — ascending coherence change, frames 1148+1153 "
                 "mosaicked", fontsize=12.5, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .93])
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
