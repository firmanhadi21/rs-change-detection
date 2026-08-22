"""Descending path 61: does an independent look direction see the same event?

This is the one measurement in the investigation that is not circular. GMTSAR,
MintPy and insardev all agreed to within 1 cm, but all three consumed the same
two ascending acquisitions, so the atmosphere on 18 August 2026 was common to
every one of them and no amount of agreement could remove it. Path 61 is a
different track, a different look direction, different dates (2 -> 20 August)
and a different satellite pair. Its atmosphere is an independent draw.

WHAT AGREEMENT WOULD AND WOULD NOT LOOK LIKE. Ascending and descending see
DIFFERENT projections of the same ground motion, so the two LOS magnitudes
should NOT match. For a thrust event with uplift plus horizontal motion, both
geometries usually see range decrease near the source, but by different
amounts. So the test is:

  the same SHAPE -- a signal centred on the source decaying to zero by ~50 km,
  not a ramp and not noise;
  the same SIGN in the near field;
  a magnitude of the same order.

A descending profile that is flat within its own noise would mean the
ascending signal was atmosphere after all. That is the outcome this is
genuinely able to produce, which is what makes running it worth 30 credits.

The pre-pre pair is the control. It is same-mission, same-frame, 12 days, and
contains no earthquake, so whatever structure it shows is what this track's
atmosphere and processing do to a quiet interval. The co-event profile has to
beat it, not merely be non-zero.

    conda run -n mintpy python scripts/desc61_analyse.py
"""

import argparse
import glob
import os
import sys

import numpy as np

REPO = os.path.expanduser("~/GitHub/rs-change-detection")
CO = os.path.join(REPO, "output/coseismic",
                  "flores-coseismic-2026-desc61-f621-prepost-d2")
CTRL = os.path.join(REPO, "output/coseismic",
                    "flores-coseismic-2026-desc61-f621-prepre-d2")
OUT = os.path.join(REPO, "output/coseismic/desc61_profile.png")
EPI = (121.3517, -8.3101)
RINGS = [(20, 30), (30, 40), (40, 50), (50, 65)]
# Ascending, for context only -- NOT a target to match, since the geometry
# differs. Deramped MintPy values with their empirical 12-day noise.
ASC = [-6.50, -4.13, -0.94, +1.05]
ASC_SD = [1.65, 1.30, 1.05, 0.99]


def band(d, name):
    hits = glob.glob(os.path.join(d, f"*_{name}.tif"))
    if not hits:
        sys.exit(f"no {name} in {os.path.basename(d)}")
    return hits[0]


def load(d, name):
    import rioxarray  # noqa: F401
    import xarray as xr
    da = xr.open_dataarray(band(d, name), engine="rasterio")
    if "band" in da.dims:
        da = da.isel(band=0)
    return da


def radial(d, min_coh, ref_lo):
    """Ring medians of LOS displacement, referenced to the outer ring."""
    from pyproj import Transformer

    los = load(d, "los_disp")
    coh = load(d, "corr").values
    water = load(d, "water_mask").values
    v = los.values.astype("float64") * 100.0             # metres -> cm

    xs = los[los.dims[-1]].values
    ys = los[los.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", los.rio.crs, always_xy=True)
    ex, ey = fwd.transform(*EPI)
    R = np.hypot(xs[None, :] - ex, ys[:, None] - ey) / 1000.0

    good = np.isfinite(v) & (coh >= min_coh) & (water > 0)
    ref = np.median(v[good & (R >= ref_lo)]) if (
        good & (R >= ref_lo)).sum() > 200 else 0.0

    rows = []
    for r0, r1 in RINGS:
        m = good & (R >= r0) & (R < r1)
        rows.append((np.median(v[m]) - ref, int(m.sum())) if m.sum() >= 200
                    else (np.nan, int(m.sum())))
    return rows, good, coh, R, v - ref, (xs, ys, ex, ey)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.3,
                    help="lower than the ascending 0.4: an 18-day "
                         "cross-mission pair decorrelates more, and being "
                         "strict here would empty the near-field rings")
    ap.add_argument("--ref-km", type=float, default=65.0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    co, good_co, coh_co, R, field, geom = radial(CO, a.min_coh, a.ref_km)
    ct, good_ct, coh_ct, _, _, _ = radial(CTRL, a.min_coh, a.ref_km)

    print(f"co-event  coherence: mean {np.nanmean(coh_co):.3f}, "
          f"{100*good_co.mean():.1f}% usable")
    print(f"control   coherence: mean {np.nanmean(coh_ct):.3f}, "
          f"{100*good_ct.mean():.1f}% usable")

    print(f"\n  {'ring km':>10}{'px':>9}{'co-event':>11}{'control':>10}"
          f"{'asc (diff geom)':>18}")
    for (r0, r1), (c, n), (q, _), asc in zip(RINGS, co, ct, ASC):
        cs = f"{c:.2f}" if np.isfinite(c) else "--"
        qs = f"{q:.2f}" if np.isfinite(q) else "--"
        print(f"  {f'{r0}-{r1}':>10}{n:>9}{cs:>11}{qs:>10}{asc:>18.2f}")

    cv = np.array([c for c, _ in co])
    qv = np.array([q for q, _ in ct])
    ok = np.isfinite(cv) & np.isfinite(qv)
    if ok.sum() < 3:
        sys.exit("\ntoo few coherent rings to judge")

    swing_co = np.nanmax(cv[ok]) - np.nanmin(cv[ok])
    swing_ct = np.nanmax(qv[ok]) - np.nanmin(qv[ok])
    print(f"\n  near-to-far swing:  co-event {swing_co:.2f} cm, "
          f"control {swing_ct:.2f} cm  (ratio {swing_co/swing_ct:.1f}x)"
          if swing_ct > 0 else "")

    # Monotonic outward decay is NOT evidence of a source here, and this
    # script originally claimed it was. The coherent ground spans about 110
    # degrees of azimuth around the epicentre -- one-sided. Over a sector that
    # narrow, distance from the epicentre is nearly collinear with position,
    # so a plain linear ramp produces a perfectly monotonic radial decay. The
    # test cannot separate the two and is reported here only as a description
    # of the profile, not as a verdict.
    mono = bool(np.all(np.diff(cv[ok]) > 0)) if cv[ok][0] < 0 else False
    print(f"  profile decays monotonically outward: {mono} "
          f"(descriptive only -- see desc61_discriminate.py)")

    r_asc = np.corrcoef(cv[ok], np.array(ASC)[ok])[0, 1]
    print(f"  shape correlation with the ascending profile: {r_asc:+.3f}")

    print()
    if swing_ct > 0 and swing_co > 2.5 * swing_ct:
        print(f"  The co-event profile swings {swing_co/swing_ct:.1f}x its own")
        print("  quiet control on the same track. That is worth following up,")
        print("  but it is NOT yet a source: a ramp would do it too over")
        print("  one-sided ground. Run desc61_discriminate.py, which removes")
        print("  the best plane from both and asks what survives.")
    elif swing_ct > 0 and swing_co > 1.5 * swing_ct:
        print("  The co-event profile exceeds the control but not decisively.")
        print("  Suggestive; the near-field coherence is the limiting factor.")
    else:
        print("  The co-event profile is not clearly larger than the quiet")
        print("  control on this track. On its own this does NOT confirm the")
        print("  ascending signal -- and given the ascending step cleared 76")
        print("  quiet intervals, a null here needs explaining rather than")
        print("  averaging in. Check near-field coherence first.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xs, ys, ex, ey = geom
    mid = [(r0 + r1) / 2 for r0, r1 in RINGS]
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 5),
                           gridspec_kw={"width_ratios": [1.15, 1]})
    ax[0].axhline(0, color="#999", lw=.8)
    ax[0].errorbar(mid, ASC, yerr=ASC_SD, fmt="--o", ms=4, lw=1.2, capsize=3,
                   color="#8aa0a6", label="ascending p112 (different geometry)")
    ax[0].plot(mid, qv, "-s", ms=5, lw=1.5, color="#c8a415",
               label="descending p61 control (21 Jul→2 Aug, no quake)")
    ax[0].plot(mid, cv, "-^", ms=7, lw=2.2, color="#7a1fa2",
               label="descending p61 co-event (2→20 Aug)")
    ax[0].set_xlabel("distance from epicentre, km")
    ax[0].set_ylabel("LOS displacement, cm")
    ax[0].set_title("Independent look direction vs its own quiet control",
                    fontsize=10.5, loc="left")
    ax[0].grid(alpha=.25); ax[0].legend(fontsize=8.5)

    show = np.where(good_co & (R <= 90), field, np.nan)
    im = ax[1].imshow(show, cmap="RdBu_r", vmin=-10, vmax=10, origin="upper",
                      extent=[xs.min(), xs.max(), ys.min(), ys.max()])
    ax[1].plot(ex, ey, "*", color="#111", ms=15)
    ax[1].set_title("descending p61 co-event LOS, cm", fontsize=10.5,
                    loc="left")
    ax[1].set_xticks([]); ax[1].set_yticks([])
    fig.colorbar(im, ax=ax[1], shrink=.8)
    fig.suptitle("Flores M7.7: does descending path 61 confirm the ascending "
                 "result?", fontsize=12.5, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .93])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
