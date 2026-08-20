"""Show the northwest-patch anomaly beside the pairs it is being compared to.

The claim is that the co-event pair's north gradient over northwest Flores,
-0.605 cm/km, sits 8.8 sigma outside 70 earthquake-free pairs on the same
ground and is 3.9x the most extreme of them. A z-score is only as convincing
as the population behind it, so this puts the co-event next to the actual
baselines -- including the most extreme ones, which are the honest comparison,
not the typical ones.

Every panel is the same patch, the same colour scale, and the same processing.
If the claim is sound the co-event should be visibly different from pairs that
contain no earthquake; if it merely sits at the end of a continuum, that will
be visible too, and is worth seeing before anyone writes it up.

Panels are re-referenced to their own median rather than to the HyP3 reference
pixel, which lies far outside this patch. An unwrapped product carries an
arbitrary constant, so only the GRADIENT across each panel is meaningful --
the colour of any single pixel is not.

    conda run -n base python scripts/plot_nw_patch_evidence.py
"""

import argparse
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                   # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradient_zscore import (COEVENT, FRAME_LATMAX, FRINGE_CM,   # noqa: E402
                             gradient, products)

EPI_LON, EPI_LAT = 121.3517, -8.3101
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/nw_patch_evidence.png")


def load_patch(unw_path, corr_path, lat_max, min_coh=0.3):
    with rasterio.open(unw_path) as src:
        phi = src.read(1).astype("float64")
        tr, crs, H, W = src.transform, src.crs, src.height, src.width
    with rasterio.open(corr_path) as src:
        coh = src.read(1)
    if coh.shape != phi.shape:
        return None
    rows, cols = np.mgrid[0:H, 0:W]
    xs = tr.c + (cols + .5) * tr.a
    ys = tr.f + (rows + .5) * tr.e
    lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(phi.shape)
    lat = np.array(lat).reshape(phi.shape)
    ok = (np.isfinite(phi) & (phi != 0) & (coh >= min_coh)
          & (lat <= lat_max))
    if ok.sum() < 5000:
        return None
    rr = np.flatnonzero(ok.any(axis=1))
    cc = np.flatnonzero(ok.any(axis=0))
    sl = (slice(rr[0], rr[-1] + 1), slice(cc[0], cc[-1] + 1))
    cm = np.where(ok, phi * FRINGE_CM / (2 * np.pi), np.nan)[sl]
    cm = cm - np.nanmedian(cm)
    return cm, [lon[sl].min(), lon[sl].max(), lat[sl].min(), lat[sl].max()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1153)
    ap.add_argument("--n-extreme", type=int, default=3)
    ap.add_argument("--n-typical", type=int, default=2)
    a = ap.parse_args()

    unw = products(a.frame, "unw_phase")
    corr = products(a.frame, "corr")
    lat_max = FRAME_LATMAX[a.frame]

    print(f"frame {a.frame}: ranking {len(unw)-1} earthquake-free pairs")
    rows = []
    for k in sorted(unw):
        if k == COEVENT or k not in corr:
            continue
        g = gradient(unw[k], corr[k], 0.3, lat_max)
        if g:
            rows.append((k, g["north"]))
    rows.sort(key=lambda r: -abs(r[1]))
    gco = gradient(unw[COEVENT], corr[COEVENT], 0.3, lat_max)
    base = np.array([r[1] for r in rows])
    mu, sd = base.mean(), base.std(ddof=1)
    z = (gco["north"] - mu) / sd
    print(f"  co-event {gco['north']:+.4f} cm/km   z = {z:+.2f}")
    print(f"  most extreme baseline {rows[0][1]:+.4f} ({rows[0][0]})")

    picks = [(COEVENT, gco["north"], "CO-EVENT 6->18 Aug")]
    picks += [(k, v, "no earthquake") for k, v in rows[:a.n_extreme]]
    mid = len(rows) // 2
    picks += [(k, v, "no earthquake") for k, v in rows[mid:mid + a.n_typical]]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(picks)
    fig = plt.figure(figsize=(15, 4.2 * ((n + 2) // 3) + 4))
    gs = fig.add_gridspec((n + 2) // 3 + 1, 3, hspace=.35, wspace=.22,
                          height_ratios=[1] * ((n + 2) // 3) + [0.85])

    panels = [load_patch(unw[k], corr[k], lat_max) for k, _, _ in picks]
    lim = np.nanpercentile(
        np.abs(np.concatenate([p[0][np.isfinite(p[0])] for p in panels
                               if p])), 98)

    for i, ((k, val, tag), p) in enumerate(zip(picks, panels)):
        if p is None:
            continue
        cm, ext = p
        ax = fig.add_subplot(gs[i // 3, i % 3])
        im = ax.imshow(cm, cmap="RdYlBu_r", extent=ext, origin="upper",
                       vmin=-lim, vmax=lim, interpolation="nearest")
        ax.plot(EPI_LON, EPI_LAT, "*", color="#00ff88", ms=13, mec="k",
                mew=.6)
        lead = "★ " if k == COEVENT else ""
        ax.set_title(f"{lead}{k[:8]}→{k[9:]}   {tag}\n"
                     f"north gradient {val:+.4f} cm/km", fontsize=9.5,
                     loc="left",
                     fontweight="bold" if k == COEVENT else "normal")
        ax.set_xticks([]); ax.set_yticks([])
        if i == 0:
            fig.colorbar(im, ax=ax, shrink=.85, pad=.02,
                         label="cm line-of-sight")

    ax = fig.add_subplot(gs[-1, :])
    order = np.argsort(base)
    ax.axhspan(mu - 2 * sd, mu + 2 * sd, color="#4477aa", alpha=.13,
               label="baseline ±2σ")
    ax.axhline(mu, color="#4477aa", lw=1.0)
    ax.plot(np.arange(len(base)), base[order], "o", ms=5, color="#4477aa",
            label=f"{len(base)} earthquake-free pairs")
    ax.axhline(gco["north"], color="#cc3311", lw=1.6, ls="--")
    ax.plot([len(base)], [gco["north"]], "*", ms=22, color="#cc3311",
            mec="k", mew=.7, label="co-event")
    ax.set_ylabel("north gradient (cm/km)")
    ax.set_xlabel("earthquake-free pairs, sorted")
    ax.set_title(f"co-event {gco['north']:+.4f} cm/km against {len(base)} "
                 f"pairs on the same ground:  z = {z:+.2f},  "
                 f"{abs(gco['north']/rows[0][1]):.1f}x the most extreme",
                 fontsize=10.5, loc="left")
    ax.legend(fontsize=8, loc="lower right", framealpha=.9)

    fig.suptitle("Flores M7.7 — northwest patch, nearest the rupture: "
                 "co-event against its own history", fontsize=13, y=.995)
    fig.savefig(OUT, dpi=130, bbox_inches="tight")
    print(f"\nwrote {OUT}")
    print("\n  Panels share one colour scale and one patch. Only the GRADIENT")
    print("  across each is meaningful -- unwrapped phase carries an")
    print("  arbitrary constant, so no single pixel's colour means anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
