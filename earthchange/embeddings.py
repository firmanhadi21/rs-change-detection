#!/usr/bin/env python3
"""Embeddings — change, similarity, few-shot classes and clusters from
pre-computed Earth-observation foundation-model embeddings.

Each 10 m pixel of each year is a vector summarising a year of Sentinel-1/2
(and Landsat) observations. Two sources:

  --source aef      Google DeepMind AlphaEarth Foundations, the Earth Engine
                    collection GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL (64-d,
                    unit length, 2017 onwards). Runs on Earth Engine, so it
                    scales to a province.
  --source tessera  TESSERA (Cambridge), streamed with geotessera (128-d,
                    2017-2025). Runs locally; keep the area to a few tens of
                    km or use --stride 2 (20 m).

Modes (--emb-mode):
  change    1 - cosine similarity between --start-year and each later year,
            the share of the area above --change-thr, and the first year a
            pixel crossed it.
  similar   cosine similarity to the mean vector of one class in --labels
            (--like CLASS): everything that looks like the examples.
  classify  a random forest trained on --labels polygons (property "class")
            in --train-year, applied to every year: area per class per year.
            The polygons are split into two folds per class; each fold is
            scored by a model trained on the other, so the accuracy is
            measured on places the model never saw.
  clusters  k-means with --k groups, no labels.

Outputs: stats.json, area_by_class_year.csv (classify / similar / change),
per-year class or score maps (PNG; GeoTIFF for tessera and the last year of
aef), and a chart.
"""

import csv
import json
import math
import os

import numpy as np

AEF = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
PALETTE = {"bare": "#e6550d", "built": "#636363", "forest": "#1b7837",
           "other_veg": "#a6d96a", "water": "#2c7fb8"}
STABLE = {"forest", "water"}          # classes assumed unchanged since the start year
FALLBACK = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628",
            "#f781bf", "#999999", "#66c2a5", "#ffd92f"]


# ----------------------------- pure helpers (testable) -----------------------------
def unit(v, axis=-1):
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.where(n > 0, n, 1)


def cosine_change(a, b):
    """1 - cosine similarity of two (..., D) arrays; NaN where either is NaN."""
    return 1.0 - np.sum(unit(a) * unit(b), axis=-1)


def first_crossing(series, years, thr):
    """series: (Y, H, W) change scores vs the base year. Returns the first year
    with score > thr, 0 where it never crosses."""
    out = np.zeros(series.shape[1:], "int16")
    for k in range(len(years) - 1, -1, -1):        # walk back so the earliest wins
        out = np.where(series[k] > thr, years[k], out)
    return out


def similarity(arr, ref):
    """Cosine similarity of every vector in (..., D) to one reference vector."""
    return np.sum(unit(arr) * unit(np.asarray(ref, "f4")), axis=-1)


def folds_by_polygon(poly_ids, classes):
    """Two folds, alternating polygons within each class, so a fold never
    shares a polygon (and so never shares neighbouring pixels) with the other."""
    fold = {}
    for c in sorted(set(classes)):
        ps = sorted({p for p, k in zip(poly_ids, classes) if k == c})
        for i, p in enumerate(ps):
            fold[p] = i % 2
    return np.array([fold[p] for p in poly_ids])


def expansion_table(cls, first, targets, years, px_ha):
    """Area of the target classes (in the label year) by the first year the pixel's
    embedding departed from the start year. first == 0: never departed (already
    open at the start, or a change too small to cross the threshold)."""
    m = np.isin(cls, targets)
    out = {"before_or_unchanged": round(float((m & (first == 0)).sum() * px_ha), 1)}
    for y in years[1:]:
        out[str(y)] = round(float((m & (first == y)).sum() * px_ha), 1)
    return out


def stable_threshold(values, q=99.0):
    """Change threshold from pixels that should not have changed (closed forest,
    water): the q-th percentile of their 1 - cosine similarity."""
    v = np.asarray(values, "f8")
    v = v[np.isfinite(v)]
    if v.size == 0:
        raise ValueError("no stable pixels to calibrate the change threshold")
    return float(np.percentile(v, q))


def class_colors(names):
    return [PALETTE.get(n, FALLBACK[i % len(FALLBACK)]) for i, n in enumerate(names)]


def load_labels(path):
    with open(path) as f:
        gj = json.load(f)
    feats = [ft for ft in gj["features"] if ft.get("properties", {}).get("class")]
    if not feats:
        raise SystemExit(f"{path}: no features with a 'class' property.")
    names = sorted({ft["properties"]["class"] for ft in feats})
    return feats, names


def land_geojson(bbox, config_key=None):
    """Land inside the bbox from FAO GAUL 2025 (admin-1 polygons), as GeoJSON.

    Embeddings exist over coastal water too, and shallow reef or turbid water
    can look like built-up ground to a classifier, so areas are counted on land
    only. Water bodies inland (lakes, rivers) stay in and keep their own class.
    """
    import ee
    from .gee_utils import gaul, initialize_ee
    initialize_ee(config_key)
    rect = ee.Geometry.Rectangle(list(bbox))
    g = gaul(1).filterBounds(rect).geometry().intersection(rect, 1)
    return {"type": "Feature", "properties": {"source": "FAO GAUL 2025 level 1"},
            "geometry": g.getInfo()}


def land_mask_grid(land, shape, transform, crs):
    from rasterio import features as rf
    from pyproj import Transformer
    from shapely.geometry import shape as shp
    from shapely.ops import transform as stf
    g = stf(Transformer.from_crs(4326, crs, always_xy=True).transform, shp(land["geometry"]))
    return rf.rasterize([(g, 1)], out_shape=shape, transform=transform).astype(bool)


# ----------------------------- TESSERA (local) -----------------------------
def _tess():
    try:
        from geotessera import GeoTesseraZarr
    except ImportError:
        raise SystemExit("--source tessera needs geotessera >= 0.11: pip install 'geotessera>=0.11'")
    return GeoTesseraZarr()


def tess_read(gt, bbox, year, stride=1):
    """(H, W, D) float32 with NaN outside coverage, affine transform, CRS."""
    from affine import Affine
    arr, tr, crs = gt.read_region(tuple(bbox), year=year)
    arr = np.asarray(arr, "f4")
    if stride > 1:
        arr = arr[::stride, ::stride]
        tr = tr * Affine.scale(stride)
    return arr, tr, crs


def _poly_pixels(gt, feat, year, cap, rng):
    from rasterio import features as rf
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as stf
    g = shape(feat["geometry"])
    arr, tr, crs = tess_read(gt, g.bounds, year)
    gp = stf(Transformer.from_crs(4326, crs, always_xy=True).transform, g)
    m = rf.rasterize([(gp, 1)], out_shape=arr.shape[:2], transform=tr).astype(bool)
    m &= ~np.isnan(arr).any(-1)
    X = arr[m]
    if len(X) > cap:
        X = X[rng.choice(len(X), cap, replace=False)]
    return X


def _poly_change(gt, feat, y0, y1, cap=2000, seed=0):
    """1 - cosine similarity between two years for the pixels of one polygon."""
    from rasterio import features as rf
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as stf
    g = shape(feat["geometry"])
    a, tr, crs = tess_read(gt, g.bounds, y0)
    b, _, _ = tess_read(gt, g.bounds, y1)
    gp = stf(Transformer.from_crs(4326, crs, always_xy=True).transform, g)
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    m = rf.rasterize([(gp, 1)], out_shape=(h, w), transform=tr).astype(bool)
    c = cosine_change(a[:h, :w], b[:h, :w])[m]
    c = c[np.isfinite(c)]
    if len(c) > cap:
        c = np.random.default_rng(seed).choice(c, cap, replace=False)
    return c


def tess_training(gt, feats, names, year, cap=600, seed=0):
    rng = np.random.default_rng(seed)
    X, y, pid = [], [], []
    for i, ft in enumerate(feats):
        x = _poly_pixels(gt, ft, year, cap, rng)
        X.append(x); y += [names.index(ft["properties"]["class"])] * len(x); pid += [i] * len(x)
    return np.concatenate(X), np.array(y), np.array(pid)


def rf_model(n=200, seed=0):
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(n_estimators=n, class_weight="balanced", n_jobs=-1,
                                  random_state=seed, min_samples_leaf=2)


def fold_accuracy(X, y, pid, names):
    """Polygon-held-out accuracy (mean of the two folds) and per-class recall."""
    from sklearn.metrics import confusion_matrix
    f = folds_by_polygon(pid, y)
    preds = np.empty_like(y)
    for k in (0, 1):
        tr, te = f != k, f == k
        if len(set(y[tr])) < len(names) or te.sum() == 0:
            continue
        preds[te] = rf_model().fit(X[tr], y[tr]).predict(X[te])
    cm = confusion_matrix(y, preds, labels=range(len(names)))
    recall = {n: round(float(cm[i, i] / cm[i].sum()), 3) if cm[i].sum() else None
              for i, n in enumerate(names)}
    return round(float((preds == y).mean()), 3), recall, cm.tolist()


def tess_predict(model, arr, chunk=400_000):
    H, W, D = arr.shape
    flat = arr.reshape(-1, D)
    ok = ~np.isnan(flat).any(1)
    out = np.full(H * W, 255, "uint8")
    idx = np.flatnonzero(ok)
    for s in range(0, len(idx), chunk):
        j = idx[s:s + chunk]
        out[j] = model.predict(flat[j]).astype("uint8")
    return out.reshape(H, W)


def _write_tif(path, a, tr, crs, nodata):
    import rasterio
    with rasterio.open(path, "w", driver="GTiff", height=a.shape[0], width=a.shape[1], count=1,
                       dtype=a.dtype, crs=crs, transform=tr, nodata=nodata, compress="deflate") as w:
        w.write(a, 1)


# ----------------------------- AlphaEarth (Earth Engine) -----------------------------
def aef_year(geom, year):
    import ee
    return (ee.ImageCollection(AEF).filterBounds(geom)
            .filterDate(f"{year}-01-01", f"{year + 1}-01-01").mosaic())


def aef_training(feats, names, year, per_poly=400):
    import ee
    fcs = []
    for i, ft in enumerate(feats):
        g = ee.Geometry(ft["geometry"])
        s = aef_year(g, year).sample(region=g, scale=10, numPixels=per_poly, seed=i,
                                     geometries=False)
        fcs.append(s.map(lambda f, i=i, c=names.index(ft["properties"]["class"]):
                         f.set({"cls": c, "poly": i})))
    return ee.FeatureCollection(fcs).flatten()


def aef_rf(n=200):
    import ee
    return ee.Classifier.smileRandomForest(numberOfTrees=n, minLeafPopulation=2, seed=0)


def aef_fold_accuracy(samples, bands, feats, names):
    import ee
    classes = [names.index(ft["properties"]["class"]) for ft in feats]
    fold = folds_by_polygon(list(range(len(feats))), classes)
    fpoly = {k: [i for i in range(len(feats)) if fold[i] == k] for k in (0, 1)}
    hits, total, cms = 0, 0, None
    for k in (0, 1):
        tr = samples.filter(ee.Filter.inList("poly", fpoly[1 - k]))
        te = samples.filter(ee.Filter.inList("poly", fpoly[k]))
        clf = aef_rf().train(tr, "cls", bands)
        cm = np.array(te.classify(clf).errorMatrix("cls", "classification",
                                                    list(range(len(names)))).getInfo())
        cms = cm if cms is None else cms + cm
    recall = {n: round(float(cms[i, i] / cms[i].sum()), 3) if cms[i].sum() else None
              for i, n in enumerate(names)}
    return round(float(np.trace(cms) / cms.sum()), 3), recall, cms.tolist()


def aef_class_area(cls_img, geom, n):
    import ee
    g = (ee.Image.pixelArea().divide(1e4).addBands(cls_img.rename("c"))
         .reduceRegion(ee.Reducer.sum().group(1, "c"), geom, 10, maxPixels=1e12, tileScale=4)
         .getInfo()["groups"])
    out = {i: 0.0 for i in range(n)}
    for r in g:
        out[int(r["c"])] = round(r["sum"], 1)
    return out


def _thumb(img, geom, path, vis, width=900):
    import urllib.request
    url = img.visualize(**vis).getThumbURL({"region": geom, "dimensions": width, "format": "png"})
    with open(path, "wb") as f:
        f.write(urllib.request.urlopen(url, timeout=300).read())


# ----------------------------- figures -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def chart_areas(areas, names, path, title, ref=None):
    """areas: {year: {class: ha}}; ref: optional {year: ha} (e.g. Dynamic World)."""
    plt = _plt()
    ys = sorted(areas)
    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    for n, c in zip(names, class_colors(names)):
        if n in ("forest", "water", "other_veg"):
            continue
        ax.plot(ys, [areas[y].get(n, 0) for y in ys], "-o", color=c, label=n, lw=2)
    if ref:
        ry = sorted(int(k) for k in ref)
        ax.plot(ry, [ref[str(y)] if str(y) in ref else ref[y] for y in ry], "--", color="k",
                label="Dynamic World bare + built", lw=1.4)
    ax.set_ylabel("ha")
    ax.set_title(title, loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_expansion(tab, years, dw, path, title):
    """Cumulative open ground by year of first embedding change, with Dynamic World."""
    plt = _plt()
    cum, ys, vals = tab["before_or_unchanged"], [years[0]], [tab["before_or_unchanged"]]
    for y in years[1:]:
        cum += tab[str(y)]
        ys.append(y); vals.append(cum)
    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax.plot(ys, vals, "-o", color="#e6550d", lw=2, label="embedding: open ground by year it changed")
    if dw:
        ry = sorted(int(k) for k in dw)
        ax.plot(ry, [dw[str(y)] for y in ry], "--", color="k", lw=1.4,
                label="Dynamic World bare + built (all surfaces in the box)")
    ax.set_ylabel("ha")
    ax.set_title(title, loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def panel(maps, years, names, path, title):
    """Small multiples of class maps (uint8 arrays, 255 = no data)."""
    plt = _plt()
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    cols = min(5, len(years))
    rows = math.ceil(len(years) / cols)
    h, w = maps[0].shape
    fig, axs = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.2 * rows * h / w + 0.6),
                            constrained_layout=True, squeeze=False)
    cmap = ListedColormap(class_colors(names))
    for ax in axs.flat:
        ax.axis("off")
    for ax, m, y in zip(axs.flat, maps, years):
        ax.imshow(np.ma.masked_equal(m, 255), cmap=cmap, vmin=0, vmax=len(names) - 1,
                  interpolation="nearest")
        ax.set_title(str(y), fontsize=10)
    fig.legend(handles=[Patch(color=c, label=n) for n, c in zip(names, class_colors(names))],
               loc="lower center", ncol=len(names), frameon=False, fontsize=9)
    fig.suptitle(title, fontsize=11)
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None, admin=None,
        bbox=None, source="aef", mode="classify", start_year=2017, end_year=2025,
        labels=None, like=None, k=8, train_year=None, change_thr=0.3, stride=1,
        compare_dw=False, land_only=True, targets=("bare", "built")):
    import datetime as dt  # noqa: F401
    start_year, end_year = start_year or 2017, end_year or 2025
    years = list(range(start_year, end_year + 1))
    train_year = train_year or end_year
    if mode in ("classify", "similar", "expansion") and not labels:
        raise SystemExit(f"--emb-mode {mode} needs --labels FILE.geojson (polygons with a 'class').")
    os.makedirs(run_dir, exist_ok=True)
    if bbox is None:
        d = radius / 111.32
        bbox = [lon - d, lat - d, lon + d, lat + d]
    feats, names = load_labels(labels) if labels else ([], [])
    stats = {"run_id": run_id, "scenario": "embeddings", "source": source, "mode": mode,
             "name": name, "bbox": list(bbox), "years": years, "train_year": train_year,
             "labels": os.path.basename(labels) if labels else None, "classes": names}
    land = None
    if land_only:
        land = land_geojson(bbox, config_key)
        with open(os.path.join(run_dir, "land.geojson"), "w") as f:
            json.dump(land, f)
        stats["land_mask"] = "FAO GAUL 2025 level 1 (areas counted on land only)"
    if source == "aef":
        out = _run_aef(bbox, years, mode, feats, names, train_year, like, k, change_thr,
                       run_dir, name, config_key, stats, land, targets)
    elif source == "tessera":
        out = _run_tess(bbox, years, mode, feats, names, train_year, like, k, change_thr,
                        stride, run_dir, name, stats, land, targets)
    else:
        raise SystemExit("--source must be aef or tessera")
    if compare_dw and out:
        from .forest_account import open_ground
        from .gee_utils import initialize_ee
        import ee
        initialize_ee(config_key)
        og = open_ground(ee.Geometry.Rectangle(list(bbox)), [y for y in years if y >= 2016])
        stats["dynamic_world_bare_built_ha"] = {str(y): round(v["bare"] + v["built"], 1)
                                                for y, v in og.items()}
    if mode == "expansion" and out:
        tab = stats["expansion_ha"]
        with open(os.path.join(run_dir, "expansion.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["first_change_year", "ha", "cumulative_ha"])
            cum = tab["before_or_unchanged"]
            w.writerow([f"<= {years[0]} or unchanged", tab["before_or_unchanged"], round(cum, 1)])
            for y in years[1:]:
                cum += tab[str(y)]
                w.writerow([y, tab[str(y)], round(cum, 1)])
        chart_expansion(tab, years, stats.get("dynamic_world_bare_built_ha"),
                        os.path.join(run_dir, "expansion.png"),
                        f"{name}: {' + '.join(stats['targets'])} in {train_year}, by year the "
                        f"{source.upper()} embedding first changed")
    if mode == "classify" and out:
        with open(os.path.join(run_dir, "area_by_class_year.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["year"] + names)
            for y in years:
                w.writerow([y] + [out[y].get(n, 0) for n in names])
        chart_areas(out, names, os.path.join(run_dir, "area_by_year.png"),
                    f"{name}: {source.upper()} classes per year",
                    ref=stats.get("dynamic_world_bare_built_ha"))
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps({k_: stats[k_] for k_ in stats if k_ in ("accuracy", "recall", "area_ha",
                                                             "changed_pct", "similar_ha")},
                     indent=1))
    return stats


def _run_tess(bbox, years, mode, feats, names, train_year, like, k, thr, stride, run_dir,
              name, stats, land=None, targets=("bare", "built")):
    gt = _tess()
    _read = globals()["tess_read"]

    def tess_read(gt_, bb, yr, st):                 # every read honours the land mask
        arr, tr, crs = _read(gt_, bb, yr, st)
        if land is not None and mode != "classify":
            arr[~land_mask_grid(land, arr.shape[:2], tr, crs)] = np.nan
        return arr, tr, crs
    if mode == "classify":
        X, y, pid = tess_training(gt, feats, names, train_year)
        acc, rec, cm = fold_accuracy(X, y, pid, names)
        stats.update(accuracy=acc, recall=rec, confusion=cm,
                     samples={n: int((y == i).sum()) for i, n in enumerate(names)})
        print(f"  held-out accuracy {acc}  recall {rec}")
        model = rf_model().fit(X, y)
        areas, maps = {}, []
        for yr in years:
            arr, tr, crs = _read(gt, bbox, yr, stride)
            if land is not None:
                arr[~land_mask_grid(land, arr.shape[:2], tr, crs)] = np.nan
            m = tess_predict(model, arr)
            px_ha = abs(tr.a * tr.e) / 1e4
            areas[yr] = {n: round(float((m == i).sum() * px_ha), 1) for i, n in enumerate(names)}
            areas[yr]["_nodata_pct"] = round(100 * float((m == 255).mean()), 1)
            _write_tif(os.path.join(run_dir, f"classes_{yr}.tif"), m, tr, crs, 255)
            maps.append(m)
            print(f"  {yr}: " + ", ".join(f"{n} {areas[yr][n]:.0f}" for n in names if n not in ("forest", "water")))
            del arr
        stats["area_ha"] = {str(y): v for y, v in areas.items()}
        panel(maps, years, names, os.path.join(run_dir, "classes_by_year.png"),
              f"{name}: TESSERA classes, trained on {train_year}")
        return areas
    if mode == "expansion":
        X, y, pid = tess_training(gt, feats, names, train_year)
        acc, rec, cm = fold_accuracy(X, y, pid, names)
        stats.update(accuracy=acc, recall=rec, confusion=cm)
        model = rf_model().fit(X, y)
        stable = [ft for ft in feats if ft["properties"]["class"] in STABLE]
        vals = np.concatenate([_poly_change(gt, ft, years[0], train_year) for ft in stable])
        thr = stable_threshold(vals)
        stats.update(change_thr=round(thr, 4), change_thr_from="99th pct of stable-class pixels "
                     f"({', '.join(sorted(STABLE & set(names)))}), {years[0]} vs {train_year}")
        print(f"  held-out accuracy {acc}; change threshold {thr:.3f} (stable 99th pct)")
        base, tr, crs = tess_read(gt, bbox, years[0], stride)
        series = []
        for yr in years[1:]:
            arr, _, _ = tess_read(gt, bbox, yr, stride)
            series.append(np.nan_to_num(cosine_change(base, arr), nan=-1))
            if yr == train_year:
                cls = tess_predict(model, arr)
            del arr
        first = first_crossing(np.stack(series), years[1:], thr)
        tg = [names.index(t) for t in targets if t in names]
        px_ha = abs(tr.a * tr.e) / 1e4
        tab = expansion_table(cls, first, tg, years, px_ha)
        stats["expansion_ha"] = tab
        stats["targets"] = [t for t in targets if t in names]
        stats[f"{'_'.join(stats['targets'])}_{train_year}_ha"] = round(float(np.isin(cls, tg).sum() * px_ha), 1)
        _write_tif(os.path.join(run_dir, "first_change_year.tif"), first, tr, crs, 0)
        _write_tif(os.path.join(run_dir, f"classes_{train_year}.tif"), cls, tr, crs, 255)
        conv = np.where(np.isin(cls, tg), first, 0).astype("int16")
        _write_tif(os.path.join(run_dir, "open_ground_year.tif"), conv, tr, crs, 0)
        _change_png(conv, years, os.path.join(run_dir, "open_ground_year.png"), name, "TESSERA")
        return tab
    if mode == "change":
        base, tr, crs = tess_read(gt, bbox, years[0], stride)
        series, out = [], {}
        for yr in years[1:]:
            arr, _, _ = tess_read(gt, bbox, yr, stride)
            c = cosine_change(base, arr)
            series.append(np.nan_to_num(c, nan=-1))
            out[yr] = round(100 * float(np.nanmean(c > thr)), 2)
        fc = first_crossing(np.stack(series), years[1:], thr)
        _write_tif(os.path.join(run_dir, f"first_change_year.tif"), fc, tr, crs, 0)
        _write_tif(os.path.join(run_dir, f"change_{years[0]}_{years[-1]}.tif"),
                   series[-1].astype("f4"), tr, crs, -1)
        stats["changed_pct"] = {str(y): v for y, v in out.items()}
        stats["change_thr"] = thr
        _change_png(fc, years, os.path.join(run_dir, "first_change_year.png"), name, "TESSERA")
        return out
    if mode == "similar":
        X, y, pid = tess_training(gt, feats, names, train_year)
        ref = unit(X[y == names.index(like)]).mean(0)
        out = {}
        for yr in years:
            arr, tr, crs = tess_read(gt, bbox, yr, stride)
            s = similarity(arr, ref)
            out[yr] = round(float(np.nansum(s > thr) * abs(tr.a * tr.e) / 1e4), 1)
            _write_tif(os.path.join(run_dir, f"similar_{yr}.tif"), np.nan_to_num(s, nan=-1).astype("f4"), tr, crs, -1)
        stats["similar_ha"] = {str(y): v for y, v in out.items()}
        stats.update(like=like, similar_thr=thr)
        return out
    if mode == "clusters":
        from sklearn.cluster import MiniBatchKMeans
        arr, tr, crs = tess_read(gt, bbox, years[-1], stride)
        flat = arr.reshape(-1, arr.shape[-1]); ok = ~np.isnan(flat).any(1)
        km = MiniBatchKMeans(n_clusters=k, random_state=0, n_init=3).fit(flat[ok][::7])
        lab = np.full(len(flat), 255, "uint8"); lab[ok] = km.predict(flat[ok])
        _write_tif(os.path.join(run_dir, f"clusters_{years[-1]}.tif"), lab.reshape(arr.shape[:2]), tr, crs, 255)
        stats["k"] = k
        return None


def _change_png(fc, years, path, name, src):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 8 * fc.shape[0] / fc.shape[1]), constrained_layout=True)
    im = ax.imshow(np.ma.masked_equal(fc, 0), cmap="plasma", vmin=years[1], vmax=years[-1])
    fig.colorbar(im, ax=ax, shrink=0.7, label=f"first year changed vs {years[0]}")
    ax.set_title(f"{name}: {src} embedding change", fontsize=11)
    ax.axis("off")
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _run_aef(bbox, years, mode, feats, names, train_year, like, k, thr, run_dir, name,
             config_key, stats, land=None, targets=("bare", "built")):
    import ee
    from .gee_utils import initialize_ee, download_geotiff
    initialize_ee(config_key)
    geom = ee.Geometry.Rectangle(list(bbox))
    _year = globals()["aef_year"]
    bands = _year(geom, train_year).bandNames()
    landimg = (ee.Image(0).paint(ee.FeatureCollection([ee.Feature(ee.Geometry(land["geometry"]))]), 1).eq(1)
               if land is not None else None)

    def aef_year(g, y):                             # every year honours the land mask
        img = _year(g, y)
        return img.updateMask(landimg) if landimg is not None else img
    if mode == "classify":
        samples = aef_training(feats, names, train_year)
        acc, rec, cm = aef_fold_accuracy(samples, bands, feats, names)
        stats.update(accuracy=acc, recall=rec, confusion=cm)
        print(f"  held-out accuracy {acc}  recall {rec}")
        clf = aef_rf().train(samples, "cls", bands)
        vis = {"min": 0, "max": len(names) - 1,
               "palette": [c.lstrip("#") for c in class_colors(names)]}
        areas = {}
        for yr in years:
            cls = aef_year(geom, yr).classify(clf)
            areas[yr] = aef_class_area(cls, geom, len(names))
            areas[yr] = {n: areas[yr][i] for i, n in enumerate(names)}
            _thumb(cls.clip(geom), geom, os.path.join(run_dir, f"classes_{yr}.png"), vis)
            print(f"  {yr}: " + ", ".join(f"{n} {areas[yr][n]:.0f}" for n in names if n not in ("forest", "water")))
        download_geotiff(aef_year(geom, years[-1]).classify(clf).toByte(), geom,
                         os.path.join(run_dir, f"classes_{years[-1]}.tif"), scale=10)
        stats["area_ha"] = {str(y): v for y, v in areas.items()}
        _panel_from_pngs(run_dir, years, names, name)
        return areas
    if mode == "expansion":
        samples = aef_training(feats, names, train_year)
        acc, rec, cm = aef_fold_accuracy(samples, bands, feats, names)
        stats.update(accuracy=acc, recall=rec, confusion=cm)
        clf = aef_rf().train(samples, "cls", bands)
        base = aef_year(geom, years[0])

        def chg(y):
            return ee.Image(1).subtract(base.multiply(aef_year(geom, y)).reduce(ee.Reducer.sum()))

        stable_fc = ee.FeatureCollection([ee.Feature(ee.Geometry(ft["geometry"])) for ft in feats
                                          if ft["properties"]["class"] in STABLE])
        b0, b1 = _year(geom, years[0]), _year(geom, train_year)       # unmasked: sea seeds count
        stable_chg = ee.Image(1).subtract(b0.multiply(b1).reduce(ee.Reducer.sum()))
        thr = list(stable_chg.reduceRegion(ee.Reducer.percentile([99]), stable_fc.geometry(), 10,
                                           maxPixels=1e10).getInfo().values())[0]
        stats.update(change_thr=round(thr, 4), change_thr_from="99th pct of stable-class pixels "
                     f"({', '.join(sorted(STABLE & set(names)))}), {years[0]} vs {train_year}")
        print(f"  held-out accuracy {acc}; change threshold {thr:.3f} (stable 99th pct)")
        first = ee.Image(0)
        for yr in reversed(years[1:]):
            first = first.where(chg(yr).gt(thr), yr)
        cls = aef_year(geom, train_year).classify(clf)
        tg = [names.index(t) for t in targets if t in names]
        is_t = cls.remap(tg, [1] * len(tg), 0).eq(1)
        conv = first.updateMask(is_t).rename("y")
        g = (ee.Image.pixelArea().divide(1e4).addBands(conv.unmask(-1).updateMask(is_t))
             .reduceRegion(ee.Reducer.sum().group(1, "y"), geom, 10, maxPixels=1e12, tileScale=4)
             .getInfo()["groups"])
        tab = {"before_or_unchanged": 0.0, **{str(y): 0.0 for y in years[1:]}}
        for r in g:
            k_ = "before_or_unchanged" if int(r["y"]) == 0 else str(int(r["y"]))
            tab[k_] = round(r["sum"], 1)
        stats["expansion_ha"] = tab
        stats["targets"] = [t for t in targets if t in names]
        stats[f"{'_'.join(stats['targets'])}_{train_year}_ha"] = round(sum(tab.values()), 1)
        _thumb(conv.selfMask().clip(geom), geom, os.path.join(run_dir, "open_ground_year.png"),
               {"min": years[1], "max": years[-1],
                "palette": ["0d0887", "7e03a8", "cc4778", "f89540", "f0f921"]})
        download_geotiff(conv.unmask(0).toInt16(), geom, os.path.join(run_dir, "open_ground_year.tif"), scale=10)
        return tab
    if mode == "change":
        base = aef_year(geom, years[0])
        out, first = {}, ee.Image(0)
        for yr in reversed(years[1:]):
            c = ee.Image(1).subtract(base.multiply(aef_year(geom, yr)).reduce(ee.Reducer.sum()))
            first = first.where(c.gt(thr), yr)
        for yr in years[1:]:
            c = ee.Image(1).subtract(base.multiply(aef_year(geom, yr)).reduce(ee.Reducer.sum()))
            v = c.gt(thr).reduceRegion(ee.Reducer.mean(), geom, 10, maxPixels=1e12, tileScale=4).getInfo()
            out[yr] = round(100 * (list(v.values())[0] or 0), 2)
            print(f"  {yr}: {out[yr]}% changed vs {years[0]}")
        first = first.selfMask().clip(geom)
        _thumb(first, geom, os.path.join(run_dir, "first_change_year.png"),
               {"min": years[1], "max": years[-1], "palette": ["0d0887", "7e03a8", "cc4778", "f89540", "f0f921"]})
        download_geotiff(first.toInt16(), geom, os.path.join(run_dir, "first_change_year.tif"), scale=10)
        stats["changed_pct"] = {str(y): v for y, v in out.items()}
        stats["change_thr"] = thr
        return out
    if mode == "similar":
        samples = aef_training(feats, names, train_year).filter(ee.Filter.eq("cls", names.index(like)))
        ref = ee.Array(samples.reduceColumns(ee.Reducer.mean().repeat(64), bands).get("mean"))
        refimg = ee.Image.constant(ee.List(ref.toList()))
        out = {}
        for yr in years:
            s = aef_year(geom, yr).multiply(refimg).reduce(ee.Reducer.sum()).divide(
                ee.Number(ref.pow(2).reduce(ee.Reducer.sum(), [0]).get([0])).sqrt())
            v = ee.Image.pixelArea().divide(1e4).updateMask(s.gt(thr)).reduceRegion(
                ee.Reducer.sum(), geom, 10, maxPixels=1e12, tileScale=4).getInfo()
            out[yr] = round(list(v.values())[0] or 0, 1)
        stats["similar_ha"] = {str(y): v for y, v in out.items()}
        stats.update(like=like, similar_thr=thr)
        return out
    if mode == "clusters":
        img = aef_year(geom, years[-1])
        tr = img.sample(region=geom, scale=10, numPixels=5000, seed=0)
        cl = img.cluster(ee.Clusterer.wekaKMeans(k).train(tr))
        _thumb(cl.clip(geom), geom, os.path.join(run_dir, f"clusters_{years[-1]}.png"),
               {"min": 0, "max": k - 1, "palette": [c.lstrip("#") for c in FALLBACK[:k]]})
        stats["k"] = k
        return None


def _panel_from_pngs(run_dir, years, names, name):
    from PIL import Image
    ims = [Image.open(os.path.join(run_dir, f"classes_{y}.png")).convert("RGB") for y in years]
    w, h = 300, int(ims[0].height * 300 / ims[0].width)
    cols = min(5, len(ims)); rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * w, rows * (h + 22)), "white")
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for i, (im, y) in enumerate(zip(ims, years)):
        x0, y0 = (i % cols) * w, (i // cols) * (h + 22)
        sheet.paste(im.resize((w, h)), (x0, y0 + 22))
        d.text((x0 + 5, y0 + 4), str(y), fill="black")
    sheet.save(os.path.join(run_dir, "classes_by_year.png"))
