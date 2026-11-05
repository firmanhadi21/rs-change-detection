#!/usr/bin/env python3
"""Balance, sensitivity and covariate attribution for the Kalimantan matched concession effect
(kalimantan_excess_burn.py --stage match): the two checks a reviewer will ask for (paper plan E10, E13).

Same sample (cells with a cloud-free S2 pair), treated zones (3 oil palm, 2 pulpwood-only) vs
unpermitted land (1), CEM strata SEQ[-1] and estimator `matched` as the main run.

1. BALANCE. CEM matches on coarsened bins; within a bin the raw covariates can still differ. For each
   uncoarsened covariate: treated mean, control mean before matching, control mean after CEM weighting
   (control cell weight = treated / control count in its stratum), and the standardised mean difference
   SMD = (mean_T - mean_C) / sqrt((var_T + var_C) / 2) (raw-sample variances, Stuart 2010). |SMD| < 0.1
   is the usual balance threshold.
2. ATTRIBUTION (order-free ladder). The burned-share ratio is computed for all 64 subsets of the six
   covariates (point estimates). Each covariate's Shapley value is its average contribution to the change
   in log ratio from raw to full over all orders in which covariates can be added; the values sum to
   log(full) - log(raw). Leave-one-out ratios (full minus one covariate) get block-bootstrap CIs.
3. SENSITIVITY. E-values (VanderWeele & Ding 2017) for the matched ratio and for its CI bound nearest 1:
   the minimum strength of association, on the risk-ratio scale, that an unmeasured confounder would
   need with both tenure and burning, beyond the measured covariates, to explain the estimate away.
   Benchmarked against the measured covariates via the leave-one-out shifts.

    python scripts/kalimantan_balance.py
"""
import itertools
import json
import math
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import DATA, NBOOT, OUT, SEQ, NAMES, matched, stratum  # noqa: E402

KEYS = SEQ[-1]                       # peat, depth_bin, lc, hist, water_bin, settle_bin
LABEL = dict(zip(KEYS, [n.replace("+ ", "") for n in NAMES[1:]]))
RES = os.path.join(OUT, "balance_sensitivity.json")


def evalue(rr):
    """E-value for a risk ratio (VanderWeele & Ding 2017); protective ratios are inverted."""
    r = 1 / rr if rr < 1 else rr
    return r + math.sqrt(r * (r - 1)) if r > 1 else 1.0


def main():
    import numpy as np
    import pandas as pd
    cols = ["zone", "valid", "burned", "peat", "thick", "lc", "hist", "d_water", "d_settle", "block"] + KEYS
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"), columns=list(dict.fromkeys(cols)))
    df = df[df.valid].reset_index(drop=True)
    blocks = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    W = np.random.default_rng(42).multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                                              size=NBOOT).astype(float)
    one = np.ones((1, len(blocks)))
    # uncoarsened covariates for balance
    df["peat_f"] = df.peat.astype(float)
    df["depth_cm"] = np.where(df.peat, df.thick, 0).astype(float)
    df["burns_prior"] = df["hist"].astype(float)          # df.hist is the pandas plotting method
    for name, cls in (("intact_forest", [4]), ("degraded_forest", [5, 6]), ("nonforest", [7]), ("palm", [0, 1, 2, 3])):
        df[name] = df.lc.isin(cls).astype(float)
    BAL = [("peat_f", "on peat (share)"), ("depth_cm", "peat depth, cm (0 off peat)"),
           ("burns_prior", "burned in 2015/2019/2023 (count)"), ("d_water", "distance to water, km"),
           ("d_settle", "distance to settlement, km"), ("intact_forest", "intact forest (share)"),
           ("degraded_forest", "degraded forest (share)"), ("nonforest", "non-forest (share)"),
           ("palm", "oil palm, Descals (share)")]
    out = {"balance": {}, "attribution": {}, "leave_one_out": {}, "sensitivity": {}}

    for z, kind in ((3, "oil palm"), (2, "pulpwood")):
        d = df[df.zone.isin([1, z])].reset_index(drop=True)
        t = (d.zone == z).to_numpy()
        y = d.burned.to_numpy(float)

        # ---- 1. balance
        s = stratum(d, KEYS)
        g = pd.DataFrame({"s": s, "t": t})
        nt = g[g.t].groupby("s").size()
        nc = g[~g.t].groupby("s").size()
        both = nt.index.intersection(nc.index)
        wc = (nt.reindex(both) / nc.reindex(both)).rename("w")
        w_c = pd.Series(s[~t]).map(wc).fillna(0).to_numpy()
        in_t = pd.Series(s[t]).isin(both).to_numpy()
        rows = []
        print(f"\n{kind}: balance (treated n={t.sum():,}, matched {in_t.mean():.1%}; control n={(~t).sum():,})")
        print(f"  {'covariate':<36}{'treated':>9}{'ctl raw':>9}{'ctl CEM':>9}{'SMD raw':>9}{'SMD CEM':>9}")
        for c, lab in BAL:
            xt, xc = d[c].to_numpy()[t], d[c].to_numpy()[~t]
            sd = math.sqrt((xt.var() + xc.var()) / 2) or 1.0
            mt = xt[in_t].mean()
            mc_raw, mc_w = xc.mean(), np.average(xc, weights=w_c)
            r = {"covariate": lab, "treated": float(mt), "control_raw": float(mc_raw), "control_cem": float(mc_w),
                 "smd_raw": float((xt.mean() - mc_raw) / sd), "smd_cem": float((mt - mc_w) / sd)}
            rows.append(r)
            print(f"  {lab:<36}{mt:9.3f}{mc_raw:9.3f}{mc_w:9.3f}{r['smd_raw']:9.3f}{r['smd_cem']:9.3f}")
        out["balance"][kind] = rows

        # ---- 2. all 64 subsets (point estimates) -> Shapley attribution
        est = {}
        for k in range(len(KEYS) + 1):
            for sub in itertools.combinations(KEYS, k):
                pt, pc, _, _ = matched(d, t, list(sub), y, one, bidx)
                est[frozenset(sub)] = math.log(pt / pc)
        n = len(KEYS)
        shap = {}
        for c in KEYS:
            v = 0.0
            others = [x for x in KEYS if x != c]
            for k in range(n):
                for sub in itertools.combinations(others, k):
                    wgt = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
                    v += wgt * (est[frozenset(sub) | {c}] - est[frozenset(sub)])
            shap[c] = v
        raw, full = est[frozenset()], est[frozenset(KEYS)]
        out["attribution"][kind] = {
            "raw_ratio": math.exp(raw), "full_ratio": math.exp(full),
            "shapley_log": {LABEL[c]: shap[c] for c in KEYS},
            "shapley_share_of_change": {LABEL[c]: shap[c] / (full - raw) for c in KEYS},
            "ladder_orders": {},
        }
        for name, order in (("as published", KEYS), ("access first", ["settle_bin", "water_bin", "peat", "depth_bin", "lc", "hist"]),
                            ("land cover first", ["lc", "hist", "peat", "depth_bin", "water_bin", "settle_bin"]),
                            ("reverse", KEYS[::-1])):
            out["attribution"][kind]["ladder_orders"][name] = [
                {"added": LABEL[order[i - 1]] if i else "raw", "ratio": math.exp(est[frozenset(order[:i])])}
                for i in range(len(order) + 1)]
        print(f"  ratio raw x{math.exp(raw):.3f} -> full x{math.exp(full):.3f}; Shapley share of the change in log ratio:")
        for c in KEYS:
            print(f"    {LABEL[c]:<26}{shap[c]:+.4f}  ({100 * shap[c] / (full - raw):+.0f}%)")
        for name, lad in out["attribution"][kind]["ladder_orders"].items():
            print(f"  {name:<17}" + " -> ".join(f"{s_['added'][:10]} {s_['ratio']:.3f}" for s_ in lad))

        # ---- leave-one-out with bootstrap CIs
        pt, pc, _, bs = matched(d, t, KEYS, y, W, bidx)
        q = bs[:, 0] / bs[:, 1]
        full_ci = [float(np.percentile(q, 2.5)), float(np.percentile(q, 97.5))]
        loo = [{"dropped": "none", "ratio": pt / pc, "ci": full_ci}]
        for c in KEYS:
            ks = [x for x in KEYS if x != c]
            a, b_, _, bs_ = matched(d, t, ks, y, W, bidx)
            q_ = bs_[:, 0] / bs_[:, 1]
            loo.append({"dropped": LABEL[c], "ratio": a / b_, "ci": [float(np.percentile(q_, 2.5)), float(np.percentile(q_, 97.5))]})
        out["leave_one_out"][kind] = loo
        print("  leave-one-out:")
        for r in loo:
            print(f"    drop {r['dropped']:<26} x{r['ratio']:.3f} [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]")

        # ---- 3. E-values, benchmarked
        rr = pt / pc
        near = full_ci[1] if rr < 1 else full_ci[0]
        crosses = full_ci[0] <= 1 <= full_ci[1]
        shifts = {r["dropped"]: max(r["ratio"], rr) / min(r["ratio"], rr) for r in loo[1:]}
        out["sensitivity"][kind] = {
            "ratio": rr, "ci": full_ci, "evalue_point": evalue(rr),
            "evalue_ci": 1.0 if crosses else evalue(near),
            "measured_shift_when_dropped": shifts,
            "largest_measured_shift": max(shifts.values()),
        }
        S = out["sensitivity"][kind]
        print(f"  E-value: point {S['evalue_point']:.2f}, CI {S['evalue_ci']:.2f}; largest shift from dropping one "
              f"measured covariate x{S['largest_measured_shift']:.3f} ({max(shifts, key=shifts.get)})")

    json.dump(out, open(RES, "w"), indent=1, default=float)
    print(f"\nSaved: {RES}")


if __name__ == "__main__":
    main()
