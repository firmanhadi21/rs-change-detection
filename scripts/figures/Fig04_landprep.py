"""Fig04: was concession fire land preparation for planting? (landprep/landprep_tests.json)

(a) T1 share of 2015-burned non-palm land planted to palm 2016-2021 (Descals et al. 2024) vs matched
    unburned non-palm land in the same zone; ratio [95% CI] above each pair.
(b) T2 share of 2026-burned cells cleared before the fire (Sentinel-2 NDVI), concession vs matched
    unpermitted burned cells.
(c) T3 overpasses with >= 3 new VIIRS ignitions in one unit, per 100 km2, Jul-Oct 2026 (descriptive;
    open land grouped in 10 km cells).

    python scripts/figures/Fig04_landprep.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from _style import CTL, INK, OIL, PULP, W_DOUBLE, panel, run, save, setup  # noqa: E402

COL = {"oil palm": OIL, "pulpwood": PULP, "unpermitted": CTL, "open": CTL}


def pairs(ax, items, ylab, labels):
    x = np.arange(len(items))
    for i, (zone, r) in enumerate(items):
        ax.bar(i - 0.19, 100 * r["treated"], 0.36, color=COL[zone])
        ax.bar(i + 0.19, 100 * r["control"], 0.36, color="white", edgecolor=COL[zone], hatch="///", lw=1.0)
        top = 100 * max(r["treated"], r["control"])
        ax.text(i, top * 1.06 + 0.05, f"×{r['ratio']:.2f}\n[{r['ci'][0]:.2f}, {r['ci'][1]:.2f}]", ha="center",
                fontsize=6, color=INK)
    ax.set_xticks(x, [z for z, _ in items])
    ax.set_ylabel(ylab)
    ax.set_ylim(0, max(100 * max(r["treated"], r["control"]) for _, r in items) * 1.45)
    h = [plt.Rectangle((0, 0), 1, 1, color=CTL), plt.Rectangle((0, 0), 1, 1, fc="white", ec=CTL, hatch="///")]
    ax.legend(h, labels, frameon=False, loc="upper left", fontsize=6.5)


def main():
    setup()
    L = run("landprep/landprep_tests.json")
    fig, axes = plt.subplots(1, 3, figsize=(W_DOUBLE, 2.6), gridspec_kw={"width_ratios": [1.35, 1, 0.9]})
    pairs(axes[0], [(z, L["T1"]["2015"][z]) for z in ("oil palm", "pulpwood", "unpermitted")],
          "Planted to oil palm 2016–21 (%)", ["burned in 2015", "matched, not burned"])
    panel(axes[0], "a")
    pairs(axes[1], [(z, L["T2"][z]) for z in ("oil palm", "pulpwood")],
          "Cleared before the 2026 fire (%)", ["concession, burned", "matched unpermitted"])
    panel(axes[1], "b")
    ax = axes[2]
    T3 = L["T3"]
    zs = ["oil palm", "pulpwood", "open"]
    ax.bar(range(3), [T3[z]["per_100km2"] for z in zs], 0.6, color=[COL[z] for z in zs])
    for i, z in enumerate(zs):
        ax.text(i, T3[z]["per_100km2"] + 0.015, f"{T3[z]['per_100km2']:.2f}", ha="center", fontsize=6.5)
    ax.set_xticks(range(3), ["oil\npalm", "pulp-\nwood", "open\nland"])
    ax.set_ylabel("Overpasses with ≥ 3 new\nignitions per 100 km²")
    panel(ax, "c")
    fig.subplots_adjust(wspace=0.5)
    save(fig, "Fig04_landprep")


if __name__ == "__main__":
    main()
