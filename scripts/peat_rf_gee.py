#!/usr/bin/env python3
"""Peat / mineral random-forest model for Borneo in Google Earth Engine.

A rebuild of the team's R workflow (RandomForest_VariableSelection.R and
amsantac.R, which made data/peat/Kalimantan_3857.tif) that fixes what an
audit of those scripts and their training data found:

  - accuracy was estimated on a random point split although points are
    clustered and 579 are exact duplicates -> spatial block CV here
  - 90% of the training points sit at fire hotspots (Hotspot Australia Web,
    hotspot brg); only ~2,450 are field surveys -> leave-source-out test:
    train on hotspot-derived points, test on field points
  - spectral and C-band bands barely separate the classes; terrain flatness
    and distance to coast do the work, so flat mineral lowlands were called
    peat (2.8x the BBSDLP area at Ketapang) -> add terrain relief, HAND,
    L-band (canopy-penetrating) and surface water
  - "variable selection" was never applied -> forward selection under
    spatial CV
  - per-scene normImage made the model untransferable -> physical units only
  - class labels only -> peat probability, so thresholds and uncertainty
    can be reported

Existing peat or soil-carbon products are NOT predictors by default
(--with-soil adds SoilGrids SOC and PEATGRIDS), so the result can be compared
against them rather than copying them.

STAGES
  sample     predictors at the training points -> output/peat_rf/samples.csv
  cv         spatial-block CV, leave-source-out, feature selection, and the
             old map / BBSDLP scored at the same field points (local, sklearn)
  map        final RF in GEE on the selected features; peat probability for
             the Ketapang AOI on the 25 m analysis grid
  export     Borneo-wide probability as a GEE asset (long-running task)

    conda run -n base python scripts/peat_rf_gee.py --stage sample
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

OUT = os.path.join(_DATA_ROOT, "output", "peat_rf")
TRAIN = "/Volumes/ExtremeSSD/Dropbox/Works/05_Archives/Peatlands/Training Point/borneo_training.shp"
OLD_MAP = os.path.join(_DATA_ROOT, "data", "peat", "Kalimantan_3857.tif")
BORNEO = (108.5, -4.6, 119.6, 7.5)
FIELD = ("groundtruth survey", "Survei Ketapang")
BLOCK_KM = 50
CHUNK = 1500
SEED = 42


# ------------------------------------------------------------- predictors
# The team's original 21 variables (as given by the authors): ARI, PSRI, REIP,
# NDVI and NDWI from Sentinel-2 (red edge B5-B7); B2, B3, B4, B8 from Landsat
# 8/9 as named -- B8 is the 15 m panchromatic band, which only the TOA
# collection carries, so the Landsat bands are TOA reflectance.
ORIGINAL = ["ari", "ls_b2", "ls_b3", "ls_b4", "ls_b8",
            "vh_wet_max", "vv_wet_max", "vh_dry_max", "vv_dry_max",
            "vh_wet_min", "vv_wet_min", "vh_dry_min", "vv_dry_min",
            "ndvi", "ndwi", "psri", "reip", "dist_coast", "dist_river", "mrrtf", "mrvbf"]
EXTENDED = ["elev", "slope", "relief_1k", "relief_5k", "tpi_1k", "tpi_5k", "hand", "log_upa",
            "water_occ", "hh_l", "hv_l", "nbr", "ndmi", "vv_dry_minus_wet"]
# what borneo_training.shp itself carries (the authors' own extracted values)
SHP_COLS = ["lereng", "b1_landsat", "b2_landsat", "b3_landsat", "b4_landsat", "b5_landsat",
            "b6_landsat", "b7_landsat", "ndwi", "MRRTF", "MRVBF", "vhwetmax", "vvwetmax",
            "vhdrymax", "vvdrymax", "vhwetmin", "vvwetmin", "vhdrymin", "vvdrymin", "river", "coast"]


def mrvbf_mrrtf(dem):
    """Multi-resolution valley-bottom and ridge-top flatness (Gallant & Dowling
    2003, Water Resour. Res. 39:1347), approximated for Earth Engine: six
    scales, 30 m to 2.4 km, slope threshold halving from 16% each step;
    elevation percentile approximated by the position between the local
    minimum and maximum. The authors' values come from SAGA GIS on SRTM;
    the input here is SRTM too, and SAGA's defaults (t_slope 16, p_slope 4,
    p_pctl 3) are used, but SAGA ranks elevation percentiles exactly and
    resamples differently, so values are close, not identical -- the CV stage
    reports their rank correlation against the SAGA values."""
    import ee
    levels = [(30, 16.0, 3), (30, 8.0, 6), (90, 4.0, 6), (270, 2.0, 6), (810, 1.0, 6), (2430, 0.5, 6)]
    mv = mr = None
    for k, (res, t, rad) in enumerate(levels, start=1):
        d = dem.resample("bilinear").reproject("EPSG:4326", None, res)
        if k == 2:
            d = d.focalMean(1, "circle", "pixels")
        s = ee.Terrain.slope(d).multiply(3.14159265 / 180).tan().multiply(100)
        F = ee.Image(1).divide(s.divide(t).pow(4).add(1))
        lo = d.focalMin(rad, "circle", "pixels")
        hi = d.focalMax(rad, "circle", "pixels")
        P = d.subtract(lo).divide(hi.subtract(lo).add(0.01))
        vf = F.multiply(ee.Image(1).divide(P.divide(0.4).pow(3).add(1)))
        rf = F.multiply(ee.Image(1).divide(ee.Image(1).subtract(P).divide(0.4).pow(3).add(1)))
        if k == 1:
            mv, mr = vf, rf
        else:
            wv = ee.Image(1).subtract(ee.Image(1).divide(vf.divide(0.4).pow(6).add(1)))
            wr = ee.Image(1).subtract(ee.Image(1).divide(rf.divide(0.4).pow(6).add(1)))
            mv = wv.multiply(vf.add(k - 1)).add(ee.Image(1).subtract(wv).multiply(mv))
            mr = wr.multiply(rf.add(k - 1)).add(ee.Image(1).subtract(wr).multiply(mr))
    return (mv.reproject("EPSG:4326", None, 30).rename("mrvbf"),
            mr.reproject("EPSG:4326", None, 30).rename("mrrtf"))


def predictors(with_soil=False):
    """One multi-band image; every band in physical units."""
    import ee
    roi = ee.Geometry.Rectangle(list(BORNEO), None, False)

    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic() \
        .setDefaultProjection("EPSG:4326", None, 30)
    slope = ee.Terrain.slope(dem).rename("slope")
    merit = ee.Image("MERIT/Hydro/v1_0_1")
    elv90 = merit.select("elv")
    # relief / position: computed on the 90 m DEM so big kernels stay cheap
    rel1 = elv90.subtract(elv90.focalMin(1000, "circle", "meters")).rename("relief_1k")
    rel5 = elv90.subtract(elv90.focalMin(5000, "circle", "meters")).rename("relief_5k")
    tpi1 = elv90.subtract(elv90.focalMean(1000, "circle", "meters")).rename("tpi_1k")
    tpi5 = elv90.subtract(elv90.focalMean(5000, "circle", "meters")).rename("tpi_5k")
    hand = merit.select("hnd").rename("hand")
    upa = merit.select("upa").max(0.01).log10().rename("log_upa")

    # distance to coast and to rivers (km)
    land = ee.Image("MODIS/MOD44W/MOD44W_005_2000_02_24").select("water_mask").eq(0)
    sea = land.Not().selfMask()
    d_coast = sea.fastDistanceTransform(1024, "pixels", "squared_euclidean") \
        .sqrt().multiply(ee.Image.pixelArea().sqrt()).divide(1000) \
        .reproject("EPSG:4326", None, 250).rename("dist_coast")
    river = merit.select("upa").gt(100).selfMask()     # > 100 km2 catchment
    d_river = river.fastDistanceTransform(512, "pixels", "squared_euclidean") \
        .sqrt().multiply(ee.Image.pixelArea().sqrt()).divide(1000) \
        .reproject("EPSG:4326", None, 90).rename("dist_river")

    gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
    occ = gsw.select("occurrence").unmask(0).rename("water_occ")

    # Sentinel-1 C band, wet (Nov-Mar) and dry (Jun-Sep) medians 2020-2023, dB
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(roi)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .filterDate("2020-01-01", "2024-01-01").select(["VV", "VH"]))
    wet = s1.filter(ee.Filter.calendarRange(11, 3, "month")).median()
    dry = s1.filter(ee.Filter.calendarRange(6, 9, "month")).median()
    s1b = ee.Image.cat([wet.rename(["vv_wet", "vh_wet"]), dry.rename(["vv_dry", "vh_dry"]),
                        dry.select("VV").subtract(wet.select("VV")).rename("vv_dry_minus_wet")])

    # ALOS-2 PALSAR-2 L band yearly mosaics 2019-2022, mean gamma0 dB
    pal = ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH") \
        .filterDate("2019-01-01", "2023-01-01").select(["HH", "HV"]).mean()
    pal_db = pal.pow(2).log10().multiply(10).subtract(83).rename(["hh_l", "hv_l"])

    # Sentinel-2 dry-season median indices 2021-2024
    def s2m(im):
        scl = im.select("SCL")
        ok = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        return im.updateMask(ok)
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(roi)
          .filterDate("2021-01-01", "2025-01-01")
          .filter(ee.Filter.calendarRange(6, 9, "month"))
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(s2m).median())
    s2b = ee.Image.cat([s2.normalizedDifference(["B8", "B4"]).rename("ndvi"),
                        s2.normalizedDifference(["B3", "B8"]).rename("ndwi"),
                        s2.normalizedDifference(["B8", "B12"]).rename("nbr"),
                        s2.normalizedDifference(["B8", "B11"]).rename("ndmi")])

    # --- the team's original variables ---------------------------------
    # Sentinel-2 bands and red-edge indices from an all-season 2021-2024 median
    s2a = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(roi)
           .filterDate("2021-01-01", "2025-01-01")
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(s2m).median()
           .divide(10000))
    b = {k: s2a.select(k) for k in ("B2", "B3", "B4", "B5", "B6", "B7", "B8")}
    ari = ee.Image(1).divide(b["B3"]).subtract(ee.Image(1).divide(b["B5"])).rename("ari")
    psri = b["B4"].subtract(b["B2"]).divide(b["B6"]).rename("psri")
    reip = ee.Image(700).add(ee.Image(40).multiply(
        b["B4"].add(b["B7"]).divide(2).subtract(b["B5"]).divide(b["B6"].subtract(b["B5"])))).rename("reip")
    def lmask(im):
        qa = im.select("QA_PIXEL")
        return im.updateMask(qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0)))
    ls = (ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
          .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_TOA"))
          .filterBounds(roi).filterDate("2021-01-01", "2025-01-01")
          .filter(ee.Filter.lt("CLOUD_COVER", 60)).map(lmask)
          .select(["B2", "B3", "B4", "B8"]).median()
          .rename(["ls_b2", "ls_b3", "ls_b4", "ls_b8"]))
    s2orig = ee.Image.cat([ari, ls, psri, reip])
    # Sentinel-1 per-season max and min (the R workflow's statistics)
    s1w = s1.filter(ee.Filter.calendarRange(11, 3, "month"))
    s1d = s1.filter(ee.Filter.calendarRange(6, 9, "month"))
    s1orig = ee.Image.cat([
        s1w.select("VH").max().rename("vh_wet_max"), s1w.select("VV").max().rename("vv_wet_max"),
        s1d.select("VH").max().rename("vh_dry_max"), s1d.select("VV").max().rename("vv_dry_max"),
        s1w.select("VH").min().rename("vh_wet_min"), s1w.select("VV").min().rename("vv_wet_min"),
        s1d.select("VH").min().rename("vh_dry_min"), s1d.select("VV").min().rename("vv_dry_min")])
    # the authors computed MRVBF/MRRTF from SRTM in SAGA GIS: same DEM here
    srtm = ee.Image("USGS/SRTMGL1_003").select("elevation")
    mv, mr = mrvbf_mrrtf(srtm)

    img = ee.Image.cat([dem.rename("elev"), slope, rel1, rel5, tpi1, tpi5, hand, upa,
                        d_coast, d_river, occ, s1b, pal_db, s2b,
                        s2orig, s1orig, mv, mr])
    if with_soil:
        soc = ee.Image("projects/soilgrids-isric/soc_mean").select("soc_0-5cm_mean").rename("soc")
        pg = ee.Image("projects/sat-io/open-datasets/PEATGRIDS/THICKNESS_CM").select(0) \
            .unmask(0).rename("peatgrids_cm")
        img = img.addBands([soc, pg])
    return img.toFloat()


# -------------------------------------------------------------- training
def training_points():
    """Deduplicated points: label y (1 peat, 0 mineral), source, 50 km block."""
    import geopandas as gpd
    import numpy as np
    g = gpd.read_file(TRAIN).to_crs(4326)
    g = g[g.Lahan.isin(["Gambut", "Mineral"])].copy()
    g["lon"], g["lat"] = g.geometry.x.round(6), g.geometry.y.round(6)
    lab = g.groupby(["lon", "lat"]).Lahan.nunique()
    conflict = lab[lab > 1].index
    n0 = len(g)
    g = g.set_index(["lon", "lat"]).drop(index=conflict, errors="ignore").reset_index()
    g = g.drop_duplicates(subset=["lon", "lat"])
    g["y"] = (g.Lahan == "Gambut").astype(int)
    g["field"] = g.Sumber.isin(FIELD).astype(int)
    km = 111.32
    g["block"] = (np.floor(g.lat * km / BLOCK_KM).astype(int) * 1000
                  + np.floor(g.lon * km * np.cos(np.radians(g.lat)) / BLOCK_KM).astype(int))
    g["pid"] = np.arange(len(g))
    print(f"training points: {n0:,} -> {len(g):,} after removing duplicates and "
          f"{len(conflict)} conflicting coordinates; peat {g.y.mean():.0%}, field {g.field.sum():,}")
    shp = g[[c for c in SHP_COLS if c in g.columns]].add_prefix("shp_")
    return pd_concat([g[["pid", "lon", "lat", "y", "field", "Sumber", "block"]], shp])


def pd_concat(parts):
    import pandas as pd
    return pd.concat(parts, axis=1)


def stage_sample(a):
    import ee
    import pandas as pd
    os.makedirs(OUT, exist_ok=True)
    pts = training_points()
    img = predictors(a.with_soil)
    bands = img.bandNames().getInfo()
    print("predictors:", bands)
    out_csv = os.path.join(OUT, "samples_soil.csv" if a.with_soil else "samples.csv")
    done = pd.read_csv(out_csv) if os.path.exists(out_csv) else pd.DataFrame()
    have = set(done.pid) if len(done) else set()
    if len(done):
        done = done[["pid"] + [b for b in bands if b in done.columns]]
    rows = [done] if len(done) else []
    # sort by location so each request covers a compact area (cheaper predictors)
    todo = pts[~pts.pid.isin(have)].sort_values(["block", "lat", "lon"])
    chunks = [todo.iloc[i:i + CHUNK] for i in range(0, len(todo), CHUNK)]

    def one(ch):
        # each request returns at most CHUNK (< 5,000) rows, as a single list
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]), {"pid": int(r.pid)})
                                   for r in ch.itertuples()])
        s = img.sampleRegions(collection=fc, properties=["pid"], scale=30, tileScale=8,
                              geometries=False)
        recs = s.reduceColumns(ee.Reducer.toList(len(bands) + 1), ["pid"] + bands) \
            .get("list").getInfo()
        return pd.DataFrame(recs, columns=["pid"] + bands)

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    lock = threading.Lock()
    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(one, ch) for ch in chunks]
        for f in as_completed(futs):
            df = f.result()
            with lock:
                rows.append(df)
                n += 1
                pd.concat(rows).to_csv(out_csv, index=False)    # resumable
                print(f"  chunk {n}/{len(chunks)} ({len(df)} rows with data)", flush=True)
    allr = pd.concat(rows).merge(pts, on="pid")
    allr.to_csv(out_csv, index=False)
    print(f"Saved: {out_csv} ({len(allr):,} rows)")


# -------------------------------------------------------------------- CV
def stage_cv(a):
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio.warp import transform as wtransform
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import f1_score, roc_auc_score, brier_score_loss, accuracy_score
    from sklearn.model_selection import GroupKFold

    d = pd.read_csv(os.path.join(OUT, "samples_soil.csv" if a.with_soil else "samples.csv"))
    shp = [c for c in d.columns if c.startswith("shp_")]
    gee = ORIGINAL + EXTENDED + (["soc", "peatgrids_cm"] if a.with_soil else [])
    d = d.dropna(subset=gee).reset_index(drop=True)
    for c in shp:                                   # shapefile values: -9999 style gaps
        d.loc[d[c] < -1e4, c] = np.nan
    feats_all = gee
    print(f"{len(d):,} complete rows; peat {d.y.mean():.0%}; {d.block.nunique()} blocks")

    def rf(n=200):
        return RandomForestClassifier(n_estimators=n, min_samples_leaf=2, n_jobs=-1,
                                      class_weight="balanced", random_state=SEED)

    def metrics(y, p):
        yhat = (p >= 0.5).astype(int)
        return {"acc": accuracy_score(y, yhat), "f1_peat": f1_score(y, yhat, pos_label=1),
                "f1_mineral": f1_score(y, yhat, pos_label=0),
                "auc": roc_auc_score(y, p) if len(set(y)) > 1 else np.nan,
                "brier": brier_score_loss(y, p), "n": len(y)}

    def spatial_cv(feats, k=5, n=200):
        p = np.zeros(len(d))
        for tr, te in GroupKFold(k).split(d, d.y, d.block):
            m = rf(n).fit(d.loc[tr, feats], d.loc[tr, "y"])
            p[te] = m.predict_proba(d.loc[te, feats])[:, 1]
        return p

    res = {}
    from sklearn.model_selection import StratifiedKFold

    def random_cv(feats):
        p = np.zeros(len(d))
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=SEED).split(d, d.y):
            p[te] = rf().fit(d.loc[tr, feats], d.loc[tr, "y"]).predict_proba(d.loc[te, feats])[:, 1]
        return p

    def show(k):
        print(f"  {k:<34}", {kk: round(v, 3) for kk, v in res[k].items()})

    # A: the authors' own extracted values (shapefile); B: their 21 variables
    # rebuilt in GEE; C: B + extended predictors. Random split (what the R
    # script did) vs spatial block CV for each.
    dA = d.dropna(subset=shp).index
    for name, feats, idx in (("A_shapefile_values", shp, dA), ("B_original_in_GEE", ORIGINAL, d.index),
                             ("C_extended", feats_all, d.index)):
        sub = d.loc[idx].reset_index(drop=True)
        dd, d_ = d, sub
        d = d_                                     # spatial_cv/random_cv read d
        res[f"{name}_random"] = metrics(d.y, random_cv(feats))
        res[f"{name}_spatial"] = metrics(d.y, spatial_cv(feats))
        show(f"{name}_random")
        show(f"{name}_spatial")
        d = dd
    # how close the GEE MRVBF/MRRTF come to the authors' SAGA values
    if "shp_MRVBF" in d:
        res["mrvbf_corr_gee_vs_saga"] = float(d[["mrvbf", "shp_MRVBF"]].corr(method="spearman").iloc[0, 1])
        res["mrrtf_corr_gee_vs_saga"] = float(d[["mrrtf", "shp_MRRTF"]].corr(method="spearman").iloc[0, 1])
        print("  MRVBF / MRRTF Spearman GEE vs SAGA:", round(res["mrvbf_corr_gee_vs_saga"], 3),
              round(res["mrrtf_corr_gee_vs_saga"], 3))

    # forward feature selection under spatial CV (3 folds, 100 trees, AUC)
    sel, best = [], 0.0
    pool = list(feats_all)
    while pool and len(sel) < a.max_features:
        scores = {}
        for f in pool:
            p = spatial_cv(sel + [f], k=3, n=100)
            scores[f] = roc_auc_score(d.y, p)
        f, s = max(scores.items(), key=lambda kv: kv[1])
        if s - best < 0.002 and len(sel) >= 3:
            break
        sel.append(f)
        pool.remove(f)
        best = s
        print(f"  + {f:<18} spatial-CV AUC {s:.3f}")
    res["selected"] = sel
    res["spatial_cv_selected"] = metrics(d.y, spatial_cv(sel))
    print("selected  :", {k: round(v, 3) for k, v in res["spatial_cv_selected"].items()})

    # leave-source-out: train on hotspot-derived, test on field points
    tr, te = d.field == 0, d.field == 1
    m = rf(300).fit(d.loc[tr, sel], d.loc[tr, "y"])
    pf = m.predict_proba(d.loc[te, sel])[:, 1]
    res["train_hotspot_test_field"] = metrics(d.loc[te, "y"], pf)
    print("hotspot->field:", {k: round(v, 3) for k, v in res["train_hotspot_test_field"].items()})

    # permutation importance on the field test set
    from sklearn.inspection import permutation_importance
    pi = permutation_importance(m, d.loc[te, sel], d.loc[te, "y"], scoring="roc_auc",
                                n_repeats=10, random_state=SEED, n_jobs=-1)
    res["importance_field"] = dict(sorted(zip(sel, pi.importances_mean.round(4)),
                                          key=lambda kv: -kv[1]))

    # the old map at the same field points
    fld = d[te].copy()
    with rasterio.open(OLD_MAP) as ds:
        xs, ys = wtransform("EPSG:4326", ds.crs, fld.lon.tolist(), fld.lat.tolist())
        v = np.array([x[0] for x in ds.sample(list(zip(xs, ys)))])
    fld["old"] = (v == 1).astype(int)
    covered = v != ds.nodata if ds.nodata is not None else np.ones(len(v), bool)
    res["old_map_at_field_points"] = {
        "acc": accuracy_score(fld.y, fld.old),
        "f1_peat": f1_score(fld.y, fld.old, pos_label=1),
        "f1_mineral": f1_score(fld.y, fld.old, pos_label=0),
        "peat_rate_predicted": float(fld.old.mean()), "peat_rate_true": float(fld.y.mean()),
        "n": int(len(fld))}
    print("old map @field:", {k: round(v, 3) if isinstance(v, float) else v
                              for k, v in res["old_map_at_field_points"].items()})
    yhat = (pf >= 0.5).astype(int)
    res["new_model_at_field_points_rates"] = {"peat_rate_predicted": float(yhat.mean()),
                                              "peat_rate_true": float(fld.y.mean())}
    json.dump(res, open(os.path.join(OUT, "cv_report.json"), "w"), indent=2, default=float)
    print(f"Saved: {os.path.join(OUT, 'cv_report.json')}")


# -------------------------------------------------------------- GEE map
PART = 5000          # EE returns at most 5,000 elements per collection query


def stage_upload(a):
    """Training points -> EE table assets, <= PART features each, so no later
    request carries all ~28k geometries inline (~10 MB payload cap)."""
    import time
    import ee
    pts = training_points()
    tasks = []
    for k, i in enumerate(range(0, len(pts), PART)):
        ch = pts.iloc[i:i + PART]
        fc = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([r.lon, r.lat]),
                       {"pid": int(r.pid), "y": int(r.y), "field": int(r.field), "block": int(r.block)})
            for r in ch.itertuples()])
        aid = f"{a.asset_prefix}_part{k}"
        t = ee.batch.Export.table.toAsset(collection=fc, description=f"peat_train_part{k}",
                                          assetId=aid)
        t.start()
        tasks.append((aid, t))
        print(f"  export {aid}: {len(ch)} points")
    while any(t.status()["state"] in ("READY", "RUNNING") for _, t in tasks):
        time.sleep(20)
    for aid, t in tasks:
        print(f"  {aid}: {t.status()['state']}")
    json.dump([aid for aid, _ in tasks], open(os.path.join(OUT, "training_assets.json"), "w"))


def stage_sample_batch(a):
    """Sampling as batch tasks: interactive requests time out (~5 min) on
    these predictors, batch exports do not. Each uploaded training part
    (<= 5,000 points) is sampled server-side and exported as a table asset,
    then fetched as CSV and joined to the local point table."""
    import io
    import time
    import ee
    import pandas as pd
    import requests
    parts = json.load(open(os.path.join(OUT, "training_assets.json")))
    img = predictors(a.with_soil)
    bands = img.bandNames().getInfo()
    tasks = []
    for k, aid in enumerate(parts):
        out = f"{a.asset_prefix}_samples{'_soil' if a.with_soil else ''}_part{k}"
        try:
            ee.data.getAsset(out)
            print(f"  {out}: exists")
            tasks.append((out, None))
            continue
        except Exception:                                 # noqa: BLE001
            pass
        # table assets need a geometry on every feature, so keep the points
        s = img.sampleRegions(collection=ee.FeatureCollection(aid), properties=["pid"],
                              scale=30, tileScale=16, geometries=True)
        t = ee.batch.Export.table.toAsset(collection=s, description=f"peat_samples_part{k}",
                                          assetId=out)
        t.start()
        tasks.append((out, t))
        print(f"  export {out}")
    while any(t is not None and t.status()["state"] in ("READY", "RUNNING") for _, t in tasks):
        time.sleep(30)
    frames = []
    for out, t in tasks:
        st = "COMPLETED" if t is None else t.status()["state"]
        if st != "COMPLETED":
            print(f"  {out}: {st} {t.status().get('error_message', '')}")
            continue
        url = ee.FeatureCollection(out).getDownloadURL("csv", ["pid"] + bands)
        frames.append(pd.read_csv(io.StringIO(requests.get(url, timeout=600).text)))
        print(f"  {out}: {len(frames[-1])} rows")
    pts = training_points()
    allr = pd.concat(frames).merge(pts, on="pid")
    out_csv = os.path.join(OUT, "samples_soil.csv" if a.with_soil else "samples.csv")
    allr.to_csv(out_csv, index=False)
    print(f"Saved: {out_csv} ({len(allr):,} rows, {len(bands)} predictors)")


HOLDOUT_FRAC = 0.3       # share of field-point blocks held out entirely
WEIGHTS = (1, 3, 6, 10)  # candidate field-point weights (row duplication in EE)


def stage_final(a):
    """Final model. Field points are the trustworthy labels, so:
      1. hold out 30% of the 50 km blocks that contain field points -- every
         point in those blocks leaves training; only their field points are
         scored (spatially honest, never seen by any choice below)
      2. choose the field weight by spatial out-of-fold field AUC on the
         training blocks (sklearn sample_weight)
      3. calibrate the peat threshold on those out-of-fold field predictions
         (maximum balanced accuracy)
      4. upload the training rows (selected features + y, field rows repeated
         `weight` times, since smileRandomForest takes no sample weights) and
         the held-out field rows as table assets <= 5,000 rows each
      5. train smileRandomForest on the table, classify the held-out field
         rows in EE, and score them at the calibrated threshold."""
    import time
    import ee
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score, balanced_accuracy_score, accuracy_score, f1_score, \
        brier_score_loss
    from sklearn.model_selection import GroupKFold

    sel = json.load(open(os.path.join(OUT, "cv_report.json")))["selected"]
    d = pd.read_csv(os.path.join(OUT, "samples.csv")).dropna(subset=sel).reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    fblocks = np.array(sorted(d.loc[d.field == 1, "block"].unique()))
    hold = set(rng.choice(fblocks, int(round(HOLDOUT_FRAC * len(fblocks))), replace=False).tolist())
    te = d.block.isin(hold)
    tr_d, te_d = d[~te].reset_index(drop=True), d[te & (d.field == 1)].reset_index(drop=True)
    print(f"{len(fblocks)} field blocks, {len(hold)} held out: train {len(tr_d):,} rows "
          f"({tr_d.field.sum():,} field), held-out field points {len(te_d):,} "
          f"(peat {te_d.y.mean():.0%}; {te_d.Sumber.value_counts().to_dict()})")

    def rf(n=200):
        return RandomForestClassifier(n_estimators=n, min_samples_leaf=2, n_jobs=-1,
                                      class_weight="balanced", random_state=SEED)

    def metrics(y, p, thr):
        yhat = (p >= thr).astype(int)
        return {"acc": accuracy_score(y, yhat), "balanced_acc": balanced_accuracy_score(y, yhat),
                "f1_peat": f1_score(y, yhat, pos_label=1), "f1_mineral": f1_score(y, yhat, pos_label=0),
                "auc": roc_auc_score(y, p), "brier": brier_score_loss(y, p),
                "peat_rate_predicted": float(yhat.mean()), "peat_rate_true": float(np.mean(y)),
                "n": int(len(y))}

    def oof(w):
        p = np.zeros(len(tr_d))
        sw = np.where(tr_d.field == 1, w, 1.0)
        for i, j in GroupKFold(5).split(tr_d, tr_d.y, tr_d.block):
            m = rf().fit(tr_d.loc[i, sel], tr_d.loc[i, "y"], sample_weight=sw[i])
            p[j] = m.predict_proba(tr_d.loc[j, sel])[:, 1]
        return p

    fm = (tr_d.field == 1).to_numpy()
    scan = {}
    for w in WEIGHTS:
        p = oof(w)
        scan[w] = (roc_auc_score(tr_d.y[fm], p[fm]), p)
        print(f"  field weight {w:>2}: out-of-fold field AUC {scan[w][0]:.3f}")
    w_best = max(scan, key=lambda k: scan[k][0])
    p_f = scan[w_best][1][fm]
    y_f = tr_d.y[fm].to_numpy()
    grid = np.round(np.arange(0.20, 0.81, 0.01), 2)
    ba = [balanced_accuracy_score(y_f, (p_f >= t).astype(int)) for t in grid]
    thr = float(grid[int(np.argmax(ba))])
    print(f"chosen field weight {w_best}; threshold {thr:.2f} (OOF field balanced acc {max(ba):.3f})")

    # sklearn reference on the held-out field points
    m = rf(300).fit(tr_d[sel], tr_d.y, sample_weight=np.where(tr_d.field == 1, w_best, 1.0))
    p_sk = m.predict_proba(te_d[sel])[:, 1]
    rep = {"selected": sel, "field_weight": w_best, "threshold": thr,
           "weight_scan_oof_field_auc": {str(k): float(v[0]) for k, v in scan.items()},
           "holdout_blocks": sorted(int(b) for b in hold),
           "oof_field_train": metrics(y_f, p_f, thr),
           "holdout_sklearn": metrics(te_d.y, p_sk, thr),
           "holdout_sklearn_at_0.5": metrics(te_d.y, p_sk, 0.5)}
    print("held-out field, sklearn:", {k: round(v, 3) for k, v in rep["holdout_sklearn"].items()})

    # upload: training rows (field repeated) and held-out field rows
    def feats(df, extra):
        return [ee.Feature(ee.Geometry.Point([r.lon, r.lat]),
                           {**{f: float(getattr(r, f)) for f in sel}, **{e: int(getattr(r, e)) for e in extra}})
                for r in df.itertuples()]
    up = pd.concat([tr_d] + [tr_d[tr_d.field == 1]] * (w_best - 1), ignore_index=True)
    prefix = f"{a.asset_prefix}_final"
    jobs = []
    for name, df, extra in (("train", up, ["y"]), ("holdout", te_d, ["y", "pid"])):
        for k, i in enumerate(range(0, len(df), PART)):
            aid = f"{prefix}_{name}_part{k}"
            try:
                ee.data.deleteAsset(aid)                  # a re-run replaces old tables
            except Exception:                             # noqa: BLE001
                pass
            t = ee.batch.Export.table.toAsset(
                collection=ee.FeatureCollection(feats(df.iloc[i:i + PART], extra)),
                description=f"peat_final_{name}_{k}", assetId=aid)
            t.start()
            jobs.append((name, aid, t))
    print(f"uploading {len(up):,} training rows and {len(te_d)} held-out rows "
          f"as {len(jobs)} table assets")
    while any(t.status()["state"] in ("READY", "RUNNING") for _, _, t in jobs):
        time.sleep(20)
    bad = [(aid, t.status()) for _, aid, t in jobs if t.status()["state"] != "COMPLETED"]
    if bad:
        raise SystemExit(f"upload failed: {bad}")
    rep["assets"] = {n: [aid for nn, aid, _ in jobs if nn == n] for n in ("train", "holdout")}
    json.dump(rep, open(os.path.join(OUT, "final_report.json"), "w"), indent=2, default=float)

    # train in EE and score the held-out field points with the EE classifier
    clf = final_classifier(rep)
    ho = merged(rep["assets"]["holdout"]).classify(clf, "p")
    rows = ho.reduceColumns(ee.Reducer.toList(2), ["y", "p"]).get("list").getInfo()
    yy, pp = np.array(rows).T
    rep["holdout_gee"] = metrics(yy.astype(int), pp, thr)
    rep["holdout_gee_at_0.5"] = metrics(yy.astype(int), pp, 0.5)
    print("held-out field, GEE   :", {k: round(v, 3) for k, v in rep["holdout_gee"].items()})
    json.dump(rep, open(os.path.join(OUT, "final_report.json"), "w"), indent=2, default=float)
    print(f"Saved: {os.path.join(OUT, 'final_report.json')}")


def merged(aids):
    import ee
    fc = ee.FeatureCollection(aids[0])
    for q in aids[1:]:
        fc = fc.merge(ee.FeatureCollection(q))
    return fc


def final_classifier(rep):
    import ee
    return (ee.Classifier.smileRandomForest(numberOfTrees=300, minLeafPopulation=2,
                                            bagFraction=0.632, seed=SEED)
            .setOutputMode("PROBABILITY")
            .train(merged(rep["assets"]["train"]), "y", rep["selected"]))


def training_fc():
    import ee
    p = os.path.join(OUT, "training_assets.json")
    if not os.path.exists(p):
        raise SystemExit("run --stage upload first")
    parts = [ee.FeatureCollection(aid) for aid in json.load(open(p))]
    fc = parts[0]
    for q in parts[1:]:
        fc = fc.merge(q)
    return fc


def trained_classifier(sel, with_soil):
    import ee
    img = predictors(with_soil).select(sel)
    samp = img.sampleRegions(collection=training_fc(), properties=["y"], scale=30, tileScale=8)
    clf = (ee.Classifier.smileRandomForest(numberOfTrees=300, minLeafPopulation=2,
                                           bagFraction=0.632, seed=SEED)
           .setOutputMode("PROBABILITY").train(samp, "y", sel))
    return img, clf


def stage_map(a):
    import numpy as np
    import rasterio
    from ketapang_fire_origin import CONC, FOUR, BUF_DEG, GRID, TILES
    from ketapang_landprep_tests import ee_download
    import geopandas as gpd
    img, clf, sel = map_classifier(a)
    prob = img.classify(clf).multiply(1000).round().toInt16().rename("peat_prob")
    conc = gpd.read_file(CONC).to_crs(4326)
    four = conc[conc.company.str.contains("|".join(FOUR.values()), na=False)]
    x0, y0, x1, y1 = four.total_bounds
    bbox = (x0 - BUF_DEG, y0 - BUF_DEG, x1 + BUF_DEG, y1 + BUF_DEG)
    # classifying on the fly per download tile gets 503s (the classifier is
    # rebuilt for every request), so the AOI is exported once as an asset
    import time
    import ee
    aid = f"{a.asset}_ketapang"
    try:
        ee.data.getAsset(aid)
        print(f"  {aid}: exists")
    except Exception:                                     # noqa: BLE001
        t = ee.batch.Export.image.toAsset(
            image=prob, description="peat_prob_ketapang", assetId=aid,
            region=ee.Geometry.Rectangle(list(bbox), None, False),
            crs="EPSG:4326", crsTransform=[GRID, 0, bbox[0], 0, -GRID, bbox[3]], maxPixels=1e10)
        t.start()
        print(f"  export {aid} ({t.id})")
        while t.status()["state"] in ("READY", "RUNNING"):
            time.sleep(30)
        if t.status()["state"] != "COMPLETED":
            raise SystemExit(f"export failed: {t.status()}")
    prob = ee.Image(aid)
    arr, tr = ee_download(prob, bbox, os.path.join(OUT, "ketapang_tiles"), "prob", GRID, TILES)
    p = os.path.join(OUT, "peat_prob_ketapang_25m.tif")
    with rasterio.open(p, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=1,
                       dtype="int16", crs="EPSG:4326", transform=tr, compress="deflate") as ds:
        ds.write(arr[0], 1)
    print(f"Saved: {p}  (peat probability x1000; selected features {sel})")


def map_classifier(a):
    """The final (field-weighted) classifier when stage final has run,
    otherwise the plain one trained by re-sampling the training points."""
    fp = os.path.join(OUT, "final_report.json")
    if os.path.exists(fp) and not a.with_soil:
        rep = json.load(open(fp))
        if "assets" in rep:
            return predictors(False).select(rep["selected"]), final_classifier(rep), rep["selected"]
    sel = json.load(open(os.path.join(OUT, "cv_report.json")))["selected"]
    img, clf = trained_classifier(sel, a.with_soil)
    return img, clf, sel


def stage_export(a):
    import ee
    img, clf, _ = map_classifier(a)
    prob = img.classify(clf).multiply(1000).round().toInt16().rename("peat_prob")
    region = ee.Geometry.Rectangle(list(BORNEO), None, False)
    task = ee.batch.Export.image.toAsset(
        image=prob, description="peat_prob_borneo", assetId=a.asset, region=region,
        scale=50, crs="EPSG:4326", maxPixels=1e13)
    task.start()
    print(f"export started: {task.id} -> {a.asset}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True,
                    choices=["sample", "upload", "sample-batch", "cv", "final", "map", "export"])
    ap.add_argument("--workers", type=int, default=4, help="parallel EE requests in sampling")
    ap.add_argument("--asset-prefix",
                    default="projects/ee-geodeticengineeringundip/assets/peat_training_borneo")
    ap.add_argument("--with-soil", action="store_true")
    ap.add_argument("--max-features", type=int, default=12)
    ap.add_argument("--asset", default="projects/ee-geodeticengineeringundip/assets/peat_prob_borneo")
    a = ap.parse_args()
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    {"sample": stage_sample, "upload": stage_upload, "sample-batch": stage_sample_batch,
     "cv": stage_cv, "final": stage_final, "map": stage_map, "export": stage_export}[a.stage](a)


if __name__ == "__main__":
    main()
