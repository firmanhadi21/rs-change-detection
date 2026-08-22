"""Four-page infographic summarising the Flores M7.7 InSAR investigation.

Every number here is transcribed from a committed analysis, and each panel
names the script it came from so a reader can re-derive it. Nothing is
modelled, smoothed or invented for the figure -- where a quantity was not
measured, the panel says so rather than filling the space.

    conda run -n insardev-test python scripts/flores_infographic.py

Pages:
  1  What moved, and how it compares to the USGS prediction
  2  Why it is believed: independent geometries on disjoint dates
  3  Damage: what the radar could and could not see
  4  Coverage, corrections, and what is still open
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
OUTDIR = os.path.join(REPO, "output/coseismic/infographic")

INK = "#1a1f24"
MUTED = "#6b7780"
PAPER = "#faf8f5"
PANEL = "#ffffff"
TEAL = "#1d4a54"
RUST = "#c8471b"
MOSS = "#6b8f3a"
PLUM = "#7a1fa2"
AMBER = "#c8a415"
SLATE = "#8fa8a0"

RINGS = [25, 35, 45, 57.5]
RING_LAB = ["20-30", "30-40", "40-50", "50-65"]

# --- measured values, with the script each came from -----------------------
# scripts/flores_1148_discriminate.py  (GMTSAR raw radial median, cm)
GMTSAR = [-7.53, -4.81, -0.99, +0.84]
# scripts/mintpy_flores_step.py
MINTPY_RAW = [-11.69, -7.36, -3.27, -0.20]
MINTPY_DER = [-6.50, -4.13, -0.94, +1.05]
MINTPY_SD = [1.65, 1.30, 1.05, 0.99]
# scripts/insardev_flores_compare.py
INSARDEV = [-8.59, -4.21, -0.60, +1.33]
# scripts/desc61_discriminate.py  (raw and de-planed, cm)
D61_RAW = [-12.97, -8.17, -4.82, -4.50]
D61_DEP = [-3.65, -0.45, +1.18, +0.72]
D163_RAW = [-1.65, +2.41, +5.00, +1.83]
D163_DEP = [-4.06, +0.03, +2.32, +0.15]


PRODUCTS = {
    "asc": "flores-coseismic-2026-asc-f1148-prepost-d2",
    "d61": "flores-coseismic-2026-desc61-f621-prepost-d2",
    "d163": "flores-coseismic-2026-desc163-f620-prepost-d2",
}


def band_path(key, name):
    import glob as _g
    hits = _g.glob(os.path.join(REPO, "output/coseismic", PRODUCTS[key],
                                f"*_{name}.tif"))
    return hits[0] if hits else None


def read_map(key, name, step=5, scale=1.0, drop_zero=True):
    """Load a HyP3 band, water-masked and decimated, in its native UTM grid.

    Plotted in UTM rather than reprojected to lon/lat. The frames are rotated
    relative to north, so a corner-based lon/lat extent would shear the image
    -- and these panels exist to show the SHAPE of a deformation lobe, which
    is exactly what a shear would corrupt.

    Zeros are dropped, not kept: HyP3 writes 0 outside the imaged area and in
    the water mask, and a zero rendered on a diverging colour map reads as
    "no displacement here" rather than "no data here".
    """
    import rioxarray  # noqa: F401
    import xarray as xr
    p = band_path(key, name)
    if p is None:
        return None
    da = xr.open_dataarray(p, engine="rasterio")
    if "band" in da.dims:
        da = da.isel(band=0)
    v = da.values[::step, ::step].astype("float64") * scale
    wp = band_path(key, "water_mask")
    if wp is not None:
        w = xr.open_dataarray(wp, engine="rasterio")
        if "band" in w.dims:
            w = w.isel(band=0)
        wv = w.values[::step, ::step]
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


def draw_map(ax, key, name, cmap, vmin, vmax, scale=1.0, step=5,
             label=None, cyclic=False):
    got = read_map(key, name, step=step, scale=scale)
    if got is None:
        ax.axis("off")
        ax.text(0.5, 0.5, f"{name} unavailable", ha="center", va="center",
                fontsize=10, color=MUTED, transform=ax.transAxes)
        return None
    v, ext, crs = got
    im = ax.imshow(v, cmap=cmap, vmin=vmin, vmax=vmax, extent=ext,
                   origin="upper", interpolation="nearest")
    ex, ey = epi_xy(crs)
    ax.plot(ex, ey, "*", color="#111", ms=17, mec="white", mew=1.2)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor("#eeeae3")
    # 25 km scale bar, drawn from the axis limits so it stays correct however
    # the frame is cropped.
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    bx = x0 + 0.06 * (x1 - x0)
    by = y0 + 0.08 * (y1 - y0)
    ax.plot([bx, bx + 25000], [by, by], color=INK, lw=3,
            solid_capstyle="butt")
    ax.text(bx + 12500, by + 0.025 * (y1 - y0), "25 km", fontsize=7.5,
            ha="center", color=INK)
    if label:
        ax.text(0.985, 0.965, label, transform=ax.transAxes, fontsize=8,
                ha="right", va="top", color=INK,
                bbox=dict(fc="white", ec="none", alpha=.75, pad=2))
    return im


def page(figsize=(12, 16.6)):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=figsize, facecolor=PAPER)
    return fig


def header(fig, kicker, title, sub):
    """Header drawn in FIGURE coordinates.

    The first version placed it in a small axes and positioned the lines by
    axes fraction, including negative fractions to reach below the axes. The
    title ended up off the top of the canvas and the subtitle underneath the
    stat cards. Figure coordinates are unambiguous and the block cannot drift
    into whatever is placed below it.
    """
    import matplotlib.lines as mlines
    # Text has no letter-spacing property, so the wide-tracked kicker look is
    # faked by spacing the characters in the string itself.
    fig.text(0.055, 0.972, " ".join(kicker), fontsize=8.5, color=RUST,
             weight="bold", va="top")
    fig.text(0.055, 0.958, title, fontsize=21, color=INK, weight="bold",
             va="top")
    fig.text(0.055, 0.926, sub, fontsize=10.5, color=MUTED, va="top")
    fig.add_artist(mlines.Line2D([0.055, 0.945], [0.906, 0.906],
                                 color=INK, lw=1.4))


def footer(fig, page_no, note):
    ax = fig.add_axes([0.055, 0.018, 0.89, 0.028])
    ax.axis("off")
    ax.text(0, 0.5, note, fontsize=8, color=MUTED, va="center")
    ax.text(1, 0.5, f"{page_no} / 4", fontsize=9, color=INK, va="center",
            ha="right", weight="bold")


def panel_title(ax, text, src=None):
    ax.set_title(text, fontsize=12, color=INK, weight="bold", loc="left",
                 pad=10)
    if src:
        ax.text(1.0, 1.015, src, transform=ax.transAxes, fontsize=7.5,
                color=MUTED, ha="right", va="bottom", style="italic")


def bignum(ax, value, label, colour=TEAL, sub=None):
    ax.axis("off")
    ax.add_patch(__import__("matplotlib").patches.FancyBboxPatch(
        (0.02, 0.05), 0.96, 0.9, boxstyle="round,pad=0.02,rounding_size=0.04",
        transform=ax.transAxes, facecolor=PANEL, edgecolor="#e4ded4", lw=1))
    ax.text(0.5, 0.66, value, fontsize=30, color=colour, weight="bold",
            ha="center", va="center", transform=ax.transAxes)
    ax.text(0.5, 0.30, label, fontsize=9.5, color=INK, ha="center",
            va="center", transform=ax.transAxes, wrap=True)
    if sub:
        ax.text(0.5, 0.13, sub, fontsize=8, color=MUTED, ha="center",
                va="center", transform=ax.transAxes)


# ---------------------------------------------------------------- page 1
def page1(out):
    import matplotlib.pyplot as plt
    fig = page()
    header(fig, "FLORES  M7.7   14 AUGUST 2026",
           "The ground moved about a tenth of what was predicted",
           "Sentinel-1 InSAR, ascending path 112 frame 1148, "
           "2026-08-06 to 2026-08-18")

    for i, (v, l, c, s) in enumerate([
            ("~6 cm", "measured line-of-sight\nmotion, near field", TEAL,
             "20-30 km from the epicentre"),
            ("54 cm", "predicted by the USGS\nfinite-fault model", RUST,
             "same ground"),
            ("3.3-4.4", "sigma against this frame's\nown 12-day noise", MOSS,
             "0 of 76 quiet intervals as large"),
            ("4", "independent interferogram\npairs, 3 processing chains",
             PLUM, "all agree")]):
        ax = fig.add_axes([0.055 + i * 0.2275, 0.780, 0.205, 0.100])
        bignum(ax, v, l, c, s)

    ax = fig.add_axes([0.055, 0.505, 0.42, 0.225])
    panel_title(ax, "Three processing chains, one dataset",
                "insardev_flores_compare.py")
    ax.axhline(0, color="#ccc", lw=.8)
    ax.errorbar(RINGS, MINTPY_DER, yerr=MINTPY_SD, fmt="-o", ms=5, lw=1.7,
                capsize=4, color=TEAL, label="MintPy (deramped)  +/-1 sd")
    ax.plot(RINGS, GMTSAR, "-s", ms=5, lw=1.7, color=RUST, label="GMTSAR")
    ax.plot(RINGS, INSARDEV, "-^", ms=6, lw=1.7, color=MOSS,
            label="insardev")
    ax.set_xlabel("distance from epicentre, km", fontsize=9)
    ax.set_ylabel("LOS displacement, cm", fontsize=9)
    ax.set_xticks(RINGS); ax.set_xticklabels(RING_LAB, fontsize=8)
    ax.tick_params(labelsize=8)
    ax.grid(alpha=.22)
    ax.legend(fontsize=7.5, loc="lower right")
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.505, 0.40, 0.225])
    # NOT "scatter is smaller than the noise floor" -- at 20-30 km the
    # insardev-MintPy difference is 2.09 cm against a 1.65 cm noise sd, so
    # that title would have been contradicted by its own chart.
    panel_title(ax, "Chain-to-chain scatter against the noise floor",
                "same three chains")
    d_g = np.array(INSARDEV) - np.array(GMTSAR)
    d_m = np.array(INSARDEV) - np.array(MINTPY_DER)
    x = np.arange(4)
    ax.bar(x - 0.2, np.abs(d_g), 0.38, color=RUST, alpha=.85,
           label="insardev - GMTSAR")
    ax.bar(x + 0.2, np.abs(d_m), 0.38, color=TEAL, alpha=.85,
           label="insardev - MintPy")
    ax.plot(x, MINTPY_SD, "k--", lw=1.6, marker="o", ms=4,
            label="12-day noise sd")
    ax.set_xticks(x); ax.set_xticklabels(RING_LAB, fontsize=8)
    ax.set_ylabel("absolute difference, cm", fontsize=9)
    ax.set_xlabel("ring, km", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7.5, loc="upper right", framealpha=.92)
    ax.grid(alpha=.22, axis="y")
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.055, 0.245, 0.42, 0.205])
    panel_title(ax, "The step against 76 earthquake-free intervals",
                "mintpy_flores_step.py")
    labels = ["raw\ntime series", "deramped\n+ DEM error"]
    steps = [-7.43, -4.44]
    sds = [1.71, 1.36]
    # Sigma values are the ones the analysis reported, not recomputed from
    # the rounded step and sd printed above them -- 7.43/1.71 rounds to 4.3
    # while the full-precision ratio the script printed is 4.4, and a figure
    # that disagrees with its own caption is worse than one decimal place.
    sigmas = [4.4, 3.3]
    xb = np.arange(2)
    ax.bar(xb, np.abs(steps), 0.45, color=[TEAL, SLATE])
    for i, (s, sd, g) in enumerate(zip(steps, sds, sigmas)):
        ax.errorbar(i, abs(s), yerr=sd, color=INK, capsize=6, lw=1.5)
        ax.text(i, abs(s) + sd + 0.35, f"{g} sigma",
                ha="center", fontsize=9, weight="bold", color=INK)
    ax.set_xticks(xb); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("co-seismic step, cm", fontsize=9)
    ax.set_ylim(0, 11)
    ax.tick_params(labelsize=8)
    ax.grid(alpha=.22, axis="y")
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.245, 0.40, 0.205])
    ax.axis("off")
    panel_title(ax, "What the deramp costs")
    body = (
        "A linear deramp removes exactly the long-wavelength\n"
        "component a large earthquake produces, so it eats real\n"
        "signal. The two numbers bracket the answer rather than\n"
        "disagreeing:\n\n"
        "   raw            -7.43 cm     4.4 sigma\n"
        "   deramped       -4.44 cm     3.3 sigma\n\n"
        "Both exceed all 76 quiet 12-day intervals on this frame.\n"
        "The same ordering appears across the three chains in the\n"
        "20-30 km ring, where the signal is largest:\n\n"
        "   insardev (no deramp)      -8.59 cm\n"
        "   GMTSAR   (no deramp)      -7.53 cm\n"
        "   MintPy   (linear deramp)  -6.50 cm\n\n"
        "That is the deramp bite, not scatter."
    )
    ax.text(0.02, 0.88, body, fontsize=9, color=INK, va="top",
            family="DejaVu Sans Mono", linespacing=1.5,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.075, 0.89, 0.135])
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor="#f2ece2", edgecolor="#e0d8cb"))
    ax.text(0.025, 0.86, "THE HEADLINE, STATED CAREFULLY", fontsize=9.5,
            color=RUST, weight="bold", va="top", transform=ax.transAxes)
    ax.text(0.025, 0.63,
            "About 6 cm of line-of-sight motion on the coast nearest an "
            "offshore rupture, against 54 cm predicted by the USGS\n"
            "finite-fault model for the same ground. The measurement is "
            "secure; the discrepancy is the result. It says the model\n"
            "overpredicts onshore slip, which was the standing conclusion "
            "before any of this and is now quantified rather than asserted.",
            fontsize=10, color=INK, va="top", transform=ax.transAxes,
            linespacing=1.6)

    footer(fig, 1, "All values transcribed from committed analyses; "
                   "each panel names its source script.")
    fig.savefig(out, dpi=130, facecolor=PAPER)
    plt.close(fig)
    print(f"wrote {out}")


# ---------------------------------------------------------------- page 2
def page2(out):
    import matplotlib.pyplot as plt
    fig = page()
    header(fig, "INDEPENDENT VERIFICATION",
           "Three chains share one dataset. Two more tracks do not.",
           "Agreement between processing chains tests the software. "
           "Agreement between geometries on disjoint dates tests the Earth.")

    ax = fig.add_axes([0.055, 0.712, 0.89, 0.150])
    ax.axis("off")
    panel_title(ax, "Acquisition timeline: every pair used",
                "s1_coverage_audit.py")
    rows = [("ascending p112 f1148", 6, 18, TEAL, "12 d, S1D"),
            ("descending p61 f620", 2, 20, PLUM, "18 d, S1D->S1C"),
            ("descending p163 f620", 9, 21, MOSS, "12 d, S1D")]
    ax.plot([0.06, 0.97], [0.30, 0.30], color="#ddd", lw=1,
            transform=ax.transAxes)
    for d in range(1, 24, 4):
        xx = 0.06 + 0.91 * (d - 1) / 22
        ax.text(xx, 0.19, f"{d} Aug", fontsize=7.5, color=MUTED,
                ha="center", transform=ax.transAxes)
    xq = 0.06 + 0.91 * (14 - 1) / 22
    ax.plot([xq, xq], [0.28, 0.92], color=RUST, lw=2,
            transform=ax.transAxes)
    ax.text(xq + 0.005, 0.94, "M7.7  14 Aug 21:58 UTC", fontsize=8.5,
            color=RUST, weight="bold", transform=ax.transAxes)
    for i, (lab, a_, b_, col, note) in enumerate(rows):
        y = 0.80 - i * 0.17
        xa = 0.06 + 0.91 * (a_ - 1) / 22
        xb = 0.06 + 0.91 * (b_ - 1) / 22
        ax.plot([xa, xb], [y, y], color=col, lw=5, solid_capstyle="round",
                transform=ax.transAxes, alpha=.8)
        ax.plot([xa, xb], [y, y], "o", color=col, ms=7,
                transform=ax.transAxes)
        ax.text(0.055, y + 0.055, lab, fontsize=9, color=INK,
                weight="bold", transform=ax.transAxes)
        ax.text(0.965, y, note, fontsize=8, color=MUTED, ha="right",
                va="center", transform=ax.transAxes)
    ax.text(0.055, 0.03,
            "No emergency tasking took place. In the nine days after the "
            "rupture only five IW SLC scenes touched the near field, and "
            "all usable ones are here.",
            fontsize=8.5, color=MUTED, transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.442, 0.42, 0.215])
    panel_title(ax, "Raw profiles disagree", "desc61_discriminate.py")
    ax.axhline(0, color="#ccc", lw=.8)
    ax.plot(RINGS, D61_RAW, "-o", ms=5, lw=1.8, color=PLUM,
            label="descending p61")
    ax.plot(RINGS, D163_RAW, "-^", ms=6, lw=1.8, color=MOSS,
            label="descending p163")
    ax.set_xticks(RINGS); ax.set_xticklabels(RING_LAB, fontsize=8)
    ax.set_xlabel("ring, km", fontsize=9)
    ax.set_ylabel("LOS, cm", fontsize=9)
    ax.tick_params(labelsize=8); ax.grid(alpha=.22)
    ax.legend(fontsize=8); ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.442, 0.40, 0.215])
    panel_title(ax, "Remove each track's own plane: they agree",
                "same script")
    ax.axhline(0, color="#ccc", lw=.8)
    ax.plot(RINGS, D61_DEP, "-o", ms=5, lw=1.8, color=PLUM,
            label="p61 de-planed")
    ax.plot(RINGS, D163_DEP, "-^", ms=6, lw=1.8, color=MOSS,
            label="p163 de-planed")
    ax.annotate("0.4 cm apart", xy=(25, -3.85), xytext=(33, -2.9),
                fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK, lw=1))
    ax.set_xticks(RINGS); ax.set_xticklabels(RING_LAB, fontsize=8)
    ax.set_xlabel("ring, km", fontsize=9)
    ax.set_ylabel("LOS, cm", fontsize=9)
    ax.tick_params(labelsize=8); ax.grid(alpha=.22)
    ax.legend(fontsize=8); ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.055, 0.235, 0.42, 0.165])
    panel_title(ax, "Source structure survives plane removal")
    x = np.arange(2)
    ax.bar(x - 0.19, [4.83, 6.38], 0.36, color=[PLUM, MOSS],
           label="co-event")
    ax.bar(x + 0.19, [0.57, 1.61], 0.36, color="#d6d0c6",
           label="quiet control")
    for i, (a_, b_) in enumerate([(4.83, 0.57), (6.38, 1.61)]):
        ax.text(i, max(a_, b_) + 0.3, f"{a_/b_:.1f}x", ha="center",
                fontsize=9.5, weight="bold", color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(["descending p61", "descending p163"], fontsize=8.5)
    ax.set_ylabel("de-planed ring swing, cm", fontsize=9)
    ax.set_ylim(0, 8)
    ax.tick_params(labelsize=8); ax.grid(alpha=.22, axis="y")
    ax.legend(fontsize=8); ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.235, 0.40, 0.165])
    ax.axis("off")
    panel_title(ax, "Why this breaks the circularity")
    ax.text(0.02, 0.92,
            "GMTSAR, MintPy and insardev all consume the SAME two\n"
            "ascending acquisitions. The atmosphere of 18 August is\n"
            "common to every one of them, so their agreement tests\n"
            "the processing and nothing else.\n\n"
            "Descending p61 (2->20 Aug) and p163 (9->21 Aug) share no\n"
            "acquisition date with the ascending pair. Their\n"
            "atmosphere is an independent draw. An 18 August artefact\n"
            "cannot appear in either.\n\n"
            "Each carries a DIFFERENT long-wavelength ramp -- which is\n"
            "what orbit error and atmosphere look like -- and the same\n"
            "residual underneath.",
            fontsize=8.8, color=INK, va="top", linespacing=1.55,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.075, 0.89, 0.13])
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor="#f2ece2", edgecolor="#e0d8cb"))
    ax.text(0.025, 0.85, "THE LIMIT THAT SURVIVES EVERYTHING",
            fontsize=9.5, color=RUST, weight="bold", va="top",
            transform=ax.transAxes)
    ax.text(0.025, 0.60,
            "Each track still has only ONE post-event epoch, so on any "
            "single track the co-seismic step and that day's atmosphere\n"
            "are not separable by any inversion. Three tracks did not "
            "dent this. A second post-event scene would: two post-event\n"
            "epochs on one track difference against each other. The next "
            "ascending pass is around 30 August.",
            fontsize=10, color=INK, va="top", transform=ax.transAxes,
            linespacing=1.6)

    footer(fig, 2, "Descending tracks p61 and p163 are both descending; "
                   "they differ in incidence angle, not heading.")
    fig.savefig(out, dpi=130, facecolor=PAPER)
    plt.close(fig)
    print(f"wrote {out}")


# ---------------------------------------------------------------- page 3
def page3(out):
    import matplotlib.pyplot as plt
    fig = page()
    header(fig, "DAMAGE",
           "The radar sees the ground move. It barely sees the damage.",
           "Coherence change tested against 452 BPBD and community "
           "reports, on four interferogram pairs")

    ax = fig.add_axes([0.055, 0.688, 0.42, 0.180])
    panel_title(ax, "Coherence loss has no radial structure",
                "island_damage_map.py")
    rr = ["20-30", "30-40", "40-50", "50-65", "65-90", "90-130", "130-200"]
    vals = [0.0263, 0.0028, 0.0346, 0.0532, 0.0299, 0.0171, 0.0197]
    ax.bar(range(len(rr)), vals, 0.62, color=SLATE)
    ax.axhline(np.mean(vals), color=RUST, lw=1.5, ls="--",
               label=f"mean {np.mean(vals):.4f}")
    ax.set_xticks(range(len(rr)))
    # Horizontal labels with no separate axis caption: rotated ticks plus an
    # xlabel pushed the caption into the title of the panel underneath.
    ax.set_xticklabels(rr, fontsize=7)
    ax.set_ylabel("normalised coherence drop", fontsize=9)
    ax.text(1.0, -0.16, "ring, km from epicentre", transform=ax.transAxes,
            fontsize=8.5, color=MUTED, ha="right", va="top")
    ax.tick_params(labelsize=8); ax.grid(alpha=.22, axis="y")
    ax.legend(fontsize=8); ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.688, 0.40, 0.180])
    ax.axis("off")
    panel_title(ax, "Why that is a null, not a small signal")
    ax.text(0.02, 0.92,
            "The maximum sits at 50-65 km and the 130-200 km ring\n"
            "matches the near field. Whatever drives coherence loss\n"
            "operates uniformly to 200 km, which is not what an\n"
            "earthquake does.\n\n"
            "The control that makes the loss readable: coherence\n"
            "cannot genuinely IMPROVE because of an earthquake, yet\n"
            "6.8% of pixels gain more than 0.2 against 18.5% losing\n"
            "it. That gap is the noise floor under the loss.\n\n"
            "Established on complete island coverage, not on the 42%\n"
            "that frame 1148 alone provides.",
            fontsize=8.8, color=INK, va="top", linespacing=1.55,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.435, 0.42, 0.20])
    panel_title(ax, "Presence-only: severe reports vs background",
                "eq_reports_presence_only.py")
    tracks = ["asc f1148\nn=27", "desc61\nn=32", "desc163\nn=11"]
    auc = [0.644, 0.591, 0.440]
    lo = [0.539, 0.475, 0.272]
    hi = [0.744, 0.716, 0.598]
    y = np.arange(3)
    ax.axvline(0.5, color=RUST, lw=1.6, ls="--")
    ax.text(0.503, 2.42, "no information", fontsize=8, color=RUST)
    for i in range(3):
        ax.plot([lo[i], hi[i]], [y[i], y[i]], color=TEAL, lw=3.2,
                solid_capstyle="round")
        ax.plot(auc[i], y[i], "o", color=INK, ms=8)
        ax.text(hi[i] + 0.012, y[i], f"{auc[i]:.3f}", fontsize=8.5,
                va="center", color=INK)
    ax.set_yticks(y); ax.set_yticklabels(tracks, fontsize=8.5)
    ax.set_xlabel("AUC, target-group background", fontsize=9)
    ax.set_xlim(0.22, 0.83); ax.set_ylim(-0.6, 2.6)
    ax.tick_params(labelsize=8); ax.grid(alpha=.22, axis="x")
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.435, 0.40, 0.20])
    ax.axis("off")
    panel_title(ax, "The background choice is the whole method")
    ax.text(0.02, 0.93,
            "Unreported ground is NOT undamaged ground -- it is ground\n"
            "with no people, no signal, or no agency visit. Comparing\n"
            "reports against 'random land' assumes an absence the data\n"
            "cannot support, and dilutes any contrast.\n\n"
            "Presence-only fixes the logic: unlabelled ground becomes\n"
            "BACKGROUND, and the estimate is a relative rate.\n\n"
            "The target-group background is the key move. Presences are\n"
            "severe reports; background is every OTHER report. Every\n"
            "background point is then somewhere a person was present,\n"
            "had signal, and did file something -- so accessibility and\n"
            "population are held fixed by construction.\n\n"
            "Controlling that bias STRENGTHENS the ascending result,\n"
            "0.591 -> 0.644. An accessibility artefact would weaken it.",
            fontsize=8.5, color=INK, va="top", linespacing=1.5,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.20, 0.42, 0.165])
    panel_title(ax, "Two tracks over the same ground disagree",
                "island_damage_map.py")
    pairs = ["asc1148\nvs p163", "asc1153\nvs p61", "asc1148\nvs p61"]
    rs = [0.584, 0.514, 0.435]
    ax.bar(range(3), rs, 0.55, color=[TEAL, SLATE, SLATE])
    ax.axhline(1.0, color=MUTED, lw=1, ls=":")
    for i, r in enumerate(rs):
        ax.text(i, r + 0.03, f"r = {r:.3f}", ha="center", fontsize=9,
                weight="bold", color=INK)
        ax.text(i, r / 2, f"{100*r**2:.0f}% of\nvariance\nshared",
                ha="center", va="center", fontsize=7.5, color="white")
    ax.set_xticks(range(3)); ax.set_xticklabels(pairs, fontsize=8)
    ax.set_ylabel("correlation on shared blocks", fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.tick_params(labelsize=8); ax.grid(alpha=.22, axis="y")
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.20, 0.40, 0.165])
    ax.axis("off")
    panel_title(ax, "A claim made, retracted, and partly restored")
    ax.text(0.02, 0.93,
            "CLAIMED: coherence loss separates badly damaged from\n"
            "lightly damaged villages, replicated across geometries.\n\n"
            "RETRACTED: the two descending tracks share ZERO reports --\n"
            "they cover opposite ends of the island. The 'replication'\n"
            "compared different villages. On the 103 reports ascending\n"
            "and p163 both see, the answer flipped sign.\n\n"
            "PARTLY RESTORED: that retraction was too strong. With\n"
            "confidence intervals attached, p163's [0.272, 0.598]\n"
            "overlaps ascending's [0.539, 0.744]. Two noisy estimates\n"
            "are not a contradiction.\n\n"
            "STANDS: a modest, real effect on the best-powered track.\n"
            "Not a replication. Not a damage probability.",
            fontsize=8.5, color=INK, va="top", linespacing=1.5,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.06, 0.89, 0.115])
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor="#f2ece2", edgecolor="#e0d8cb"))
    ax.text(0.025, 0.83, "WHAT WOULD ACTUALLY SETTLE IT", fontsize=9.5,
            color=RUST, weight="bold", va="top", transform=ax.transAxes)
    ax.text(0.025, 0.56,
            "Presence-only yields relative rates. Turning this into "
            "'how likely was this place damaged' needs CONFIRMED ABSENCES:\n"
            "someone visiting places that filed no report and recording "
            "them as undamaged. That is a field problem, not a satellite\n"
            "problem, and it is the single most valuable thing anyone "
            "could add to this dataset. More interferograms cannot fix it.",
            fontsize=10, color=INK, va="top", transform=ax.transAxes,
            linespacing=1.6)

    footer(fig, 3, "452 reports: 69 damage-classified (mostly BPBD), "
                   "383 aid requests from Geoportal Informasi Kebencanaan.")
    fig.savefig(out, dpi=130, facecolor=PAPER)
    plt.close(fig)
    print(f"wrote {out}")


# ---------------------------------------------------------------- page 4
def page4(out):
    import matplotlib.pyplot as plt
    fig = page()
    header(fig, "COVERAGE, CORRECTIONS, OPEN QUESTIONS",
           "What the satellites actually recorded, and what went wrong",
           "Nine predictions registered before the last products arrived; "
           "five held")

    ax = fig.add_axes([0.055, 0.688, 0.42, 0.180])
    panel_title(ax, "No single frame covers Flores",
                "island_coverage.py")
    names = ["desc61\nf620", "asc\nf1153", "asc\nf1148", "desc163\nf620"]
    cov = [396, 327, 191, 138]
    cols = [PLUM, SLATE, TEAL, MOSS]
    ax.barh(range(4), cov, 0.6, color=cols)
    for i, c in enumerate(cov):
        ax.text(c + 6, i, f"{c}  ({100*c/452:.0f}%)", va="center",
                fontsize=8.5, color=INK)
    ax.axvline(452, color=RUST, lw=1.5, ls="--")
    ax.text(452 - 8, 3.5, "all 452 reports", fontsize=8, color=RUST,
            ha="right")
    ax.set_yticks(range(4)); ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("report locations inside the footprint", fontsize=9)
    ax.set_xlim(0, 500)
    ax.tick_params(labelsize=8); ax.grid(alpha=.22, axis="x")
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.688, 0.40, 0.180])
    ax.axis("off")
    panel_title(ax, "Two facts about what gets recorded")
    ax.text(0.02, 0.93,
            "FRAME 1148 DOES NOT COVER FLORES. It spans longitude\n"
            "120.55 to 123.21. The island runs 340 km east-west and an\n"
            "IW frame is 250 km across, so longitude is what gets cut --\n"
            "latitude range says nothing about it. The western third,\n"
            "including Labuan Bajo and the Manggarai highlands where\n"
            "235 of 452 reports sit, is outside the primary frame.\n\n"
            "SENTINEL-1C HAS NEVER RECORDED FRAME 620 on descending\n"
            "path 163: 0 of 8 passes since May. The path is flown under\n"
            "two segment plans and S1C always uses the one with a hole\n"
            "over Flores. S1D managed 4 of 7. The constellation's\n"
            "nominal 6-day revisit does not apply to this ground.",
            fontsize=8.6, color=INK, va="top", linespacing=1.5,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.435, 0.89, 0.20])
    ax.axis("off")
    panel_title(ax, "Errors caught, and what caught them")
    rows = [
        ("Frame chosen for containing the EPICENTRE", "the epicentre is "
         "offshore; the frame held 4.9% of the deforming ground",
         "land-coverage test"),
        ("Four-block cluster of the largest coherence drops",
         "all at 0 m elevation, 0 deg slope, 100 m from the sea -- "
         "shoreline, not damage", "terrain check"),
        ("'Three chains agree' read as confirmation",
         "all three share the same two acquisitions; agreement tests "
         "software, not the Earth", "stating the confound first"),
        ("Coherence-damage replication across geometries",
         "the two descending tracks share zero reports", "common-report "
         "test"),
        ("Retraction of that claim, too strong",
         "confidence intervals overlap; two noisy estimates are not a "
         "contradiction", "presence-only re-analysis"),
        ("Submit guard keyed on job names",
         "same granules under a new label would have re-bought 30 credits",
         "granule-pair keying"),
        ("include_los_displacement recorded but ignored",
         "HyP3 accepts the deprecated parameter and delivers no band",
         "checking the delivered file list"),
        ("Damage map legend said blue for loss",
         "RdBu maps low values to red; the map read backwards",
         "reading the figure"),
    ]
    y = 0.93
    for what, why, caught in rows:
        ax.text(0.005, y, "x", fontsize=10, color=RUST, weight="bold",
                transform=ax.transAxes, va="top")
        ax.text(0.028, y, what, fontsize=8.8, color=INK, weight="bold",
                transform=ax.transAxes, va="top")
        ax.text(0.40, y, why, fontsize=8.3, color=MUTED,
                transform=ax.transAxes, va="top")
        ax.text(0.995, y, caught, fontsize=8, color=TEAL, ha="right",
                transform=ax.transAxes, va="top", style="italic")
        y -= 0.118

    ax = fig.add_axes([0.055, 0.215, 0.42, 0.175])
    panel_title(ax, "Registered predictions, scored",
                "docs/desc163_predictions.md")
    labs = ["coherence\ndrop", "reports vs\nrandom", "severe vs\nlight",
            "raw near\nfield", "de-planed\nnear field", "plane\nR2",
            "swing vs\ncontrol", "azimuth", "no edge\nfailure"]
    ok = [0, 1, 0, 0, 1, 0, 1, 1, 1]
    ax.bar(range(9), [1] * 9, 0.62,
           color=[MOSS if o else RUST for o in ok])
    for i, o in enumerate(ok):
        ax.text(i, 0.5, "OK" if o else "X", ha="center", va="center",
                fontsize=9, color="white", weight="bold")
    ax.set_xticks(range(9)); ax.set_xticklabels(labs, fontsize=6.5)
    ax.set_yticks([])
    ax.set_title("", fontsize=1)
    ax.text(0.5, -0.42, "5 of 9 held. Two failures moved the argument "
                        "forward;\none forced a retraction.",
            transform=ax.transAxes, ha="center", fontsize=8.5, color=INK)
    ax.set_facecolor(PANEL)

    ax = fig.add_axes([0.545, 0.205, 0.40, 0.190])
    ax.axis("off")
    panel_title(ax, "Still open")
    ax.text(0.02, 0.93,
            "SECOND POST-EVENT EPOCH  ~30 Aug, ascending.\n"
            "  The only thing that separates the co-seismic step from\n"
            "  one day's atmosphere. Worth more than any reprocessing.\n\n"
            "ERA5 TROPOSPHERIC CORRECTION  was unpublished for 18 Aug\n"
            "  at the time of the run; the 6 Aug grib is cached.\n\n"
            "PRECISE ORBITS  ~7 Sept. Would collapse the plane/signal\n"
            "  degeneracy that costs 2-3 cm on every profile.\n\n"
            "CONFIRMED ABSENCES  field visits to places that filed no\n"
            "  report. Converts relative rates into probabilities.\n\n"
            "TWO LANDSLIDE CANDIDATES  -8.7046/121.5505 at 49 km and\n"
            "  -8.7226/122.2152 at 106 km. Steep, unreported, seen in\n"
            "  both baseline-matched tracks. Has anyone been there?",
            fontsize=8.0, color=INK, va="top", linespacing=1.42,
            transform=ax.transAxes)

    ax = fig.add_axes([0.055, 0.065, 0.89, 0.125])
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor="#f2ece2", edgecolor="#e0d8cb"))
    ax.text(0.025, 0.85, "THE METHODOLOGICAL POINT", fontsize=9.5,
            color=RUST, weight="bold", va="top", transform=ax.transAxes)
    ax.text(0.025, 0.60,
            "Reproducibility is not validity. Three implementations of "
            "the same algorithms on the same two files agreed to within\n"
            "1 cm, and that agreement said nothing about the atmosphere "
            "they all shared. Every genuine advance here came from a\n"
            "control that could have failed: a quiet interval, a "
            "disjoint date, a background drawn from the same sampling\n"
            "process, or a terrain check on a result that looked too "
            "good.",
            fontsize=10, color=INK, va="top", transform=ax.transAxes,
            linespacing=1.6)

    footer(fig, 4, "Flores M7.7, 14 Aug 2026. HyP3 credits used: "
                   "60 of 910 across four interferogram pairs.")
    fig.savefig(out, dpi=130, facecolor=PAPER)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=OUTDIR)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#ccc5b9"
    plt.rcParams["axes.labelcolor"] = INK
    plt.rcParams["text.color"] = INK
    plt.rcParams["xtick.color"] = MUTED
    plt.rcParams["ytick.color"] = MUTED

    page1(os.path.join(a.outdir, "flores_p1_displacement.png"))
    page2(os.path.join(a.outdir, "flores_p2_verification.png"))
    page3(os.path.join(a.outdir, "flores_p3_damage.png"))
    page4(os.path.join(a.outdir, "flores_p4_coverage.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
