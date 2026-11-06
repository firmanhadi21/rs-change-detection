"""Fig02: robustness of the matched concession effect (oil palm, pulpwood), log ratio axis.

Since review round 2 the upper block is matched on all strata + the season-peak Drought Code band
(dc_stratum.json, dc_robustness.json); the lower block keeps checks matched on land strata only.
Earlier row list (land strata, kept for reference):
  main (S2 burned >= half cell, all strata)            matched.json
  outcomes: S2 >= quarter cell, VIIRS presence, counts  concession_checks.json
  peat map: Greifswald GPM 2.0                         robustness.json R2
  edges: 5 km buffer both sides                        robustness.json R1
  covariates: without distance to settlement, without land cover   balance_sensitivity.json
  boundaries: GFW v2025                                robustness.json R4
  seasons (MODIS MCD64A1): 2015, 2019, 2023            robustness.json R3

    python scripts/figures/Fig02_robustness.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from _style import CTL, INK, KIND_COL, W_DOUBLE, panel, run, save, setup  # noqa: E402


def rows(kind):
    """Drought-matched block first (dc_robustness.json, review round 2), then land-strata-only checks
    that have no drought-matched counterpart (earlier seasons, early 2026 MODIS, GFW v2025)."""
    D = {(r["check"], r["variant"]): r for r in run("dc_robustness.json") if r["treated"] == kind}
    dc = next(r for r in run("dc_stratum.json")["burned_share"] if r["treated"] == kind
              and r["matched_on"] == "all strata + peak-DC band")
    out = [("Primary: all strata + same drought", dc["ratio"], dc["ci"], "main")]
    for key, lab in ((("outcome", "S2 burned >= 1/4 of the cell"), "S2 burned ≥ ¼ cell"),
                     (("outcome", "any VIIRS fire within ~300 m, Jun-Oct"), "VIIRS fire within ~300 m"),
                     (("outcome", "VIIRS detections per cell, Jun-Oct"), "VIIRS detections per cell"),
                     (("peat map", "Greifswald GPM 2.0 peat + depth bins"), "Greifswald peat map"),
                     (("interior", "controls >= 5 km out, treated >= 5 km in"), "Away from edges (5 km, both sides)"),
                     (("leave-out", "without distance to settlement"), "Without distance to settlement"),
                     (("leave-out", "without land cover"), "Without land cover"),
                     (("leave-out", "without burn history"), "Without burn history")):
        out.append((lab, *_rc(D[key]), "dc"))
    m = next(r for r in run("matched.json") if r["test"] == "burn" and r["treated"] == kind
             and r["matched_on"] == "+ distance to settlement")
    out.append(("Land strata only, 2026 S2", m["ratio"], m["ratio_ci95"], "land"))
    R = {(r.get("check"), r.get("variant"), r.get("treated")): r for r in run("robustness.json") if "ratio" in r}
    for y in ("2015", "2019", "2023"):
        out.append((f"Season {y} (MODIS MCD64A1)", *_rc(R[("R3", f"{y} MCD64", kind)]), "land"))
    out.append(("2026 MODIS, Jan–Aug only", *_rc(R[("R3", "2026 MCD64", kind)]), "land"))
    out.append(("Boundaries: GFW v2025", *_rc(R[("R4", "GFW v2025 oil palm", kind)]), "land"))
    return out


def _rc(r):
    return r["ratio"], r["ci"]


def main():
    setup()
    fig, axes = plt.subplots(1, 2, figsize=(W_DOUBLE, 4.6), sharey=True)
    for ax, (kind, col), letter in zip(axes, KIND_COL.items(), "ab"):
        R = rows(kind)
        y = np.arange(len(R))[::-1]
        for yi, (lab, r, ci, grp) in zip(y, R):
            main_, land = grp == "main", grp == "land"
            ax.plot(ci, [yi, yi], color=col, lw=2.2 if main_ else 1.3, solid_capstyle="butt", alpha=0.55 if land else 1)
            ax.plot([r], [yi], "D" if main_ else "o", color="white" if land else col, mec=col, ms=5 if main_ else 4, mew=1.2)
            ax.text(2.25, yi, f"{r:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]", va="center", fontsize=6.5, color=INK)
        nd = sum(1 for g in R if g[3] != "land")
        ax.axhline(len(R) - 1.5, color="#E5E5E5", lw=0.6)
        ax.axhline(len(R) - nd - 0.5, color="#9A9A9A", lw=0.8)
        ax.text(0.31, len(R) - nd - 0.42, "below: land strata only (no 2026 drought band)", fontsize=6, color=CTL, va="bottom")
        ax.axvline(1, color=CTL, ls="--", lw=0.8)
        ax.set_xscale("log")
        ax.set_xlim(0.3, 2.2)
        ax.set_xticks([0.3, 0.5, 0.7, 1.0, 1.4, 2.0]), ax.set_xticklabels(["0.3", "0.5", "0.7", "1.0", "1.4", "2.0"]), ax.minorticks_off()
        ax.set_xlabel("Burned-share ratio, concession / matched unpermitted land")
        ax.set_title(kind.capitalize(), color=col, fontweight="bold", loc="left")
        ax.set_yticks(y, [lab for lab, *_ in R])
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        panel(ax, letter)
    fig.subplots_adjust(wspace=0.55)
    save(fig, "Fig02_robustness")


if __name__ == "__main__":
    main()
