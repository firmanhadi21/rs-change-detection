"""Where will oil palm be planted next in Kalimantan? A conversion-risk model on the 500 m MODIS panel.

Outcome: a cell that is under 50% oil palm (industrial + smallholder, Descals et al. 2024 planting years)
at the end of year s becomes >= 50% palm within the next three years (s+1 .. s+3). Predictors describe
the cell at the end of year s: closeness to existing palm, concessions, forest-area status, peat, forest
condition, recent clearing, fire, access and terrain. Planting years end in 2021 and planting after ~2019
is under-detected, so the model is trained on s = 2002-2016 (outcomes up to 2019).

Builds on scripts/kalimantan_palm_fire_panel.py (panel) and scripts/kalimantan_fire_factors.py (status,
access). Stages:
    python scripts/kalimantan_palm_expansion.py --stage model      # block CV, factor-group ranking
    python scripts/kalimantan_palm_expansion.py --stage forecast   # hindcasts, risk map from end-2021

Outputs in output/fire/kalimantan_palm_panel/: palm_expansion_model.json, palm_expansion_importance.csv,
palm_expansion_forecast.json, palm_expansion_risk.tif.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kalimantan_palm_fire_panel import OUT, CELL_KM, YEARS, _read  # noqa: E402
from kalimantan_fire_factors import ACCESS, STATUS_ORDER, BLOCK_CV_KM, _arrays, _fit  # noqa: E402

H = 3                                   # horizon in years
PALM_LAST = 2019                        # last outcome year trusted in the palm map
S_FIRST, S_LAST = 2002, PALM_LAST - H   # state years used for training
NB_CELLS = 21                           # neighbourhood window (~9.7 km) for the local palm share
GROUPS = {
    "closeness to existing palm": ["d_palm", "d_ind", "nb_palm", "nb_growth", "own_palm"],
    "concessions": ["conc", "hti", "d_conc"],
    "forest-area status (APL etc.)": ["status"],
    "peat": ["peat", "depth"],
    "forest condition": ["und", "deg", "reg"],
    "recent clearing": ["dund", "ddeg"],
    "fire": ["burn", "nburn3"],
    "access & terrain": ACCESS,
    "settlement": ["built00"],
    "climate (mean Jun-Oct rain)": ["rain_mean"],
}
FEATS = [f for g in GROUPS.values() for f in g]


class Ctx:
    """Panel arrays plus per-year palm context (distance to palm, neighbourhood share) for all cells."""

    def __init__(self):
        import numpy as np
        from scipy import ndimage
        self.cells, self.A = _arrays()
        c = self.cells
        self.rr, self.cc = c.r.to_numpy(), c.c.to_numpy()
        self.shp = _read("env")[3]
        self.tot = self.A["ind"].astype(np.int16) + self.A["sh"]
        self.rain_mean = self.A["rain"].astype(np.float32).mean(0)
        g = np.zeros(self.shp, bool)
        g[self.rr, self.cc] = c.conc.to_numpy().astype(bool)
        self.d_conc = np.minimum(ndimage.distance_transform_edt(~g) * CELL_KM, 60)[self.rr, self.cc].astype(np.float32)
        self.status = np.array([{s: i for i, s in enumerate(STATUS_ORDER + ["none"])}[s] for s in c.status], np.int8)
        self._pc = {}

    def palm_ctx(self, t):
        import numpy as np
        from scipy import ndimage
        if t not in self._pc:
            g = np.zeros(self.shp, np.float32)
            g[self.rr, self.cc] = self.tot[t]
            d = np.minimum(ndimage.distance_transform_edt(g < 50) * CELL_KM, 60)[self.rr, self.cc]
            nb = ndimage.uniform_filter(g, NB_CELLS, mode="constant")[self.rr, self.cc]
            self._pc[t] = (d.astype(np.float16), nb.astype(np.float16))
        return self._pc[t]

    def risk_set(self, t):
        return (self.tot[t] < 50) & (self.cells.palm_ny.to_numpy() < 50)

    def features(self, idx, t):
        import pandas as pd
        A, c = self.A, self.cells
        d_palm, nb = self.palm_ctx(t)
        nb0 = self.palm_ctx(max(t - 3, 0))[1]
        d = pd.DataFrame({
            "cell": idx, "s": YEARS[0] + t,
            "d_palm": d_palm[idx].astype("float32"), "d_ind": A["d_ind"][t, idx].clip(0, 60),
            "nb_palm": nb[idx].astype("float32"), "nb_growth": (nb[idx] - nb0[idx]).astype("float32"),
            "own_palm": self.tot[t, idx],
            "conc": c.conc.to_numpy()[idx].astype("uint8"), "hti": c.hti.to_numpy()[idx].astype("uint8"),
            "d_conc": self.d_conc[idx], "status": self.status[idx],
            "peat": c.peat.to_numpy()[idx].astype("uint8"), "depth": c.depth.to_numpy()[idx],
            "und": A["und"][t, idx], "deg": A["deg"][t, idx], "reg": A["reg"][t, idx],
            "dund": A["und"][max(t - 1, 0), idx].astype("int16") - A["und"][t, idx],
            "ddeg": A["deg"][t, idx].astype("int16") - A["deg"][max(t - 1, 0), idx],
            "burn": A["burn"][t, idx], "nburn3": A["burn"][max(t - 2, 0):t + 1, idx].sum(0),
            "built00": c.built00.to_numpy()[idx], "rain_mean": self.rain_mean[idx],
        })
        for f in ACCESS:
            d[f] = c[f].to_numpy()[idx]
        if t + H < len(YEARS) and YEARS[0] + t + H <= PALM_LAST:
            d["conv"] = (self.tot[t + H, idx] >= 50).astype("uint8")
            d["conv_ind"] = (d.conv.to_numpy() & (A["ind"][t + H, idx] >= A["sh"][t + H, idx])).astype("uint8")
        return d

    def design(self, sample, seed=0, last=S_LAST):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(seed)
        n = len(self.cells)
        idx = np.sort(rng.choice(n, size=min(sample, n), replace=False))
        parts = []
        for s in range(S_FIRST, last + 1):
            t = s - YEARS[0]
            i = idx[self.risk_set(t)[idx]]
            parts.append(self.features(i, t))
        d = pd.concat(parts, ignore_index=True)
        r, c = self.rr[d.cell.to_numpy()], self.cc[d.cell.to_numpy()]
        d["fold_block"] = (r * CELL_KM // BLOCK_CV_KM).astype(int) * 1000 + (c * CELL_KM // BLOCK_CV_KM).astype(int)
        return d


def _capture(p, y):
    import numpy as np
    o = np.argsort(-p, kind="stable")
    cum = np.cumsum(y[o]) / max(y.sum(), 1)
    return {f"top{q}": round(100 * float(cum[int(len(p) * q / 100) - 1]), 1) for q in (5, 10, 20)}


def stage_model(a):
    import numpy as np
    import pandas as pd
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import GroupKFold
    X = Ctx()
    d = X.design(a.sample)
    y = d.conv.to_numpy()
    print(f"rows {len(d):,}, cells {d.cell.nunique():,}, converted within {H} yr {100 * y.mean():.2f}%", flush=True)
    oof = np.zeros(len(d))
    perm = {g: np.zeros(len(d)) for g in GROUPS}
    for k, (tr, te) in enumerate(GroupKFold(n_splits=a.folds).split(d, y, d.fold_block)):
        m = _fit(d.iloc[tr], y[tr], FEATS)
        Xte = d.iloc[te][FEATS].copy()
        oof[te] = m.predict_proba(Xte)[:, 1]
        rng = np.random.default_rng(k)
        for g, cols in GROUPS.items():
            Xp = Xte.copy()
            Xp[cols] = Xte[cols].to_numpy()[rng.permutation(len(Xp))]
            perm[g][te] = m.predict_proba(Xp)[:, 1]
        print(f"  fold {k + 1}/{a.folds} done", flush=True)
    full = {"pr_auc": float(average_precision_score(y, oof)), "roc_auc": float(roc_auc_score(y, oof))}
    rows = [{"group": g, "perm_pr_auc_loss": full["pr_auc"] - average_precision_score(y, perm[g]),
             "perm_roc_auc_loss": full["roc_auc"] - roc_auc_score(y, perm[g])} for g in GROUPS]
    imp = pd.DataFrame(rows).sort_values("perm_pr_auc_loss", ascending=False).round(4)
    os.makedirs(OUT, exist_ok=True)
    imp.to_csv(os.path.join(OUT, "palm_expansion_importance.csv"), index=False)
    res = {"rows": len(d), "cells": int(d.cell.nunique()), "base_rate_pct": round(100 * float(y.mean()), 2),
           "horizon_yr": H, "state_years": [S_FIRST, S_LAST], "block_cv_km": BLOCK_CV_KM,
           "spatial_block_cv": full, "groups": GROUPS}
    json.dump(res, open(os.path.join(OUT, "palm_expansion_model.json"), "w"), indent=1, default=float)
    print(f"spatial-block CV PR-AUC {full['pr_auc']:.3f} (base rate {y.mean():.3f}), ROC-AUC {full['roc_auc']:.3f}")
    print(imp.to_string(index=False))


def stage_forecast(a):
    import numpy as np
    import pandas as pd
    import rasterio
    X = Ctx()
    n = len(X.cells)
    allidx = np.arange(n)
    res = {"hindcast": {}}
    # hindcast: train on state years up to 2010 (outcomes <= 2013), rank all unplanted cells later
    d = X.design(a.sample, last=2010)
    m = _fit(d, d.conv.to_numpy(), FEATS)
    rng = np.random.default_rng(0)
    for s in (2013, 2016):
        t = s - YEARS[0]
        rs = allidx[X.risk_set(t)]
        F = X.features(rs, t)
        yv = F.conv.to_numpy()
        jit = 1e-6 * rng.random(len(F))
        res["hindcast"][f"{s + 1}-{s + H}"] = {
            "converted_km2": round(float(yv.sum() * CELL_KM ** 2)),
            "model": _capture(m.predict_proba(F[FEATS])[:, 1], yv),
            "baseline_distance_to_palm": _capture(-F.d_palm.to_numpy().astype(float) + jit, yv),
            "baseline_concession_then_distance": _capture(
                100 * F.conc.to_numpy() - F.d_palm.to_numpy().astype(float) + jit, yv)}
        print(s, res["hindcast"][f"{s + 1}-{s + H}"], flush=True)
    # forecast: train on all state years, predict from the end of 2021 (latest palm map year)
    d = X.design(a.sample)
    m = _fit(d, d.conv.to_numpy(), FEATS)
    t = 2021 - YEARS[0]
    rs = X.risk_set(t)
    F = X.features(allidx, t)
    p = m.predict_proba(F[FEATS])[:, 1]
    p[~rs] = np.nan
    _, tr, crs, shp = _read("env")
    band = np.full(shp, -1, np.float32)
    band[X.rr, X.cc] = np.nan_to_num(p, nan=-1)
    with rasterio.open(os.path.join(OUT, "palm_expansion_risk.tif"), "w", driver="GTiff", height=shp[0],
                       width=shp[1], count=1, dtype="float32", crs=crs, transform=tr, compress="deflate",
                       nodata=-1) as ds:
        ds.write(band, 1)
        ds.set_band_description(1, f"p_palm_within_{H}yr_from_end_2021")
    pr, Fr = p[rs], F[rs].reset_index(drop=True)
    top = pr >= np.quantile(pr, 0.9)
    km2 = CELL_KM ** 2
    # independent check: forest loss (TMF undisturbed share drop >= 30 points) between end-2021 and end-2024
    t24 = 2024 - YEARS[0]
    loss = (X.A["und"][t, allidx[rs]].astype(np.int16) - X.A["und"][t24, allidx[rs]]) >= 30
    tab = pd.DataFrame({
        "p": pr, "top": top, "status": X.cells.status.to_numpy()[rs],
        "soil": np.where(Fr.peat == 1, "peat", "mineral"),
        "forest_2021": np.where(Fr.und >= 90, "intact", np.where(Fr.und >= 30, "partial", "open")),
        "concession": np.where(Fr.conc == 1, "oil palm concession", np.where(Fr.hti == 1, "pulpwood", "none")),
        "distance_to_palm": pd.cut(Fr.d_palm.astype(float), [-1, 1, 5, 10, 99],
                                   labels=["<=1 km", "1-5 km", "5-10 km", ">10 km"]).astype(str),
        "burned_2019_2021": np.where(Fr.nburn3 > 0, "yes", "no")})
    summ = {}
    for k in ("status", "soil", "forest_2021", "concession", "distance_to_palm", "burned_2019_2021"):
        g = tab.groupby(k).agg(top=("top", "sum"), n=("top", "size"), exp=("p", "sum"))
        summ[k] = {str(i): {"share_of_top10_pct": round(100 * r_.top / top.sum(), 1),
                            "pct_of_class_in_top10": round(100 * r_.top / r_.n, 1),
                            "expected_new_palm_km2": round(float(r_.exp * km2))} for i, r_ in g.iterrows()}
    res["forecast_2022_2024"] = {
        "unplanted_cells": int(rs.sum()), "expected_new_palm_km2": round(float(np.nansum(pr) * km2)),
        "top10_km2": round(float(top.sum() * km2)),
        "observed_new_palm_km2_per_3yr": {f"{s + 1}-{s + H}": round(float(
            ((X.tot[s - YEARS[0] + H] >= 50) & X.risk_set(s - YEARS[0])).sum() * km2)) for s in (2010, 2013, 2016)},
        "forest_loss_2022_2024_in_top10_pct": round(100 * float(loss[top].sum() / max(loss.sum(), 1)), 1),
        "forest_loss_2022_2024_km2": round(float(loss.sum() * km2)),
        "top10": summ}
    json.dump(res, open(os.path.join(OUT, "palm_expansion_forecast.json"), "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


def _sim_features(X, base, share, share_prev, ind):
    """Version-1 predictors with the closeness-to-palm group recomputed from a simulated palm map.
    base: features of every cell at the start year (land state, fire, access ... held fixed)."""
    import numpy as np
    from scipy import ndimage
    F = base.copy()

    def grid(v):
        g = np.zeros(X.shp, np.float32)
        g[X.rr, X.cc] = v
        return g
    g, gp = grid(share), grid(share_prev)
    F["d_palm"] = np.minimum(ndimage.distance_transform_edt(g < 50) * CELL_KM, 60)[X.rr, X.cc].astype("float32")
    F["d_ind"] = np.minimum(ndimage.distance_transform_edt(grid(ind) == 0) * CELL_KM, 60)[X.rr, X.cc].astype("float32")
    nb = ndimage.uniform_filter(g, NB_CELLS, mode="constant")[X.rr, X.cc]
    F["nb_palm"] = nb.astype("float32")
    F["nb_growth"] = (nb - ndimage.uniform_filter(gp, NB_CELLS, mode="constant")[X.rr, X.cc]).astype("float32")
    F["own_palm"] = share.astype(F["own_palm"].dtype)
    return F


def _run_dynamic(X, m, y0, demands, allowed=None):
    """Step the version-1 model forward in H-year periods from the end of y0. demands: cells per period.
    Returns the period (1..) each cell converts in, 0 if it does not."""
    import numpy as np
    t = y0 - YEARS[0]
    n = len(X.cells)
    base = X.features(np.arange(n), t)
    share = X.tot[t].astype(np.int16)
    prev = X.tot[max(t - H, 0)].astype(np.int16)
    ind = X.A["ind"][t] >= 50
    free = X.risk_set(t) & (np.ones(n, bool) if allowed is None else allowed)
    when = np.zeros(n, np.int8)
    for k, D in enumerate(demands, start=1):
        F = _sim_features(X, base, share, prev, ind)
        p = m.predict_proba(F[FEATS])[:, 1]
        p[~free] = -1
        D = int(min(D, free.sum()))
        pick = np.argpartition(-p, D)[:D]
        prev = share.copy()
        share[pick] = 100
        ind[pick] = True
        free[pick] = False
        when[pick] = k
    return when


def stage_dynamic(a):
    """Version 1 run forward: rank with the 3-year model, plant the period's demand in the top cells,
    recompute closeness to palm from the simulated map, repeat. Tested 2010 -> 2016 (two steps), then
    scenarios 2022-2030 (three steps)."""
    import numpy as np
    import rasterio
    from kalimantan_palm_ca import simulate, _fom, LEGAL
    X = Ctx()
    km2 = CELL_KM ** 2
    n = len(X.cells)
    res = {}
    # --- test: model trained on state years <= 2007 (outcomes <= 2010), start at the end of 2010
    d = X.design(a.sample, last=2007)
    m = _fit(d, d.conv.to_numpy(), FEATS)
    t0 = 2010 - YEARS[0]
    cand = X.risk_set(t0)
    conv_by = lambda y: cand & (X.tot[y - YEARS[0]] >= 50)  # noqa: E731
    ref1, ref2 = conv_by(2013), conv_by(2016)
    dem = [int(ref1.sum()), int((ref2 & ~ref1).sum())]
    w = _run_dynamic(X, m, 2010, dem)
    v = {"demand_cells_per_period": dem, "dynamic": {"2010_2016": _fom(w > 0, ref2),
                                                     "period_2014_2016": _fom(w == 2, ref2 & ~ref1)}}
    p0 = m.predict_proba(X.features(np.arange(n), t0)[FEATS])[:, 1]
    p0[~cand] = -1
    st = np.zeros(n, bool)
    st[np.argpartition(-p0, sum(dem))[:sum(dem)]] = True
    v["static_one_shot"] = {"2010_2016": _fom(st, ref2)}
    cal = json.load(open(os.path.join(OUT, "palm_ca_calibration.json")))["tuning_2010_2016"]["best"]
    yearly = [int(((X.tot[y - YEARS[0]] >= 50) & (X.tot[y - 1 - YEARS[0]] < 50) & cand).sum()) for y in range(2011, 2017)]
    from kalimantan_palm_ca import suitability
    S, _ = suitability(X, 2008, 2010)
    wc = simulate(X, S, X.tot[t0] >= 50, cand, yearly, cal["k"], cal["eps"], cal["alpha"], 0)
    v["ca_version2"] = {"2010_2016": _fom(wc > 0, ref2), "note": "CA parameters were tuned on this period"}
    res["test_2010_2016"] = v
    print(json.dumps(v, indent=1), flush=True)
    # --- scenarios from the end of 2021
    d = X.design(a.sample)
    m = _fit(d, d.conv.to_numpy(), FEATS)
    t = 2021 - YEARS[0]
    new = lambda y0, y1: np.mean([((X.tot[y - YEARS[0]] >= 50) & (X.tot[y - 1 - YEARS[0]] < 50)).sum()  # noqa: E731
                                  for y in range(y0, y1 + 1)])
    stt = X.cells.status.to_numpy()
    legal = np.isin(stt, list(LEGAL))
    scen = {"slow": (new(2017, 2019), None), "boom": (new(2011, 2016), None), "legal": (new(2017, 2019), legal)}
    with rasterio.open(os.path.join(OUT, "fire_risk_2027.tif")) as ds:
        bi = [i + 1 for i, s in enumerate(ds.descriptions) if s and "dry" in s][0]
        pf = ds.read(bi)[X.rr, X.cc]
    fire_top = pf >= np.quantile(pf[pf >= 0], 0.9)
    with rasterio.open(os.path.join(OUT, "palm_ca_2030.tif")) as ds:
        ca = {s: ds.read(i + 1)[X.rr, X.cc] for i, s in enumerate(
            x.replace("share_of_runs_palm_by_2030_", "") for x in ds.descriptions)}
    base = X.features(np.arange(n), t)
    peat, conc, intact = base.peat.to_numpy() == 1, base.conc.to_numpy() == 1, base.und.to_numpy() >= 90
    _, tr, crs, shp = _read("env")
    res["scenarios"] = {}
    bands = {}
    for name, (yr, allowed) in scen.items():
        w = _run_dynamic(X, m, 2021, [int(round(yr * H))] * 3, allowed)
        bands[name] = w
        c = w > 0
        tot = float(c.sum())
        pct = lambda mask: round(100 * float((c & mask).sum()) / tot, 1)  # noqa: E731
        res["scenarios"][name] = {
            "demand_km2_per_yr": round(yr * km2), "new_palm_2022_2030_km2": round(tot * km2),
            "by_period_km2": {f"{2019 + 3 * k}-{2021 + 3 * k}": round(float((w == k).sum() * km2)) for k in (1, 2, 3)},
            "pct_on_peat": pct(peat), "pct_in_intact_forest_2021": pct(intact),
            "pct_outside_oil_palm_concessions": pct(~conc), "pct_in_2027_fire_top10": pct(fire_top),
            "pct_by_status": {s: pct(stt == s) for s in ("APL", "HPK", "HP", "HPT", "HL", "KSA/KPA", "none", "other")},
            "pct_also_new_in_ca_version2": pct(ca[name] >= 0.5) if name in ca else None,
        }
        print(name, json.dumps(res["scenarios"][name]), flush=True)
    with rasterio.open(os.path.join(OUT, "palm_dynamic_2030.tif"), "w", driver="GTiff", height=shp[0],
                       width=shp[1], count=len(bands), dtype="int8", crs=crs, transform=tr, compress="deflate",
                       nodata=-1) as ds:
        for i, (name, w) in enumerate(bands.items(), start=1):
            g = np.full(shp, -1, np.int8)
            g[X.rr, X.cc] = w
            ds.write(g, i)
            ds.set_band_description(i, f"period_converted_{name} (1=2022-24, 2=2025-27, 3=2028-30)")
    json.dump(res, open(os.path.join(OUT, "palm_dynamic_forecast.json"), "w"), indent=1)
    # map: three scenarios, colour by period
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    r0, r1, c0, c1 = X.rr.min(), X.rr.max() + 1, X.cc.min(), X.cc.max() + 1
    cols = ["#ffffff", "#e9e6df", "#8c8c8c", "#1d5c34", "#3f8f5a", "#9fd4ae"]
    fig, axs = plt.subplots(1, 3, figsize=(18, 7), dpi=150)
    for ax, (name, w) in zip(axs, bands.items()):
        cls = np.zeros(shp, np.uint8)
        cls[X.rr, X.cc] = 1
        cls[X.rr[X.tot[t] >= 50], X.cc[X.tot[t] >= 50]] = 2
        for k in (1, 2, 3):
            cls[X.rr[w == k], X.cc[w == k]] = 2 + k
        ax.imshow(cls[r0:r1, c0:c1], cmap=ListedColormap(cols), vmin=0, vmax=5, interpolation="nearest")
        ax.set_axis_off()
        ax.set_title(f"{name}: {res['scenarios'][name]['new_palm_2022_2030_km2']:,} km² new palm 2022-2030", fontsize=11)
    fig.legend(handles=[Patch(color=cols[2], label="Oil palm by 2021"), Patch(color=cols[3], label="New 2022-24"),
                        Patch(color=cols[4], label="New 2025-27"), Patch(color=cols[5], label="New 2028-30")],
               loc="lower center", ncol=4, frameon=False)
    fig.suptitle("Kalimantan oil palm 2022-2030, version-1 model stepped forward in 3-year periods", fontsize=13)
    fig.savefig(os.path.join(OUT, "palm_dynamic_2030_map.png"), bbox_inches="tight")
    print("Saved:", os.path.join(OUT, "palm_dynamic_2030_map.png"))


def stage_map(_a):
    """Overlay the top 10% palm-conversion risk on the top 10% 2027 fire risk (El Nino scenario)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    import rasterio
    X = Ctx()
    with rasterio.open(os.path.join(OUT, "palm_expansion_risk.tif")) as ds:
        pp = ds.read(1)[X.rr, X.cc]
    with rasterio.open(os.path.join(OUT, "fire_risk_2027.tif")) as ds:
        b = [ds.descriptions[i] or "" for i in range(ds.count)].index(
            next(s for s in ds.descriptions if s and "dry" in s)) + 1
        pf = ds.read(b)[X.rr, X.cc]
    t = 2021 - YEARS[0]
    rs = pp >= 0
    top_p = rs & (pp >= np.quantile(pp[rs], 0.9))
    top_f = pf >= np.quantile(pf, 0.9)
    palm = X.tot[t] >= 50
    km2 = CELL_KM ** 2
    both = top_p & top_f
    pk = X.cells.peat.to_numpy()
    st = X.cells.status.to_numpy()
    stats = {
        "top10_palm_km2": round(float(top_p.sum() * km2)), "top10_fire_km2": round(float(top_f.sum() * km2)),
        "both_km2": round(float(both.sum() * km2)),
        "pct_of_palm_top10_also_fire_top10": round(100 * float(both.sum() / top_p.sum()), 1),
        "pct_of_fire_top10_also_palm_top10": round(100 * float(both.sum() / top_f.sum()), 1),
        "expected_new_palm_km2_in_fire_top10": round(float(pp[both].sum() * km2)),
        "both_on_peat_pct": round(100 * float((both & pk).sum() / both.sum()), 1),
        "both_by_status_pct": {s: round(100 * float((both & (st == s)).sum() / both.sum()), 1)
                               for s in STATUS_ORDER + ["none"]},
    }
    json.dump(stats, open(os.path.join(OUT, "palm_fire_overlap.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))
    cls = np.zeros(X.shp, np.uint8)                       # 0 sea / outside
    cls[X.rr, X.cc] = 1                                   # land
    cls[X.rr[palm], X.cc[palm]] = 2                       # palm by 2021
    cls[X.rr[top_f & ~top_p], X.cc[top_f & ~top_p]] = 3
    cls[X.rr[top_p & ~top_f], X.cc[top_p & ~top_f]] = 4
    cls[X.rr[both], X.cc[both]] = 5
    r0, r1, c0, c1 = X.rr.min(), X.rr.max() + 1, X.cc.min(), X.cc.max() + 1
    cols = ["#ffffff", "#e9e6df", "#8c8c8c", "#f0a35e", "#3f8f5a", "#c0262d"]
    fig, ax = plt.subplots(figsize=(10, 9.5), dpi=200)
    ax.imshow(cls[r0:r1, c0:c1], cmap=ListedColormap(cols), vmin=0, vmax=5, interpolation="nearest")
    ax.set_axis_off()
    ax.set_title("Kalimantan: where new oil palm is most likely (2022-2024)\n"
                 "and where fire risk is highest in an El Nino 2027", fontsize=13, loc="left")
    lab = [("Oil palm by 2021", 2),
           (f"Top 10% palm-conversion risk only ({(top_p & ~top_f).sum() * km2:,.0f} km²)", 4),
           (f"Top 10% fire risk 2027 only ({(top_f & ~top_p).sum() * km2:,.0f} km²)", 3),
           (f"Both ({stats['both_km2']:,} km²)", 5)]
    ax.legend(handles=[Patch(color=cols[i], label=s) for s, i in lab], loc="lower left", fontsize=9, frameon=False)
    px = 100 / CELL_KM                                    # 100 km scale bar
    yb = (r1 - r0) * 0.97
    ax.plot([(c1 - c0) * 0.72, (c1 - c0) * 0.72 + px], [yb, yb], color="k", lw=2)
    ax.text((c1 - c0) * 0.72 + px / 2, yb - 12, "100 km", ha="center", fontsize=8)
    fig.text(0.01, 0.01, "Palm risk: gradient boosting on 2002-2016 conversions, state at end-2021 "
             "(Descals et al. 2024 palm, JRC TMF forest, GFW concessions & forest area, BBSDLP peat). "
             "Fire risk: MCD64A1 model, dry-year rainfall.\nMODIS sinusoidal grid, 463 m cells. "
             "Top 10% = highest-ranked tenth of unplanted land (palm) or of all land (fire).", fontsize=6.5)
    fig.savefig(os.path.join(OUT, "palm_fire_risk_map.png"), bbox_inches="tight")
    print("Saved:", os.path.join(OUT, "palm_fire_risk_map.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", required=True, choices=["model", "forecast", "map", "dynamic"])
    ap.add_argument("--sample", type=int, default=200_000, help="number of cells sampled for training")
    ap.add_argument("--folds", type=int, default=4)
    a = ap.parse_args()
    {"model": stage_model, "forecast": stage_forecast, "map": stage_map, "dynamic": stage_dynamic}[a.stage](a)


if __name__ == "__main__":
    main()
