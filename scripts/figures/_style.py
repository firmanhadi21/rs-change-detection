"""Shared style and data helpers for the ERL figures (paper plan §13).

Palette: Okabe-Ito colour-blind-safe hues; oil palm = vermilion, pulpwood = blue, unpermitted / control
= grey. Every figure reads numbers from the Kalimantan run files; nothing is typed in by hand.
"""
import json
import os

import matplotlib as mpl
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUN = os.path.join(ROOT, "output", "fire", "kalimantan_excess")
DATA = os.path.join(ROOT, "data", "kalimantan")
FIG = os.path.join(ROOT, "output", "figures")

W_DOUBLE = 7.2          # in, 183 mm
W_SINGLE = 3.5          # in, 89 mm
OIL, PULP, CTL, INK, MID, LIGHT = "#D55E00", "#0072B2", "#7F7F7F", "#222222", "#9A9A9A", "#D9D9D9"
EXCESS, NODIFF, DEFICIT = "#D55E00", "#BDBDBD", "#6BAED6"
BURN = "#5A5A5A"          # 2026 burned cells (1 km)
KIND_COL = {"oil palm": OIL, "pulpwood": PULP}


def setup():
    mpl.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7, "axes.linewidth": 0.8,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8, "lines.linewidth": 1.4,
        "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.dpi": 300, "figure.dpi": 100,
    })


def run(name):
    return json.load(open(os.path.join(RUN, name)))


def panel(ax, letter):
    ax.text(-0.02, 1.02, letter, transform=ax.transAxes, fontsize=10, fontweight="bold", va="bottom", ha="right")


def save(fig, stem):
    os.makedirs(FIG, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(FIG, f"{stem}.{ext}")
        fig.savefig(p, bbox_inches="tight")
        print(f"  {p} ({os.path.getsize(p) / 1e3:.0f} kB)")
    plt.close(fig)
