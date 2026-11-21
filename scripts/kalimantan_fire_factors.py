"""Which factors best predict where Kalimantan burns? Forest-area status (APL vs kawasan hutan) added
to the 500 m MODIS panel, then a ranking of factor groups by out-of-sample prediction loss.

Builds on scripts/kalimantan_palm_fire_panel.py (run its export / download / panel stages first).
Every predictor is known before the fire season of year y (land state at the end of y-1, fire history
up to y-1), except the June-October rainfall of y itself, which stands in for a seasonal drought forecast.

Stages:
    python scripts/kalimantan_fire_factors.py --stage status    # GFW idn_forest_area v201709 -> grid
    python scripts/kalimantan_fire_factors.py --stage access    # roads, rivers, terrain (panel export 'access')
    python scripts/kalimantan_fire_factors.py --stage rates     # burned % by status x peat x dry year
    python scripts/kalimantan_fire_factors.py --stage model     # spatial-block CV, factor-group ranking
    python scripts/kalimantan_fire_factors.py --stage predict   # hindcast 2019/2023/2024, 2026 risk map
    python scripts/kalimantan_fire_factors.py --stage forecast  # 2026 test, 2027 scenarios, lead-time check
                                                                # (needs panel export/download 'y2026')

Outputs in output/fire/kalimantan_palm_panel/: fire_rates_status.csv, fire_factors.json,
fire_factors_importance.csv.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kalimantan_palm_fire_panel import DATA, OUT, CELL_KM, YEARS, _read  # noqa: E402
from kalimantan_heterogeneity import gfw_key  # noqa: E402

FA = os.path.join(os.path.dirname(DATA), "kalimantan", "gfw_forest_area_kalimantan.gpkg")
# fungsikawa codes (KLHK forest function) -> short class
STATUS = {1007: "APL", 1003: "HP", 1004: "HPT", 1005: "HPK", 1001: "HL"}
STATUS_ORDER = ["APL", "HPK", "HP", "HPT", "HL", "KSA/KPA", "other"]
DRY = (2002, 2004, 2006, 2014, 2015, 2019)          # dry years as in describe.json of the panel
BLOCK_CV_KM = 50
SAMPLE_CELLS = 200_000
GROUPS = {
    "drought (Jun-Oct rain)": ["rain_anom", "rain_mean"],
    "peat": ["peat", "depth"],
    "forest condition": ["und_l", "deg_l", "reg_l"],
    "recent clearing": ["dund", "ddeg"],
    "oil palm & concessions": ["ind_l", "sh_l", "d_ind_l", "conc", "hti"],
    "forest-area status (APL etc.)": ["status"],
    "settlement": ["built00"],
    "fire history": ["burn_l1", "nburn_l3"],
}


def stage_status(_a):
    """Download the Kalimantan forest-area polygons and rasterize them (cell centre) onto the grid."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    import requests
    from rasterio import features
    from shapely.geometry import shape
    if not os.path.exists(FA):
        u = "https://data-api.globalforestwatch.org/dataset/idn_forest_area/v201709/query/json"
        rows = []
        for prov in (61, 62, 63, 64, 65):
            r = requests.get(u, headers={"x-api-key": gfw_key()}, timeout=900, params={"sql":
                             f"SELECT kelas, fungsikawa, ST_AsGeoJSON(geom) AS gj FROM data WHERE kodeprov = {prov}"})
            r.raise_for_status()
            d = r.json()["data"]
            for x in d:
                x["geometry"] = shape(json.loads(x.pop("gj")))
                x["kodeprov"] = prov
            rows += d
            print(f"province {prov}: {len(d)} polygons", flush=True)
        g = gpd.GeoDataFrame(rows, crs=4326)
        g.to_file(FA)
        print("Saved:", FA)
    g = gpd.read_file(FA)
    code = g.fungsikawa.fillna(0).astype(int)
    g["cls"] = np.where(g.kelas.eq("Hutan Konservasi"), "KSA/KPA", code.map(STATUS).fillna("other"))
    _, tr, crs, shp = _read("env")
    g = g.to_crs(crs)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    ids = {c: i + 1 for i, c in enumerate(STATUS_ORDER)}
    ras = features.rasterize([(geom, ids[c]) for geom, c in zip(g.geometry.make_valid(), g.cls)],
                             out_shape=shp, transform=tr, dtype="uint8", all_touched=False)
    with rasterio.open(os.path.join(DATA, "status.tif"), "w", driver="GTiff", height=shp[0], width=shp[1],
                       count=1, dtype="uint8", crs=crs, transform=tr, compress="deflate") as ds:
        ds.write(ras, 1)
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    s = ras[cells.r.to_numpy(), cells.c.to_numpy()]
    cells["status"] = np.where(s == 0, "none", np.array(["none"] + STATUS_ORDER)[s])
    cells.to_parquet(os.path.join(DATA, "cells.parquet"))
    print("cells by status (%):\n", (cells.status.value_counts(normalize=True) * 100).round(1).to_string())


def _arrays():
    """Panel columns as (year, cell) arrays plus cell attributes."""
    import numpy as np
    import pandas as pd
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    n = len(cells)
    p = pd.read_parquet(os.path.join(DATA, "panel.parquet"))
    assert len(p) == n * len(YEARS) and (p.cell.to_numpy()[:n] == cells.cell.to_numpy()).all()
    A = {k: p[k].to_numpy().reshape(len(YEARS), n) for k in ("burn", "ind", "sh", "d_ind", "und", "deg", "rain")}
    R = _read("reg")[0]
    rr, cc = cells.r.to_numpy(), cells.c.to_numpy()
    A["reg"] = np.stack([R[f"reg_{min(y, 2024)}"][rr, cc] for y in YEARS])
    return cells, A


def stage_rates(_a):
    import numpy as np
    import pandas as pd
    cells, A = _arrays()
    yrs = np.array(YEARS)
    dry = np.isin(yrs, DRY)
    rows = []
    for st in ["all"] + STATUS_ORDER + ["none"]:
        sel = np.ones(len(cells), bool) if st == "all" else (cells.status == st).to_numpy()
        for pt, pm in (("peat", cells.peat.to_numpy()), ("mineral", ~cells.peat.to_numpy())):
            m = sel & pm
            if m.sum() < 500:
                continue
            b = A["burn"][:, m]
            rows.append({"status": st, "soil": pt, "cells": int(m.sum()),
                         "km2": round(float(m.sum() * CELL_KM ** 2)),
                         "burned_pct_dry": round(100 * float(b[dry].mean()), 2),
                         "burned_pct_normal": round(100 * float(b[~dry].mean()), 2),
                         "share_of_all_burned_pct": round(100 * float(b.sum() / A["burn"].sum()), 1)})
    out = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    out.to_csv(os.path.join(OUT, "fire_rates_status.csv"), index=False)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))


ACCESS = ["d_road", "d_river", "elev", "slope"]   # pop00 left out: GHS-POP band came out wrong (negative, ~0)


def _groups(cells):
    g = dict(GROUPS)
    if all(c in cells for c in ACCESS):
        g["access & terrain"] = ACCESS
    return g


def _features(cells, A, idx, t, rain_anom=None, L=1):
    """Predictors for year index t (t == len(YEARS) is 2026) on cells idx. Land state and fire history
    come from the end of year t-L (L=2: two years ahead); rain_anom overrides the rain ratio of year t."""
    import numpy as np
    import pandas as pd
    rain = A["rain"][:, idx].astype(np.float32)
    rain_mean = rain.mean(0)
    lag = {k: A[k][t - L, idx] for k in ("burn", "ind", "sh", "d_ind", "und", "deg", "reg")}
    prev_und = A["und"][t - L - 1, idx] if t - L >= 1 else cells.und2000.to_numpy()[idx]
    prev_deg = A["deg"][t - L - 1, idx] if t - L >= 1 else lag["deg"]
    ra = rain_anom if rain_anom is not None else rain[t] / np.maximum(rain_mean, 1)
    d = pd.DataFrame({
        "cell": idx, "year": YEARS[0] + t,
        "rain_anom": np.broadcast_to(ra, idx.shape).astype(np.float32), "rain_mean": rain_mean,
        "peat": cells.peat.to_numpy()[idx].astype(np.uint8), "depth": cells.depth.to_numpy()[idx],
        "und_l": lag["und"], "deg_l": lag["deg"], "reg_l": lag["reg"],
        "dund": prev_und.astype(np.int16) - lag["und"].astype(np.int16),
        "ddeg": lag["deg"].astype(np.int16) - prev_deg.astype(np.int16),
        "ind_l": lag["ind"], "sh_l": lag["sh"], "d_ind_l": np.minimum(lag["d_ind"], 50),
        "conc": cells.conc.to_numpy()[idx].astype(np.uint8), "hti": cells.hti.to_numpy()[idx].astype(np.uint8),
        "status": pd.Categorical(cells.status.to_numpy()[idx], categories=STATUS_ORDER + ["none"]).codes.astype(np.int8),
        "built00": cells.built00.to_numpy()[idx],
        "burn_l1": lag["burn"], "nburn_l3": A["burn"][max(t - L - 2, 0):t - L + 1, idx].sum(0),
    })
    for c in ACCESS:
        if c in cells:
            d[c] = cells[c].to_numpy()[idx]
    if t < A["burn"].shape[0]:
        d["burn"] = A["burn"][t, idx]
    return d


def _design(cells, A, sample, seed=0, L=1, last=None):
    """Cell-year rows (2001+L .. last year index, default 2025) on a random sample of cells."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    n = len(cells)
    idx = np.sort(rng.choice(n, size=min(sample, n), replace=False))
    last = len(YEARS) - 1 if last is None else last
    d = pd.concat([_features(cells, A, idx, t, L=L) for t in range(L, last + 1)], ignore_index=True)
    r = cells.r.to_numpy()[d.cell.to_numpy()]
    c = cells.c.to_numpy()[d.cell.to_numpy()]
    d["fold_block"] = (r * CELL_KM // BLOCK_CV_KM).astype(int) * 1000 + (c * CELL_KM // BLOCK_CV_KM).astype(int)
    return d


def stage_access(_a):
    """Distance to roads and rivers (km, EDT on the grid), elevation, slope, population 2000 -> cells."""
    import numpy as np
    import pandas as pd
    from scipy import ndimage
    X = _read("access")[0]
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    rr, cc = cells.r.to_numpy(), cells.c.to_numpy()
    cells["d_road"] = (ndimage.distance_transform_edt(X["road"] == 0) * CELL_KM)[rr, cc].astype(np.float32)
    cells["d_river"] = (ndimage.distance_transform_edt(X["river"] == 0) * CELL_KM)[rr, cc].astype(np.float32)
    cells["elev"] = X["elev"][rr, cc].astype(np.int16)
    cells["slope"] = (X["slope10"][rr, cc] / 10).astype(np.float32)
    cells["pop00"] = X["pop00"][rr, cc].astype(np.float32)
    cells.to_parquet(os.path.join(DATA, "cells.parquet"))
    print(cells[ACCESS].describe().round(1).to_string())


def _fit(X, y, feats):
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
                                       min_samples_leaf=200, l2_regularization=1.0,
                                       categorical_features=[f == "status" for f in feats],
                                       early_stopping=False, random_state=0)
    return m.fit(X[feats], y)


def stage_model(a):
    import numpy as np
    import pandas as pd
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import GroupKFold
    cells, A = _arrays()
    d = _design(cells, A, a.sample)
    y = d.burn.to_numpy()
    print(f"rows {len(d):,}, cells {d.cell.nunique():,}, burned {100 * y.mean():.2f}%", flush=True)
    G = _groups(cells)
    allf = [f for g in G.values() for f in g]
    res = {"rows": len(d), "cells": int(d.cell.nunique()), "burn_rate_pct": round(100 * float(y.mean()), 3),
           "block_cv_km": BLOCK_CV_KM, "groups": G}

    def score(p, yy):
        return {"pr_auc": float(average_precision_score(yy, p)), "roc_auc": float(roc_auc_score(yy, p))}

    rows = []
    for label, base in (("with fire history", allf),
                        ("without fire history", [f for f in allf if f not in G["fire history"]])):
        gkf = GroupKFold(n_splits=a.folds)
        names = [g for g in G if label == "with fire history" or g != "fire history"]
        oof = {k: np.zeros(len(d)) for k in ["full"] + names}
        perm = {g: np.zeros(len(d)) for g in names}
        for k, (tr, te) in enumerate(gkf.split(d, y, d.fold_block)):
            m = _fit(d.iloc[tr], y[tr], base)
            Xte = d.iloc[te][base].copy()
            oof["full"][te] = m.predict_proba(Xte)[:, 1]
            rng = np.random.default_rng(k)
            for g in names:                                   # permutation: shuffle the whole group
                Xp = Xte.copy()
                sh = rng.permutation(len(Xp))
                Xp[G[g]] = Xte[G[g]].to_numpy()[sh]
                perm[g][te] = m.predict_proba(Xp)[:, 1]
                if a.drop:                                    # drop-group refit
                    f2 = [f for f in base if f not in G[g]]
                    oof[g][te] = _fit(d.iloc[tr], y[tr], f2).predict_proba(d.iloc[te][f2])[:, 1]
            print(f"  [{label}] fold {k + 1}/{a.folds} done", flush=True)
        full = score(oof["full"], y)
        res[label] = {"full": full}
        for g in names:
            row = {"model": label, "group": g,
                   "perm_pr_auc_loss": full["pr_auc"] - score(perm[g], y)["pr_auc"],
                   "perm_roc_auc_loss": full["roc_auc"] - score(perm[g], y)["roc_auc"]}
            if a.drop:
                s = score(oof[g], y)
                row |= {"drop_pr_auc_loss": full["pr_auc"] - s["pr_auc"],
                        "drop_roc_auc_loss": full["roc_auc"] - s["roc_auc"]}
            rows.append(row)
        print(f"{label}: spatial-block CV PR-AUC {full['pr_auc']:.3f} (base rate {y.mean():.3f}), "
              f"ROC-AUC {full['roc_auc']:.3f}", flush=True)
        # temporal check: train 2002-2018, predict 2019-2025
        trm, tem = d.year.to_numpy() <= 2018, d.year.to_numpy() >= 2019
        m = _fit(d[trm], y[trm], base)
        res[label]["temporal_2019_2025"] = score(m.predict_proba(d[tem][base])[:, 1], y[tem])
        res[label]["temporal_2019_2025"]["base_rate"] = float(y[tem].mean())
        print(f"{label}: train 2002-2018 -> 2019-2025 {res[label]['temporal_2019_2025']}", flush=True)
    imp = pd.DataFrame(rows).round(4)
    imp.to_csv(os.path.join(OUT, "fire_factors_importance.csv"), index=False)
    json.dump(res, open(os.path.join(OUT, "fire_factors.json"), "w"), indent=1, default=float)
    pd.set_option("display.width", 200)
    for label in ("with fire history", "without fire history"):
        t = imp[imp.model == label].sort_values("perm_pr_auc_loss", ascending=False)
        print(f"\n-- {label} (loss in PR-AUC / ROC-AUC when the group is shuffled or dropped)\n",
              t.drop(columns="model").to_string(index=False))


def stage_predict(a):
    """Fire-prone map for the 2026 season. Hindcast check first: train on 2002-2018 and rank the cells
    for 2019 (dry) and 2023; report the share of burned area that falls in the top 5 / 10 / 20% of risk.
    Then train on 2002-2025 and predict 2026 under a normal season (rain ratio 1) and a dry season (each
    cell's mean Jun-Oct rain ratio in the dry years)."""
    import numpy as np
    import pandas as pd
    import rasterio
    cells, A = _arrays()
    G = _groups(cells)
    feats = [f for g in G.values() for f in g]
    d = _design(cells, A, a.sample)
    n = len(cells)
    allidx = np.arange(n)
    res = {"features": feats, "hindcast": {}}

    def capture(p, b, area_w=None):
        o = np.argsort(-p)
        cum = np.cumsum(b[o]) / max(b.sum(), 1)
        return {f"top{q}pct_captures_pct": round(100 * float(cum[int(len(p) * q / 100) - 1]), 1) for q in (5, 10, 20)}
    m = _fit(d[d.year <= 2018], d.burn[d.year <= 2018].to_numpy(), feats)
    for y in (2019, 2023, 2024):
        t = YEARS.index(y)
        X = _features(cells, A, allidx, t)
        p = m.predict_proba(X[feats])[:, 1]
        res["hindcast"][y] = {"burned_cells": int(X.burn.sum()), **capture(p, X.burn.to_numpy())}
        # simple baselines: peat only, fire history only
        base_peat = cells.peat.to_numpy() * 1.0 + 1e-6 * np.random.default_rng(0).random(n)
        base_hist = X.nburn_l3.to_numpy() + 0.5 * X.peat.to_numpy() + 1e-6 * np.random.default_rng(1).random(n)
        res["hindcast"][y]["baseline_peat"] = capture(base_peat, X.burn.to_numpy())
        res["hindcast"][y]["baseline_history_peat"] = capture(base_hist, X.burn.to_numpy())
        print(y, res["hindcast"][y], flush=True)
    m = _fit(d, d.burn.to_numpy(), feats)
    t = len(YEARS)
    rain = A["rain"].astype(np.float32)
    ratio = rain / np.maximum(rain.mean(0), 1)
    dry_ratio = ratio[[YEARS.index(y) for y in DRY]].mean(0)
    out = {}
    for scen, ra in (("normal", np.ones(n, np.float32)), ("dry", dry_ratio)):
        X = _features(cells, A, allidx, t, rain_anom=ra)
        out[scen] = m.predict_proba(X[feats])[:, 1]
    _, tr, crs, shp = _read("env")
    with rasterio.open(os.path.join(OUT, "fire_risk_2026.tif"), "w", driver="GTiff", height=shp[0], width=shp[1],
                       count=2, dtype="float32", crs=crs, transform=tr, compress="deflate", nodata=-1) as ds:
        for i, scen in enumerate(("normal", "dry")):
            band = np.full(shp, -1, np.float32)
            band[cells.r.to_numpy(), cells.c.to_numpy()] = out[scen]
            ds.write(band, i + 1)
            ds.set_band_description(i + 1, f"p_burn_2026_{scen}")
    # where the top 5% (dry scenario) lies
    p = out["dry"]
    top = p >= np.quantile(p, 0.95)
    X = _features(cells, A, allidx, t, rain_anom=dry_ratio)
    tab = pd.DataFrame({"status": cells.status, "soil": np.where(cells.peat, "peat", "mineral"), "top": top,
                        "forest": np.where(X.und_l >= 90, "intact", np.where(X.und_l >= 30, "partial", "open")),
                        "near_palm": np.where(X.d_ind_l <= 5, "<=5 km", ">5 km")})
    summ = {}
    for k in ("status", "soil", "forest", "near_palm"):
        g = tab.groupby(k).top.agg(["sum", "size"])
        summ[k] = {str(i): {"share_of_top5_pct": round(100 * r_["sum"] / top.sum(), 1),
                            "pct_of_class_in_top5": round(100 * r_["sum"] / r_["size"], 1)} for i, r_ in g.iterrows()}
    res["top5_dry_2026"] = summ
    res["expected_burned_km2_2026"] = {s: round(float(out[s].sum() * CELL_KM ** 2)) for s in out}
    json.dump(res, open(os.path.join(OUT, "fire_predict_2026.json"), "w"), indent=1, default=float)
    print(json.dumps({k: v for k, v in res.items() if k != "features"}, indent=1, default=float))


def _viirs_cells(cells, year=2026):
    """Grid cells with >= 1 nominal/high-confidence VIIRS detection in `year` (local FIRMS file)."""
    import numpy as np
    import pandas as pd
    v = pd.read_parquet(os.path.join(os.path.dirname(DATA), "kalimantan", f"viirs_{year}.parquet"))
    if v.confidence.dtype.kind in "iu":                         # 0 low, 1 nominal, 2 high
        v = v[v.confidence >= 1]
    else:
        v = v[v.confidence.astype(str).str.lower().str[0].isin(["n", "h"])]
    g = json.load(open(os.path.join(DATA, "grid.json")))
    px, x0, y0 = g["transform"][0], g["transform"][2], g["transform"][5]
    R = 6371007.181
    lat = np.radians(v.lat.to_numpy())
    x = R * np.radians(v.lon.to_numpy()) * np.cos(lat)
    y = R * lat
    r = ((y0 - y) / px).astype(int)
    c = ((x - x0) / px).astype(int)
    H, W = g["shape"]
    ok = (r >= 0) & (r < H) & (c >= 0) & (c < W)
    hit = np.zeros((H, W), bool)
    hit[r[ok], c[ok]] = True
    t = pd.to_datetime(v.acq_epoch, unit="s")
    return hit[cells.r.to_numpy(), cells.c.to_numpy()], (str(t.min().date()), str(t.max().date()), int(ok.sum()))


def stage_forecast(a):
    """(1) 2026 out-of-sample test against MCD64A1 Jan-Sep 2026 and VIIRS 2026; (2) 2027 normal and dry
    scenarios with 2026 fires as history; (3) one- vs two-year-ahead skill in hindcasts 2019/2023/2024.
    Uses Jun-Sep rain throughout (CHIRPS ends Sep 2026). Land layers stop at 2024 (TMF) and 2021 (palm)
    and are carried forward unchanged."""
    import numpy as np
    import pandas as pd
    import rasterio
    cells, A = _arrays()
    Y = _read("y2026")[0]
    rr, cc = cells.r.to_numpy(), cells.c.to_numpy()
    A["rain"] = np.stack([Y[f"rainjs_{y}"][rr, cc] for y in list(YEARS) + [2026]])
    for k in ("ind", "sh", "d_ind", "und", "deg", "reg"):
        A[k] = np.vstack([A[k], A[k][-1:]])                       # 2026 land state = last known
    A["burn"] = np.vstack([A["burn"], (Y["burn_2026"][rr, cc] > 0)[None].astype(A["burn"].dtype)])
    G = _groups(cells)
    feats = [f for g in G.values() for f in g]
    n = len(cells)
    allidx = np.arange(n)
    t26 = len(YEARS)
    rng = np.random.default_rng(0)

    def capture(p, b):
        o = np.argsort(-(p + 1e-9 * rng.random(len(p))))
        cum = np.cumsum(b[o]) / max(b.sum(), 1)
        return {f"top{q}": round(100 * float(cum[int(len(p) * q / 100) - 1]), 1) for q in (5, 10, 20)}
    res = {"note": "capture = % of burned (or VIIRS-hit) cells inside the top q% risk cells", "features": feats}

    # (3) one- vs two-year-ahead hindcasts
    res["lead_time"] = {}
    for L in (1, 2):
        d = _design(cells, A, a.sample, L=L, last=YEARS.index(2018))
        m = _fit(d, d.burn.to_numpy(), feats)
        for y in (2019, 2023, 2024):
            X = _features(cells, A, allidx, YEARS.index(y), L=L)
            res["lead_time"][f"L{L}_{y}"] = capture(m.predict_proba(X[feats])[:, 1], X.burn.to_numpy())
        print(f"lead {L} yr:", {k: v for k, v in res["lead_time"].items() if k.startswith(f"L{L}")}, flush=True)

    # (1) 2026 test: train 2002-2025, predict 2026 with observed Jun-Sep rain and with scenarios
    d = _design(cells, A, a.sample)
    m = _fit(d, d.burn.to_numpy(), feats)
    ratio = A["rain"].astype(np.float32) / np.maximum(A["rain"][:t26].astype(np.float32).mean(0), 1)
    dry = ratio[[YEARS.index(y) for y in DRY]].mean(0)
    vi, vmeta = _viirs_cells(cells)
    truth = {"MCD64A1 Jan-Sep 2026": A["burn"][t26].astype(bool), "VIIRS 2026": vi}
    res["test_2026"] = {"viirs_dates_detections": vmeta,
                        "mcd64_burned_cells": int(truth["MCD64A1 Jan-Sep 2026"].sum()),
                        "viirs_cells": int(vi.sum()),
                        "jun_sep_rain_ratio_2026_median": round(float(np.median(ratio[t26])), 2)}
    for scen, ra in (("observed rain", None), ("normal", np.ones(n, np.float32)), ("dry", dry)):
        X = _features(cells, A, allidx, t26, rain_anom=ra)
        p = m.predict_proba(X[feats])[:, 1]
        for tn, tv in truth.items():
            res["test_2026"][f"{scen} vs {tn}"] = capture(p, tv)
    base_hist = A["burn"][t26 - 3:t26].sum(0) + 0.5 * cells.peat.to_numpy()
    for tn, tv in truth.items():
        res["test_2026"][f"baseline peat+recent fire vs {tn}"] = capture(base_hist.astype(float), tv)
        res["test_2026"][f"baseline peat only vs {tn}"] = capture(cells.peat.to_numpy().astype(float), tv)
    print("test 2026:", json.dumps(res["test_2026"], indent=1), flush=True)

    # (2) 2027 scenarios: retrain on 2002-2026, land state end-2026 (carried), fires to Sep 2026
    t27 = t26 + 1
    for k in A:
        if k not in ("burn", "rain") and A[k].shape[0] == t27:
            A[k] = np.vstack([A[k], A[k][-1:]])
    A["rain"] = np.vstack([A["rain"], A["rain"].mean(0, keepdims=True)])   # placeholder: keeps the cell mean
    d = _design(cells, A, a.sample, last=t26)
    m = _fit(d, d.burn.to_numpy(), feats)
    out = {}
    for scen, ra in (("normal", np.ones(n, np.float32)), ("dry", dry)):
        X = _features(cells, A, allidx, t27, rain_anom=ra)
        out[scen] = m.predict_proba(X[feats])[:, 1]
    _, tr, crs, shp = _read("env")
    with rasterio.open(os.path.join(OUT, "fire_risk_2027.tif"), "w", driver="GTiff", height=shp[0], width=shp[1],
                       count=2, dtype="float32", crs=crs, transform=tr, compress="deflate", nodata=-1) as ds:
        for i, scen in enumerate(("normal", "dry")):
            band = np.full(shp, -1, np.float32)
            band[rr, cc] = out[scen]
            ds.write(band, i + 1)
            ds.set_band_description(i + 1, f"p_burn_2027_{scen}")
    X = _features(cells, A, allidx, t27, rain_anom=dry)
    tab = pd.DataFrame({"status": cells.status, "soil": np.where(cells.peat, "peat", "mineral"),
                        "forest": np.where(X.und_l >= 90, "intact", np.where(X.und_l >= 30, "partial", "open")),
                        "near_palm": np.where(X.d_ind_l <= 5, "<=5 km", ">5 km"),
                        "burned_2024_26": np.where(A["burn"][t26 - 2:t27].sum(0) > 0, "yes", "no")})
    res["forecast_2027"] = {"expected_burned_km2": {s: round(float(out[s].sum() * CELL_KM ** 2)) for s in out},
                            "top5_overlap_normal_dry_pct": round(100 * float(
                                ((out["normal"] >= np.quantile(out["normal"], .95)) &
                                 (out["dry"] >= np.quantile(out["dry"], .95))).sum() / (0.05 * n)), 1)}
    top = out["dry"] >= np.quantile(out["dry"], 0.95)
    for k in tab.columns:
        g = pd.DataFrame({"k": tab[k], "top": top}).groupby("k").top.agg(["sum", "size"])
        res["forecast_2027"][f"top5_dry_by_{k}"] = {
            str(i): {"share_of_top5_pct": round(100 * r_["sum"] / top.sum(), 1),
                     "pct_of_class_in_top5": round(100 * r_["sum"] / r_["size"], 1)} for i, r_ in g.iterrows()}
    json.dump(res, open(os.path.join(OUT, "fire_forecast_2027.json"), "w"), indent=1, default=float)
    print("forecast 2027:", json.dumps(res["forecast_2027"], indent=1), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", required=True, choices=["status", "access", "rates", "model", "predict", "forecast"])
    ap.add_argument("--sample", type=int, default=SAMPLE_CELLS, help="model: number of cells sampled")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--drop", action="store_true", help="model: also refit without each group (slow)")
    a = ap.parse_args()
    {"status": stage_status, "access": stage_access, "rates": stage_rates, "model": stage_model,
     "predict": stage_predict, "forecast": stage_forecast}[a.stage](a)


if __name__ == "__main__":
    main()
