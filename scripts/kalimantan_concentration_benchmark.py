#!/usr/bin/env python3
"""Review round 2, M2: is the concentration of concession burned area more than fire clustering
would give any partition of the land?

Pseudo-units are square tiles of unpermitted land (zone 1) whose sizes follow the concessions':
each concession's analysable cell count is mapped to a tile of the same number of cells (side
round(sqrt(n)), on a lattice with a random offset), and one tile is drawn per concession from the
tiles of that side with >= MIN_CELLS unpermitted analysable cells. Each tile then gets exactly the
per-concession treatment of kalimantan_concession_checks.py --dc-stratum: drought-matched ratio
(SEQ[-1] + peak-DC band) against unpermitted controls across Kalimantan, with the tile's own cells
removed from the control pool, 2,000 block-bootstrap draws, percentile p, Benjamini-Hochberg at
q <= 0.05 within each replicate. Reported per replicate: share of pseudo-units in excess and the
share of pseudo-unit burned area they hold, against the concessions (51/908 -> 40%; 14/187 -> 52%).

Tiles are compact and unpermitted land is not managed, so this is a benchmark for "a few units
hold much of the burned area", not a matched counterfactual for any concession.

    python scripts/kalimantan_concentration_benchmark.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_dc_stratum import peak_dc_bin  # noqa: E402
from kalimantan_excess_burn import DATA, OUT, SEQ, stratum  # noqa: E402

RES = os.path.join(OUT, "concentration_benchmark.json")
MIN_CELLS, Q_FDR, NBOOT_UNIT, REPS = 250, 0.05, 2000, 3


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
                         columns=sorted(set(["r", "c", "zone", "valid", "burned", "block"] + SEQ[-1])))
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
                                    "excess_share_pct": 100 * float(g.burned_km2[ex].sum() / g.burned_km2.sum())}
    for rep in range(REPS):
        tiles = {}                                            # side -> (tile id per control cell)
        for kind in ("oil palm", "pulpwood"):
            sizes = P[P.kind == kind].cells.to_numpy()
            rows = []
            for side in np.unique(np.round(np.sqrt(sizes)).astype(int)):
                if side not in tiles:
                    oy, ox = rng.integers(0, side, 2)
                    tid = ((r + oy) // side) * 100000 + (c + ox) // side
                    t = pd.Series(np.where(ctl, tid, -1))
                    cnt = t[t >= 0].value_counts()
                    tiles[side] = (t.to_numpy(), cnt[cnt >= MIN_CELLS].index.to_numpy())
                tid, eligible = tiles[side]
                need = int((np.round(np.sqrt(sizes)).astype(int) == side).sum())
                if len(eligible) == 0:
                    continue
                for k in rng.choice(eligible, size=need, replace=len(eligible) < need):
                    m = tid == k
                    q, p = unit(m)
                    rows.append({"side": int(side), "cells": int(m.sum()), "ratio": float(q), "p": float(p),
                                 "burned_km2": 0.04 * float(val[m].sum())})
            T = pd.DataFrame(rows)
            T["q_bh"] = bh(T.p.to_numpy())
            exc = (T.q_bh <= Q_FDR) & (T.ratio > 1)
            res = {"replicate": rep, "kind_sizes": kind, "units": int(len(T)), "excess": int(exc.sum()),
                   "excess_pct": 100 * float(exc.mean()),
                   "excess_share_pct": 100 * float(T.burned_km2[exc].sum() / T.burned_km2.sum()),
                   "deficit": int(((T.q_bh <= Q_FDR) & (T.ratio < 1)).sum()),
                   "zero_burn_units": int((T.burned_km2 == 0).sum()),
                   "median_cells": float(T.cells.median())}
            out["replicates"].append(res)
            print(f"  rep {rep} {kind:<9} sizes: {res['excess']}/{res['units']} pseudo-units excess "
                  f"({res['excess_pct']:.1f}%), holding {res['excess_share_pct']:.0f}% of their burned area; "
                  f"deficit {res['deficit']}, zero-burn {res['zero_burn_units']}", flush=True)
    for kind, cc in out["concessions"].items():
        print(f"  concessions {kind}: {cc['excess_pct']:.1f}% excess holding {cc['excess_share_pct']:.0f}%")
    json.dump(out, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
