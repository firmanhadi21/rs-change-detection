#!/usr/bin/env python3
"""Review round 4: calibrate the per-concession flag and benchmark the peat association, using the
unpermitted patches of kalimantan_concentration_benchmark.py (same analysable size, same dominant drought
band, same drought-matched per-unit test; concentration_benchmark_patches.csv).

M1  The BH flag is not calibrated: patches, which have no tenure by construction, are also flagged. Here
    each concession's matched ratio is ranked against the patch ratios for its concession type (all
    replicates pooled): empirical p = (1 + #patches with ratio >= r) / (N + 1), then Benjamini-Hochberg at
    q <= 0.05 within type. A concession flagged this way burned more than unpermitted land of the same
    size and drought usually does, clustering included.
M2  Does peat raise the odds of excess more inside concessions than on unpermitted land? Firth logit on
    concessions and patches pooled (per replicate): excess ~ peat share (10 pp) + concession + concession x
    peat share + log size (z). Peat share is BBSDLP, the same definition for both.

Writes output/fire/kalimantan_excess/flag_calibration.json.

    python scripts/kalimantan_flag_calibration.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import OUT  # noqa: E402
from kalimantan_firth import firth, profile  # noqa: E402

RES = os.path.join(OUT, "flag_calibration.json")
Q = 0.05


def bh(p):
    import numpy as np
    o = np.argsort(p)
    adj = np.minimum.accumulate((p[o] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    q = np.empty_like(p)
    q[o] = np.minimum(adj, 1)
    return q


def main():
    import numpy as np
    import pandas as pd
    P = pd.read_csv(os.path.join(OUT, "per_concession_matched_dc.csv"))
    T = pd.read_csv(os.path.join(OUT, "concentration_benchmark_patches.csv"))
    out = {"calibrated_flag": {}, "peat_interaction": {}}

    # M1 -- concession ratio against the patch-ratio null
    for kind in ("oil palm", "pulpwood"):
        g = P[P.kind == kind].copy()
        null = np.sort(T[T.kind_sizes == kind].ratio.to_numpy())
        n = len(null)
        ge = n - np.searchsorted(null, g.ratio.to_numpy(), side="left")
        g["p_emp"] = (1 + ge) / (n + 1)
        g["q_emp"] = bh(g.p_emp.to_numpy())
        flag = (g.q_emp <= Q).to_numpy()
        top5 = (g.p_emp <= 0.05).to_numpy()
        old = g.class_fdr.eq("excess").to_numpy()
        tot = g.burned_km2.sum()
        r = {"units": int(len(g)), "null_patches": int(n),
             "patch_ratio_p95": float(np.percentile(null, 95)), "patch_ratio_p99": float(np.percentile(null, 99)),
             "flag_bh": int(flag.sum()), "flag_bh_share_pct": 100 * float(g.burned_km2[flag].sum() / tot),
             "above_patch_p95": int(top5.sum()), "above_patch_p95_share_pct": 100 * float(g.burned_km2[top5].sum() / tot),
             "expected_above_p95_if_like_patches": 0.05 * len(g),
             "fdr_excess": int(old.sum()), "fdr_excess_also_flag_bh": int((old & flag).sum()),
             "median_concession_ratio": float(g.ratio.median()), "median_patch_ratio": float(np.median(null))}
        out["calibrated_flag"][kind] = r
        print(f"{kind}: {r['flag_bh']} of {r['units']} flagged against patches (BH q<=0.05), holding "
              f"{r['flag_bh_share_pct']:.0f}% of burned area; {r['above_patch_p95']} above the patch 95th percentile "
              f"(x{r['patch_ratio_p95']:.2f}; {r['expected_above_p95_if_like_patches']:.0f} expected if like patches), "
              f"holding {r['above_patch_p95_share_pct']:.0f}%; of the {r['fdr_excess']} FDR-excess, "
              f"{r['fdr_excess_also_flag_bh']} keep the calibrated flag; median ratio {r['median_concession_ratio']:.2f} "
              f"vs patches {r['median_patch_ratio']:.2f}", flush=True)

    # M2 -- peat x tenure, oil palm, Firth, per replicate
    C = P[P.kind == "oil palm"][["cells", "peat_share", "class_fdr"]].assign(
        conc=1.0, excess=lambda d: d.class_fdr.eq("excess").astype(float))
    for rep, Tp in T[T.kind_sizes == "oil palm"].groupby("replicate"):
        D = pd.concat([C[["cells", "peat_share", "conc", "excess"]],
                       Tp.assign(conc=0.0, excess=Tp.excess.astype(float))[["cells", "peat_share", "conc", "excess"]]])
        D["ps10"] = D.peat_share / 0.1
        D["ps10_x_conc"] = D.ps10 * D.conc
        ls = np.log(D.cells)
        D["log_size_z"] = (ls - ls.mean()) / ls.std()
        cols = ["ps10", "conc", "ps10_x_conc", "log_size_z"]
        X = np.column_stack([np.ones(len(D)), D[cols].to_numpy(float)])
        y = D.excess.to_numpy(float)
        b = firth(X, y)
        res = {}
        for j, c in enumerate(cols, start=1):
            lo, hi, p = profile(X, y, b, j)
            res[c] = {"or": float(np.exp(b[j])), "lo": float(np.exp(lo)), "hi": float(np.exp(hi)), "p": p}
        # peat odds ratio inside concessions = exp(b_ps10 + b_interaction), point only
        res["ps10_in_concessions_point"] = float(np.exp(b[1] + b[3]))
        res["patches_with_peat_pct"] = 100 * float((Tp.peat_share > 0.01).mean())
        res["patch_excess_pct_peat_vs_not"] = [100 * float(Tp[Tp.peat_share > 0.01].excess.mean()),
                                              100 * float(Tp[Tp.peat_share <= 0.01].excess.mean())]
        out["peat_interaction"][str(rep)] = res
        print(f"  rep {rep}: peat OR on patches {res['ps10']['or']:.2f} [{res['ps10']['lo']:.2f}, {res['ps10']['hi']:.2f}]; "
              f"interaction (concessions vs patches) {res['ps10_x_conc']['or']:.2f} "
              f"[{res['ps10_x_conc']['lo']:.2f}, {res['ps10_x_conc']['hi']:.2f}] p {res['ps10_x_conc']['p']:.3f}; "
              f"patches excess with/without peat {res['patch_excess_pct_peat_vs_not'][0]:.1f}% / "
              f"{res['patch_excess_pct_peat_vs_not'][1]:.1f}%", flush=True)
    c = P[P.kind == "oil palm"]
    out["concession_excess_pct_peat_vs_not"] = [100 * float(c[c.peat_share > 0.01].class_fdr.eq("excess").mean()),
                                                100 * float(c[c.peat_share <= 0.01].class_fdr.eq("excess").mean())]
    print(f"concessions excess with/without peat: {out['concession_excess_pct_peat_vs_not'][0]:.1f}% / "
          f"{out['concession_excess_pct_peat_vs_not'][1]:.1f}%")
    json.dump(out, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
