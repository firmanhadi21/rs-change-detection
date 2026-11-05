#!/usr/bin/env python3
"""WP6 robustness of the Kalimantan matched concession effect (kalimantan_excess_burn.py).

Baseline: S2 burned share 2026, oil palm (zone 3) or pulpwood-only (zone 2) vs unpermitted
(zone 1), CEM on all SEQ strata, 5 km block bootstrap (NBOOT draws), cloud-free cells.

R1 BOUNDARY BUFFERS. Drop unpermitted cells within b km of a concession (fire spilling out,
   or land just outside managed like the inside), and in a second variant also concession
   cells within b km of their boundary (c. 2012 boundaries misplaced). b = 0.5, 1, 2, 5 km.
R2 ALTERNATIVE PEAT MAP. Greifswald Global Peatland Map 2.0 (1 km; peat dominated or peat in
   soil mosaic) replaces BBSDLP in the peat and depth-bin strata.
R3 OTHER SEASONS. MODIS MCD64A1 burned (any date in the year, all land cells, no S2 needed)
   for 2015, 2019, 2023 and 2026, matched on peat, depth bin, distance to water and settlement
   and burn history BEFORE that year (land cover is left out: it is mapped after the earlier
   fires). The 2026 MCD64 row shows how much the outcome measure alone changes the estimate.
R4 NEWER BOUNDARIES. GFW gfw_oil_palm v2025 (Indonesia) replaces the c. 2012 layer for zone 3.

    python scripts/kalimantan_robustness.py --stage extra      # Earth Engine: MCD64 2023/2026 + GPM
    python scripts/kalimantan_robustness.py --stage gfw2025    # GFW data API
    python scripts/kalimantan_robustness.py --stage run
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import DATA, HTI, KAL, NBOOT, OUT, SEQ, STACK, STEP, direct_download, matched  # noqa: E402

EXTRA = os.path.join(DATA, "robust_200m.tif")
EXTRA_BANDS = ["b2023", "b2026", "gpm"]
FATE = os.path.join(DATA, "fate_200m.tif")          # kalimantan_landprep.py: b2015, b2019
OP2025 = os.path.join(DATA, "gfw_oil_palm_2025_kalimantan.gpkg")
GPM = "projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE"
BUFFERS_KM = (0.5, 1, 2, 5)
PX_KM = STEP * 111.32
RES = os.path.join(OUT, "robustness.json")
NOLC = ["peat", "depth_bin", "water_bin", "settle_bin"]


def stage_extra():
    import ee
    import rasterio
    from earthchange.fire_national import BURN_IC
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    grid = ee.Projection("EPSG:4326", [STEP, 0, 0, 0, -STEP, 0])
    b = [ee.ImageCollection(BURN_IC).filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("BurnDate")
         .map(lambda im: im.gt(0)).max().unmask(0).reproject(grid).rename(f"b{y}") for y in (2023, 2026)]
    gpm = ee.Image(GPM).gte(1).unmask(0).reproject(grid).rename("gpm")
    last = ee.ImageCollection(BURN_IC).filterDate("2026-01-01", "2027-01-01").aggregate_max("system:index").getInfo()
    print(f"MCD64A1 2026 latest image: {last}")
    arr, tr = direct_download(ee.Image.cat(b + [gpm]).toInt16(), os.path.join(DATA, "robust_tiles"))
    with rasterio.open(STACK) as ref:
        if arr.shape[1:] != (ref.height, ref.width):
            raise SystemExit(f"grid {arr.shape[1:]} != stack {(ref.height, ref.width)}")
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype="int16",
                crs="EPSG:4326", transform=tr, compress="deflate", tiled=True)
    with rasterio.open(EXTRA, "w", **prof) as ds:
        ds.write(arr.astype("int16"))
        ds.descriptions = tuple(EXTRA_BANDS)
    json.dump({"mcd64_2026_latest": last}, open(EXTRA.replace(".tif", ".json"), "w"))
    print(f"Saved: {EXTRA} {arr.shape}")


def stage_gfw2025():
    import geopandas as gpd
    import requests
    import shapely
    from shapely.geometry import shape
    from kalimantan_heterogeneity import gfw_key
    url = "https://data-api.globalforestwatch.org/dataset/gfw_oil_palm/v2025/query/json"
    x0, y0, x1, y1 = KAL
    sql = ("SELECT conc_name, company, comp_group, conc_type, conc_stat, source, source_yr, gfw_area__ha, "
           "ST_AsGeoJSON(geom) AS gj FROM data WHERE iso3 = 'IDN' AND "
           f"ST_Intersects(geom, ST_MakeEnvelope({x0}, {y0}, {x1}, {y1}, 4326))")
    r = requests.get(url, headers={"x-api-key": gfw_key()}, params={"sql": sql}, timeout=900)
    r.raise_for_status()
    rows = r.json()["data"]
    for x in rows:
        x["geometry"] = shapely.force_2d(shape(json.loads(x.pop("gj"))))
    g = gpd.GeoDataFrame(rows, crs=4326)
    g.to_file(OP2025)
    print(f"Saved: {OP2025} ({len(g)} polygons)")
    print(g.source_yr.value_counts().head(10).to_string())
    print(g.conc_stat.value_counts().head(10).to_string())


def stage_run():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from scipy import ndimage

    cols = ["r", "c", "zone", "op", "valid", "burned", "peat", "thick", "lc", "hist", "block",
            "depth_bin", "water_bin", "settle_bin"]
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"), columns=cols)
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, shape = rasterio.Affine(*grid["transform"]), tuple(grid["shape"])
    r, c = df.r.to_numpy(), df.c.to_numpy()
    zone = np.zeros(shape, np.uint8)
    zone[r, c] = df.zone.to_numpy()
    conc = (zone == 2) | (zone == 3)
    df["d_out"] = (ndimage.distance_transform_edt(~conc) * PX_KM)[r, c]   # unpermitted: km to a concession
    df["d_in"] = (ndimage.distance_transform_edt(conc) * PX_KM)[r, c]     # concession: km to its edge

    blocks = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    W = np.random.default_rng(42).multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                                              size=NBOOT).astype(float)
    rows = []

    def row(check, variant, d, z, keys, val):
        treat = (d.zone == z).to_numpy()
        pt, pc, cov, bs = matched(d, treat, keys, val, W, bidx)
        q = bs[:, 0] / np.where(bs[:, 1] > 0, bs[:, 1], np.nan)
        lo, hi = np.nanpercentile(q, [2.5, 97.5])
        label = {3: "oil palm", 2: "pulpwood"}[z]
        rows.append({"check": check, "variant": variant, "treated": label, "treated_pct": 100 * pt,
                     "control_pct": 100 * pc, "ratio": pt / pc, "ci": [float(lo), float(hi)],
                     "coverage": float(cov), "n_treated": int(treat.sum()), "n_control": int((~treat).sum())})
        print(f"  {check:<4}{variant:<38}{label:<10}{100 * pt:6.2f}% vs {100 * pc:6.2f}%  x{pt / pc:.2f} "
              f"[{lo:.2f}, {hi:.2f}]  cov {100 * cov:.0f}%", flush=True)

    v = df[df.valid]
    print("baseline and R1 boundary buffers (S2 burned 2026, all strata)")
    for z in (3, 2):
        d = v[v.zone.isin([1, z])]
        row("base", "main estimate", d, z, SEQ[-1], d.burned.to_numpy(float))
        for b in BUFFERS_KM:
            d1 = d[(d.zone != 1) | (d.d_out >= b)]
            row("R1", f"controls >= {b} km from concessions", d1, z, SEQ[-1], d1.burned.to_numpy(float))
            d2 = d1[(d1.zone == 1) | (d1.d_in >= b)]
            row("R1", f"+ treated >= {b} km inside edge", d2, z, SEQ[-1], d2.burned.to_numpy(float))

    print("R2 Greifswald GPM 2.0 peat instead of BBSDLP")
    with rasterio.open(EXTRA) as ds:
        X = {b: ds.read(i + 1)[r, c] for i, b in enumerate(EXTRA_BANDS)}
    df["gpm"] = X["gpm"] > 0
    df["depth_bin_gpm"] = np.where(df.gpm, np.digitize(df.thick, [1, 100, 200, 300]), 9).astype(np.uint8)
    keys_gpm = ["gpm", "depth_bin_gpm"] + SEQ[-1][2:]
    v = df[df.valid]
    for z in (3, 2):
        d = v[v.zone.isin([1, z])]
        row("R2", "GPM peat + depth bins", d, z, keys_gpm, d.burned.to_numpy(float))

    print("R3 other seasons (MCD64A1 burned, all land cells, history before the year, no land cover)")
    with rasterio.open(FATE) as ds:
        names = list(ds.descriptions)
        for y in (2015, 2019):
            df[f"b{y}"] = ds.read(names.index(f"b{y}") + 1)[r, c] > 0
    for y in (2023, 2026):
        df[f"b{y}"] = X[f"b{y}"] > 0
    prior = {2015: [], 2019: [2015], 2023: [2015, 2019], 2026: [2015, 2019, 2023]}
    for y, pr in prior.items():
        df["hist_pre"] = sum((df[f"b{p}"].astype(np.uint8) for p in pr), np.zeros(len(df), np.uint8))
        for z in (3, 2):
            d = df[df.zone.isin([1, z])]
            row("R3", f"{y} MCD64", d, z, NOLC + (["hist_pre"] if pr else []), d[f"b{y}"].to_numpy(float))
    v = df[df.valid]
    for z in (3, 2):
        d = v[v.zone.isin([1, z])]
        row("R3", "2026 S2, same strata as seasons", d, z, NOLC + ["hist_pre"], d.burned.to_numpy(float))

    if os.path.exists(OP2025):
        print("R4 GFW oil palm v2025 boundaries")
        g = gpd.read_file(OP2025)
        g["geometry"] = g.geometry.make_valid()
        op25 = features.rasterize([(x, 1) for x in g.geometry if x is not None], out_shape=shape,
                                  transform=tr, dtype="uint8")[r, c] > 0
        hti_m = features.rasterize([(x, 1) for x in gpd.read_file(HTI).geometry], out_shape=shape,
                                   transform=tr, dtype="uint8")[r, c] > 0
        z25 = np.ones(len(df), np.uint8)
        z25[hti_m] = 2
        z25[op25] = 3
        old3, new3 = df.zone.to_numpy() == 3, z25 == 3
        overlap = {"cells_old": int(old3.sum()), "cells_new": int(new3.sum()), "both": int((old3 & new3).sum())}
        print(f"  oil-palm cells c.2012 {overlap['cells_old']:,}, v2025 {overlap['cells_new']:,}, "
              f"both {overlap['both']:,}")
        rows.append({"check": "R4", "variant": "overlap", **overlap})
        d0 = df.assign(zone=z25)
        v = d0[d0.valid]
        for z in (3, 2):
            d = v[v.zone.isin([1, z])]
            row("R4", "GFW v2025 oil palm", d, z, SEQ[-1], d.burned.to_numpy(float))

    json.dump(rows, open(RES, "w"), indent=1, default=float)
    pd.DataFrame([x for x in rows if "ratio" in x]).to_csv(RES.replace(".json", ".csv"), index=False)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["extra", "gfw2025", "run"], required=True)
    {"extra": stage_extra, "gfw2025": stage_gfw2025, "run": stage_run}[ap.parse_args().stage]()
