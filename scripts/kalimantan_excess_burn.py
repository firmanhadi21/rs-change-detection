#!/usr/bin/env python3
"""Do Kalimantan's concessions burn more than comparable unpermitted land,
and does fire arrive there earlier? The Ketapang case study scaled to all
of Kalimantan (research plan WP0, WP2 and the timing test; output/
RESEARCH_PLAN.md).

Unit: a 200 m cell on a lattice of 0.0018 deg anchored at 0,0 (8 x 8 of the
25 m Ketapang cells; MCD64A1 at 500 m is sampled, not aggregated).
Everything with a finer native grid is reduced to it in Earth Engine:

  lc       land-cover class as ketapang_fire_origin.classify (Descals palm
           + planting year, Hansen forest 2000 / loss year), computed at
           30 m and reduced by MODE
  bfrac    share of the cell with Sentinel-2 dNBR >= 0.27 (20 m; median
           Apr-mid Jul vs Sep-Oct 2026), and okfrac, the share with a
           cloud-free pair. Burned = bfrac >= 50% AND a VIIRS detection
           within ~750 m (the Ketapang rule), applied locally
  hist     times burned in 2015, 2019, 2023 (MCD64A1)
  depth    PEATGRIDS thickness (cm)
  built    GHSL built-up share (2020), for distance to settlement
  land     Hansen datamask share

Tenure: GFW oil palm concessions (c. 2012) and wood-fibre (HTI) permits,
rasterised locally; peat: BBSDLP (GFW 'Indonesia peat lands').

STAGES (in order; each caches its output)
  vectors   HTI and BBSDLP peat polygons for Kalimantan (GFW ArcGIS)
  stack     export the band stack to an Earth Engine asset (batch task)
  download  the asset, tiled, to data/kalimantan/stack_200m.tif
  viirs     VIIRS 375 m detections (NASA LANCE, S-NPP + NOAA-20), 2026
  sample    one parquet row per land cell, all covariates (same strata
            and 5 km blocks as ketapang_excess_burn.py)

    conda run -n base python scripts/kalimantan_excess_burn.py --stage vectors
    ...
"""

import argparse
import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import (_DATA_ROOT, AGE_BINS, PEAT_URL, VIIRS, DNBR_T,  # noqa: E402
                                  NEAR_BURN_M)

STEP = 0.0018                                   # 200 m
KAL = (108.5, -4.3, 119.3, 4.5)                 # bbox; cells outside GAUL Kalimantan dropped
DATA = os.path.join(_DATA_ROOT, "data", "kalimantan")
OUT = os.path.join(_DATA_ROOT, "output", "fire", "kalimantan_excess")
CONC = os.path.join(_DATA_ROOT, "data", "concessions", "gfw_idn_oil_palm.gpkg")
HTI = os.path.join(DATA, "gfw_hti_kalimantan.gpkg")
PEAT = os.path.join(DATA, "gfw_peat_kalimantan.gpkg")
ASSET = "projects/ee-geodeticengineeringundip/assets/kalimantan_stack_200m"
STACK = os.path.join(DATA, "stack_200m.tif")
BANDS = ["lc", "bfrac", "okfrac", "hist", "depth", "built", "land", "kal"]
HTI_URL = "https://gis-gfw.wri.org/arcgis/rest/services/country_data/asia/MapServer/0/query"
S2_PRE, S2_POST = ("2026-04-01", "2026-07-15"), ("2026-09-01", "2026-11-01")
V_START, V_END = "2026-06-01", "2026-11-04"
BLOCK_KM = 5.0


# ------------------------------------------------------------------ vectors
def _arcgis(url, bbox, fields="*"):
    """All features of an ArcGIS MapServer layer inside bbox, as a GeoDataFrame
    (Esri JSON; GFW's GeoJSON output nulls large polygons)."""
    import geopandas as gpd
    import requests
    from shapely import make_valid
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    def poly(rings):
        def ccw(r):
            return sum((x2 - x1) * (y2 + y1) for (x1, y1), (x2, y2) in zip(r, r[1:])) < 0
        shells = [make_valid(Polygon(r)) for r in rings if len(r) >= 4 and not ccw(r)]
        holes = [make_valid(Polygon(r)) for r in rings if len(r) >= 4 and ccw(r)]
        g = unary_union(shells)
        return g.difference(unary_union(holes)) if holes else g

    feats, off = [], 0
    while True:
        for k in range(4):
            try:
                r = requests.get(url, params={
                    "where": "1=1", "outFields": fields, "f": "json", "outSR": 4326, "inSR": 4326,
                    "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
                    "spatialRel": "esriSpatialRelIntersects", "resultOffset": off,
                    "resultRecordCount": 500, "maxAllowableOffset": 0.0002}, timeout=300)
                r.raise_for_status()
                f = r.json()["features"]
                break
            except Exception:                                  # noqa: BLE001
                if k == 3:
                    raise
        feats += f
        print(f"  {len(feats):,} features", end="\r")
        if len(f) < 500:
            break
        off += len(f)
    rows = [f["attributes"] | {"geometry": poly([[tuple(p[:2]) for p in ring if p[0] is not None]
                                                 for ring in f["geometry"]["rings"]])} for f in feats]
    print()
    return gpd.GeoDataFrame(rows, crs=4326)


def stage_vectors(_a):
    os.makedirs(DATA, exist_ok=True)
    for path, url, name in ((HTI, HTI_URL, "HTI"), (PEAT, PEAT_URL, "BBSDLP peat")):
        if os.path.exists(path):
            print("have", path)
            continue
        print(f"{name} ...")
        g = _arcgis(url if url.endswith("query") else url, KAL)
        g = g[~g.geometry.is_empty]
        g.to_file(path)
        print(f"Saved: {path} ({len(g):,} polygons)")


# ------------------------------------------------------------- Earth Engine
def kal_geom():
    import ee
    from earthchange.gee_utils import gaul
    return gaul(1).filter(ee.Filter.stringContains("ADM1_NAME", "Kalimantan")).geometry()


def stack_image():
    import ee
    from earthchange.fire_national import BURN_IC
    grid = ee.Projection("EPSG:4326", [STEP, 0, 0, 0, -STEP, 0])
    gfc = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
    op = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2")
    cls = op.select("classification").mosaic().unmask(0)
    py = op.select("planting_year").mosaic().unmask(0)
    tc, loss, dm = gfc.select("treecover2000"), gfc.select("lossyear"), gfc.select("datamask")

    # land cover at 30 m, exactly as ketapang_fire_origin.classify
    palm = cls.gt(0)
    lc = ee.Image(255)
    for k, (_, lo, hi) in enumerate(AGE_BINS):
        lc = lc.where(palm.And(py.gte(lo)).And(py.lte(hi)), k)
    lc = lc.where(palm.And(py.eq(0)), 2)
    forest = tc.gte(30)
    np_ = palm.Not()
    lc = (lc.where(np_.And(forest).And(loss.eq(0)), 4)
            .where(np_.And(forest).And(loss.gte(1)).And(loss.lte(15)), 5)
            .where(np_.And(forest).And(loss.gte(16)), 6)
            .where(np_.And(forest.Not()), 7)
            .where(dm.neq(1), 255))
    lc = lc.setDefaultProjection(gfc.projection()).reduceResolution(
        ee.Reducer.mode(), maxPixels=128).reproject(grid).rename("lc")
    land = dm.eq(1).setDefaultProjection(gfc.projection()).reduceResolution(
        ee.Reducer.mean(), maxPixels=128).reproject(grid).multiply(100).rename("land")

    # Sentinel-2 dNBR at 20 m
    def nbr(lo, hi):
        def one(im):
            scl = im.select("SCL")
            ok = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
            return im.normalizedDifference(["B8", "B12"]).updateMask(ok)
        return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(lo, hi)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80)).map(one).median())
    p20 = ee.Projection("EPSG:4326").atScale(20)
    dnbr = nbr(*S2_PRE).subtract(nbr(*S2_POST)).setDefaultProjection(p20)
    ok = dnbr.mask().gt(0).unmask(0).setDefaultProjection(p20)
    burn = dnbr.gte(DNBR_T).unmask(0).setDefaultProjection(p20)
    bfrac = burn.reduceResolution(ee.Reducer.mean(), maxPixels=256).reproject(grid) \
        .multiply(100).rename("bfrac")
    okfrac = ok.reduceResolution(ee.Reducer.mean(), maxPixels=256).reproject(grid) \
        .multiply(100).rename("okfrac")

    hist = ee.Image(0)
    for y in (2015, 2019, 2023):
        hist = hist.add(ee.ImageCollection(BURN_IC).filterDate(f"{y}-01-01", f"{y + 1}-01-01")
                        .select("BurnDate").map(lambda im: im.gt(0)).max().unmask(0))
    hist = hist.reproject(grid).rename("hist")
    depth = ee.Image("projects/sat-io/open-datasets/PEATGRIDS/THICKNESS_CM").select(0) \
        .unmask(0).reproject(grid).rename("depth")
    gh = ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2020").select("built_surface").unmask(0)
    built = gh.setDefaultProjection(gh.projection()).reduceResolution(
        ee.Reducer.mean(), maxPixels=64).reproject(grid).divide(100).rename("built")   # % of cell
    kal = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(kal_geom())]), 1) \
        .reproject(grid).rename("kal")
    return ee.Image.cat([lc, bfrac, okfrac, hist, depth, built, land, kal]).round().toInt16()


def stage_stack(_a):
    import ee
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    try:
        ee.data.getAsset(ASSET)
        print("asset exists:", ASSET)
        return
    except Exception:                                         # noqa: BLE001
        pass
    x0, y0, x1, y1 = KAL
    task = ee.batch.Export.image.toAsset(
        image=stack_image(), description="kalimantan_stack_200m", assetId=ASSET,
        region=ee.Geometry.Rectangle([x0, y0, x1, y1], None, False),
        crs="EPSG:4326", crsTransform=[STEP, 0, 0, 0, -STEP, 0], maxPixels=1e10)
    task.start()
    print(f"export started: {task.id} -> {ASSET}")


def stage_download(_a):
    import ee
    import rasterio
    from earthchange.gee_utils import initialize_ee
    from ketapang_landprep_tests import ee_download
    initialize_ee()
    arr, tr = ee_download(ee.Image(ASSET), KAL, os.path.join(DATA, "stack_tiles"), "stack", STEP, 6)
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                dtype="int16", crs="EPSG:4326", transform=tr, compress="deflate", tiled=True)
    with rasterio.open(STACK, "w", **prof) as ds:
        ds.write(arr.astype("int16"))
        ds.descriptions = tuple(BANDS)
    print(f"Saved: {STACK} {arr.shape}")


def stage_viirs(_a):
    """Detections in 2 x 2 deg tiles x months (getInfo size limits)."""
    import ee
    import numpy as np
    import pandas as pd
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    vdir = os.path.join(DATA, "viirs")
    os.makedirs(vdir, exist_ok=True)
    months = pd.date_range(V_START, V_END, freq="MS").tolist() + [pd.Timestamp(V_END)]
    xs, ys = np.arange(KAL[0], KAL[2], 2.0), np.arange(KAL[1], KAL[3], 2.0)
    for m0, m1 in zip(months[:-1], months[1:]):
        for x in xs:
            for y in ys:
                p = os.path.join(vdir, f"v_{m0:%Y%m}_{x:.1f}_{y:.1f}.csv")
                if os.path.exists(p):
                    continue
                rect = ee.Geometry.Rectangle([x, y, min(x + 2, KAL[2]), min(y + 2, KAL[3])], None, False)
                rows = []
                for cid in VIIRS:
                    ic = ee.ImageCollection(cid).filterDate(str(m0.date()), str(m1.date())).filterBounds(rect)

                    def pts(img):
                        b = img.select(["confidence", "frp", "acq_epoch"])
                        return b.addBands(ee.Image.pixelLonLat()).sample(
                            region=rect, projection=img.select("frp").projection(),
                            geometries=False, dropNulls=True)
                    cols = ["longitude", "latitude", "confidence", "frp", "acq_epoch"]
                    lst = ee.FeatureCollection(ic.map(pts)).flatten() \
                        .reduceColumns(ee.Reducer.toList(len(cols)), cols).get("list").getInfo()
                    sat = cid.split("/")[2].split("_")[0]
                    rows += [r + [sat] for r in lst]
                pd.DataFrame(rows, columns=["lon", "lat", "confidence", "frp", "acq_epoch", "sat"]) \
                    .to_csv(p + ".part", index=False)
                os.replace(p + ".part", p)
                print(f"  {m0:%Y-%m} {x:.0f},{y:.0f}: {len(rows):,}")
    allv = pd.concat([pd.read_csv(p) for p in sorted(glob.glob(os.path.join(vdir, "v_*.csv")))])
    allv.to_parquet(os.path.join(DATA, "viirs_2026.parquet"))
    print(f"Saved: viirs_2026.parquet ({len(allv):,} detections)")


# ------------------------------------------------------------------ sample
def stage_sample(_a):
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from scipy import ndimage

    with rasterio.open(STACK) as ds:
        S = {b: ds.read(i + 1) for i, b in enumerate(BANDS)}
        tr, shape = ds.transform, (ds.height, ds.width)
    land = (S["land"] >= 50) & (S["kal"] == 1) & (S["lc"] != 255)
    px_km = STEP * 111.32

    # tenure
    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]].reset_index(drop=True)
    op["geometry"] = op.geometry.make_valid()
    op_id = features.rasterize([(g, i + 1) for i, g in enumerate(op.geometry) if g is not None],
                               out_shape=shape, transform=tr, dtype="int32")
    hti = gpd.read_file(HTI)
    hti_m = features.rasterize([(g, 1) for g in hti.geometry], out_shape=shape, transform=tr,
                               dtype="uint8") > 0
    peat = features.rasterize([(g, 1) for g in gpd.read_file(PEAT).geometry], out_shape=shape,
                              transform=tr, dtype="uint8") > 0
    zone = np.zeros(shape, np.uint8)
    zone[land] = 1                                    # unpermitted
    zone[land & hti_m] = 2                            # pulpwood only
    zone[land & (op_id > 0)] = 3                      # oil palm (incl. overlap with HTI)

    # VIIRS: first day (WIB) per cell, and the 750 m evidence rule
    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"))
    v["t"] = pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)
    day = (v.t.dt.normalize() - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    rr, cc = rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy())
    rr, cc = np.asarray(rr), np.asarray(cc)
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    first = np.full(shape, 9999, np.int16)
    np.minimum.at(first, (rr[ok], cc[ok]), day[ok].astype(np.int16))
    seen = first < 9999
    near = ndimage.binary_dilation(seen, np.ones((3, 3), bool),
                                   iterations=int(np.ceil(NEAR_BURN_M / 200)) - 1)
    first3 = ndimage.minimum_filter(first, size=3)            # ~ the 375 m pixel

    valid = S["okfrac"] >= 50
    burned = valid & (S["bfrac"] * 2 >= S["okfrac"]) & near & land
    d_water = ndimage.distance_transform_edt(S["land"] >= 50) * px_km
    d_settle = ndimage.distance_transform_edt(S["built"] < 5) * px_km

    yy, xx = np.nonzero(land)
    df = pd.DataFrame({
        "r": yy.astype(np.int32), "c": xx.astype(np.int32),
        "zone": zone[yy, xx], "op": op_id[yy, xx], "hti": hti_m[yy, xx],
        "valid": valid[yy, xx], "burned": burned[yy, xx],
        "peat": peat[yy, xx], "thick": S["depth"][yy, xx], "lc": S["lc"][yy, xx].astype(np.uint8),
        "hist": S["hist"][yy, xx].astype(np.uint8),
        "d_water": d_water[yy, xx].astype(np.float32), "d_settle": d_settle[yy, xx].astype(np.float32),
        "day": np.where(first3[yy, xx] < 9999, first3[yy, xx], -1).astype(np.int16),
        "block": ((yy * px_km // BLOCK_KM).astype(np.int32) * 10000
                  + (xx * px_km // BLOCK_KM).astype(np.int32)),
    })
    df["depth_bin"] = np.where(df.peat, np.digitize(df.thick, [1, 100, 200, 300]), 9).astype(np.uint8)
    df["water_bin"] = np.digitize(df.d_water, [1, 3, 10]).astype(np.uint8)
    df["settle_bin"] = np.digitize(df.d_settle, [1, 3, 10]).astype(np.uint8)
    os.makedirs(OUT, exist_ok=True)
    df.to_parquet(os.path.join(DATA, "sample_200m.parquet"))
    op.drop(columns="geometry").assign(op=np.arange(1, len(op) + 1)) \
        .to_csv(os.path.join(DATA, "op_index.csv"), index=False)
    json.dump({"transform": list(tr)[:6], "shape": list(shape)},
              open(os.path.join(DATA, "sample_grid.json"), "w"))
    z = df.groupby("zone").agg(n=("burned", "size"), valid=("valid", "mean"), burned=("burned", "mean"))
    print(f"land cells {len(df):,} ({len(df) * 0.04:,.0f} km2)\n{z}")


# ------------------------------------------------------------------- match
SEQ = [[], ["peat"], ["peat", "depth_bin"], ["peat", "depth_bin", "lc"],
       ["peat", "depth_bin", "lc", "hist"], ["peat", "depth_bin", "lc", "hist", "water_bin"],
       ["peat", "depth_bin", "lc", "hist", "water_bin", "settle_bin"]]
NAMES = ["raw", "+ peat", "+ peat depth", "+ land cover", "+ burn history", "+ distance to water",
         "+ distance to settlement"]
NBOOT = 300


def stratum(d, keys):
    import numpy as np
    code = np.zeros(len(d), np.int64)
    for k in keys:
        x = d[k].to_numpy().astype(np.int64)
        code = code * (int(x.max()) + 1) + x
    return code


def matched(d, treat_mask, keys, val, boot_w, bidx):
    """CEM ATT of `val` (treated minus stratum-weighted control), on rows
    aggregated to (block, stratum, treated), block bootstrap. Returns the
    treated mean, matched-control mean and their bootstrap draws."""
    import numpy as np
    import pandas as pd
    code = stratum(d, keys) if keys else np.zeros(len(d), np.int64)
    g = pd.DataFrame({"b": bidx[d.block.to_numpy()], "s": code, "t": treat_mask,
                      "v": val}).groupby(["b", "s", "t"]).agg(n=("v", "size"), x=("v", "sum")).reset_index()
    s_codes, s_idx = np.unique(g.s.to_numpy(), return_inverse=True)
    ns = len(s_codes)
    t = g.t.to_numpy()
    b = g.b.to_numpy()
    n, x = g.n.to_numpy(float), g.x.to_numpy(float)

    def att(w):
        wb = w[b]
        tn = np.bincount(s_idx[t], wb[t] * n[t], ns)
        tx = np.bincount(s_idx[t], wb[t] * x[t], ns)
        cn = np.bincount(s_idx[~t], wb[~t] * n[~t], ns)
        cx = np.bincount(s_idx[~t], wb[~t] * x[~t], ns)
        m = (tn > 0) & (cn > 0)
        W = tn[m].sum()
        return tx[m].sum() / W, (tn[m] * cx[m] / cn[m]).sum() / W, W / max(tn.sum(), 1)
    pt, pc, cov = att(np.ones(boot_w.shape[1]))
    bs = np.array([att(w)[:2] for w in boot_w])
    return pt, pc, cov, bs


def stage_match(_a):
    import numpy as np
    import pandas as pd
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"))
    df = df[df.valid].reset_index(drop=True)
    blocks = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    rng = np.random.default_rng(42)
    boot_w = rng.multinomial(len(blocks), np.ones(len(blocks)) / len(blocks), size=NBOOT).astype(float)
    print(f"cells with a cloud-free S2 pair: {len(df):,}; blocks {len(blocks):,}")
    rows = []

    def burn_row(d, treat, label, keys, name):
        pt, pc, cov, bs = matched(d, treat, keys, d.burned.to_numpy(float), boot_w, bidx)
        r = bs[:, 0] / bs[:, 1]
        rows.append({"test": "burn", "treated": label, "matched_on": name,
                     "treated_pct": 100 * pt, "control_pct": 100 * pc, "ratio": pt / pc,
                     "ratio_ci95": [float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))],
                     "gap_pts": 100 * (pt - pc), "coverage": cov, "n_treated": int(treat.sum())})
        print(f"  {label:<12} {name:<26} {100 * pt:5.1f}% vs {100 * pc:5.1f}%  x{pt / pc:.2f} "
              f"[{rows[-1]['ratio_ci95'][0]:.2f}, {rows[-1]['ratio_ci95'][1]:.2f}]  cov {100 * cov:.0f}%")

    for z, label in ((3, "oil palm"), (2, "pulpwood")):
        d = df[df.zone.isin([1, z])].reset_index(drop=True)
        for nm, keys in zip(NAMES, SEQ):
            burn_row(d, (d.zone == z).to_numpy(), label, keys, nm)

    # timing: burned cells with a VIIRS date, Jun-Oct
    full = SEQ[-1]
    for z, label in ((3, "oil palm"), (2, "pulpwood")):
        d = df[df.zone.isin([1, z]) & df.burned & (df.day >= 152) & (df.day < 305)].reset_index(drop=True)
        for nm, keys in ((NAMES[0], SEQ[0]), (NAMES[-1], full)):
            pt, pc, cov, bs = matched(d, (d.zone == z).to_numpy(), keys, d.day.to_numpy(float), boot_w, bidx)
            g = bs[:, 0] - bs[:, 1]
            rows.append({"test": "first-fire day", "treated": label, "matched_on": nm,
                         "treated_day": pt, "control_day": pc, "gap_days": pt - pc,
                         "gap_ci95": [float(np.percentile(g, 2.5)), float(np.percentile(g, 97.5))],
                         "coverage": cov, "n_treated": int((d.zone == z).sum())})
            print(f"  timing {label:<10} {nm:<26} {pt - pc:+.1f} d "
                  f"[{rows[-1]['gap_ci95'][0]:+.1f}, {rows[-1]['gap_ci95'][1]:+.1f}]")

    # the Ketapang four in this pipeline, as a check against the 25 m study
    idx = pd.read_csv(os.path.join(DATA, "op_index.csv"))
    from ketapang_fire_origin import FOUR
    ids = [int(idx[idx.company.str.contains(n, case=False, na=False)].op.iloc[0]) for n in FOUR.values()]
    d = df[(df.zone == 1) | df.op.isin(ids)].reset_index(drop=True)
    d = d[(d.r >= df[df.op.isin(ids)].r.min() - 120) & (d.r <= df[df.op.isin(ids)].r.max() + 120)
          & (d.c >= df[df.op.isin(ids)].c.min() - 120) & (d.c <= df[df.op.isin(ids)].c.max() + 120)]
    d = d.reset_index(drop=True)
    for nm, keys in ((NAMES[0], SEQ[0]), (NAMES[-1], full)):
        burn_row(d, d.op.isin(ids).to_numpy(), "Ketapang 4", keys, nm)

    pd.DataFrame(rows).to_csv(os.path.join(OUT, "matched.csv"), index=False)
    json.dump(rows, open(os.path.join(OUT, "matched.json"), "w"), indent=1, default=float)
    print(f"Saved: {OUT}/matched.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True,
                    choices=["vectors", "stack", "download", "viirs", "sample", "match"])
    a = ap.parse_args()
    {"vectors": stage_vectors, "stack": stage_stack, "download": stage_download,
     "viirs": stage_viirs, "sample": stage_sample, "match": stage_match}[a.stage](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
