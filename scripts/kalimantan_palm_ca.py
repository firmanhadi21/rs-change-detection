"""Oil-palm expansion in Kalimantan as a cellular automaton (CA-Markov / FLUS style) on the 500 m MODIS grid.

Each simulated year, every unplanted cell gets a transition potential

    TP = S x (eps + Omega_k) x R

  S        suitability: gradient-boosting probability that the cell becomes >= 50% oil palm next year,
           from land state only (forest, clearing, fire, peat, status, concessions, access, terrain,
           settlement, climate). The closeness-to-palm predictors are left out on purpose: the CA's
           neighbourhood term carries them, and it is updated as the simulation plants palm.
  Omega_k  share of palm in the k x k window around the cell (the cell itself excluded), recomputed
           every year from the simulated map, so new palm attracts more palm.
  eps      floor that lets palm start away from existing plantations (new frontiers).
  R        stochastic term 1 + (-ln u)^alpha, u ~ U(0,1) (alpha = 0: deterministic).

The yearly demand (number of cells that convert) is set from outside: observed counts when testing,
scenarios when forecasting. The demand cells with the highest TP convert; the map is updated; repeat.

Testing follows Pontius' figure of merit (FoM = hits / (hits + misses + false alarms)) on the cells that
really converted: k, eps, alpha are tuned on 2010 -> 2016 (suitability trained on years before 2010),
then the tuned CA is scored on 2016 -> 2019 (suitability trained on years before 2016) against
suitability without neighbourhood, neighbourhood without suitability, and distance to palm alone.

Forecast from the end of 2021 to 2030 under three demand scenarios, 20 stochastic runs each:
    slow   mean yearly conversion 2017-2019 (the post-2016 slowdown)
    boom   mean yearly conversion 2011-2016
    legal  slow demand, but only APL, HPK and land outside the forest-area map may convert

    python scripts/kalimantan_palm_ca.py --stage calibrate
    python scripts/kalimantan_palm_ca.py --stage forecast
    python scripts/kalimantan_palm_ca.py --stage map

Variant ANN + CA-Markov (--suit ann --demand markov): suitability from a multilayer perceptron
(standardised inputs, one-hot forest-area status), and yearly demand from a Markov chain over three
states (intact-ish forest = TMF undisturbed >= 50%, other non-palm land, oil palm), with the yearly
transition matrix averaged over 2016-2019 and projected from the end of 2021. Scenarios: markov, and
markov_legal (same demand, APL / HPK / outside the forest-area map only). The Markov quantity is checked
by projecting a 2013-2016 matrix over 2016-2019 against the observed conversions.

Outputs in output/fire/kalimantan_palm_panel/: palm_ca{tag}_calibration.json, palm_ca{tag}_forecast.json,
palm_ca{tag}_2030.tif (share of runs converted by 2030, one band per scenario), palm_ca{tag}_2030_map.png;
tag is empty for the default and "_ann_markov" for the variant.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kalimantan_palm_fire_panel import OUT, CELL_KM, YEARS, _read  # noqa: E402
from kalimantan_palm_expansion import Ctx, FEATS, GROUPS  # noqa: E402
from kalimantan_fire_factors import _fit  # noqa: E402

SUIT_FEATS = [f for f in FEATS if f not in GROUPS["closeness to existing palm"]]
KS, EPS, ALPHAS = (3, 5, 9, 15), (0.002, 0.02, 0.1), (0.0, 0.5, 1.0)
RUNS = 20
LEGAL = {"APL", "HPK", "none"}


def _yi(y):
    return y - YEARS[0]


def _tag(a):
    return "" if (a.suit, a.demand) == ("gbm", "scenario") else f"_{a.suit}_{a.demand}"


def _fit_ann(d, y):
    """Multilayer perceptron on standardised inputs, forest-area status one-hot."""
    from sklearn.compose import ColumnTransformer
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    num = [f for f in SUIT_FEATS if f != "status"]
    pre = ColumnTransformer([("num", StandardScaler(), num),
                             ("cat", OneHotEncoder(handle_unknown="ignore"), ["status"])])
    mlp = MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-4, batch_size=4096, learning_rate_init=1e-3,
                        max_iter=60, early_stopping=True, validation_fraction=0.1, n_iter_no_change=6,
                        random_state=0)
    m = make_pipeline(pre, mlp).fit(d[SUIT_FEATS], y)
    print(f"  ANN: {mlp.n_iter_} epochs, best validation score {mlp.best_validation_score_:.4f}", flush=True)
    return m


def markov_states(X, t):
    """0 forest (TMF undisturbed >= 50%), 1 other non-palm land, 2 oil palm; -1 palm of unknown year."""
    import numpy as np
    s = np.where(X.tot[t] >= 50, 2, np.where(X.A["und"][t] >= 50, 0, 1)).astype(np.int8)
    s[X.cells.palm_ny.to_numpy() >= 50] = -1
    return s


def markov_matrix(X, y0, y1):
    """Yearly transition matrix, transitions pooled over y0->y0+1 .. y1-1->y1."""
    import numpy as np
    C = np.zeros((3, 3))
    for y in range(y0, y1):
        a, b = markov_states(X, _yi(y)), markov_states(X, _yi(y + 1))
        ok = (a >= 0) & (b >= 0)
        np.add.at(C, (a[ok], b[ok]), 1)
    return C / C.sum(1, keepdims=True)


def markov_demand(X, P, start_year, n_years):
    """Cells that become palm each year when the state counts at start_year are projected with P."""
    import numpy as np
    s = markov_states(X, _yi(start_year))
    n = np.bincount(s[s >= 0], minlength=3).astype(float)
    out = []
    for _ in range(n_years):
        n2 = n @ P
        out.append(int(round(n2[2] - n[2])))
        n = n2
    return out


def suitability(X, last_s, state_year, sample=200_000, seed=0, method="gbm"):
    """Fit P(cell >= 50% palm at end of s+1 | unplanted at end of s) on s = 2002..last_s; predict for every
    cell from its state at the end of state_year."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    n = len(X.cells)
    idx = np.sort(rng.choice(n, size=min(sample, n), replace=False))
    parts = []
    for s in range(2002, last_s + 1):
        t = _yi(s)
        i = idx[X.risk_set(t)[idx]]
        F = X.features(i, t)
        F["y"] = (X.tot[t + 1, i] >= 50).astype("uint8")
        parts.append(F)
    d = pd.concat(parts, ignore_index=True)
    m = _fit_ann(d, d.y.to_numpy()) if method == "ann" else _fit(d, d.y.to_numpy(), SUIT_FEATS)
    F = X.features(np.arange(n), _yi(state_year))
    return m.predict_proba(F[SUIT_FEATS])[:, 1].astype(np.float32), float(d.y.mean())


def simulate(X, S, palm0, cand, demand, k, eps, alpha, seed):
    """Run the CA. palm0/cand: bool per cell (palm at start / may convert). demand: cells per year.
    Returns the simulated year index (1..len(demand)) a cell converts, 0 if it does not."""
    import numpy as np
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    palm = palm0.copy()
    when = np.zeros(len(palm), np.int16)
    g = np.zeros(X.shp, np.float32)
    for yr, D in enumerate(demand, start=1):
        g[:] = 0
        g[X.rr, X.cc] = palm
        om = (ndimage.uniform_filter(g, k, mode="constant") * k * k - g)[X.rr, X.cc] / (k * k - 1)
        tp = S * (eps + om)
        if alpha > 0:
            tp = tp * (1 + (-np.log(rng.random(len(tp)))) ** alpha)
        free = cand & ~palm
        tp[~free] = -1
        D = int(min(D, free.sum()))
        pick = np.argpartition(-tp, D)[:D]
        palm[pick] = True
        when[pick] = yr
    return when


def _fom(sim, ref):
    import numpy as np
    h = int(np.sum(sim & ref))
    return {"fom": round(h / max(int(np.sum(sim | ref)), 1), 4), "hits": h,
            "misses": int(np.sum(ref & ~sim)), "false_alarms": int(np.sum(sim & ~ref))}


def _period(X, y0, y1):
    import numpy as np
    t0, t1 = _yi(y0), _yi(y1)
    palm0 = X.tot[t0] >= 50
    cand = X.risk_set(t0)
    demand = [int(((X.tot[t] >= 50) & (X.tot[t - 1] < 50) & cand).sum()) for t in range(t0 + 1, t1 + 1)]
    ref = cand & (X.tot[t1] >= 50)
    return palm0, cand, demand, ref


def stage_calibrate(a):
    import numpy as np
    X = Ctx()
    res = {"suit_feats": SUIT_FEATS, "suitability": a.suit, "demand": a.demand}
    # tune on 2010 -> 2016
    S, br = suitability(X, 2008, 2010, method=a.suit)   # outcomes up to 2009: before the tuning period
    palm0, cand, demand, ref = _period(X, 2010, 2016)
    print(f"tuning 2010->2016: demand/yr {demand}, converted {ref.sum():,} cells", flush=True)
    grid = []
    for k in KS:
        for eps in EPS:
            for al in ALPHAS:
                seeds = (0,) if al == 0 else (0, 1, 2)
                f = [_fom(simulate(X, S, palm0, cand, demand, k, eps, al, s) > 0, ref)["fom"] for s in seeds]
                grid.append({"k": k, "eps": eps, "alpha": al, "fom": round(float(np.mean(f)), 4)})
                print(f"  k={k:2d} eps={eps:<6} alpha={al}: FoM {grid[-1]['fom']:.4f}", flush=True)
    best = max(grid, key=lambda r: r["fom"])
    res["tuning_2010_2016"] = {"grid": grid, "best": best}
    # validate on 2016 -> 2019 with the tuned parameters
    S, _ = suitability(X, 2014, 2016, method=a.suit)
    palm0, cand, demand, ref = _period(X, 2016, 2019)
    k, eps, al = best["k"], best["eps"], best["alpha"]
    seeds = range(RUNS if al > 0 else 1)
    v = {"demand_cells_per_yr": demand, "converted_cells": int(ref.sum())}
    runs = [_fom(simulate(X, S, palm0, cand, demand, k, eps, al, s) > 0, ref) for s in seeds]
    v["ca"] = {"fom_mean": round(float(np.mean([r["fom"] for r in runs])), 4),
               "fom_min": min(r["fom"] for r in runs), "fom_max": max(r["fom"] for r in runs), "run0": runs[0]}
    D = sum(demand)
    free = np.where(cand & ~palm0)[0]

    def top(score):
        sim = np.zeros(len(cand), bool)
        sim[free[np.argsort(-score[free], kind="stable")[:D]]] = True
        return _fom(sim, ref)
    dpalm = X.palm_ctx(_yi(2016))[0].astype(np.float32)
    v["suitability_only"] = top(S)
    v["neighbourhood_only"] = _fom(simulate(X, np.ones_like(S), palm0, cand, demand, k, eps, 0.0, 0) > 0, ref)
    v["distance_to_palm_only"] = top(-dpalm + 1e-6 * np.random.default_rng(0).random(len(dpalm)))
    v["random_expected_fom"] = round(float(D / (2 * len(free) - D)) if len(free) else 0, 4)
    # the static model (kalimantan_palm_expansion.py: gradient boosting with closeness to palm, 3-yr
    # horizon), trained on state years up to 2013 so its outcomes end by 2016, same quantity
    from kalimantan_palm_expansion import FEATS as F_ALL
    dd = X.design(200_000, last=2013)
    ms = _fit(dd, dd.conv.to_numpy(), F_ALL)
    v["static_model_with_closeness"] = top(ms.predict_proba(X.features(np.arange(len(cand)), _yi(2016))[F_ALL])[:, 1])
    if a.demand == "markov":                    # quantity check: 2013-2016 matrix projected over 2016-2019
        P = markov_matrix(X, 2013, 2016)
        pred = markov_demand(X, P, 2016, 3)
        v["markov_quantity_check"] = {"matrix_years": [2013, 2016], "predicted_cells_per_yr": pred,
                                      "observed_cells_per_yr": demand,
                                      "error_pct": round(100 * (sum(pred) - D) / D, 1)}
    res["validation_2016_2019"] = v
    json.dump(res, open(os.path.join(OUT, f"palm_ca{_tag(a)}_calibration.json"), "w"), indent=1)
    print(json.dumps({"best": best, "validation_2016_2019": v}, indent=1))


def stage_forecast(a):
    import numpy as np
    import rasterio
    X = Ctx()
    tag = _tag(a)
    cal = json.load(open(os.path.join(OUT, f"palm_ca{tag}_calibration.json")))
    b = cal["tuning_2010_2016"]["best"]
    k, eps, al = b["k"], b["eps"], b["alpha"]
    S, _ = suitability(X, 2018, 2021, method=a.suit)    # outcomes up to 2019, state at the end of 2021
    t = _yi(2021)
    palm0 = X.tot[t] >= 50
    cand = X.risk_set(t)
    new = lambda y0, y1: np.mean([((X.tot[_yi(y)] >= 50) & (X.tot[_yi(y) - 1] < 50)).sum()  # noqa: E731
                                  for y in range(y0, y1 + 1)])
    years = list(range(2022, 2031))
    st = X.cells.status.to_numpy()
    legal = cand & np.isin(st, list(LEGAL))
    if a.demand == "markov":
        P = markov_matrix(X, 2016, 2019)
        dem = markov_demand(X, P, 2021, len(years))
        scen = {"markov": (dem, cand), "markov_legal": (dem, legal)}
        markov_info = {"matrix_years": [2016, 2019], "states": ["forest", "other non-palm", "oil palm"],
                       "P_yearly": np.round(P, 5).tolist(), "demand_cells_per_yr": dem}
        print("Markov", markov_info, flush=True)
    else:
        scen = {"slow": ([int(round(new(2017, 2019)))] * len(years), cand),
                "boom": ([int(round(new(2011, 2016)))] * len(years), cand),
                "legal": ([int(round(new(2017, 2019)))] * len(years), legal)}
        markov_info = None
    km2 = CELL_KM ** 2
    with rasterio.open(os.path.join(OUT, "fire_risk_2027.tif")) as ds:
        bi = [i + 1 for i, s in enumerate(ds.descriptions) if s and "dry" in s][0]
        pf = ds.read(bi)[X.rr, X.cc]
    fire_top = pf >= np.quantile(pf[pf >= 0], 0.9)
    with rasterio.open(os.path.join(OUT, "palm_expansion_risk.tif")) as ds:
        pml = ds.read(1)[X.rr, X.cc]
    ml_top = (pml >= 0) & (pml >= np.quantile(pml[pml >= 0], 0.9))
    peat = X.cells.peat.to_numpy().astype(bool)
    F = X.features(np.arange(len(cand)), t)
    intact = F.und.to_numpy() >= 90
    conc = F.conc.to_numpy() == 1
    res = {"suitability": a.suit, "demand": a.demand, "params": b, "years": [years[0], years[-1]],
           "runs": RUNS, "markov": markov_info, "scenarios": {}}
    _, tr, crs, shp = _read("env")
    bands = {}
    for name, (demand, cnd) in scen.items():
        dem = float(np.mean(demand))
        share = np.zeros(len(cand), np.float32)
        by2024 = np.zeros(len(cand), np.float32)
        for s in range(RUNS if al > 0 else 1):
            w = simulate(X, S, palm0, cnd, demand, k, eps, al, s)
            share += w > 0
            by2024 += (w > 0) & (w <= 3)
        n = RUNS if al > 0 else 1
        share /= n
        by2024 /= n
        bands[name] = share
        tot = float(share.sum() * km2)
        res["scenarios"][name] = {
            "demand_km2_per_yr": round(dem * km2), "new_palm_2022_2030_km2": round(tot),
            "pct_on_peat": round(100 * float(share[peat].sum() * km2) / tot, 1),
            "pct_in_intact_forest_2021": round(100 * float(share[intact].sum() * km2) / tot, 1),
            "pct_outside_oil_palm_concessions": round(100 * float(share[~conc].sum() * km2) / tot, 1),
            "pct_in_2027_fire_top10": round(100 * float(share[fire_top].sum() * km2) / tot, 1),
            "pct_by_status": {s_: round(100 * float(share[st == s_].sum() * km2) / tot, 1)
                              for s_ in ("APL", "HPK", "HP", "HPT", "HL", "KSA/KPA", "none", "other")},
            "pct_2022_2024_in_static_model_top10": round(100 * float(by2024[ml_top].sum() / max(by2024.sum(), 1)), 1),
            "cells_converted_in_most_runs_km2": round(float((share >= 0.5).sum() * km2)),
        }
        print(name, json.dumps(res["scenarios"][name]), flush=True)
    with rasterio.open(os.path.join(OUT, f"palm_ca{tag}_2030.tif"), "w", driver="GTiff", height=shp[0], width=shp[1],
                       count=len(bands), dtype="float32", crs=crs, transform=tr, compress="deflate",
                       nodata=-1) as ds:
        for i, (name, v) in enumerate(bands.items(), start=1):
            g = np.full(shp, -1, np.float32)
            g[X.rr, X.cc] = np.where(cand, v, -1)
            ds.write(g, i)
            ds.set_band_description(i, f"share_of_runs_palm_by_2030_{name}")
    json.dump(res, open(os.path.join(OUT, f"palm_ca{tag}_forecast.json"), "w"), indent=1)


def stage_map(a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import rasterio
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    X = Ctx()
    tag = _tag(a)
    with rasterio.open(os.path.join(OUT, f"palm_ca{tag}_2030.tif")) as ds:
        names = [d.replace("share_of_runs_palm_by_2030_", "") for d in ds.descriptions]
        B = {n: ds.read(i + 1)[X.rr, X.cc] for i, n in enumerate(names)}
    t = _yi(2021)
    palm = X.tot[t] >= 50
    r0, r1, c0, c1 = X.rr.min(), X.rr.max() + 1, X.cc.min(), X.cc.max() + 1
    cols = ["#ffffff", "#e9e6df", "#8c8c8c", "#a8d5b5", "#3f8f5a", "#1d5c34"]
    fig, axs = plt.subplots(1, len(names), figsize=(6 * len(names), 7), dpi=150)
    for ax, n in zip(axs, names):
        v = B[n]
        cls = np.zeros(X.shp, np.uint8)
        cls[X.rr, X.cc] = 1
        cls[X.rr[palm], X.cc[palm]] = 2
        for lev, lo in ((3, 0.1), (4, 0.5), (5, 0.9)):
            m = v >= lo
            cls[X.rr[m], X.cc[m]] = lev
        ax.imshow(cls[r0:r1, c0:c1], cmap=ListedColormap(cols), vmin=0, vmax=5, interpolation="nearest")
        ax.set_axis_off()
        ax.set_title(f"{n}: {np.sum(v[v > 0]) * CELL_KM ** 2:,.0f} km² new palm 2022-2030", fontsize=11)
    fig.legend(handles=[Patch(color=cols[2], label="Oil palm by 2021"),
                        Patch(color=cols[3], label="New palm in 10-50% of runs"),
                        Patch(color=cols[4], label="50-90% of runs"), Patch(color=cols[5], label="≥90% of runs")],
               loc="lower center", ncol=4, frameon=False)
    how = "ANN suitability + CA-Markov" if a.suit == "ann" else "gradient-boosting suitability + CA"
    fig.suptitle(f"Kalimantan oil palm 2022-2030, {how} (20 runs per scenario)", fontsize=13)
    p = os.path.join(OUT, f"palm_ca{tag}_2030_map.png")
    fig.savefig(p, bbox_inches="tight")
    print("Saved:", p)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", required=True, choices=["calibrate", "forecast", "map"])
    ap.add_argument("--suit", choices=["gbm", "ann"], default="gbm", help="suitability model")
    ap.add_argument("--demand", choices=["scenario", "markov"], default="scenario", help="yearly demand")
    a = ap.parse_args()
    {"calibrate": stage_calibrate, "forecast": stage_forecast, "map": stage_map}[a.stage](a)


if __name__ == "__main__":
    main()
