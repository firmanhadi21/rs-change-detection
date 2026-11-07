#!/usr/bin/env python3
"""Review (Jenni AI, Q1): how much differential outcome error would change the headline results?

Any misclassification that differs between concession and control land enters a burned-share ratio as one
relative factor a = [(1 - c_t) / d_t] / [(1 - c_c) / d_c], with d the detection rate (1 - omission) and c the
commission share of cells called burned, so true ratio = observed ratio x a. For each result we report the a
needed to reach a target (point estimate, and the interval bound that would have to cross 1) and compare it with
the detection gap measured from VIIRS-seen cells (a_obs = adjusted / observed ratio, detection_adjust.json,
cover x tenure x drought band). For the concentration benchmark, concession ratios are multiplied by a_obs and
ranked again against the unpermitted patches (patches are unpermitted land, so their detection is the control's).

Writes output/fire/kalimantan_excess/tipping.json.

    python scripts/kalimantan_tipping.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import OUT  # noqa: E402

RES = os.path.join(OUT, "tipping.json")
J = lambda *p: json.load(open(os.path.join(OUT, *p)))       # noqa: E731


def main():
    import numpy as np
    import pandas as pd
    dc = {r["treated"]: r for r in J("dc_stratum.json")["burned_share"] if r["matched_on"] == "all strata + peak-DC band"}
    adj = {r["treated"]: r for r in J("detection_adjust.json")["ratios"]
           if r["outcome"] == "detection-adjusted (cover x tenure x DC band)"}
    out = {"definition": "true ratio = observed ratio x a; a = relative (1 - commission)/detection, concession over control",
           "headline": {}, "landprep": {}, "concentration": {}}
    for k in ("oil palm", "pulpwood"):
        r, (lo, hi) = dc[k]["ratio"], dc[k]["ci"]
        a_obs = adj[k]["ratio"] / r
        out["headline"][k] = {
            "observed": r, "ci": [lo, hi], "a_observed_detection_gap": a_obs,
            "a_for_point_1.10": 1.10 / r, "a_for_point_1.25": 1.25 / r, "a_for_point_1.50": 1.50 / r,
            "a_for_lower_bound_above_1": 1 / lo,
            "detection_ratio_equivalent_for_1.25": r / 1.25,     # d_t/d_c if commission is equal
        }
    lp = J("landprep", "landprep_tests_dc.json")
    lp15 = J("landprep", "landprep_tests.json")["T1"]["2015"]
    for name, rr in (("T1 2015 burns planted, oil palm", lp15["oil palm"]), ("T1 2015 burns planted, pulpwood", lp15["pulpwood"]),
                     ("T2 cleared before fire, oil palm (+ drought band)", lp["T2"]["oil palm"]),
                     ("T2 cleared before fire, pulpwood (+ drought band)", lp["T2"]["pulpwood"])):
        r, (lo, hi) = rr["ratio"], rr["ci"]
        out["landprep"][name] = {"observed": r, "ci": [lo, hi],
                                 "a_to_make_significant_excess": (1 / lo) if lo < 1 else None,
                                 "a_to_remove_excess": (1 / lo) if lo > 1 else None}
    P = pd.read_csv(os.path.join(OUT, "per_concession_matched_dc.csv"))
    T = pd.read_csv(os.path.join(OUT, "concentration_benchmark_patches.csv"))
    for k in ("oil palm", "pulpwood"):
        a_obs = out["headline"][k]["a_observed_detection_gap"]
        null = T[T.kind_sizes == k].ratio.to_numpy()
        g = P[P.kind == k].ratio.to_numpy()
        res = {}
        for q in (95, 99, 99.9):
            thr = np.percentile(null, q)
            res[f"p{q}"] = {"threshold": float(thr), "observed_above": int((g > thr).sum()),
                            "adjusted_above": int((g * a_obs > thr).sum()), "expected": len(g) * (100 - q) / 100}
        res["adjusted_max"] = float((g * a_obs).max())
        res["patch_max"] = float(null.max())
        out["concentration"][k] = res
    json.dump(out, open(RES, "w"), indent=1)
    for k, v in out["headline"].items():
        print(f"{k}: observed {v['observed']:.3f} ({v['ci'][0]:.3f}-{v['ci'][1]:.3f}); measured gap a = {v['a_observed_detection_gap']:.3f}; "
              f"a for 1.10 = {v['a_for_point_1.10']:.3f}, 1.25 = {v['a_for_point_1.25']:.3f}, 1.50 = {v['a_for_point_1.50']:.3f}; "
              f"lower bound > 1 needs a = {v['a_for_lower_bound_above_1']:.3f}")
    for k, v in out["landprep"].items():
        print(f"{k}: {v['observed']:.2f} ({v['ci'][0]:.2f}-{v['ci'][1]:.2f}); a to make significant {v['a_to_make_significant_excess']}")
    for k, v in out["concentration"].items():
        print(f"{k} concentration with measured gap: " + "; ".join(
            f"{q}: {d['observed_above']} -> {d['adjusted_above']} (expected {d['expected']:.1f})" for q, d in v.items() if q.startswith("p9"))
              + f"; adjusted max {v['adjusted_max']:.1f} vs patch max {v['patch_max']:.1f}")
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
