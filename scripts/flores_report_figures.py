"""Figures for the Flores report and artifact -- maps first, charts second.

The written report had no maps, which for an InSAR result is the wrong way
round: the argument that the signal is deformation rather than atmosphere
rests entirely on WHERE it sits, and no table shows that.

Maps are drawn in each product's native UTM grid rather than reprojected to
lon/lat. The frames are rotated relative to north, so a corner-based lon/lat
extent would shear the image, and shape is exactly what these panels exist to
show.

Zeros are dropped rather than plotted. HyP3 writes 0 outside the imaged area
and under the water mask, and a zero on a diverging colour map reads as "no
displacement here" instead of "no data here".

THE WRAPPED-PHASE PANEL IS A ZOOM, AT FULL RESOLUTION, AND HAS TO BE. Drawn
over the whole frame decimated 4x it rendered as pure speckle, and would have
been captioned "fringes" while showing none. That was sampling, not data:
near-field coherence is median 0.41 with 68% of land above 0.3, and the
fringes run about 20 pixels apart. Sampling every 4th pixel and then squeezing
8000 px into a 700 px panel destroys a 20 px feature twice over.

    conda run -n insardev-test python scripts/flores_report_figures.py
"""

import argparse
import glob
import json
import os
import sys

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_REPO_ROOT, "output/coseismic")
FIGDIR = os.path.join(_REPO_ROOT, "docs/figures")
REPORTS = os.path.join(_REPO_ROOT, "data/eq_reports.geojson")
EPI = (121.3517, -8.3101)

INK = "#1a1f24"
MUTED = "#6b7780"
TEAL = "#1d4a54"
RUST = "#c8471b"
MOSS = "#6b8f3a"
PLUM = "#7a1fa2"
SLATE = "#8fa8a0"

RINGS = [25, 35, 45, 57.5]
RING_LAB = ["20-30", "30-40", "40-50", "50-65"]
GMTSAR = [-7.53, -4.81, -0.99, +0.84]
MINTPY_DER = [-6.50, -4.13, -0.94, +1.05]
MINTPY_SD = [1.65, 1.30, 1.05, 0.99]
INSARDEV = [-8.59, -4.21, -0.60, +1.33]
D61_RAW = [-12.97, -8.17, -4.82, -4.50]
D61_DEP = [-3.65, -0.45, +1.18, +0.72]
D163_RAW = [-1.65, +2.41, +5.00, +1.83]
D163_DEP = [-4.06, +0.03, +2.32, +0.15]

PRODUCTS = {
    "asc": "flores-coseismic-2026-asc-f1148-prepost-d2",
    "asc_pre": "flores-coseismic-2026-asc-f1148-prepre-d2",
    "d61": "flores-coseismic-2026-desc61-f621-prepost-d2",
    "d163": "flores-coseismic-2026-desc163-f620-prepost-d2",
}


def band(key, name):
    hits = glob.glob(os.path.join(OUT, PRODUCTS[key], f"*_{name}.tif"))
    return hits[0] if hits else None


def _open(path):
    import rioxarray  # noqa: F401
    import xarray as xr
    da = xr.open_dataarray(path, engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def read_band(key, name, step=4, scale=1.0, water=True, drop_zero=True):
    p = band(key, name)
    if p is None:
        return None
    da = _open(p)
    v = da.values[::step, ::step].astype("float64") * scale
    if water:
        wp = band(key, "water_mask")
        if wp:
            wv = _open(wp).values[::step, ::step]
            if wv.shape == v.shape:
                v = np.where(wv > 0, v, np.nan)
    if drop_zero:
        v = np.where(v == 0, np.nan, v)
    xs = da[da.dims[-1]].values[::step]
    ys = da[da.dims[-2]].values[::step]
    return v, (xs.min(), xs.max(), ys.min(), ys.max()), da.rio.crs


def epi_xy(crs):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", crs,
                                always_xy=True).transform(*EPI)


def style_map(ax, crs, note=None):
    ex, ey = epi_xy(crs)
    ax.plot(ex, ey, "*", color="#111", ms=18, mec="white", mew=1.3, zorder=5)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor("#ece8e1")
    # Scale bar length from the axis width, not fixed: a hardcoded 50 km bar
    # spanned the entire width of the 50 km zoom panel and read as a fault.
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    span_km = abs(x1 - x0) / 1000.0
    nice = [1, 2, 5, 10, 20, 25, 50, 100, 200]
    barkm = min(nice, key=lambda n: abs(n - span_km * 0.25))
    bx = x0 + 0.05 * (x1 - x0); by = y0 + 0.07 * (y1 - y0)
    ax.plot([bx, bx + barkm * 1000], [by, by], color=INK, lw=3.5,
            solid_capstyle="butt", zorder=5)
    ax.text(bx + barkm * 500, by + 0.03 * (y1 - y0), f"{barkm} km",
            fontsize=8, ha="center", color=INK, zorder=5)
    if note:
        ax.text(0.985, 0.96, note, transform=ax.transAxes, fontsize=8.5,
                ha="right", va="top", color=INK, zorder=5,
                bbox=dict(fc="white", ec="none", alpha=.8, pad=2.5))


def zoom_wrapped(half_km=25.0, min_coh=0.25):
    """Wrapped phase over the deforming ground, full resolution.

    Centred on the LOS minimum rather than the epicentre: the epicentre is
    28 km offshore, so a box around it is mostly sea. The data chooses the
    crop, because the lobe is what the panel is for.
    """
    pw, pl, pc, pm = (band("asc", "wrapped_phase"), band("asc", "los_disp"),
                      band("asc", "corr"), band("asc", "water_mask"))
    if not all((pw, pl, pc, pm)):
        return None
    wp, los, coh, wm = _open(pw), _open(pl), _open(pc), _open(pm)
    xs = wp[wp.dims[-1]].values
    ys = wp[wp.dims[-2]].values

    L = los.values
    good = (wm.values > 0) & np.isfinite(L) & (L != 0) & (coh.values >= 0.3)
    if good.sum() < 5000:
        return None
    thr = np.percentile(L[good], 2)
    iy, ix = np.nonzero(good & (L <= thr))
    cy, cx = ys[int(np.median(iy))], xs[int(np.median(ix))]

    h = half_km * 1000.0
    jx = np.where((xs >= cx - h) & (xs <= cx + h))[0]
    jy = np.where((ys >= cy - h) & (ys <= cy + h))[0]
    if len(jx) < 50 or len(jy) < 50:
        return None
    sl = (slice(jy.min(), jy.max() + 1), slice(jx.min(), jx.max() + 1))
    v = wp.values[sl].astype("float64")
    v = np.where((wm.values[sl] > 0) & (coh.values[sl] >= min_coh), v, np.nan)
    ext = (xs[jx.min()], xs[jx.max()], ys[jy.max()], ys[jy.min()])
    return v, ext, wp.rio.crs


def fig1(plt):
    import matplotlib.patches as mp
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    g = read_band("asc", "los_disp", scale=100.0)
    if g:
        v, ext, crs = g
        im = ax[0].imshow(v, cmap="RdBu_r", vmin=-10, vmax=10, extent=ext,
                          origin="upper", interpolation="nearest")
        style_map(ax[0], crs, "star = epicentre, 28 km offshore")
        cb = fig.colorbar(im, ax=ax[0], shrink=.85)
        cb.set_label("LOS displacement, cm\n(negative = away from satellite)",
                     fontsize=8.5)
        cb.ax.tick_params(labelsize=8)
    ax[0].set_title("a  Line-of-sight displacement", fontsize=11,
                    weight="bold", loc="left")

    z = zoom_wrapped()
    if z:
        v, ext, crs = z
        im = ax[1].imshow(v, cmap="twilight_shifted", vmin=-np.pi, vmax=np.pi,
                          extent=ext, origin="upper", interpolation="nearest")
        style_map(ax[1], crs, "one colour cycle = 2.8 cm of range change")
        cb = fig.colorbar(im, ax=ax[1], shrink=.85, ticks=[-np.pi, 0, np.pi])
        cb.ax.set_yticklabels(["$-\\pi$", "0", "$\\pi$"], fontsize=8)
        cb.set_label("wrapped phase, radians", fontsize=8.5)
        ax[0].add_patch(mp.Rectangle((ext[0], ext[3]), ext[1] - ext[0],
                                     ext[2] - ext[3], fill=False, ec="#111",
                                     lw=1.4, ls="--", zorder=6))
    ax[1].set_title("b  Wrapped phase over the deforming coast "
                    "(50 km box, full resolution)", fontsize=11,
                    weight="bold", loc="left")
    fig.suptitle("Ascending path 112 frame 1148, 2026-08-06 to 2026-08-18",
                 fontsize=12, y=1.0)
    fig.tight_layout()
    return fig


def fig2(plt):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4),
                           gridspec_kw={"width_ratios": [1.35, 1]})
    ax[0].axhline(0, color="#ccc", lw=.8)
    ax[0].errorbar(RINGS, MINTPY_DER, yerr=MINTPY_SD, fmt="-o", ms=5, lw=1.7,
                   capsize=4, color=TEAL,
                   label="MintPy (deramped) $\\pm$1 sd of 76 quiet intervals")
    ax[0].plot(RINGS, GMTSAR, "-s", ms=5, lw=1.7, color=RUST,
               label="GMTSAR (snaphu)")
    ax[0].plot(RINGS, INSARDEV, "-^", ms=6, lw=1.7, color=MOSS,
               label="insardev (IRLS)")
    ax[0].set_xticks(RINGS); ax[0].set_xticklabels(RING_LAB, fontsize=9)
    ax[0].set_xlabel("distance from epicentre, km", fontsize=9.5)
    ax[0].set_ylabel("LOS displacement, cm", fontsize=9.5)
    ax[0].set_title("a  Three processing chains, one dataset", fontsize=11,
                    weight="bold", loc="left")
    ax[0].grid(alpha=.25); ax[0].legend(fontsize=8)

    steps, sds, sig = [-7.43, -4.44], [1.71, 1.36], [4.4, 3.3]
    ax[1].bar([0, 1], np.abs(steps), 0.48, color=[TEAL, SLATE])
    for i, (s, sd, g) in enumerate(zip(steps, sds, sig)):
        ax[1].errorbar(i, abs(s), yerr=sd, color=INK, capsize=6, lw=1.5)
        ax[1].text(i, abs(s) + sd + 0.35, f"{g}$\\sigma$", ha="center",
                   fontsize=10, weight="bold", color=INK)
    ax[1].set_xticks([0, 1])
    ax[1].set_xticklabels(["raw time series", "deramped + DEM error"],
                          fontsize=9)
    ax[1].set_ylabel("co-seismic step, cm", fontsize=9.5)
    ax[1].set_ylim(0, 11)
    ax[1].set_title("b  Step vs 76 earthquake-free intervals", fontsize=11,
                    weight="bold", loc="left")
    ax[1].grid(alpha=.25, axis="y")
    ax[1].text(0.5, 0.06, "0 of 76 quiet intervals is this large",
               transform=ax[1].transAxes, ha="center", fontsize=8.5,
               color=MUTED)
    fig.tight_layout()
    return fig


def fig3(plt):
    fig = plt.figure(figsize=(13, 8.4))
    for i, (k, ttl) in enumerate([
            ("d61", "a  Descending p61, 2 $\\to$ 20 Aug (18 d, S1D$\\to$S1C)"),
            ("d163", "b  Descending p163, 9 $\\to$ 21 Aug (12 d, S1D)")]):
        ax = fig.add_subplot(2, 2, i + 1)
        g = read_band(k, "los_disp", scale=100.0)
        if g:
            v, ext, crs = g
            im = ax.imshow(v, cmap="RdBu_r", vmin=-10, vmax=10, extent=ext,
                           origin="upper", interpolation="nearest")
            style_map(ax, crs)
            cb = fig.colorbar(im, ax=ax, shrink=.85)
            cb.set_label("LOS, cm", fontsize=8.5)
            cb.ax.tick_params(labelsize=8)
        ax.set_title(ttl, fontsize=10.5, weight="bold", loc="left")

    ax = fig.add_subplot(2, 2, 3)
    ax.axhline(0, color="#ccc", lw=.8)
    ax.plot(RINGS, D61_RAW, "-o", ms=5, lw=1.8, color=PLUM, label="p61")
    ax.plot(RINGS, D163_RAW, "-^", ms=6, lw=1.8, color=MOSS, label="p163")
    ax.set_xticks(RINGS); ax.set_xticklabels(RING_LAB, fontsize=9)
    ax.set_xlabel("distance from epicentre, km", fontsize=9.5)
    ax.set_ylabel("LOS, cm", fontsize=9.5)
    ax.set_title("c  Raw profiles disagree", fontsize=10.5, weight="bold",
                 loc="left")
    ax.grid(alpha=.25); ax.legend(fontsize=8.5)

    ax = fig.add_subplot(2, 2, 4)
    ax.axhline(0, color="#ccc", lw=.8)
    ax.plot(RINGS, D61_DEP, "-o", ms=5, lw=1.8, color=PLUM, label="p61")
    ax.plot(RINGS, D163_DEP, "-^", ms=6, lw=1.8, color=MOSS, label="p163")
    ax.annotate("0.4 cm apart", xy=(25.5, -3.85), xytext=(34, -2.7),
                fontsize=9, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK, lw=1.1))
    ax.set_xticks(RINGS); ax.set_xticklabels(RING_LAB, fontsize=9)
    ax.set_xlabel("distance from epicentre, km", fontsize=9.5)
    ax.set_title("d  Remove each track's own plane: they agree",
                 fontsize=10.5, weight="bold", loc="left")
    ax.grid(alpha=.25); ax.legend(fontsize=8.5, loc="lower right")
    fig.suptitle("Independent geometries, on dates disjoint from the "
                 "ascending pair", fontsize=12, y=1.0)
    fig.tight_layout()
    return fig


def fig4(plt):
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8),
                           gridspec_kw={"width_ratios": [1.3, 1]})
    a = read_band("asc", "corr", water=True, drop_zero=False)
    b = read_band("asc_pre", "corr", water=True, drop_zero=False)
    if a and b and a[0].shape == b[0].shape:
        pre, post = b[0], a[0]
        ok = np.isfinite(pre) & np.isfinite(post) & (pre >= 0.3)
        ch = np.where(ok, pre - post, np.nan)
        im = ax[0].imshow(ch, cmap="RdBu", vmin=-0.35, vmax=0.35,
                          extent=a[1], origin="upper",
                          interpolation="nearest")
        style_map(ax[0], a[2], "speckle everywhere, no lobe at the source")
        cb = fig.colorbar(im, ax=ax[0], shrink=.85)
        cb.set_label("coherence change\n(red = lost)", fontsize=8.5)
        cb.ax.tick_params(labelsize=8)
    else:
        ax[0].axis("off")
        ax[0].text(.5, .5, "coherence rasters unavailable", ha="center",
                   va="center", transform=ax[0].transAxes, color=MUTED)
    ax[0].set_title("a  Coherence change across the rupture", fontsize=11,
                    weight="bold", loc="left")

    rr = ["20-30", "30-40", "40-50", "50-65", "65-90", "90-130", "130-200"]
    vals = [0.0263, 0.0028, 0.0346, 0.0532, 0.0299, 0.0171, 0.0197]
    ax[1].bar(range(len(rr)), vals, 0.62, color=SLATE)
    ax[1].axhline(np.mean(vals), color=RUST, lw=1.5, ls="--",
                  label=f"mean {np.mean(vals):.4f}")
    ax[1].set_xticks(range(len(rr)))
    ax[1].set_xticklabels(rr, fontsize=8, rotation=35, ha="right")
    ax[1].set_ylabel("normalised coherence drop", fontsize=9.5)
    ax[1].set_xlabel("distance from epicentre, km", fontsize=9.5)
    ax[1].set_title("b  No radial structure, all four tracks", fontsize=11,
                    weight="bold", loc="left")
    ax[1].grid(alpha=.25, axis="y"); ax[1].legend(fontsize=8.5)
    fig.tight_layout()
    return fig


def fig5(plt):
    from matplotlib.lines import Line2D
    from pyproj import Transformer
    fig, ax = plt.subplots(figsize=(13, 5.4))
    cols = {"asc": TEAL, "d61": PLUM, "d163": MOSS}
    names = {"asc": "ascending p112 f1148", "d61": "descending p61 f620",
             "d163": "descending p163 f620"}
    for k in ("d61", "asc", "d163"):
        g = read_band(k, "corr", step=12, water=True, drop_zero=True)
        if not g:
            continue
        v, ext, crs = g
        inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        ny, nx = v.shape
        xs = np.linspace(ext[0], ext[1], nx)
        ys = np.linspace(ext[3], ext[2], ny)
        X, Y = np.meshgrid(xs, ys)
        m = np.isfinite(v)
        lon, lat = inv.transform(X[m], Y[m])
        ax.scatter(lon, lat, s=0.6, color=cols[k], alpha=.20, linewidths=0,
                   label=names[k])

    d = json.load(open(REPORTS))
    rl, rt, lv = [], [], []
    for f in d["features"]:
        c = (f.get("geometry") or {}).get("coordinates")
        if c:
            rl.append(float(c[0])); rt.append(float(c[1]))
            x = f["properties"].get("damage_level")
            lv.append(x if isinstance(x, (int, float)) else -99)
    rl, rt, lv = np.array(rl), np.array(rt), np.array(lv)
    ax.scatter(rl, rt, s=5, color="#444", alpha=.55, linewidths=0,
               label=f"reports ({len(rl)})")
    sev = lv >= 3
    ax.scatter(rl[sev], rt[sev], s=40, facecolors="none", edgecolors="#111",
               linewidths=1.2, label=f"severe ({int(sev.sum())})")

    # Unlabelled star plus a small proxy for the legend. Labelling the ms=22
    # star and then applying markerscale rendered a 55-point star inside the
    # legend box, overflowing it.
    ax.plot(*EPI, "*", color=RUST, ms=22, mec="white", mew=1.3, zorder=6)
    epi_proxy = Line2D([], [], marker="*", color="none", markerfacecolor=RUST,
                       markeredgecolor="white", markersize=11)

    ax.axvline(120.55, color="#777", lw=1.2, ls="--")
    ax.text(120.5, -9.0, "west of here:\noutside frame 1148", fontsize=8,
            color="#555", ha="right")
    ax.set_xlabel("longitude", fontsize=9.5)
    ax.set_ylabel("latitude", fontsize=9.5)
    ax.set_title("Frame coverage and damage reports. No single frame spans "
                 "the island.", fontsize=11.5, weight="bold", loc="left")
    ax.set_xlim(118.9, 123.6); ax.set_ylim(-9.35, -7.75)
    ax.set_aspect("equal"); ax.grid(alpha=.22)
    h, l = ax.get_legend_handles_labels()
    lg = ax.legend(h + [epi_proxy], l + ["M7.7 epicentre"], fontsize=8,
                   loc="upper right", markerscale=2.0, framealpha=.95)
    for hh in lg.legend_handles:
        try:
            hh.set_alpha(1.0)
        except Exception:                                   # noqa: BLE001
            pass
    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=FIGDIR)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["text.color"] = INK
    plt.rcParams["axes.labelcolor"] = INK

    for name, fn in [("fig1_ascending_los", fig1), ("fig2_profiles", fig2),
                     ("fig3_descending", fig3), ("fig4_coherence", fig4),
                     ("fig5_coverage", fig5)]:
        try:
            f = fn(plt)
        except Exception as e:                              # noqa: BLE001
            print(f"  {name}: FAILED {e.__class__.__name__}: {e}")
            continue
        p = os.path.join(a.outdir, name + ".png")
        f.savefig(p, dpi=140, bbox_inches="tight", facecolor="white")
        plt.close(f)
        print(f"wrote {p}  ({os.path.getsize(p)/1e3:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
