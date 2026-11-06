"""Fig05: when concession land burns.

(a) matched gap in first-fire day (VIIRS, Jun-Oct 2026), concession minus comparable unpermitted
    burned cells (matched.json, first-fire day, all strata).
(b) matched gap in the Drought Code on the first-fire day (fire_weather.json W2, all strata).
(c) matched burned-share ratio by the cell's season-peak Drought Code band (fire_weather.json W1);
    bands are regions of the island, not a dose.

    python scripts/figures/Fig05_timing_drought.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from _style import CTL, KIND_COL, W_DOUBLE, panel, run, save, setup  # noqa: E402


def gap(ax, rows, xlab, letter, labels=True):
    """rows: list of (label, kind, primary?, gap, ci); primary (drought-matched) filled, land strata only open."""
    for i, (lab, kind, prim, g, ci) in enumerate(rows):
        col = KIND_COL[kind]
        ax.plot(ci, [i, i], color=col, lw=1.6 if prim else 1.0)
        ax.plot([g], [i], "D" if prim else "o", color=col if prim else "white", mec=col, ms=5 if prim else 4, mew=1.1)
        ax.text(g, i + 0.26, f"{g:+.1f} [{ci[0]:+.1f}, {ci[1]:+.1f}]", ha="center", fontsize=6, color=col)
    ax.axvline(0, color=CTL, ls="--", lw=0.8)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows] if labels else [""] * len(rows), fontsize=6.5)
    ax.set_ylim(-0.6, len(rows) - 0.3)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(xlab)
    panel(ax, letter)


def timing_rows(var):
    T = run("dc_stratum.json")["timing"]
    rows = []
    for kind in ("pulpwood", "oil palm"):
        for name, lab, prim in (("all strata", "land strata", False), ("all strata + peak-DC band", "+ same drought", True)):
            r = next(x for x in T if x["treated"] == kind and x["matched_on"] == name and x["variable"] == var)
            rows.append((f"{kind}, {lab}", kind, prim, r["gap"], r["ci"]))
    return rows


def main():
    setup()
    fig = plt.figure(figsize=(W_DOUBLE, 2.9))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.5], wspace=0.3)
    gap(fig.add_subplot(gs[0]), timing_rows("day"), "First fire, concession − matched (days)", "a")
    gap(fig.add_subplot(gs[1]), timing_rows("dc_first"), "Drought Code at first fire,\nconcession − matched", "b", labels=False)
    fw = run("fire_weather.json")
    ax = fig.add_subplot(gs[2])
    for j, (kind, col) in enumerate(KIND_COL.items()):
        rows = [r for r in fw["W1"] if r["treated"] == kind]
        x = np.arange(len(rows)) + (j - 0.5) * 0.22
        ax.errorbar(x, [r["ratio"] for r in rows],
                    yerr=[[r["ratio"] - r["ci"][0] for r in rows], [r["ci"][1] - r["ratio"] for r in rows]],
                    fmt="o", color=col, ms=4, lw=1.1, capsize=0, label=kind)
    bands = [r["dc_band"] for r in fw["W1"] if r["treated"] == "oil palm"]
    ax.set_xticks(range(len(bands)), [f"{lo}–\n{hi}" if hi < 2000 else f"≥\n{lo}" for lo, hi in bands])
    ax.axhline(1, color=CTL, ls="--", lw=0.8)
    ax.set_yscale("log")
    ax.set_yticks([0.3, 0.5, 1, 2, 3]), ax.set_yticklabels(["0.3", "0.5", "1", "2", "3"]), ax.minorticks_off()
    ax.set_xlabel("Season-peak Drought Code of the cell (Jul–Oct 2026)")
    ax.set_ylabel("Burned-share ratio,\nconcession / matched")
    ax.legend(frameon=False, loc="upper right")
    panel(ax, "c")
    save(fig, "Fig05_timing_drought")


if __name__ == "__main__":
    main()
