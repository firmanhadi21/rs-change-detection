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


def gap(ax, vals, xlab, letter):
    for i, (kind, (g, ci)) in enumerate(vals.items()):
        ax.plot(ci, [i, i], color=KIND_COL[kind], lw=1.5)
        ax.plot([g], [i], "o", color=KIND_COL[kind], ms=5)
        ax.text(g, i + 0.22, f"{g:+.1f} [{ci[0]:+.1f}, {ci[1]:+.1f}]", ha="center", fontsize=6.5, color=KIND_COL[kind])
    ax.axvline(0, color=CTL, ls="--", lw=0.8)
    ax.set_yticks(range(len(vals)), list(vals))
    ax.set_ylim(-0.6, len(vals) - 0.3)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(xlab)
    panel(ax, letter)


def main():
    setup()
    fig = plt.figure(figsize=(W_DOUBLE, 2.7))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.7], wspace=0.45)
    m = {r["treated"]: r for r in run("matched.json") if r["test"] == "first-fire day"
         and r["matched_on"] == "+ distance to settlement"}
    gap(fig.add_subplot(gs[0]), {k: (m[k]["gap_days"], m[k]["gap_ci95"]) for k in KIND_COL},
        "First fire, concession − matched (days)", "a")
    fw = run("fire_weather.json")
    w2 = {r["treated"]: r for r in fw["W2"] if r["matched_on"] == "all strata"}
    gap(fig.add_subplot(gs[1]), {k: (w2[k]["gap"], w2[k]["ci"]) for k in KIND_COL},
        "Drought Code at first fire,\nconcession − matched", "b")
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
