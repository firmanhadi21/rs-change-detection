#!/usr/bin/env python3
"""Summary of the 50-replicate unpermitted-patch benchmark (kalimantan_concentration_benchmark.py --reps 50):
quantiles over replicates of the concentration statistics, where the concessions fall among them, and the
flag calibration (concession ratios against the pooled patch-ratio distribution, with the per-replicate
spread of patch counts above each percentile). Writes concentration_benchmark_r50_summary.json.

    python scripts/kalimantan_benchmark_summary.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import OUT  # noqa: E402

RES = os.path.join(OUT, "concentration_benchmark_r50_summary.json")


def main():
    import numpy as np
    import pandas as pd
    b = json.load(open(os.path.join(OUT, "concentration_benchmark_r50.json")))
    P = pd.read_csv(os.path.join(OUT, "per_concession_matched_dc.csv"))
    T = pd.read_csv(os.path.join(OUT, "concentration_benchmark_patches_r50.csv"))
    out = {"replicates": None, "stats": {}, "tails": {}}
    for k in ("oil palm", "pulpwood"):
        c = b["concessions"][k]
        R = [r for r in b["replicates"] if r["kind_sizes"] == k]
        out["replicates"] = len(R)
        st = {}
        for key in ("excess_pct", "excess_share_pct", "excess_pct_of_burning", "zero_burn_units"):
            a = np.array([r[key] for r in R], float)
            st[key] = {"concession": float(c[key]), "median": float(np.median(a)),
                       "p2.5": float(np.percentile(a, 2.5)), "p97.5": float(np.percentile(a, 97.5)),
                       "share_of_replicates_below_concession": float(np.mean(a < c[key]))}
        out["stats"][k] = st
        g = P[P.kind == k].ratio.to_numpy()
        Tk = T[T.kind_sizes == k]
        tl = {}
        for q in (95, 99, 99.9):
            thr = float(np.nanpercentile(Tk.ratio, q))
            per = [int((Tk[Tk.replicate == r].ratio > thr).sum()) for r in Tk.replicate.unique()]
            tl[str(q)] = {"threshold": thr, "concessions_above": int((g > thr).sum()),
                          "expected": len(g) * (100 - q) / 100,
                          "patches_per_replicate_p2.5": float(np.percentile(per, 2.5)),
                          "patches_per_replicate_p97.5": float(np.percentile(per, 97.5))}
        tl["max"] = {"concession": float(g.max()), "patch": float(np.nanmax(Tk.ratio)),
                     "patch_ratio_nan": int(Tk.ratio.isna().sum())}
        out["tails"][k] = tl
    json.dump(out, open(RES, "w"), indent=1)
    print(json.dumps(out, indent=1)[:2500])


if __name__ == "__main__":
    main()
