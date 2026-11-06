#!/usr/bin/env python3
"""Review round 2, M2: is the concentration of concession burned area more than fire clustering
would give any partition of the land?

Pseudo-units (v2, review round 3): for each concession, a patch of unpermitted land (zone 1) with exactly
as many analysable cells as the concession, grown as the n nearest unpermitted analysable cells around a
random seed cell; the seed is drawn from unpermitted analysable cells in the concession's dominant
season-peak Drought Code band, so patches match concessions on size and drought. (v1 used square tiles
sized round(sqrt(n)) on all cells, which made them ~60% of concession analysable size; its output is kept
as concentration_benchmark_v1_tiles.json.) Each patch gets exactly the per-concession treatment of
kalimantan_concession_checks.py --dc-stratum: drought-matched ratio (SEQ[-1] + peak-DC band) against
unpermitted controls across Kalimantan, with the patch's own cells removed from the control pool, 2,000
block-bootstrap draws, percentile p, Benjamini-Hochberg at q <= 0.05 within each replicate. Patches may
overlap one another. Reported per replicate: share in excess, share of patch burned area they hold, zero-burn
patches, excess share among patches that burned, and patch spread (distance to the n-th cell).

Patches are unmanaged land and shaped by where unpermitted land lies, so this is a benchmark for "a few
units hold much of the burned area", not a matched counterfactual for any concession.

    python scripts/kalimantan_concentration_benchmark.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_dc_stratum import peak_dc_bin  # noqa: E402
from kalimantan_excess_burn import DATA, HTI, OUT, SEQ, stratum  # noqa: E402

RES = os.path.join(OUT, "concentration_benchmark.json")
MIN_CELLS, Q_FDR, NBOOT_UNIT, REPS = 250, 0.05, 2000, 5


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
    from scipy import sparse

    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"),
                         columns=sorted(set(["r", "c", "zone", "op", "valid", "burned", "block"] + SEQ[-1])))
    dv = df[df.valid].reset_index(drop=True)
    dv["dc_bin"] = peak_dc_bin(dv)
    code = stratum(dv, SEQ[-1] + ["dc_bin"])
    s_codes, s_all = np.unique(code, return_inverse=True)
    ns = len(s_codes)
    blocks = np.unique(dv.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    b_all = bidx[dv.block.to_numpy()].to_numpy()
    nb = len(blocks)
    rng = np.random.default_rng(42)
    Wu = np.vstack([np.ones(nb), rng.multinomial(nb, np.ones(nb) / nb, size=NBOOT_UNIT)]).astype(np.float32)
    ctl = (dv.zone == 1).to_numpy()
    val = dv.burned.to_numpy(np.float32)

    def sums(m):
        g = pd.DataFrame({"b": b_all[m], "s": s_all[m], "v": val[m]}) \
            .groupby(["b", "s"]).agg(n=("v", "size"), x=("v", "sum")).reset_index()
        return g.b.to_numpy(), g.s.to_numpy(), g.n.to_numpy(np.float32), g.x.to_numpy(np.float32)

    b, s, n, x = sums(ctl)
    Cn = np.asarray((sparse.csr_matrix((n, (b, s)), shape=(nb, ns)).T @ Wu.T).T)
    Cx = np.asarray((sparse.csr_matrix((x, (b, s)), shape=(nb, ns)).T @ Wu.T).T)

    def unit(m):
        b, s, n, x = sums(m)
        us, si = np.unique(s, return_inverse=True)
        ub, bi = np.unique(b, return_inverse=True)
        w = Wu[:, ub]
        tn = np.asarray((sparse.csr_matrix((n, (bi, si)), shape=(len(ub), len(us))).T @ w.T).T)
        tx = np.asarray((sparse.csr_matrix((x, (bi, si)), shape=(len(ub), len(us))).T @ w.T).T)
        cn, cx = Cn[:, us] - tn, Cx[:, us] - tx          # the tile's own cells out of the control pool
        ok = (tn > 0) & (cn > 0)
        T = np.where(ok, tx, 0).sum(1)
        E = np.where(ok, tn * cx / np.where(cn > 0, cn, 1), 0).sum(1)
        TN = np.where(ok, tn, 0).sum(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            q = T / E
        qb = q[1:][(TN[1:] > 0) & (E[1:] > 0)]
        B = len(qb)
        p = min(1.0, 2 * (min((qb <= 1).sum(), (qb >= 1).sum()) + 1) / (B + 1)) if B else 1.0
        return q[0], p

    P = pd.read_csv(os.path.join(OUT, "per_concession_matched_dc.csv"))
    r, c = dv.r.to_numpy(), dv.c.to_numpy()
    out = {"concessions": {}, "replicates": [], "min_cells": MIN_CELLS, "q_fdr": Q_FDR}
    for kind in ("oil palm", "pulpwood"):
        g = P[P.kind == kind]
        ex = g.class_fdr == "excess"
        out["concessions"][kind] = {"units": int(len(g)), "excess_pct": 100 * float(ex.mean()),
                                    "zero_burn_units": int((g.burned_km2 == 0).sum()),
                                    "excess_pct_of_burning": 100 * float(ex.sum() / (g.burned_km2 > 0).sum()),
                                    "median_cells": float(g.cells.median()),
                                    "excess_share_pct": 100 * float(g.burned_km2[ex].sum() / g.burned_km2.sum())}
    from scipy.spatial import cKDTree
    cidx = np.flatnonzero(ctl)
    tree = cKDTree(np.c_[r[cidx], c[cidx]])
    cband = dv.dc_bin.to_numpy()[cidx]
    # dominant drought band of each concession (pulpwood ids rasterised as in kalimantan_concession_checks)
    import geopandas as gpd
    import rasterio
    from rasterio import features
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    hid = features.rasterize([(gg, i + 1) for i, gg in enumerate(hti.geometry.make_valid())],
                             out_shape=tuple(grid["shape"]), transform=rasterio.Affine(*grid["transform"]),
                             dtype="int32")[r, c]
    bands = dv.dc_bin.to_numpy()
    uid = np.where(dv.zone == 3, dv.op.to_numpy(), np.where(dv.zone == 2, -hid, 0))
    dom = pd.DataFrame({"u": uid, "b": bands})[uid != 0].groupby("u").b.agg(lambda x: int(np.bincount(x).argmax()))
    for rep in range(REPS):
        for kind in ("oil palm", "pulpwood"):
            g = P[P.kind == kind]
            rows = []
            for _, u in g.iterrows():
                key = int(u.id) if kind == "oil palm" else -int(u.id)
                band = int(dom[key]) if key in dom.index else None
                pool = np.flatnonzero(cband == band) if band is not None else np.arange(len(cidx))
                seed = pool[rng.integers(len(pool))]
                n = int(u.cells)
                dist, nb = tree.query(np.c_[r[cidx[seed]], c[cidx[seed]]], k=n)
                m = np.zeros(len(dv), bool)
                m[cidx[np.atleast_1d(nb).ravel()]] = True
                q, p = unit(m)
                rows.append({"cells": int(m.sum()), "ratio": float(q), "p": float(p), "band": band,
                             "spread_km": 0.2 * float(np.atleast_1d(dist).ravel()[-1]),
                             "burned_km2": 0.04 * float(val[m].sum())})
            T = pd.DataFrame(rows)
            T["q_bh"] = bh(T.p.to_numpy())
            exc = (T.q_bh <= Q_FDR) & (T.ratio > 1)
            burning = T.burned_km2 > 0
            res = {"replicate": rep, "kind_sizes": kind, "units": int(len(T)), "excess": int(exc.sum()),
                   "excess_pct": 100 * float(exc.mean()),
                   "excess_share_pct": 100 * float(T.burned_km2[exc].sum() / T.burned_km2.sum()),
                   "deficit": int(((T.q_bh <= Q_FDR) & (T.ratio < 1)).sum()),
                   "zero_burn_units": int((~burning).sum()),
                   "excess_pct_of_burning": 100 * float(exc.sum() / burning.sum()),
                   "median_cells": float(T.cells.median()), "median_spread_km": float(T.spread_km.median())}
            out["replicates"].append(res)
            print(f"  rep {rep} {kind:<9}: {res['excess']}/{res['units']} patches excess ({res['excess_pct']:.1f}%), "
                  f"holding {res['excess_share_pct']:.0f}%; zero-burn {res['zero_burn_units']}, "
                  f"excess among burning {res['excess_pct_of_burning']:.1f}%, median cells {res['median_cells']:.0f}, "
                  f"spread {res['median_spread_km']:.1f} km", flush=True)
    for kind, cc in out["concessions"].items():
        print(f"  concessions {kind}: {cc['excess_pct']:.1f}% excess holding {cc['excess_share_pct']:.0f}%")
    json.dump(out, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
