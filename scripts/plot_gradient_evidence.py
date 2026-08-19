"""The co-event phase gradient against 13 pairs of its own history, per frame.

This replaces null_evidence_full.png, which is retracted. That figure concluded
"no detectable co-seismic signal" from circular means of WRAPPED phase, a
statistic with a hard ceiling at half a fringe (1.39 cm) when the signal turns
out to be ~6 fringes. Fitting a plane to UNWRAPPED phase has no such ceiling.

What is plotted, and why each panel is needed:

  TOP  the co-event unwrapped phase for each frame, in cm of line-of-sight,
       with the epicentre marked. This is the thing being measured, shown
       before any statistic is taken of it.

  BOTTOM  every earthquake-free 12-day pair's north gradient as a point, with
       the co-event marked. The question is not "is the gradient large" but
       "is it larger than what this frame does anyway", and only the spread of
       the baseline answers that. Frame 1148's baseline is loose (sd 0.083) and
       frame 1153's is tight (sd 0.005), so the SAME gradient means very
       different things in the two, which a single number cannot convey.

Frames are separated by FOOTPRINT, never by acquisition second: frames are
~25 s apart along track but the absolute time depends on the satellite, so a
prefix rule calibrated on the S1A baselines files the S1D co-event under the
wrong frame -- comparing the northern co-event against southern baselines and
reporting the difference as an earthquake.

    conda run -n base python scripts/plot_gradient_evidence.py
"""

import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                   # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradient_zscore import (COEVENT, FRAME_LATMAX, gradient,   # noqa: E402
                             products)

EPI_LON, EPI_LAT = 121.3517, -8.3101
FRINGE_CM = 5.5465 / 2
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/gradient_evidence.png")


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14.5, 11),
                             gridspec_kw=dict(height_ratios=[1.35, 1]))

    for col, frame in enumerate((1148, 1153)):
        unw = products(frame, "unw_phase")
        corr = products(frame, "corr")
        co = unw.get(COEVENT)

        rows = []
        for k in sorted(unw):
            if k == COEVENT or k not in corr:
                continue
            g = gradient(unw[k], corr[k], 0.3, FRAME_LATMAX[frame])
            if g:
                rows.append((k, g))
        base = np.array([g["north"] for _, g in rows])
        mu, sd = base.mean(), base.std(ddof=1)
        gco = gradient(co, corr[COEVENT], 0.3, FRAME_LATMAX[frame]) if co else None
        z = (gco["north"] - mu) / sd if gco and sd > 0 else np.nan

        # ---- map ------------------------------------------------------
        ax = axes[0][col]
        with rasterio.open(co) as src:
            phi = src.read(1).astype("float32")
            with rasterio.open(corr[COEVENT]) as sc:
                coh = sc.read(1)
            ok = np.isfinite(phi) & (phi != 0) & (coh >= 0.3)
            cm = np.where(ok, phi * FRINGE_CM / (2 * np.pi), np.nan)
            # Unwrapped phase is relative to an arbitrary reference pixel, so
            # only DIFFERENCES across the scene mean anything. Centre on the
            # median to make the gradient legible rather than the offset.
            cm = cm - np.nanmedian(cm)
            b = src.bounds
            lon, lat = warp_transform(
                src.crs, "EPSG:4326",
                [b.left, b.right, b.left, b.right],
                [b.bottom, b.bottom, b.top, b.top])
            ext = [min(lon), max(lon), min(lat), max(lat)]
        lim = np.nanpercentile(np.abs(cm), 98)
        im = ax.imshow(cm, cmap="RdYlBu_r", extent=ext, origin="upper",
                       vmin=-lim, vmax=lim, interpolation="nearest")
        ax.plot(EPI_LON, EPI_LAT, marker="*", color="#00ff88", ms=19,
                mec="black", mew=1.0, zorder=5)
        ax.set_title(f"Frame {frame} — co-event unwrapped phase, 6→18 Aug\n"
                     f"north gradient {gco['north']:+.4f} cm/km   "
                     f"(plane explains {100*gco['r2']:.0f}%)",
                     fontsize=10.5, loc="left")
        ax.set_xlabel("lon"); ax.set_ylabel("lat")
        fig.colorbar(im, ax=ax, shrink=.85, pad=.02, label="cm line-of-sight")

        # ---- baseline distribution -------------------------------------
        ax = axes[1][col]
        x = np.arange(len(base))
        ax.axhspan(mu - 2 * sd, mu + 2 * sd, color="#4477aa", alpha=.13,
                   label="baseline ±2σ")
        ax.axhline(mu, color="#4477aa", lw=1.1)
        ax.plot(x, base, "o", color="#4477aa", ms=6,
                label=f"{len(base)} earthquake-free pairs")
        ax.axhline(gco["north"], color="#cc3311", lw=1.6, ls="--")
        ax.plot([len(base)], [gco["north"]], "*", color="#cc3311", ms=20,
                mec="black", mew=.7, label="co-event 6→18 Aug")
        ax.set_xticks(list(x) + [len(base)])
        ax.set_xticklabels([k[4:8] for k, _ in rows] + ["CO"], rotation=90,
                           fontsize=7)
        ax.set_ylabel("north gradient (cm/km)")
        verdict = ("outside its own history" if abs(z) >= 3
                   else "within ordinary variability")
        ax.set_title(f"baseline sd {sd:.4f} cm/km   →   co-event z = {z:+.2f}"
                     f"\n{verdict}", fontsize=10.5, loc="left")
        ax.legend(fontsize=7.5, loc="best", framealpha=.9)

    fig.suptitle("Flores M7.7 — co-event phase gradient against 13 pairs of "
                 "each frame's own history\n"
                 "the same gradient means different things in the two frames, "
                 "because their baselines differ by 16x",
                 fontsize=12.5, y=.985)
    fig.tight_layout(rect=[0, 0, 1, .95])
    fig.savefig(OUT, dpi=130)
    print(f"wrote {OUT}")
    print("\nA large z says the pair is anomalous against its own history. It")
    print("does NOT say the anomaly is tectonic: over one look direction an")
    print("offshore source and an orbital ramp are both planar and cannot be")
    print("told apart. Descending path 163 is what separates them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
