"""Supplementary figures S1-S3 for the ERL paper.

S1 two dry seasons: season-peak Drought Code by latitude band (Indonesia, Malaysia) and Jul-Sep 2026 CHIRPS
   rain as a share of the 2001-2025 mean (two_seasons.json).
S2 calibration of the per-concession flag: ECDF of matched ratios, concessions against unpermitted patches of
   the same analysable size and drought band (per_concession_matched_dc.csv, concentration_benchmark_patches.csv).
S3 new fires (lineage roots) per 1,000 km2 per day by same-day Drought Code, by tenure; unmatched
   (fire_weather.json W3).

    python scripts/figures/SI_figures.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from _style import CTL, KIND_COL, RUN, W_DOUBLE, panel, run, save, setup  # noqa: E402

MYS = "#7A7A7A"


def s1():
    s = run("two_seasons.json")
    fig, (a, b) = plt.subplots(1, 2, figsize=(W_DOUBLE, 2.8), gridspec_kw={"wspace": 0.35})
    d = s["dc_by_latitude"]
    mid = [np.mean(x["lat"]) for x in d]
    a.plot([x["idn_peak"] for x in d], mid, "o-", color=KIND_COL["oil palm"], label="Indonesia")
    my = [(x["mys_peak"], m) for x, m in zip(d, mid) if x["mys_peak"] is not None]
    if my:
        a.plot(*zip(*my), "s-", color=MYS, label="Malaysia")
    for v in (300, 700):
        a.axvline(v, color=CTL, ls=":", lw=0.8)
    a.set_xlabel("Season-peak Drought Code, Jul–Oct 2026")
    a.set_ylabel("Latitude (°)")
    a.legend(frameon=False, loc="lower right")
    panel(a, "a")
    c = s["chirps"]
    y = np.arange(len(c))
    cols = [KIND_COL["oil palm"] if x["iso"] == "IDN" else MYS for x in c]
    b.barh(y, [x["pct"] for x in c], color=cols)
    b.axvline(100, color=CTL, ls="--", lw=0.8)
    b.set_yticks(y, [f"{x['iso']} {x['lat'][0]}° to {x['lat'][1]}°" for x in c], fontsize=7)
    b.set_xlabel("Rain 1 Jul–30 Sep 2026, % of 2001–2025 mean")
    panel(b, "b")
    save(fig, "FigS1_two_seasons")


def s2():
    P = pd.read_csv(os.path.join(RUN, "per_concession_matched_dc.csv"))
    T = pd.read_csv(os.path.join(RUN, "concentration_benchmark_patches.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(W_DOUBLE, 2.8), sharey=True, gridspec_kw={"wspace": 0.12})
    for ax, (k, col), letter in zip(axes, KIND_COL.items(), "ab"):
        for vals, lab, c, ls in ((T[T.kind_sizes == k].ratio, "unpermitted patches (5 draws)", CTL, "--"),
                                 (P[P.kind == k].ratio, "concessions", col, "-")):
            v = np.sort(np.clip(vals.to_numpy(), 0.01, None))
            ax.step(v, np.arange(1, len(v) + 1) / len(v), where="post", color=c, ls=ls, lw=1.4, label=lab)
        for q in (95, 99):
            thr = np.percentile(T[T.kind_sizes == k].ratio, q)
            ax.axvline(thr, color=CTL, lw=0.6, ls=":")
            ax.text(thr, 0.04, f" p{q}", fontsize=6, color=CTL)
        ax.axvline(1, color="black", lw=0.6)
        ax.set_xscale("log")
        ax.set_xlim(0.01, 120)
        ax.set_xlabel("Matched burned-share ratio (log)")
        ax.set_title(k.capitalize(), color=col, fontweight="bold", loc="left")
        panel(ax, letter)
    axes[0].set_ylabel("Cumulative share of units")
    axes[0].legend(frameon=False, loc="upper left", fontsize=6.5)
    save(fig, "FigS2_flag_calibration")


def s3():
    w = pd.DataFrame(run("fire_weather.json")["W3"])
    bands = list(dict.fromkeys(w.dc_band))
    fig, ax = plt.subplots(figsize=(W_DOUBLE * 0.55, 2.8))
    for t, c in (("oil palm", KIND_COL["oil palm"]), ("pulpwood", KIND_COL["pulpwood"]), ("open", CTL)):
        v = w[w.tenure == t].set_index("dc_band").reindex(bands).per_1000km2_day
        ax.plot(range(len(bands)), v, "o-", color=c, label="open land" if t == "open" else t)
    ax.set_xticks(range(len(bands)), [b.replace("-2000", "+") for b in bands], fontsize=7)
    ax.set_xlabel("Same-day Drought Code")
    ax.set_ylabel("New fires per 1,000 km² per day")
    ax.legend(frameon=False)
    save(fig, "FigS3_ignitions_by_dc")


if __name__ == "__main__":
    setup()
    s1()
    s2()
    s3()
