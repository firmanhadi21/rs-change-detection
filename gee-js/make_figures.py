"""Generate the Day 1 fundamentals figures as SVG.

Three diagrams, each carrying one idea the slides otherwise only assert:

  em-spectrum         where visible light sits in the whole spectrum, and
                      where the satellite's bands sit relative to it. The
                      point is proportion: the slice our eyes read is a sliver.

  interaction         what happens when radiation meets a surface -- reflect,
                      absorb, transmit -- and that the SPLIT is what differs
                      between materials, not the physics.

  spectral-signatures reflectance against wavelength for the four surfaces the
                      workshop will classify. This is the figure that makes
                      false colour obvious rather than magical: the curves
                      separate hardest in the near infrared, exactly where the
                      eye stops.

SVG rather than PNG: vector, legible when projected at any size, small, and
diffable. Generated from a script rather than drawn by hand so the numbers are
reproducible and the styling stays consistent with the deck.

Reflectance values are typical published figures for healthy vegetation,
clear water, dry bare soil and concrete. They are illustrative -- real spectra
vary with moisture, species and viewing geometry -- and the slides say so.

    python3 gee-js/make_figures.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

FMT = os.environ.get("FIG_FORMAT", "svg")   # PNG is for previewing only
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
os.makedirs(OUT, exist_ok=True)

INK = "#12241d"
MUTED = "#5d7069"
GREEN = "#0f3d2e"
ACCENT = "#b4531a"
FACE = "#f7f9fb"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.edgecolor": MUTED,
    "svg.fonttype": "none",     # keep text as text, so it stays crisp
})


# --------------------------------------------------------------- 1. spectrum
def em_spectrum():
    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(11, 4.6), height_ratios=[1.5, 1],
        gridspec_kw=dict(hspace=.72))
    fig.patch.set_facecolor(FACE)

    bands = [
        (1e-6, 1e-3, "gamma"), (1e-3, 10, "X-ray"), (10, 400, "ultraviolet"),
        (400, 700, "visible"), (700, 1e6, "infrared"),
        (1e6, 1e9, "microwave"), (1e9, 1e12, "radio"),
    ]
    for lo, hi, name in bands:
        vis = name == "visible"
        ax.add_patch(Rectangle(
            (np.log10(lo), 0), np.log10(hi) - np.log10(lo), 1,
            facecolor="#ffffff" if not vis else "#ffd166",
            edgecolor=MUTED, lw=.8, zorder=2))
        if vis:
            # The visible box is ~0.24 decades wide; a label will not fit in
            # it and overlapped "ultraviolet" when centred. Point at it.
            # Sits left of centre: the x-axis label is centred, and at
            # y = -0.6 a centred callout lands straight on top of it.
            ax.annotate("visible\n400–700 nm", xy=(np.log10(430), .5),
                        xytext=(np.log10(2e-2), -0.75),
                        arrowprops=dict(arrowstyle="->", color=INK, lw=1.3,
                                        connectionstyle="arc3,rad=-.15"),
                        fontsize=10.5, fontweight="bold", color=INK,
                        ha="center", va="center", zorder=5)
        else:
            ax.text((np.log10(lo) + np.log10(hi)) / 2, .5, name,
                    ha="center", va="center", fontsize=9.5, color=MUTED,
                    zorder=3)

    # Where the instruments measure. Individual per-band labels collided into
    # unreadable overlap at this scale -- six Sentinel-2 bands span barely half
    # a decade. One bracket per instrument instead.
    for lo, hi, label, col, y in ((490, 2190, "Sentinel-2 · 13 bands", ACCENT,
                                   1.30),
                                  (55e6, 55e6, "Sentinel-1 · radar",
                                   "#2a6f97", 1.30)):
        x0, x1 = np.log10(lo), np.log10(hi)
        if x1 > x0:
            ax.plot([x0, x1], [y, y], color=col, lw=2.4, zorder=4,
                    solid_capstyle="butt")
            for xx in (x0, x1):
                ax.plot([xx, xx], [y - .09, y + .09], color=col, lw=2.4,
                        zorder=4)
        else:
            ax.plot([x0, x0], [y - .12, y + .12], color=col, lw=2.4, zorder=4)
        ax.text((x0 + x1) / 2, y + .17, label, ha="center", va="bottom",
                fontsize=9.5, color=col, fontweight="bold", zorder=5)

    ax.set_xlim(np.log10(1e-6), np.log10(1e12))
    ax.set_ylim(0, 2.0)
    ax.set_yticks([])
    ticks = [1e-3, 1, 1e3, 1e6, 1e9, 1e12]
    ax.set_xticks([np.log10(t) for t in ticks])
    ax.set_xticklabels(["1 pm", "1 nm", "1 µm", "1 mm", "1 m", "1 km"])
    ax.set_xlabel("wavelength (log scale)")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title("The whole spectrum — our eyes read one narrow slice",
                 fontsize=12.5, fontweight="bold", loc="left", pad=12)

    # The visible band, expanded.
    grad = np.linspace(400, 700, 512).reshape(1, -1)
    axv.imshow(grad, aspect="auto", extent=[400, 700, 0, 1],
               cmap="turbo", origin="lower")
    axv.set_xlim(380, 2300)
    axv.set_ylim(0, 1)
    axv.set_yticks([])
    # 700 sat 35 nm from 665 and the two tick labels collided; the visible
    # edge is already shown by where the gradient stops.
    axv.set_xticks([400, 490, 560, 665, 842, 1610, 2190])
    axv.set_xticklabels(["400", "490", "560", "665", "842", "1610", "2190"],
                        fontsize=9)
    axv.set_xlabel("wavelength (nm) — linear")
    axv.axvspan(700, 2300, color="#e9edf0", zorder=0)
    axv.text(1500, .62, "invisible to us — but not to the satellite",
             ha="center", va="center", fontsize=10, color=MUTED, style="italic")
    # Band names go ABOVE the line, staggered, so they never meet the ticks.
    for wl, nm, dy in ((490, "blue", .82), (560, "green", .38),
                       (665, "red", .82), (842, "NIR", .18),
                       (1610, "SWIR", .18), (2190, "SWIR", .18)):
        axv.plot([wl, wl], [0, 1], color=INK, lw=1.0, alpha=.55)
        axv.text(wl, dy, nm, ha="center", va="center", fontsize=8.5,
                 color=INK,
                 bbox=dict(fc=FACE, ec="none", pad=1.2))
    for s in ("top", "right", "left"):
        axv.spines[s].set_visible(False)

    fig.savefig(f"{OUT}/em-spectrum.{FMT}", bbox_inches="tight",
                facecolor=FACE)
    plt.close(fig)
    print(f"wrote em-spectrum.{FMT}")


# ------------------------------------------------------------ 2. interaction
def interaction():
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.7))
    fig.patch.set_facecolor(FACE)

    # Fractions at 842 nm, and they must sum to 100.
    #
    # The leaf numbers matter and were wrong in the first draft: a healthy
    # leaf REFLECTS about half the near infrared and TRANSMITS almost as much,
    # absorbing only a few percent. Absorption is what happens in the RED,
    # where chlorophyll works. Swapping absorb and transmit destroys the point
    # of the panel -- that a leaf is nearly transparent to light we cannot see.
    #
    # Water at 842 nm absorbs almost everything within centimetres, so its
    # transmittance out the far side is effectively nil at this wavelength.
    cases = [
        ("Leaf", "#2e7d32", 0.50, 0.05, 0.45,
         "reflects half the NIR\nand passes most of the rest"),
        ("Water", "#1565a8", 0.03, 0.97, 0.00,
         "absorbs NIR almost entirely\n— which is why water is black"),
        ("Bare soil", "#a5733d", 0.30, 0.70, 0.00,
         "reflects moderately,\nno transmission"),
    ]
    for ax, (name, col, refl, absorb, trans, note) in zip(axes, cases):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 11.6)
        ax.axis("off")

        ax.text(5, 11.2, note, ha="center", va="top", fontsize=9.5,
                color=MUTED)

        ax.add_patch(Rectangle((0.5, 1.6), 9, 2.0, facecolor=col,
                               edgecolor="none", alpha=.9))
        ax.text(2.6, 2.6, name, ha="center", va="center", color="white",
                fontweight="bold", fontsize=11)

        # incoming, striking the surface at x=4.6
        ax.add_patch(FancyArrowPatch((1.3, 8.4), (4.5, 3.8),
                                     arrowstyle="-|>", mutation_scale=14,
                                     lw=2.4, color="#e0a800"))
        ax.text(1.1, 8.7, "incoming", fontsize=9, color="#8a6d00",
                ha="left", va="bottom")

        # reflected: line width carries the fraction, so the picture reads
        # before the numbers do
        ax.add_patch(FancyArrowPatch((4.9, 3.8), (8.2, 8.4),
                                     arrowstyle="-|>", mutation_scale=14,
                                     lw=0.8 + 5 * refl, color="#e0a800"))
        ax.text(8.4, 8.7, f"reflect {refl*100:.0f}%", fontsize=9.5,
                color="#8a6d00", ha="right", va="bottom", fontweight="bold")

        # absorbed: down the right of the block, clear of the name
        ax.add_patch(FancyArrowPatch((7.4, 3.5), (7.4, 2.1),
                                     arrowstyle="-|>", mutation_scale=11,
                                     lw=0.8 + 5 * absorb, color="#8c1d1d"))
        ax.text(8.0, 2.8, f"absorb\n{absorb*100:.0f}%", fontsize=9,
                color="#8c1d1d", ha="left", va="center")

        if trans > 0:
            ax.add_patch(FancyArrowPatch((7.4, 1.6), (7.4, 0.35),
                                         arrowstyle="-|>", mutation_scale=11,
                                         lw=0.8 + 5 * trans, color="#2a6f97"))
            ax.text(8.0, 0.8, f"transmit\n{trans*100:.0f}%", fontsize=9,
                    color="#2a6f97", ha="left", va="center")


    fig.suptitle("Same physics, different split — and the split is the "
                 "measurement  (near infrared, 842 nm)",
                 fontsize=12.5, fontweight="bold", x=.02, ha="left", y=1.02)
    fig.savefig(f"{OUT}/interaction.{FMT}", bbox_inches="tight", facecolor=FACE)
    plt.close(fig)
    print(f"wrote interaction.{FMT}")


# ------------------------------------------------------ 3. spectral curves
def signatures():
    wl = np.array([440, 490, 560, 665, 705, 740, 842, 1610, 2190])
    curves = {
        "Vegetation": ([3, 4, 10, 4, 12, 35, 50, 25, 12], "#2e7d32"),
        "Water":      ([7, 6, 5, 3, 2, 1.5, 1, 0.5, 0.3], "#1565a8"),
        "Bare soil":  ([9, 12, 17, 22, 25, 28, 31, 38, 32], "#a5733d"),
        "Concrete":   ([18, 20, 23, 25, 26, 27, 28, 30, 27], "#7a7a7a"),
    }
    fig, ax = plt.subplots(figsize=(11, 4.8))
    fig.patch.set_facecolor(FACE)

    fine = np.linspace(440, 2190, 400)
    for name, (vals, col) in curves.items():
        smooth = np.interp(fine, wl, vals)
        ax.plot(fine, smooth, color=col, lw=2.6, label=name, zorder=3)
        ax.plot(wl, vals, "o", color=col, ms=4.5, zorder=4)

    ax.axvspan(400, 700, color="#ffd166", alpha=.35, zorder=0)
    ax.text(550, 56, "visible", ha="center", fontsize=10, color="#8a6d00",
            fontweight="bold")
    ax.axvspan(700, 2300, color="#e9edf0", alpha=.85, zorder=0)
    ax.text(1400, 56, "invisible to us", ha="center", fontsize=10,
            color=MUTED, style="italic")

    ax.annotate("the gap that makes\nvegetation measurable",
                xy=(842, 50), xytext=(1050, 46),
                arrowprops=dict(arrowstyle="->", color=ACCENT, lw=1.6),
                fontsize=10, color=ACCENT, fontweight="bold")
    ax.plot([842, 842], [4, 50], color=ACCENT, lw=1.2, ls=":", zorder=2)

    ax.set_xlim(430, 2260)
    ax.set_ylim(0, 60)
    ax.set_xlabel("wavelength (nm)")
    ax.set_ylabel("reflectance (%)")
    ax.set_title("Why bands beat colours — the curves separate where the eye "
                 "cannot look", fontsize=12.5, fontweight="bold", loc="left",
                 pad=12)
    ax.legend(frameon=False, loc="center right", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#dfe5e9", lw=.7, zorder=1)

    fig.savefig(f"{OUT}/spectral-signatures.{FMT}", bbox_inches="tight",
                facecolor=FACE)
    plt.close(fig)
    print(f"wrote spectral-signatures.{FMT}")


if __name__ == "__main__":
    em_spectrum()
    interaction()
    signatures()
    print(f"\nin {OUT}")
