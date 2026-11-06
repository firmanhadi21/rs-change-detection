"""Fig02: robustness of the matched concession effect (oil palm, pulpwood), log ratio axis.

Rows (all vs comparable unpermitted land, 95% block-bootstrap CI):
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
    m = next(r for r in run("matched.json") if r["test"] == "burn" and r["treated"] == kind
             and r["matched_on"] == "+ distance to settlement")
    dc = next(r for r in run("dc_stratum.json")["burned_share"] if r["treated"] == kind
              and r["matched_on"] == "all strata + peak-DC band")
    out = [("Primary: + same peak-drought band", dc["ratio"], dc["ci"], "main"),
           ("Land strata only (S2 burned ≥ ½ cell)", m["ratio"], m["ratio_ci95"], "outcome")]
    oc = {(r["outcome"], r["treated"]): r for r in run("concession_checks.json")["outcomes"]
          if r["matched_on"] == "+ distance to settlement"}
    for key, lab in (("burned25", "S2 burned ≥ ¼ cell"), ("viirs_cell", "VIIRS fire within ~300 m"),
                     ("viirs_count", "VIIRS detections per cell")):
        r = oc[(key, kind)]
        out.append((lab, r["ratio"], r["ci95"], "outcome"))
    R = {(r.get("check"), r.get("variant"), r.get("treated")): r for r in run("robustness.json") if "ratio" in r}
    out.append(("Greifswald peat map", *_rc(R[("R2", "GPM peat + depth bins", kind)]), "peat"))
    out.append(("Away from edges (5 km, both sides)", *_rc(R[("R1", "+ treated >= 5 km inside edge", kind)]), "edge"))
    loo = {r["dropped"]: r for r in run("balance_sensitivity.json")["leave_one_out"][kind]}
    out.append(("Without distance to settlement", loo["distance to settlement"]["ratio"], loo["distance to settlement"]["ci"], "cov"))
    out.append(("Without land cover", loo["land cover"]["ratio"], loo["land cover"]["ci"], "cov"))
    out.append(("Without burn history", loo["burn history"]["ratio"], loo["burn history"]["ci"], "cov"))
    out.append(("Boundaries: GFW v2025", *_rc(R[("R4", "GFW v2025 oil palm", kind)]), "bound"))
    for y in ("2015", "2019", "2023"):
        out.append((f"Season {y} (MODIS MCD64A1)", *_rc(R[("R3", f"{y} MCD64", kind)]), "season"))
    out.append(("2026 MODIS, Jan–Aug only", *_rc(R[("R3", "2026 MCD64", kind)]), "season"))
    return out


def _rc(r):
    return r["ratio"], r["ci"]


def main():
    setup()
    fig, axes = plt.subplots(1, 2, figsize=(W_DOUBLE, 4.3), sharey=True)
    for ax, (kind, col), letter in zip(axes, KIND_COL.items(), "ab"):
        R = rows(kind)
        y = np.arange(len(R))[::-1]
        for yi, (lab, r, ci, grp) in zip(y, R):
            main_ = grp == "main"
            ax.plot(ci, [yi, yi], color=col, lw=2.2 if main_ else 1.3, solid_capstyle="butt")
            ax.plot([r], [yi], "D" if main_ else "o", color=col if main_ else "white", mec=col, ms=5 if main_ else 4, mew=1.2)
            ax.text(2.25, yi, f"{r:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]", va="center", fontsize=6.5, color=INK)
        for yb in (len(R) - 1.5, len(R) - 5.5, len(R) - 10.5, len(R) - 11.5):
            ax.axhline(yb, color="#E5E5E5", lw=0.6)
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
