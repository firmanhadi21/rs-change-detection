#!/usr/bin/env python3
"""Review round 3, Mo3: the oil-palm excess model has 51 events for ~14 covariates, so the maximum-
likelihood logit (kalimantan_dc_units_summary.py, HC1 errors) is small-sample biased. Refit with Firth's
penalised likelihood (Jeffreys prior, Firth 1993; Heinze & Schemper 2002), profile penalised-likelihood
95% intervals and penalised likelihood-ratio p-values.

Same units, classes (per_concession_matched_dc.csv, drought-matched), covariates and scaling as
kalimantan_dc_units_summary.py; plus V1 (BBSDLP share + PEATGRIDS depth on peat) as in
kalimantan_peat_depth_checks.py. Writes output/fire/kalimantan_excess/firth.json.

    python scripts/kalimantan_firth.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import DATA, OUT  # noqa: E402
from kalimantan_heterogeneity import SHARE_STEP  # noqa: E402

RES = os.path.join(OUT, "firth.json")
CTRL = ["forest_share_z", "log_area_z", "ind_share_10pp", "small_share_10pp", "recent_share_10pp", "st_in_process",
        "st_location_permit", "st_unknown", "grouped", "rspo_cert_share_10pp", "rspo_member_share_10pp",
        "other_permit_share_10pp"]


def penloglik(b, X, y):
    import numpy as np
    eta = X @ b
    p = 1 / (1 + np.exp(-eta))
    ll = np.sum(y * eta - np.logaddexp(0, eta))
    w = p * (1 - p)
    sign, logdet = np.linalg.slogdet(X.T @ (X * w[:, None]))
    return ll + 0.5 * logdet


def firth(X, y, fixed=None, b0=None, tol=1e-9, it=200):
    """Firth estimate by modified-score Newton steps; `fixed` = (j, value) holds one coefficient."""
    import numpy as np
    n, k = X.shape
    b = np.zeros(k) if b0 is None else b0.copy()
    free = np.ones(k, bool)
    if fixed is not None:
        b[fixed[0]], free[fixed[0]] = fixed[1], False
    for _ in range(it):
        p = 1 / (1 + np.exp(-(X @ b)))
        w = p * (1 - p)
        XW = X * w[:, None]
        I = X.T @ XW
        Iinv = np.linalg.pinv(I)
        h = np.einsum("ij,jk,ik->i", XW, Iinv, X)            # hat diagonal
        U = X.T @ (y - p + h * (0.5 - p))
        Uf, If = U[free], I[np.ix_(free, free)]
        step = np.linalg.solve(If, Uf)
        mx = np.max(np.abs(step))
        if mx > 5:
            step *= 5 / mx
        b_new = b.copy()
        b_new[free] += step
        # step-halving on the penalised log-likelihood
        f0 = penloglik(b, X, y)
        for _ in range(30):
            if penloglik(b_new, X, y) >= f0 - 1e-12:
                break
            step /= 2
            b_new = b.copy()
            b_new[free] += step
        b = b_new
        if np.max(np.abs(step)) < tol:
            break
    return b


def profile(X, y, b, j, chi=3.841458820694124):
    """Profile penalised-likelihood interval for coefficient j: {beta_j : 2 (l* - l*_j) <= chi2_1}."""
    import numpy as np
    from scipy.optimize import brentq
    lmax = penloglik(b, X, y)
    f = lambda v: 2 * (lmax - penloglik(firth(X, y, fixed=(j, v), b0=b), X, y)) - chi   # noqa: E731
    se = np.sqrt(np.diag(np.linalg.pinv(X.T @ (X * ((p := 1 / (1 + np.exp(-(X @ b)))) * (1 - p))[:, None]))))[j]
    out = []
    for sgn in (-1, 1):
        step, lo_ = se, b[j]
        hi_ = b[j] + sgn * step
        k = 0
        while f(hi_) < 0 and k < 40:
            lo_, hi_ = hi_, hi_ + sgn * step
            step *= 1.6
            k += 1
        out.append(brentq(f, min(lo_, hi_), max(lo_, hi_), xtol=1e-6) if k < 40 else float("inf") * sgn)
    pval_stat = 2 * (lmax - penloglik(firth(X, y, fixed=(j, 0.0), b0=b), X, y))
    from scipy.stats import chi2
    return out[0], out[1], float(chi2.sf(max(pval_stat, 0), 1))


def units():
    import pandas as pd
    U = pd.read_csv(os.path.join(OUT, "heterogeneity_units.csv")).drop(columns=["excess"])
    B = pd.read_csv(os.path.join(OUT, "per_concession_matched_dc.csv"))[["kind", "id", "class_fdr"]]
    C = pd.read_csv(os.path.join(DATA, "peat_check_covariates.csv"))[["kind", "id", "peat_share", "gpm_share",
                                                                      "depth_on_peat_cm"]]
    D = U.drop(columns=["class_fdr"], errors="ignore").merge(B, on=["kind", "id"]) \
         .merge(C.rename(columns={"peat_share": "ps"}), on=["kind", "id"])
    O = D[D.kind == "oil palm"].copy()
    O["excess"] = O.class_fdr.eq("excess")
    z = lambda x: (x - x.mean()) / x.std()      # noqa: E731
    for c in ("depth_m", "forest_share", "log_area", "depth_on_peat_cm"):
        O[c + "_z"] = z(O[c].fillna(0))
    O["peat_share_10pp"], O["gpm_share_10pp"] = O.ps / SHARE_STEP, O.gpm_share.fillna(0) / SHARE_STEP
    return O


def main():
    import numpy as np
    O = units()
    y = O.excess.to_numpy(float)
    out = {"n": int(len(O)), "n_excess": int(y.sum()), "models": {}}
    print(f"oil palm: n={len(O)}, excess={int(y.sum())} (drought-matched classes)")
    for name, terms in (("main (depth)", ["depth_m_z"]), ("BBSDLP share", ["peat_share_10pp"]),
                        ("GPM share", ["gpm_share_10pp"]),
                        ("V1 share + depth on peat", ["peat_share_10pp", "depth_on_peat_cm_z"])):
        cols = terms + CTRL
        X = np.column_stack([np.ones(len(O)), O[cols].astype(float).to_numpy()])
        b = firth(X, y)
        res = {}
        for j, c in enumerate(cols, start=1):
            lo, hi, p = profile(X, y, b, j)
            res[c] = {"or": float(np.exp(b[j])), "lo": float(np.exp(lo)), "hi": float(np.exp(hi)), "p": p}
        out["models"][name] = res
        print(f"\n== {name}")
        for c in cols:
            r = res[c]
            print(f"  {c:<26} OR {r['or']:5.2f} [{r['lo']:5.2f}, {r['hi']:5.2f}]  p {r['p']:.3f}")
    json.dump(out, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
