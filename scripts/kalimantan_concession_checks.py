#!/usr/bin/env python3
"""Kalimantan follow-ups to the matched concession effect (WP2): outcome checks and
per-concession matched ratios.

Runs on the 200 m sample of kalimantan_excess_burn.py (--stage sample) and reuses its
CEM estimator (matched, stratum, SEQ: all pre-treatment covariates) and 5 km block
bootstrap.

1. OUTCOME CHECKS. The main outcome is S2 burned (>= half of the cloud-free 20 m pixels
   in the cell with dNBR >= 0.27, within ~750 m of a VIIRS detection). Sentinel-2 can miss
   ground fire under a closed palm canopy, which would bias oil palm downwards. So:
     burned25      the same with >= a quarter of the cell burned
     viirs_cell    a VIIRS detection (any confidence) within ~300 m in Jun-Oct; needs no
                   S2, so all land cells are used
     viirs_count   nominal/high detections in the cell, Jun-Oct (persistence; ratio of means)
   plus a canopy diagnostic: of cells with a Jun-Oct VIIRS detection, the share S2 calls
   burned, by land-cover class, inside and outside concessions.

2. PER CONCESSION. Every oil-palm concession (GFW c. 2012) and wood-fibre permit with
   >= MIN_CELLS valid cells: matched burned share against unpermitted land in the same
   strata (island-wide controls), ratio and block-bootstrap 95% CI; the same for
   viirs_cell; joined to the lineage own-ignition share (kalimantan_fire_lineage.py) and
   to descriptors (peat share, mean depth, planted-palm share, area, company group).

    conda run -n base python scripts/kalimantan_concession_checks.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import (BANDS, CONC, DATA, HTI, KAL, NAMES, NBOOT, OUT, SEQ,  # noqa: E402
                                    STACK, matched, stratum)

MIN_CELLS = 250          # 10 km2 of cloud-free land
Q_FDR = 0.05             # Benjamini-Hochberg false discovery rate, per concession type
NBOOT_UNIT = 2000        # per-unit bootstrap draws (BH over ~900 units needs p < 1/300)
LINEAGE = os.path.join(os.path.dirname(OUT), "kalimantan_lineage", "per_concession.csv")


def main():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from scipy import ndimage
    from scipy.stats import spearmanr

    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"))
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, shape = rasterio.Affine(*grid["transform"]), tuple(grid["shape"])
    r, c = df.r.to_numpy(), df.c.to_numpy()

    # --- extra outcomes ---------------------------------------------------------
    with rasterio.open(STACK) as ds:
        bfrac = ds.read(BANDS.index("bfrac") + 1)[r, c]
        okfrac = ds.read(BANDS.index("okfrac") + 1)[r, c]
    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"))
    day = ((pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)).dt.normalize()
           - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy()))
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    seen = np.zeros(shape, bool)
    seen[rr[ok], cc[ok]] = True
    near = ndimage.binary_dilation(seen, np.ones((3, 3), bool), iterations=3)[r, c]   # as in sample
    sea = ok & (day >= 152) & (day < 305)
    cnt = np.zeros(shape, np.int32)
    np.add.at(cnt, (rr[sea & (v.confidence.to_numpy() >= 1)], cc[sea & (v.confidence.to_numpy() >= 1)]), 1)
    sseen = np.zeros(shape, bool)
    sseen[rr[sea], cc[sea]] = True
    df["burned25"] = df.valid & (bfrac * 4 >= okfrac) & (bfrac > 0) & near
    df["viirs_cell"] = ndimage.binary_dilation(sseen, np.ones((3, 3), bool))[r, c]
    df["viirs_count"] = cnt[r, c]

    # --- unit ids for wood-fibre permits ------------------------------------------
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    hti_id = features.rasterize([(g, i + 1) for i, g in enumerate(hti.geometry.make_valid())],
                                out_shape=shape, transform=tr, dtype="int32")
    df["hti_id"] = hti_id[r, c]
    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]].reset_index(drop=True)

    blocks_all = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks_all)), index=blocks_all)
    rng = np.random.default_rng(42)
    boot_w = rng.multinomial(len(blocks_all), np.ones(len(blocks_all)) / len(blocks_all),
                             size=NBOOT).astype(float)
    full = SEQ[-1]
    out = {"outcomes": [], "canopy": None, "per_concession": None}

    # --- 1. outcome checks ---------------------------------------------------------
    for outcome, base in (("burned", "valid"), ("burned25", "valid"), ("viirs_cell", None),
                          ("viirs_count", None)):
        d0 = df[df[base]] if base else df
        for z, label in ((3, "oil palm"), (2, "pulpwood")):
            d = d0[d0.zone.isin([1, z])].reset_index(drop=True)
            for nm, keys in ((NAMES[0], SEQ[0]), (NAMES[-1], full)):
                pt, pc, cov, bs = matched(d, (d.zone == z).to_numpy(), keys,
                                          d[outcome].to_numpy(float), boot_w, bidx)
                q = bs[:, 0] / bs[:, 1]
                ci = [float(np.percentile(q, 2.5)), float(np.percentile(q, 97.5))]
                out["outcomes"].append({"outcome": outcome, "treated": label, "matched_on": nm,
                                        "treated_mean": pt, "control_mean": pc, "ratio": pt / pc,
                                        "ci95": ci, "coverage": cov})
                print(f"  {outcome:<12} {label:<9} {nm:<26} {pt:8.4f} vs {pc:8.4f}  x{pt / pc:.2f} "
                      f"[{ci[0]:.2f}, {ci[1]:.2f}]")

    # canopy diagnostic: of VIIRS-seen valid cells, share S2 calls burned, by land cover
    d = df[df.valid & df.viirs_cell]
    can = (d.assign(where=np.where(d.zone == 1, "unpermitted", np.where(d.zone == 3, "oil palm", "pulpwood")))
           .groupby(["lc", "where"]).agg(n=("burned", "size"), s2_burned=("burned", "mean"))
           .unstack("where"))
    print("\nS2-burned share of VIIRS-seen cells, by land cover (0-3 palm by age, 4 standing forest, "
          "5-6 forest cleared, 7 non-forest):")
    print(can.round(3).to_string())
    out["canopy"] = {f"{k[0]}|{k[1]}|{lc}": float(v_) for k, col in can.items() for lc, v_ in col.items()
                     if np.isfinite(v_)}

    # --- 2. per concession ---------------------------------------------------------
    dv = df[df.valid].reset_index(drop=True)
    code = stratum(dv, full)
    s_codes, s_all = np.unique(code, return_inverse=True)
    ns = len(s_codes)
    b_all = bidx[dv.block.to_numpy()].to_numpy()
    ctl = (dv.zone == 1).to_numpy()

    # 2,000 block-bootstrap draws for the per-unit tests: Benjamini-Hochberg over ~900 units
    # needs percentile p-values well below 1/300. Sums by (block, stratum) as sparse matrices,
    # so each draw is one matrix product: weights (draws x blocks) @ sums (blocks x strata).
    from scipy import sparse
    nb = len(blocks_all)
    Wu = np.vstack([np.ones(nb), rng.multinomial(nb, np.ones(nb) / nb, size=NBOOT_UNIT)]).astype(np.float32)

    def bs_sums(m, val):
        g = pd.DataFrame({"b": b_all[m], "s": s_all[m], "v": val[m]}) \
            .groupby(["b", "s"]).agg(n=("v", "size"), x=("v", "sum")).reset_index()
        return g.b.to_numpy(), g.s.to_numpy(), g.n.to_numpy(np.float32), g.x.to_numpy(np.float32)

    def control_tables(val):
        b, s, n, x = bs_sums(ctl, val)
        N = sparse.csr_matrix((n, (b, s)), shape=(nb, ns))
        X = sparse.csr_matrix((x, (b, s)), shape=(nb, ns))
        return (N.T @ Wu.T).T, (X.T @ Wu.T).T          # (draws+1) x strata; row 0 = point estimate

    tabs = {k: control_tables(dv[k].to_numpy(np.float32)) for k in ("burned", "viirs_cell")}

    def unit_ratio(m, key):
        """Matched ratio for one unit, percentile CI and two-sided bootstrap p (ratio = 1)."""
        Cn, Cx = tabs[key]
        b, s, n, x = bs_sums(m, dv[key].to_numpy(np.float32))
        us, si = np.unique(s, return_inverse=True)
        ub, bi = np.unique(b, return_inverse=True)
        Tn = sparse.csr_matrix((n, (bi, si)), shape=(len(ub), len(us)))
        Tx = sparse.csr_matrix((x, (bi, si)), shape=(len(ub), len(us)))
        w = Wu[:, ub]
        tn, tx = np.asarray((Tn.T @ w.T).T), np.asarray((Tx.T @ w.T).T)
        cn, cx = Cn[:, us], Cx[:, us]
        ok_ = (tn > 0) & (cn > 0)
        T = np.where(ok_, tx, 0).sum(1)
        E = np.where(ok_, tn * cx / np.where(cn > 0, cn, 1), 0).sum(1)
        TN = np.where(ok_, tn, 0).sum(1)
        cov = TN[0] / tn[0].sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            q = T / E
        qb = q[1:][(TN[1:] > 0) & (E[1:] > 0)]          # draws that resampled the unit at all
        lo, hi = np.percentile(qb, [2.5, 97.5])
        B = len(qb)
        p = min(1.0, 2 * (min((qb <= 1).sum(), (qb >= 1).sum()) + 1) / (B + 1))
        return T[0] / TN[0], E[0] / TN[0], q[0], lo, hi, cov, p, B

    lin = pd.read_csv(LINEAGE) if os.path.exists(LINEAGE) else None
    rows = []
    units = [("oil palm", i, (dv.op == i).to_numpy()) for i in np.unique(dv.op[dv.op > 0])] + \
            [("pulpwood", i, ((dv.zone == 2) & (dv.hti_id == i)).to_numpy()) for i in np.unique(dv.hti_id[dv.zone == 2])
             if i > 0]
    print(f"\nper-concession matching over {len(units)} units ...")
    for kind, i, m in units:
        if m.sum() < MIN_CELLS:
            continue
        t_b, c_b, q_b, lo_b, hi_b, cov_b, p_b, nb_b = unit_ratio(m, "burned")
        t_v, c_v, q_v, lo_v, hi_v, _, p_v, _ = unit_ratio(m, "viirs_cell")
        src = op.iloc[i - 1] if kind == "oil palm" else hti.iloc[i - 1]
        luid = (i - 1) if kind == "oil palm" else len(op) + i - 1
        sub = dv[m]
        rows.append({"kind": kind, "id": int(i), "label": src.get("company", None) or src.get("name"),
                     "group": src.get("group_comp"), "cells": int(m.sum()), "area_km2": 0.04 * m.sum(),
                     "burned_pct": 100 * t_b, "matched_ctl_pct": 100 * c_b, "ratio": q_b,
                     "ci_lo": lo_b, "ci_hi": hi_b, "coverage": cov_b, "p": p_b, "boot_draws": nb_b,
                     "viirs_cell_pct": 100 * t_v, "viirs_ctl_pct": 100 * c_v, "viirs_ratio": q_v,
                     "viirs_ci_lo": lo_v, "viirs_ci_hi": hi_v, "viirs_p": p_v,
                     "peat_share": float(sub.peat.mean()), "mean_depth_cm": float(sub.thick.mean()),
                     "palm_share": float(sub.lc.isin([0, 1, 2, 3]).mean()),
                     "forest_share": float((sub.lc == 4).mean()),
                     "burned_km2": 0.04 * float(sub.burned.sum()), "lineage_uid": int(luid)})
    P = pd.DataFrame(rows)
    if lin is not None:
        P = P.merge(lin[["uid", "own", "ignitions"]].rename(columns={"uid": "lineage_uid", "own": "own_ignition_share"}),
                    on="lineage_uid", how="left")
    P["class"] = np.where(P.ci_lo > 1, "excess", np.where(P.ci_hi < 1, "deficit", "no difference"))
    # FDR: two-sided percentile-bootstrap p (share of draws on the far side of ratio 1),
    # Benjamini-Hochberg at Q_FDR within each concession type. (A normal approximation on
    # the log ratio was tried and rejected: draws with ratio 0, common for units in few
    # blocks, have no log, so its s.e. came out too small and it called more units than
    # the uncorrected 95% intervals.)
    P["q_bh"] = np.nan
    for kind in P.kind.unique():
        k = (P.kind == kind).to_numpy()
        pk = P.p.to_numpy()[k]
        o = np.argsort(pk)
        adj = np.minimum.accumulate((pk[o] * len(pk) / np.arange(1, len(pk) + 1))[::-1])[::-1]
        qv = np.empty_like(pk)
        qv[o] = np.minimum(adj, 1)
        P.loc[k, "q_bh"] = qv
    P["class_fdr"] = np.where(P.q_bh <= Q_FDR, np.where(P.ratio > 1, "excess", "deficit"), "no difference")
    P = P.sort_values("burned_km2", ascending=False)
    os.makedirs(OUT, exist_ok=True)
    P.to_csv(os.path.join(OUT, "per_concession_matched.csv"), index=False)

    summ = {}
    for kind in ("oil palm", "pulpwood"):
        q = P[P.kind == kind]
        cl = q["class"].value_counts()
        cf = q["class_fdr"].value_counts()
        summ[kind] = {"units": int(len(q)), **{k: int(cl.get(k, 0)) for k in ("excess", "no difference", "deficit")},
                      "fdr": {**{k: int(cf.get(k, 0)) for k in ("excess", "no difference", "deficit")},
                              "burned_km2_in_excess_units":
                                  float(q.burned_km2[q["class_fdr"] == "excess"].sum())},
                      "burned_km2_total": float(q.burned_km2.sum()),
                      "burned_km2_in_excess_units": float(q.burned_km2[q["class"] == "excess"].sum()),
                      "median_ratio": float(q.ratio.median())}
        lr = np.log(q.ratio.clip(lower=0.01))
        summ[kind]["spearman_log_ratio"] = {
            k: float(spearmanr(lr, q[k], nan_policy="omit").statistic)
            for k in ("peat_share", "mean_depth_cm", "palm_share", "forest_share", "area_km2",
                      "own_ignition_share") if k in q}
        ex, rest = q[q["class_fdr"] == "excess"], q[q["class_fdr"] != "excess"]
        summ[kind]["excess_vs_rest_medians"] = {
            k: [float(ex[k].median()), float(rest[k].median())]
            for k in ("peat_share", "mean_depth_cm", "palm_share", "forest_share", "area_km2",
                      "own_ignition_share") if k in q}
        summ[kind]["excess_groups"] = ex.group.fillna("?").value_counts().head(8).to_dict()
    out["per_concession"] = summ
    from ketapang_fire_origin import FOUR
    k4 = P[P.label.fillna("").str.contains("|".join(FOUR.values()), case=False)]
    out["ketapang_four"] = k4[["label", "ratio", "ci_lo", "ci_hi", "q_bh", "burned_km2"]].to_dict("records")
    json.dump(out, open(os.path.join(OUT, "concession_checks.json"), "w"), indent=1, default=float)
    print(json.dumps(summ, indent=1, default=float))
    pd.set_option("display.width", 250)
    print(P.head(20)[["kind", "label", "group", "area_km2", "burned_pct", "matched_ctl_pct", "ratio", "ci_lo",
                      "ci_hi", "viirs_ratio", "peat_share", "palm_share", "own_ignition_share"]].round(2).to_string())
    print("\nKetapang four:", json.dumps(out["ketapang_four"], default=float))
    print(f"Saved: {OUT}/per_concession_matched.csv, concession_checks.json")


if __name__ == "__main__":
    sys.exit(main())
