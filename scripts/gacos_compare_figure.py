"""See what GACOS actually did to an interferogram, panel by panel.

The summary statistic (median -0.1%, worse on 51%) says the correction is a
coin flip over Flores, but it does not show WHY. This draws, for a chosen pair:

    original phase | GACOS delay removed | corrected phase

Read left to right: if the delay field in the middle resembles the structure in
the left panel, the correction is removing something real and the right panel
is cleaner. If it looks unrelated -- a smooth ramp where the phase has none, or
topography-shaped where the phase is not -- then GACOS is subtracting a field
the weather model invented, and the right panel is worse.

Defaults to the two extreme cases from GACOS_info.txt, which is the honest way
to look: the pair GACOS helped most, and the one it hurt most.

    python3 scripts/gacos_compare_figure.py
    python3 scripts/gacos_compare_figure.py --pair 20250524_20250605
"""

import argparse
import os
import sys

import numpy as np

BASE = os.path.expanduser("~/GitHub/rs-change-detection/output/licsbas")
RAW = f"{BASE}/GEOCml4"
COR = f"{BASE}/GEOCml4GACOS"

# From GACOS_info.txt: the largest improvement and the largest degradation.
DEFAULT_PAIRS = [
    ("20250723_20250804", "best  +33.5%"),
    ("20250524_20250605", "worst -103.7%"),
]


def dims():
    par = {}
    for line in open(f"{RAW}/EQA.dem_par", errors="ignore"):
        if ":" in line:
            k, _, v = line.partition(":")
            par[k.strip()] = v.split()[0]
    return int(par["width"]), int(par["nlines"])


def read_unw(path, w, h):
    if not os.path.exists(path):
        return None
    a = np.fromfile(path, dtype=np.float32)
    if a.size != w * h:
        return None
    a = a.reshape(h, w)
    return np.where(a == 0, np.nan, a)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair", action="append", default=None)
    ap.add_argument("-o", "--out",
                    default=f"{BASE}/gacos_comparison.png")
    a = ap.parse_args()

    pairs = ([(p, "") for p in a.pair] if a.pair else DEFAULT_PAIRS)
    w, h = dims()
    print(f"grid {w} x {h}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(pairs), 3,
                             figsize=(13, 4.2 * len(pairs)),
                             constrained_layout=True)
    if len(pairs) == 1:
        axes = axes[np.newaxis, :]

    for row, (pair, label) in enumerate(pairs):
        raw = read_unw(f"{RAW}/{pair}/{pair}.unw", w, h)
        cor = read_unw(f"{COR}/{pair}/{pair}.unw", w, h)
        if raw is None or cor is None:
            print(f"  {pair}: missing .unw, skipped")
            continue

        # What GACOS removed is exactly the difference between the two, which
        # avoids re-deriving it from the per-epoch sltd files and any sign
        # convention error that would introduce.
        removed = raw - cor

        both = np.isfinite(raw) & np.isfinite(cor)
        sd_raw = float(np.nanstd(raw[both]))
        sd_cor = float(np.nanstd(cor[both]))
        rate = 100 * (sd_raw - sd_cor) / sd_raw if sd_raw else 0.0
        print(f"  {pair}: STD {sd_raw:.2f} -> {sd_cor:.2f} rad "
              f"({rate:+.1f}%) {label}")

        # One symmetric scale across the row, so the panels are comparable.
        lim = np.nanpercentile(np.abs(raw[both]), 98)
        panels = [(raw, "original phase"),
                  (removed, "GACOS delay removed"),
                  (cor, "corrected phase")]
        for col, (img, title) in enumerate(panels):
            ax = axes[row, col]
            im = ax.imshow(img, cmap="RdYlBu_r", vmin=-lim, vmax=lim)
            ax.set_title(title, fontsize=10)
            ax.set_xticks([])
            ax.set_yticks([])
            if col == 0:
                ax.set_ylabel(f"{pair}\n{label}", fontsize=9)
            if col == 2:
                fig.colorbar(im, ax=ax, shrink=0.8, label="rad")

        axes[row, 2].text(
            0.02, 0.02,
            f"STD {sd_raw:.2f} → {sd_cor:.2f} rad  ({rate:+.1f}%)",
            transform=axes[row, 2].transAxes, fontsize=9,
            bbox=dict(boxstyle="round", fc="white", alpha=0.8))

    fig.suptitle("GACOS over Flores: what the correction removes, "
                 "and whether it helps", fontsize=12)
    fig.savefig(a.out, dpi=140)
    print(f"\nwrote {a.out}")
    print("\nRead the middle panel against the left one. A delay field that")
    print("mirrors real phase structure is removing atmosphere; one that looks")
    print("unrelated is adding error, and the right panel will be noisier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
