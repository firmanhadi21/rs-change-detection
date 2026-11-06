"""Fig03: which oil-palm concessions burn in excess?

(a) share of oil-palm concessions in excess (BH q <= 0.05) by the share of the unit on peat, on two
    independent peat maps (BBSDLP; Greifswald GPM 2.0); n units above each bar.
(b) odds ratios (95% CI, HC1) from the logit on excess status (heterogeneity.json, oil palm, main
    model), plus peat share alone on each map (peat_depth_checks.json V3, V4).

    python scripts/figures/Fig03_peat_traits.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from _style import CTL, DATA, INK, OIL, RUN, W_DOUBLE, panel, run, save, setup  # noqa: E402

BINS = [(-0.01, 0.01, "<1"), (0.01, 0.25, "1–25"), (0.25, 0.5, "25–50"), (0.5, 0.75, "50–75"), (0.75, 1.01, "75–100")]
LABELS = {
    "depth_m_z": "Peat depth, unit mean (per SD)", "forest_share_z": "Forest share (per SD)",
    "log_area_z": "Unit area, log (per SD)", "ind_share_10pp": "Industrial palm (per 10 pp)",
    "small_share_10pp": "Smallholder palm (per 10 pp)", "recent_share_10pp": "Planted 2016–21 (per 10 pp)",
    "st_in_process": "Permit: title in process", "st_location_permit": "Permit: location permit only",
    "st_unknown": "Permit: status unknown", "grouped": "Member of a company group",
    "rspo_cert_share_10pp": "RSPO certified (per 10 pp)", "rspo_member_share_10pp": "RSPO member, uncertified (per 10 pp)",
    "other_permit_share_10pp": "Overlap with pulpwood permit (per 10 pp)",
}


def main():
    setup()
    U = pd.read_csv(os.path.join(RUN, "heterogeneity_units.csv")).drop(columns=["excess"])
    Bdc = pd.read_csv(os.path.join(RUN, "per_concession_matched_dc.csv"))[["kind", "id", "class_fdr"]]
    U = U.merge(Bdc.rename(columns={"class_fdr": "cls_dc"}), on=["kind", "id"]).assign(excess=lambda d: d.cls_dc.eq("excess"))
    C = pd.read_csv(os.path.join(DATA, "peat_check_covariates.csv"))[["kind", "id", "peat_share", "gpm_share"]]
    O = U[U.kind == "oil palm"].merge(C.rename(columns={"peat_share": "ps"}), on=["kind", "id"])
    O["excess"] = O.excess.astype(bool)
    fig, (axa, axb) = plt.subplots(1, 2, figsize=(W_DOUBLE, 3.6), gridspec_kw={"width_ratios": [1, 1.1]})

    x = np.arange(len(BINS))
    tops = []
    for j, (col, lab, hatch) in enumerate((("ps", "BBSDLP peat map", None), ("gpm_share", "Greifswald GPM 2.0", "///"))):
        v = O[col].fillna(0)
        sh, n = [], []
        for lo, hi, _ in BINS:
            m = (v > lo) & (v <= hi)
            sh.append(100 * O[m].excess.mean() if m.sum() else np.nan)
            n.append(int(m.sum()))
        bars = axa.bar(x + (j - 0.5) * 0.38, sh, 0.36, color=OIL if j == 0 else "white", edgecolor=OIL, hatch=hatch,
                       lw=1.0, label=lab)
        for k, (b, nn) in enumerate(zip(bars, n)):
            # stagger the two maps' counts where their bars are about the same height
            other = tops[k] if j == 1 and tops else None
            dy = 0.0                     # adjacent bars: nudge the label sideways instead of up
            if other is not None and abs(other - b.get_height()) < 1.6:
                axa.text(b.get_x() + b.get_width() * 0.95, b.get_height() + 0.5, f"{nn}", ha="left", fontsize=6, color=INK)
                continue
            axa.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.5 + dy, f"{nn}", ha="center", fontsize=6, color=INK)
        tops = [b.get_height() for b in bars]
    base = 100 * O.excess.mean()
    axa.axhline(base, color=CTL, ls="--", lw=0.8, label=f"all oil-palm units ({base:.1f}%)")
    axa.set_ylim(0, 27)
    axa.set_xticks(x, [b[2] for b in BINS], fontsize=6.5)
    axa.set_xlabel("Share of the concession on peat (%)")
    axa.set_ylabel("Oil-palm concessions in excess (%)")
    axa.legend(frameon=False, loc="upper right", fontsize=6.5, title="n units above bars", title_fontsize=6)
    panel(axa, "a")

    # Firth penalised logit, profile intervals, drought-matched classes (kalimantan_firth.py, review round 3)
    M = run("firth.json")["models"]
    het = M["main (depth)"]
    rows = [("Peat share alone, BBSDLP (per 10 pp)", M["BBSDLP share"]["peat_share_10pp"]),
            ("Peat share alone, Greifswald (per 10 pp)", M["GPM share"]["gpm_share_10pp"])]
    rows += [(LABELS[k], het[k]) for k in LABELS]
    y = np.arange(len(rows))[::-1]
    for yi, (lab, r) in zip(y, rows):
        sig = r["p"] < 0.05
        axb.plot([r["lo"], r["hi"]], [yi, yi], color=OIL if sig else CTL, lw=1.3)
        axb.plot([r["or"]], [yi], "o", color=OIL if sig else "white", mec=OIL if sig else CTL, ms=4, mew=1.1)
    axb.axhline(len(rows) - 2.5, color="#E5E5E5", lw=0.6)
    axb.axvline(1, color=CTL, ls="--", lw=0.8)
    axb.set_xscale("log")
    axb.set_xticks([0.2, 0.5, 1, 2, 5]), axb.set_xticklabels(["0.2", "0.5", "1", "2", "5"]), axb.minorticks_off()
    axb.set_xlim(0.1, 6)
    axb.set_yticks(y, [lab for lab, _ in rows], fontsize=6)
    axb.tick_params(axis="y", length=0)
    axb.spines["left"].set_visible(False)
    axb.set_xlabel("Odds ratio of excess status, Firth logit (95% CI)")
    axb.text(0.99, 0.01, "filled: p < 0.05", transform=axb.transAxes, ha="right", fontsize=6, color=CTL)
    panel(axb, "b")
    fig.subplots_adjust(wspace=1.15)
    save(fig, "Fig03_peat_traits")


if __name__ == "__main__":
    main()
