#!/usr/bin/env python3
"""Spatial cross-validation of the peat random forest over ALL field points.

The final model (peat_rf_gee.py --stage final) was scored on one 30% draw of
the 50 km field blocks (AUC 0.80). Here every field block is held out once:

  folds    the 50 km blocks that contain field points, split into K groups
           (GroupKFold on shuffled blocks); repeated R times with different
           assignments
  train    every row outside the held-out blocks (hotspot-derived and field
           points), field rows weighted w
  test     the field points inside the held-out blocks (nothing from those
           blocks is in training)
  designs  w = 0  hotspot-derived labels only (no field data in training)
           w = 1  field points as ordinary rows
           w = 10 the final model's weight
  CI       block bootstrap over the 50 km field blocks

Thresholds: AUC is threshold-free; accuracy / balanced accuracy / kappa at
the final model's calibrated 0.61 and at 0.5. The feature set is the final
model's (chosen by forward selection on all rows, so slightly optimistic for
every design alike).

    conda run -n base python scripts/peat_rf_spatial_cv.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from peat_rf_gee import OUT, SEED  # noqa: E402

K, REPEATS, NBOOT = 10, 5, 1000
WEIGHTS = (0, 1, 10)


def main():
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score, balanced_accuracy_score, accuracy_score, cohen_kappa_score

    rep = json.load(open(os.path.join(OUT, "final_report.json")))
    sel, thr = rep["selected"], rep["threshold"]
    d = pd.read_csv(os.path.join(OUT, "samples.csv")).dropna(subset=sel).reset_index(drop=True)
    fblocks = np.array(sorted(d.loc[d.field == 1, "block"].unique()))
    print(f"{len(d):,} rows, {int(d.field.sum()):,} field points in {len(fblocks)} field blocks; "
          f"features {sel}")

    def rf():
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=2, n_jobs=-1,
                                      class_weight="balanced", random_state=SEED)

    F = d[d.field == 1].reset_index()
    out = {}
    pred = {w: np.zeros((REPEATS, len(F))) for w in WEIGHTS}
    for r in range(REPEATS):
        rng = np.random.default_rng(SEED + r)
        order = rng.permutation(fblocks)
        groups = np.array_split(order, K)
        for g in groups:
            hold = d.block.isin(g)
            tr = d[~hold]
            te = F.block.isin(g).to_numpy()
            for w in WEIGHTS:
                t = tr if w > 0 else tr[tr.field == 0]
                sw = np.where(t.field == 1, w, 1.0) if w > 0 else None
                m = rf().fit(t[sel], t.y, sample_weight=sw)
                pred[w][r, te] = m.predict_proba(F.loc[te, sel])[:, 1]
        print(f"  repeat {r + 1}/{REPEATS} done")

    y = F.y.to_numpy()
    bl = F.block.to_numpy()
    ub = np.unique(bl)
    rng = np.random.default_rng(SEED)
    rows = []
    for w in WEIGHTS:
        P = pred[w]
        aucs = [roc_auc_score(y, P[r]) for r in range(REPEATS)]
        p = P.mean(0)                                   # average over repeats
        res = {"field_weight": w, "auc_mean_over_repeats": float(np.mean(aucs)),
               "auc_range_over_repeats": [float(min(aucs)), float(max(aucs))]}
        boot = []
        idx = {b: np.nonzero(bl == b)[0] for b in ub}
        for _ in range(NBOOT):
            s = np.concatenate([idx[b] for b in rng.choice(ub, len(ub))])
            if len(set(y[s])) > 1:
                boot.append(roc_auc_score(y[s], p[s]))
        res["auc_ci95_block_bootstrap"] = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
        for t in (thr, 0.5):
            yh = (p >= t).astype(int)
            res[f"at_{t}"] = {"acc": accuracy_score(y, yh), "balanced_acc": balanced_accuracy_score(y, yh),
                              "kappa": cohen_kappa_score(y, yh), "peat_called": float(yh.mean()),
                              "recall_peat": float(yh[y == 1].mean()),
                              "false_peat_on_mineral": float(yh[y == 0].mean())}
        # per field block, to see where it fails
        per = []
        for b in ub:
            m_ = bl == b
            per.append({"block": int(b), "n": int(m_.sum()), "peat_share": float(y[m_].mean()),
                        "auc": float(roc_auc_score(y[m_], p[m_])) if len(set(y[m_])) > 1 else None,
                        "acc_at_thr": float(((p[m_] >= thr) == y[m_]).mean())})
        res["per_block"] = per
        out[str(w)] = res
        a = res[f"at_{thr}"]
        rows.append({"field weight": w, "AUC": res["auc_mean_over_repeats"],
                     "AUC 95% CI": res["auc_ci95_block_bootstrap"], "AUC over repeats": res["auc_range_over_repeats"],
                     "acc": a["acc"], "bal acc": a["balanced_acc"], "kappa": a["kappa"],
                     "peat found": a["recall_peat"], "mineral called peat": a["false_peat_on_mineral"]})
    pd.set_option("display.width", 220)
    T = pd.DataFrame(rows)
    print(f"\nall {len(F):,} field points, each scored once per repeat (threshold {thr}):")
    print(T.round(3).to_string(index=False))
    pb = pd.DataFrame(out["10"]["per_block"]).sort_values("n", ascending=False)
    print("\nfield weight 10, by field block (largest first):")
    print(pb.head(15).round(3).to_string(index=False))
    print("holdout blocks of the final model:", rep["holdout_blocks"])
    json.dump({"selected": sel, "threshold": thr, "K": K, "repeats": REPEATS, "results": out},
              open(os.path.join(OUT, "spatial_cv_all_field.json"), "w"), indent=1)
    print(f"Saved: {OUT}/spatial_cv_all_field.json")


if __name__ == "__main__":
    sys.exit(main())
