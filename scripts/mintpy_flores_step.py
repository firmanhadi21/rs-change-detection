"""Is the Flores co-seismic step significant against this frame's own noise?

The GMTSAR interferogram gave 4-7 cm of line-of-sight motion near the
epicentre. What it could not give is a scale: 4 cm compared to WHAT? The
comparison I used there -- near-field span against far-field span within the
same interferogram -- is internal and weak.

The 72 earthquake-free pairs are the scale. Same frame, same track, same
12-day cadence, no earthquake in them, so the epoch-to-epoch scatter of the
time series IS what this scene's atmosphere and orbit errors do over 12 days.
The co-seismic step can then be stated in units of that.

WHAT THIS STILL CANNOT DO. Only one pair brackets the rupture, so the
atmosphere on 18 August 2026 is not separable from the step by any inversion.
This gives the step a calibrated uncertainty; it does not remove the confound.
Only more post-event scenes do.

    conda run -n mintpy python scripts/mintpy_flores_step.py
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
WORK = os.path.expanduser(_REPO_ROOT + "/data/mintpy_flores")
EPI = (121.3517, -8.3101)
EVENT = "20260814"
OUT = os.path.expanduser(
    _REPO_ROOT + "/output/coseismic/mintpy_flores_step.png")


def _iso(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--ts", default="timeseries.h5",
                    help="timeseries.h5 is uncorrected; "
                         "timeseries_SET_ERA5_demErr.h5 etc. are the "
                         "corrected products, if those steps ran")
    ap.add_argument("--min-coh", type=float, default=0.4)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    from mintpy.utils import readfile
    from pyproj import Transformer

    # An explicit --ts wins outright. That matters here: the whole point of
    # running this twice is to compare timeseries.h5 against
    # timeseries_ramp_demErr.h5, and a "prefer the most corrected" fallback
    # would silently hand back the same file both times.
    ts_file = os.path.join(a.work, a.ts)
    if not os.path.exists(ts_file):
        sys.exit(f"no {a.ts} in {a.work}")
    print(f"time series: {os.path.basename(ts_file)}")

    ts, atr = readfile.read(ts_file)
    dates = readfile.get_slice_list(ts_file)
    dates = [d.split("-")[-1] for d in dates]
    coh, _ = readfile.read(os.path.join(a.work, "avgSpatialCoh.h5"))
    mask, _ = readfile.read(os.path.join(a.work, "maskConnComp.h5"))

    x0, y0 = float(atr["X_FIRST"]), float(atr["Y_FIRST"])
    dx, dy = float(atr["X_STEP"]), float(atr["Y_STEP"])
    ny, nx = coh.shape
    epsg = atr.get("EPSG", "32751")
    fwd = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    ex, ey = fwd.transform(*EPI)
    X = x0 + dx * np.arange(nx)
    Y = y0 + dy * np.arange(ny)
    R = np.hypot(X[None, :] - ex, Y[:, None] - ey) / 1000.0

    good = (mask > 0) & (coh >= a.min_coh)
    print(f"{len(dates)} epochs, {dates[0]} .. {dates[-1]}")
    print(f"{int(good.sum()):,} pixels at coherence >= {a.min_coh}")

    pre = [i for i, d in enumerate(dates) if d < EVENT]
    post = [i for i, d in enumerate(dates) if d > EVENT]
    print(f"pre-event epochs: {len(pre)}   post-event: {len(post)} "
          f"({[dates[i] for i in post]})")
    if not post:
        sys.exit("no post-event epoch in the time series")

    # Near field: the ring where the GMTSAR result put the signal. 0-20 km is
    # offshore, so 20-40 km is the closest ground there is.
    near = good & (R >= 20) & (R < 40)
    far = good & (R >= 90)
    print(f"near-field (20-40 km) pixels: {int(near.sum()):,}")
    print(f"far-field  (>90 km)   pixels: {int(far.sum()):,}")
    if near.sum() < 500:
        sys.exit("too little coherent near-field ground")

    # Displacement of each epoch in the near field, relative to the far field.
    # Differencing against the far field removes whatever the reference pixel
    # and any residual scene-wide ramp are doing, which is common-mode.
    series = np.array([np.median(ts[i][near]) - np.median(ts[i][far])
                       for i in range(len(dates))]) * 100.0   # cm

    # The step: last pre-event epoch to the post-event epoch.
    i_pre, i_post = pre[-1], post[0]
    step = series[i_post] - series[i_pre]

    # The noise: every 12-day consecutive difference among the QUIET epochs.
    # These are what a 12-day interval does here when nothing happened, which
    # is exactly the null distribution the step must be judged against.
    quiet = []
    for j in range(1, len(pre)):
        d0, d1 = dates[pre[j - 1]], dates[pre[j]]
        gap = (np.datetime64(f"{d1[:4]}-{d1[4:6]}-{d1[6:]}")
               - np.datetime64(f"{d0[:4]}-{d0[4:6]}-{d0[6:]}")).astype(int)
        if gap <= 24:                     # one or two cycles
            quiet.append(series[pre[j]] - series[pre[j - 1]])
    quiet = np.array(quiet)

    print(f"\n  near-field displacement relative to far field")
    print(f"    last pre-event  {dates[i_pre]}   {series[i_pre]:+7.2f} cm")
    print(f"    post-event      {dates[i_post]}   {series[i_post]:+7.2f} cm")
    print(f"    STEP                        {step:+7.2f} cm")

    if len(quiet) < 5:
        print("\n  too few quiet intervals to form a noise distribution")
        return 0
    sd = float(np.std(quiet, ddof=1))
    print(f"\n  quiet 12-day intervals: n = {len(quiet)}")
    print(f"    mean {np.mean(quiet):+.2f} cm, sd {sd:.2f} cm, "
          f"range {quiet.min():+.2f} .. {quiet.max():+.2f} cm")
    z = step / sd if sd > 0 else np.nan
    bigger = int(np.sum(np.abs(quiet) >= abs(step)))
    print(f"\n    step / sd = {z:+.1f}")
    print(f"    quiet intervals at least as large: {bigger} of {len(quiet)}"
          f"  (empirical p = {(bigger+1)/(len(quiet)+1):.3f})")

    print()
    if abs(z) >= 3 and bigger == 0:
        print(f"  The step is {abs(z):.1f} sigma and larger than every one of")
        print(f"  the {len(quiet)} earthquake-free intervals. On this frame's")
        print("  own noise it is a real displacement.")
    elif bigger <= 1:
        print(f"  The step is {abs(z):.1f} sigma and exceeded by {bigger} of")
        print(f"  {len(quiet)} quiet intervals -- suggestive, not decisive.")
    else:
        print(f"  {bigger} of {len(quiet)} earthquake-free intervals are as")
        print("  large. This frame's 12-day atmosphere reproduces the step")
        print("  routinely, so the step is not distinguishable from it.")

    # Shape, not just size. A scene-wide offset and a source both produce a
    # step in the near-minus-far number above. Only a source decays with
    # distance. The quiet epochs give the profile its own error bars, so the
    # decay can be judged rather than eyeballed -- and GMTSAR's independent
    # radial profile on the same frame is the thing to compare it against.
    print("\n  radial profile of the co-seismic epoch, and what the 76 quiet")
    print("  12-day intervals do in the same rings")
    print(f"\n  {'ring km':>10}{'px':>9}{'step cm':>10}{'quiet sd':>10}"
          f"{'sigma':>8}")
    rings = [(20, 30), (30, 40), (40, 50), (50, 65), (65, 90)]
    prof = []
    for r0, r1 in rings:
        m = good & (R >= r0) & (R < r1)
        if m.sum() < 200:
            print(f"  {f'{r0}-{r1}':>10}{int(m.sum()):>9}      too few px")
            continue
        s = np.array([np.median(ts[i][m]) - np.median(ts[i][far])
                      for i in range(len(dates))]) * 100.0
        st = s[i_post] - s[i_pre]
        q = np.array([s[pre[j]] - s[pre[j - 1]] for j in range(1, len(pre))
                      if (np.datetime64(_iso(dates[pre[j]]))
                          - np.datetime64(_iso(dates[pre[j - 1]]))
                          ).astype(int) <= 24])
        qsd = float(np.std(q, ddof=1))
        prof.append((r0, r1, st, qsd))
        print(f"  {f'{r0}-{r1}':>10}{int(m.sum()):>9}{st:>10.2f}{qsd:>10.2f}"
              f"{st/qsd:>8.1f}")

    if len(prof) >= 3:
        decay = abs(prof[0][2]) - abs(prof[-1][2])
        print(f"\n  near ring {prof[0][2]:+.2f} cm -> far ring "
              f"{prof[-1][2]:+.2f} cm  (decay {decay:+.2f} cm)")
        if decay > 2 * prof[0][3]:
            print("  The step decays with distance from the epicentre by more")
            print("  than the ring noise. That is the shape of a source, not")
            print("  a scene-wide offset.")
        else:
            print("  The step does NOT decay appreciably -- consistent with a")
            print("  scene-wide offset, which a source is not.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = np.array([np.datetime64(f"{d[:4]}-{d[4:6]}-{d[6:]}") for d in dates])
    fig, ax = plt.subplots(1, 2, figsize=(14, 5),
                           gridspec_kw={"width_ratios": [2, 1]})
    ax[0].plot(t, series, "-o", ms=3.5, lw=1.1, color="#1d4a54")
    ax[0].axvline(np.datetime64("2026-08-14"), color="#c8471b", lw=1.6,
                  label="M7.7, 14 Aug 2026")
    ax[0].set_ylabel("near-field minus far-field LOS (cm)")
    ax[0].set_title(f"Frame 1148 time series, {len(dates)} epochs\n"
                    f"20-40 km from the epicentre, referenced to >90 km",
                    fontsize=10.5, loc="left")
    ax[0].grid(alpha=.25); ax[0].legend(fontsize=9)
    ax[1].hist(quiet, bins=15, color="#8fa8a0", edgecolor="white")
    ax[1].axvline(step, color="#c8471b", lw=2.2,
                  label=f"co-seismic step {step:+.2f} cm")
    ax[1].set_xlabel("12-day change, cm")
    ax[1].set_title(f"{len(quiet)} earthquake-free intervals\n"
                    f"sd = {sd:.2f} cm", fontsize=10.5, loc="left")
    ax[1].legend(fontsize=9)
    fig.suptitle("Is the Flores step larger than this frame's own 12-day "
                 "noise?", fontsize=12.5, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .93])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
