#!/usr/bin/env python3
"""Oil-palm expansion and fire in Kalimantan, 2001-2025: a yearly panel on the
MODIS 500 m grid.

Question. Does fire rise on and around peat once industrial oil palm arrives,
including on peat outside the plantation (drainage drying the dome), and how
do fires in smallholder / swidden landscapes on mineral soil compare?

Unit. One MODIS MCD64A1 pixel (463.3 m sinusoidal, SR-ORG:6974; 21.5 ha), so
the outcome is never resampled. Finer inputs are reduced to it as shares in
Earth Engine; vectors are rasterised locally on the same grid.

  burn_YYYY  MCD64A1 burned at least once in the calendar year (2001-2025)
  ind_YYYY   % of the cell industrial oil palm planted by YYYY  (Descals et al.
  sh_YYYY    % smallholder oil palm planted by YYYY              2024, 2000-2021;
  palm_ny    % oil palm with no planting year                    later years = 2021)
  und_YYYY   % JRC TMF undisturbed tropical moist forest (Dec of YYYY; 1990, 2000-2024)
  deg_YYYY   % JRC TMF degraded forest
  rain_YYYY  CHIRPS Jun-Oct rainfall (mm), the fire season's dryness
  depth      PEATGRIDS peat thickness (cm); land (% land, Hansen); kal (in GAUL
             Kalimantan); built00 (% built-up 2000, GHSL)
  peat, conc, hti  BBSDLP peat, GFW oil-palm concessions (c. 2012), HTI permits

Planting year 1989 in the palm map means "1989 or earlier". The palm map is
the extent around 2021: plantations that existed earlier but were later
abandoned or converted are missing, and palms planted after ~2019 are under-
detected.

STAGES
  export    start Earth Engine batch exports to assets (burn, palm, forest, env; with
            --parts also reg, nineties, l5burn_1991/1994/1997/2006)
  download  fetch the assets in tiles to data/kalimantan_panel/*.tif
  panel     build cells.parquet (static) and panel.parquet (cell x year)
  describe  burned share by year, peat and distance to industrial palm
  event     stacked event studies: fire on land that becomes palm (conversion) and on
            unplanted land once palm arrives within 5 km (spillover), against never-near land
            in the same 1 deg tile x peat depth x 2000 forest stratum; 5 km block bootstrap
  robust    spillover with 0-2 km and 5-10 km arrival, not-yet-treated controls, long follow-up
  viirs     VIIRS 375 m detections (FIRMS yearly country files, 2012-2025, in
            data/kalimantan_panel/viirs/) grouped into fire events, compared by landscape
            (palm, clearing, peat, permits, swidden-like rotational mosaic, other)
  nineties  Landsat 5 burn scars 1991/1994/1997 by peat and distance to palm, checked
            against MCD64A1 in 2006

    python scripts/kalimantan_palm_fire_panel.py --stage export
    python scripts/kalimantan_palm_fire_panel.py --stage export --parts reg,nineties,l5burn_1991,...
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from kalimantan_excess_burn import CONC, HTI, PEAT, KAL, kal_geom  # noqa: E402
from ketapang_fire_origin import _DATA_ROOT  # noqa: E402

YEARS = list(range(2001, 2026))
PALM_YEARS = list(range(2000, 2022))
TMF_YEARS = [1990] + list(range(2000, 2025))
DATA = os.path.join(_DATA_ROOT, "data", "kalimantan_panel")
OUT = os.path.join(_DATA_ROOT, "output", "fire", "kalimantan_palm_panel")
ASSET_ROOT = os.environ.get("KALPANEL_ASSETS", "projects/ee-efha94/assets/kalpanel_")
PARTS = ("burn", "palm", "forest", "env")
PARTS2 = ("reg", "nineties", "l5burn_1991", "l5burn_1994", "l5burn_1997", "l5burn_2006")

# MODIS sinusoidal grid (MCD64A1's own)
SIN = "SR-ORG:6974"
PX = 463.3127165279165
X0, Y0 = -20015109.354, 7783653.6376640005
CELL_KM = PX / 1000
BLOCK_KM = 5.0
PALM_MIN = 50          # a cell "is" industrial palm when >= 50% of it is
RINGS_KM = [0, 1, 2, 5, 10]


def grid_window():
    """Row/column range of the MODIS grid covering the KAL bbox."""
    import numpy as np
    from pyproj import Transformer
    t = Transformer.from_crs(4326, "+proj=sinu +R=6371007.181 +units=m", always_xy=True)
    lons = np.linspace(KAL[0], KAL[2], 50)
    lats = np.linspace(KAL[1], KAL[3], 50)
    lo, la = np.meshgrid(lons, lats)
    x, y = t.transform(lo.ravel(), la.ravel())
    c0, c1 = int(np.floor((x.min() - X0) / PX)), int(np.ceil((x.max() - X0) / PX))
    r0, r1 = int(np.floor((Y0 - y.max()) / PX)), int(np.ceil((Y0 - y.min()) / PX))
    return r0, r1, c0, c1


def region_geom():
    import ee
    r0, r1, c0, c1 = grid_window()
    return ee.Geometry.Rectangle([X0 + c0 * PX, Y0 - r1 * PX, X0 + c1 * PX, Y0 - r0 * PX],
                                 ee.Projection(SIN), False)


# ------------------------------------------------------------- Earth Engine
def share(mask, native):
    """% of the MODIS cell where mask is true; mask sampled on `native`."""
    import ee
    grid = ee.Projection(SIN, [PX, 0, X0, 0, -PX, Y0])
    return (mask.unmask(0).setDefaultProjection(native)
            .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
            .reproject(grid).multiply(100).round())


def image(part):
    import ee
    from earthchange.fire_national import BURN_IC
    p30 = ee.Projection("EPSG:4326").atScale(30)
    if part == "burn":
        bands = []
        for y in YEARS:
            ic = ee.ImageCollection(BURN_IC).filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("BurnDate")
            bands.append(ic.map(lambda im: im.gt(0)).max().unmask(0).rename(f"burn_{y}"))
        return ee.Image.cat(bands).toUint8()
    if part == "palm":
        op = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2")
        cls = op.select("classification").mosaic().unmask(0)
        py = op.select("planting_year").mosaic().unmask(0)
        bands = []
        for y in PALM_YEARS:
            known = py.gt(0).And(py.lte(y))
            bands.append(share(cls.eq(1).And(known), p30).rename(f"ind_{y}"))
            bands.append(share(cls.eq(2).And(known), p30).rename(f"sh_{y}"))
        bands.append(share(cls.gt(0).And(py.eq(0)), p30).rename("palm_ny"))
        return ee.Image.cat(bands).toUint8()
    if part == "forest":
        tmf = ee.ImageCollection("projects/JRC/TMF/v1_2024/AnnualChanges").mosaic()
        bands = []
        for y in TMF_YEARS:
            b = tmf.select(f"Dec{y}")
            bands.append(share(b.eq(1), p30).rename(f"und_{y}"))
            bands.append(share(b.eq(2), p30).rename(f"deg_{y}"))
        return ee.Image.cat(bands).toUint8()
    if part == "env":
        grid = ee.Projection(SIN, [PX, 0, X0, 0, -PX, Y0])
        gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")
        land = share(gfc.select("datamask").eq(1), p30).rename("land")
        depth = (ee.Image("projects/sat-io/open-datasets/PEATGRIDS/THICKNESS_CM").select(0)
                 .unmask(0).reproject(grid).round().rename("depth"))
        gh = ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2000").select("built_surface").unmask(0)
        built = (gh.setDefaultProjection(gh.projection())
                 .reduceResolution(ee.Reducer.mean(), maxPixels=64).reproject(grid)
                 .divide(100).round().rename("built00"))           # m2 per 100 m2 -> %
        kal = (ee.Image(0).paint(ee.FeatureCollection([ee.Feature(kal_geom())]), 1)
               .reproject(grid).rename("kal"))
        ch = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        rain = [ch.filterDate(f"{y}-06-01", f"{y}-11-01").sum().reproject(grid).round()
                .rename(f"rain_{y}") for y in YEARS]
        return ee.Image.cat([land, depth, built, kal] + rain).toInt16()
    if part == "reg":           # TMF regrowth (class 4): the fallow side of a rotation
        tmf = ee.ImageCollection("projects/JRC/TMF/v1_2024/AnnualChanges").mosaic()
        return ee.Image.cat([share(tmf.select(f"Dec{y}").eq(4), p30).rename(f"reg_{y}")
                             for y in TMF_YEARS[1:]]).toUint8()
    if part == "nineties":      # palm planted by y and forest state the December before, 1990s fire years
        op = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2")
        cls = op.select("classification").mosaic().unmask(0)
        py = op.select("planting_year").mosaic().unmask(0)
        tmf = ee.ImageCollection("projects/JRC/TMF/v1_2024/AnnualChanges").mosaic()
        bands = []
        for y in L5_YEARS:
            known = py.gt(0).And(py.lte(y))
            bands += [share(cls.eq(1).And(known), p30).rename(f"ind_{y}"),
                      share(cls.eq(2).And(known), p30).rename(f"sh_{y}"),
                      share(tmf.select(f"Dec{max(y - 1, 1990)}").eq(1), p30).rename(f"und_{y}"),
                      share(tmf.select(f"Dec{max(y - 1, 1990)}").eq(2), p30).rename(f"deg_{y}")]
        return ee.Image.cat(bands).toUint8()
    if part.startswith("l5burn_"):  # Landsat 5 dNBR burn scars, one year per export (all four
        y = int(part[-4:])          # in one job ran out of memory); 2006 calibrates against MCD64A1
        p60 = ee.Projection("EPSG:4326").atScale(60)    # 30 m scars sampled every 60 m: ~60 per cell
        pre = _l5_nbr(f"{y}-04-01", f"{y}-07-31")
        post = _l5_nbr(f"{y}-10-15", f"{y + 1}-03-15")
        ok = pre.mask().And(post.mask())
        burned = pre.subtract(post).gte(L5_DNBR).And(post.lt(0.1)).And(ok)
        return ee.Image.cat([share(burned, p60).rename(f"lb_{y}"),
                             share(ok, p60).rename(f"lok_{y}")]).toUint8()
    raise ValueError(part)


L5_YEARS = (1991, 1994, 1997, 2006)
L5_DNBR = 0.27


def _l5_nbr(lo, hi):
    """Median Landsat 5 NBR (T1 + T2 surface reflectance), cloud, shadow and dilated cloud masked."""
    import ee

    def one(im):
        qa = im.select("QA_PIXEL")
        clear = qa.bitwiseAnd(0b11010).eq(0)                     # bits 1 dilated, 3 cloud, 4 shadow
        sr = im.select(["SR_B4", "SR_B7"]).multiply(0.0000275).add(-0.2)
        return sr.normalizedDifference(["SR_B4", "SR_B7"]).updateMask(clear)
    ic = (ee.ImageCollection("LANDSAT/LT05/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LT05/C02/T2_L2"))
          .filterDate(lo, hi).filterBounds(ee.Geometry.Rectangle(list(KAL))))
    return ic.map(one).median()


def stage_export(_a):
    import ee
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    for part in (_a.parts.split(",") if _a.parts else PARTS):
        asset = ASSET_ROOT + part
        try:
            ee.data.getAsset(asset)
            print("asset exists:", asset)
            continue
        except Exception:                                           # noqa: BLE001
            pass
        task = ee.batch.Export.image.toAsset(
            image=image(part), description="kalpanel_" + part, assetId=asset,
            region=region_geom(), crs=SIN, crsTransform=[PX, 0, X0, 0, -PX, Y0], maxPixels=1e10)
        task.start()
        print(f"export started: {task.id} -> {asset}")


TILE = 400


def stage_download(_a):
    import time
    from concurrent.futures import ThreadPoolExecutor
    import numpy as np
    import rasterio
    import requests
    import ee
    from rasterio.merge import merge
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    os.makedirs(DATA, exist_ok=True)
    r0, r1, c0, c1 = grid_window()
    for part in (_a.parts.split(",") if _a.parts else PARTS):
        dst = os.path.join(DATA, f"{part}.tif")
        if os.path.exists(dst):
            print("have", dst)
            continue
        img = ee.Image(ASSET_ROOT + part)
        names = img.bandNames().getInfo()
        tdir = os.path.join(DATA, f"tiles_{part}")
        os.makedirs(tdir, exist_ok=True)
        jobs = []
        for r in range(r0, r1, TILE):
            for c in range(c0, c1, TILE):
                ra, rb, ca, cb = r, min(r + TILE, r1), c, min(c + TILE, c1)
                jobs.append((os.path.join(tdir, f"t_{r}_{c}.tif"),
                             [X0 + ca * PX, Y0 - rb * PX, X0 + cb * PX, Y0 - ra * PX]))

        def fetch(job):
            path, e = job
            if os.path.exists(path):
                return
            for attempt in range(4):
                try:
                    url = img.getDownloadURL({
                        "region": ee.Geometry.Rectangle(e, ee.Projection(SIN), False),
                        "crs": SIN, "crs_transform": [PX, 0, X0, 0, -PX, Y0],
                        "format": "GEO_TIFF"})
                    rq = requests.get(url, timeout=900)
                    rq.raise_for_status()
                    with open(path + ".part", "wb") as f:
                        f.write(rq.content)
                    os.replace(path + ".part", path)
                    return
                except Exception as exc:                            # noqa: BLE001 — retry
                    err = exc
                    time.sleep(15 * (attempt + 1))
            raise SystemExit(f"{path}: {err}")

        print(f"{part}: {len(jobs)} tiles, {len(names)} bands")
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(fetch, jobs))
        srcs = [rasterio.open(p) for p, _ in jobs]
        arr, tr = merge(srcs, method="first")
        prof = srcs[0].profile | dict(height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                                      transform=tr, compress="deflate", tiled=True,
                                      blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
        for s in srcs:
            s.close()
        with rasterio.open(dst, "w", **prof) as ds:
            ds.write(arr)
            ds.descriptions = tuple(names)
        print(f"Saved: {dst} {arr.shape}")
        del arr


# ------------------------------------------------------------------- panel
def _read(part):
    import rasterio
    with rasterio.open(os.path.join(DATA, f"{part}.tif")) as ds:
        return {d: ds.read(i + 1) for i, d in enumerate(ds.descriptions)}, ds.transform, ds.crs, \
            (ds.height, ds.width)


def stage_panel(_a):
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    from rasterio import features
    from scipy import ndimage

    E, tr, crs, shape = _read("env")
    B = _read("burn")[0]
    P = _read("palm")[0]
    F = _read("forest")[0]
    land = (E["kal"] == 1) & (E["land"] >= 50)
    yy, xx = np.nonzero(land)
    n = len(yy)
    print(f"land cells {n:,} ({n * CELL_KM ** 2:,.0f} km2)")

    def rast(path):
        g = gpd.read_file(path).to_crs(crs)
        g = g[g.geometry.notna() & ~g.geometry.is_empty]
        return features.rasterize([(geom, 1) for geom in g.geometry.make_valid()], out_shape=shape,
                                  transform=tr, dtype="uint8", all_touched=False) > 0
    peat, conc, hti = rast(PEAT), rast(CONC), rast(HTI)

    def ind(y):
        return P[f"ind_{min(max(y, PALM_YEARS[0]), PALM_YEARS[-1])}"]

    def sh(y):
        return P[f"sh_{min(max(y, PALM_YEARS[0]), PALM_YEARS[-1])}"]

    # first year the cell is >= 50% industrial palm (0 = never by 2021; 1999 = by 2000)
    first_ind = np.zeros(shape, np.int16)
    for y in reversed(PALM_YEARS):
        first_ind[P[f"ind_{y}"] >= PALM_MIN] = y if y > PALM_YEARS[0] else 1999

    blk = ((yy * CELL_KM // BLOCK_KM).astype(np.int32) * 10000 + (xx * CELL_KM // BLOCK_KM).astype(np.int32))
    cells = pd.DataFrame({
        "cell": np.arange(n, dtype=np.int32), "r": yy.astype(np.int32), "c": xx.astype(np.int32),
        "peat": peat[yy, xx], "depth": E["depth"][yy, xx], "conc": conc[yy, xx], "hti": hti[yy, xx],
        "built00": E["built00"][yy, xx].astype(np.uint8), "palm_ny": P["palm_ny"][yy, xx],
        "und1990": F["und_1990"][yy, xx], "deg1990": F["deg_1990"][yy, xx],
        "und2000": F["und_2000"][yy, xx], "first_ind": first_ind[yy, xx], "block": blk,
    })
    os.makedirs(DATA, exist_ok=True)
    cells.to_parquet(os.path.join(DATA, "cells.parquet"))

    frames = []
    for y in YEARS:
        ip = ind(y) >= PALM_MIN
        d_ind = ndimage.distance_transform_edt(~ip) * CELL_KM
        frames.append(pd.DataFrame({
            "cell": cells.cell.to_numpy(), "year": np.int16(y),
            "burn": B[f"burn_{y}"][yy, xx],
            "ind": ind(y)[yy, xx], "sh": sh(y)[yy, xx],
            "d_ind": d_ind[yy, xx].astype(np.float32),
            "und": F[f"und_{min(y, 2024)}"][yy, xx], "deg": F[f"deg_{min(y, 2024)}"][yy, xx],
            "rain": E[f"rain_{y}"][yy, xx],
        }))
        print(f"  {y}: burned {frames[-1].burn.mean() * 100:.2f}%, industrial palm cells "
              f"{(frames[-1].ind >= PALM_MIN).sum():,}", flush=True)
    panel = pd.concat(frames, ignore_index=True)
    panel.to_parquet(os.path.join(DATA, "panel.parquet"))
    json.dump({"crs": crs.to_wkt(), "transform": list(tr)[:6], "shape": list(shape),
               "cell_km": CELL_KM, "palm_min": PALM_MIN, "years": YEARS},
              open(os.path.join(DATA, "grid.json"), "w"), indent=1)
    print(f"Saved: panel.parquet ({len(panel):,} rows), cells.parquet ({n:,})")


# ---------------------------------------------------------------- describe
def stage_describe(_a):
    import numpy as np
    import pandas as pd
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    panel = pd.read_parquet(os.path.join(DATA, "panel.parquet"))
    d = panel.merge(cells[["cell", "peat"]], on="cell")
    d["ring"] = pd.cut(d.d_ind, [-0.1, 0.01] + RINGS_KM[1:] + [1e9],
                       labels=["in palm", "0-1 km", "1-2 km", "2-5 km", "5-10 km", ">10 km"])
    # the season's dryness, Kalimantan-wide: Jun-Oct rain over land
    rain = d.groupby("year").rain.mean()
    dry = rain.rank().le(6)                                   # the six driest seasons
    d["dry"] = d.year.map(dry)
    os.makedirs(OUT, exist_ok=True)
    t = (d.groupby(["peat", "dry", "ring"], observed=True)
         .agg(cells=("burn", "size"), burned_pct=("burn", "mean")).reset_index())
    t["burned_pct"] *= 100
    t.to_csv(os.path.join(OUT, "burn_by_ring.csv"), index=False)
    yr = (d.groupby(["year", "peat"]).burn.mean().unstack() * 100).rename(columns={False: "mineral", True: "peat"})
    yr["rain_jun_oct_mm"] = rain
    yr.to_csv(os.path.join(OUT, "burn_by_year.csv"))
    summary = {"dry_years": sorted(int(y) for y in dry[dry].index),
               "cells": int(len(cells)), "rows": int(len(panel)),
               "palm_cells_2021": int((panel[panel.year == 2021].ind >= PALM_MIN).sum())}
    json.dump(summary, open(os.path.join(OUT, "describe.json"), "w"), indent=1)
    pd.set_option("display.width", 140)
    print(yr.round(2))
    print(t.pivot_table(index="ring", columns=["peat", "dry"], values="burned_pct", observed=True).round(2))
    print(summary)


# ------------------------------------------------------------------- event
# The ex-Mega Rice Project (EMRP / ex-PLG, Central Kalimantan, 1996-98): state canals that
# drained ~1 Mha of peat with no oil palm involved. Approximate outline (Sebangau river to the
# Barito, Palangka Raya - Mantangai to the coast), traced from published block maps; it is
# masked out of both groups, and the sensitivity run keeps it in.
EMRP = [(113.95, -2.15), (114.25, -2.0), (114.6, -1.95), (114.85, -2.3), (114.85, -2.9),
        (114.75, -3.3), (114.3, -3.45), (113.95, -3.25)]
EVENT_BINS = [(-9, -6), (-5, -3), (-2, -1), (0, 2), (3, 5), (6, 9), (10, 21)]
COHORTS = (2004, 2018)            # arrival years with >= 3 pre and >= 3 post years
NEAR_KM, FAR_KM = 5.0, 10.0
NBOOT = 200


def _cell_lonlat(cells):
    import numpy as np
    import rasterio.transform
    from pyproj import CRS, Transformer
    g = json.load(open(os.path.join(DATA, "grid.json")))
    tr = rasterio.transform.Affine(*g["transform"])
    x, y = rasterio.transform.xy(tr, cells.r.to_numpy(), cells.c.to_numpy())
    t = Transformer.from_crs(CRS.from_wkt(g["crs"]), 4326, always_xy=True)
    lon, lat = t.transform(np.asarray(x), np.asarray(y))
    return lon, lat


def _event_study(tr_cells, T, ctrl_cells, P, strata, block, years, rng, ctrl_max=None, bins=None):
    """Stacked event study: for each arrival cohort T, burned / expected, where expected uses
    the never-near control cells' burn rate in the same stratum and calendar year.
    tr_cells / ctrl_cells: boolean over cells; T: arrival year per cell; P: panel (cell, year, burn)."""
    import numpy as np
    import pandas as pd
    bins = bins or EVENT_BINS
    d = P[P.year.isin(years)]
    tc = d[tr_cells[d.cell.to_numpy()]].copy()
    cc = d[ctrl_cells[d.cell.to_numpy()]].copy()
    if ctrl_max is not None:            # not-yet-treated controls: only their years before arrival
        cc = cc[cc.year.to_numpy() <= ctrl_max[cc.cell.to_numpy()]]
    tc["e"] = tc.year.to_numpy() - T[tc.cell.to_numpy()]
    tc["bin"] = -1
    for k, (lo, hi) in enumerate(bins):
        tc.loc[(tc.e >= lo) & (tc.e <= hi), "bin"] = k
    tc = tc[tc.bin >= 0]
    for f in (tc, cc):
        f["s"] = strata[f.cell.to_numpy()]
        f["blk"] = block[f.cell.to_numpy()]
    # control counts by (s, year, block); treated by (bin, s, year, block)
    ub, binv = np.unique(np.concatenate([tc.blk, cc.blk]), return_inverse=True)
    tc["bi"], cc["bi"] = binv[:len(tc)], binv[len(tc):]
    sy_c = cc.s.astype(np.int64) * 10000 + cc.year
    sy_t = tc.s.astype(np.int64) * 10000 + tc.year
    usy, inv = np.unique(np.concatenate([sy_c, sy_t]), return_inverse=True)
    ic, it = inv[:len(cc)], inv[len(cc):]
    has_ctrl = np.bincount(ic, minlength=len(usy)) >= 20        # stratum-years with >= 20 controls
    keep = has_ctrl[it]
    dropped = 1 - keep.mean() if len(keep) else np.nan
    tc, it = tc[keep], it[keep]
    nb = len(ub)

    def one(w):
        wc, wt = w[cc.bi.to_numpy()], w[tc.bi.to_numpy()]
        cn = np.bincount(ic, wc, len(usy))
        cb = np.bincount(ic, wc * cc.burn.to_numpy(), len(usy))
        rate = np.divide(cb, cn, out=np.zeros_like(cb), where=cn > 0)
        exp_ = wt * rate[it]
        b = tc.bin.to_numpy()
        obs = np.bincount(b, wt * tc.burn.to_numpy(), len(bins))
        ex = np.bincount(b, exp_, len(bins))
        n = np.bincount(b, wt, len(bins))
        return obs, ex, n

    obs, ex, n = one(np.ones(nb))
    boots = []
    for _ in range(NBOOT):
        o, e_, _n = one(rng.poisson(1.0, nb).astype(float))
        boots.append(np.divide(o, e_, out=np.full_like(o, np.nan), where=e_ > 0))
    boots = np.array(boots)
    rows = []
    for k, (lo, hi) in enumerate(bins):
        rows.append({"bin": f"{lo}..{hi}", "lo": lo, "cell_years": int(n[k]), "burned": int(obs[k]),
                     "expected": round(float(ex[k]), 1),
                     "ratio": round(float(obs[k] / ex[k]), 3) if ex[k] > 0 else None,
                     "ci_lo": round(float(np.nanpercentile(boots[:, k], 2.5)), 3),
                     "ci_hi": round(float(np.nanpercentile(boots[:, k], 97.5)), 3),
                     "burned_pct": round(float(100 * obs[k] / n[k]), 3) if n[k] else None,
                     "control_pct": round(float(100 * ex[k] / n[k]), 3) if n[k] else None})
    # post (0..9) over pre (-9..-3): the change once palm arrives, net of pre-existing difference
    pre, post = [0, 1], [4, 5]

    def did(o, e_):
        a, b = o[post].sum() / e_[post].sum(), o[pre].sum() / e_[pre].sum()
        return a / b
    bo = []
    for _ in range(NBOOT):
        o, e_, _n = one(rng.poisson(1.0, nb).astype(float))
        with np.errstate(divide="ignore", invalid="ignore"):
            bo.append(did(o, e_))
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = did(obs, ex)
    return pd.DataFrame(rows), {
        "did_ratio": round(float(dd), 3),
        "did_ci": [round(float(np.nanpercentile(bo, 2.5)), 3), round(float(np.nanpercentile(bo, 97.5)), 3)],
        "treated_cells": int(tr_cells.sum()), "control_cells": int(ctrl_cells.sum()),
        "treated_rows_dropped_no_control": round(float(dropped), 4)}


def _first_within(dk, km):
    import numpy as np
    yrs = np.array(dk.columns)
    near = dk.to_numpy() <= km
    return np.where(near.any(1), yrs[near.argmax(1)], 0)


def stage_robust(a):
    """Peat spillover under other definitions (EMRP masked): 0-2 km and 5-10 km arrival bands,
    not-yet-treated controls, and a long follow-up for the 2004-2010 cohorts."""
    import numpy as np
    import pandas as pd
    from shapely import contains_xy
    from shapely.geometry import Polygon
    rng = np.random.default_rng(2)
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    P = pd.read_parquet(os.path.join(DATA, "panel.parquet"), columns=["cell", "year", "burn", "d_ind", "ind"])
    lon, lat = _cell_lonlat(cells)
    emrp = contains_xy(Polygon(EMRP), lon, lat)
    tile = (np.floor(lon).astype(np.int32) - 100) * 100 + (np.floor(lat).astype(np.int32) + 10)
    dbin = np.where(cells.peat, 1 + np.digitize(cells.depth, [100, 200, 300]), 0)
    fbin = np.digitize(cells.und2000, [10, 50, 90])
    strata = (tile.astype(np.int64) * 100 + dbin * 10 + fbin).astype(np.int64)
    block = cells.block.to_numpy()
    n = len(cells)
    dk = P.pivot(index="cell", columns="year", values="d_ind").reindex(range(n))
    dmin = dk.to_numpy().min(1)
    T2, T5, T10 = (_first_within(dk, k) for k in (2.0, 5.0, 10.0))
    ind21 = P[P.year == 2021].set_index("cell").ind.reindex(range(n)).to_numpy()
    first_ind = cells.first_ind.to_numpy()
    dry = json.load(open(os.path.join(OUT, "describe.json")))["dry_years"]
    P = P[["cell", "year", "burn"]]
    coh = lambda t, lo=COHORTS[0], hi=COHORTS[1]: (t >= lo) & (t <= hi)     # noqa: E731
    long_bins = EVENT_BINS[:-1] + [(10, 15), (16, 21)]
    runs = {}
    for soil, sm in (("peat", cells.peat.to_numpy()), ("mineral", ~cells.peat.to_numpy())):
        base = sm & ~emrp & (first_ind == 0) & (ind21 < 10)
        never10 = base & (dmin > 10)
        never15 = base & (dmin > 15)
        specs = {
            "near_0_2km": (base & coh(T2), T2, never10, None, None),
            "near_5_10km": (base & coh(T10) & (dmin > 5), T10, never15, None, None),
            "not_yet_treated": (base & coh(T5, 2004, 2012), T5, base & coh(T5, 2016, 2021),
                                T5 - 3, None),
            "long_followup_2004_2010": (base & coh(T5, 2004, 2010), T5, never10, None, long_bins),
        }
        for name, (trm, T, ctrl, cmax, bins) in specs.items():
            for yset, ys in (("dry", dry), ("all", YEARS)):
                key = f"{name}_{soil}_{yset}"
                tab, s = _event_study(trm, T, ctrl, P, strata, block, ys, rng, ctrl_max=cmax, bins=bins)
                runs[key] = {"summary": s, "bins": tab.to_dict("records")}
                print(f"\n{key}: {s}")
                print(tab[["bin", "cell_years", "burned_pct", "control_pct", "ratio", "ci_lo", "ci_hi"]]
                      .to_string(index=False), flush=True)
    json.dump(runs, open(os.path.join(OUT, "event_robust.json"), "w"), indent=1)
    print("\nSaved:", os.path.join(OUT, "event_robust.json"))


def stage_event(a):
    import numpy as np
    import pandas as pd
    from shapely import contains_xy
    from shapely.geometry import Polygon
    rng = np.random.default_rng(1)
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    P = pd.read_parquet(os.path.join(DATA, "panel.parquet"), columns=["cell", "year", "burn", "d_ind", "ind"])
    lon, lat = _cell_lonlat(cells)
    emrp = contains_xy(Polygon(EMRP), lon, lat)
    tile = (np.floor(lon).astype(np.int32) - 100) * 100 + (np.floor(lat).astype(np.int32) + 10)
    dbin = np.where(cells.peat, 1 + np.digitize(cells.depth, [100, 200, 300]), 0)
    fbin = np.digitize(cells.und2000, [10, 50, 90])
    strata = (tile.astype(np.int64) * 100 + dbin * 10 + fbin).astype(np.int64)
    block = cells.block.to_numpy()
    n = len(cells)

    # arrival year: first year industrial palm is within NEAR_KM (cells' own palm excluded below)
    dk = P.pivot(index="cell", columns="year", values="d_ind").reindex(range(n))
    yrs = np.array(dk.columns)
    near = dk.to_numpy() <= NEAR_KM
    T5 = np.where(near.any(1), yrs[near.argmax(1)], 0)
    never_far = (dk.to_numpy() > FAR_KM).all(1)
    ind21 = P[P.year == 2021].set_index("cell").ind.reindex(range(n)).to_numpy()
    first_ind = cells.first_ind.to_numpy()
    peat = cells.peat.to_numpy()
    in_coh = lambda t: (t >= COHORTS[0]) & (t <= COHORTS[1])          # noqa: E731

    desc = json.load(open(os.path.join(OUT, "describe.json")))
    dry = desc["dry_years"]
    P = P[["cell", "year", "burn"]]
    runs = {}
    for soil, sm in (("peat", peat), ("mineral", ~peat)):
        for mask_emrp in (True, False):
            ok = sm & (~emrp if mask_emrp else True)
            ctrl = ok & never_far & (first_ind == 0)
            spill = ok & (first_ind == 0) & (ind21 < 10) & in_coh(T5)
            conv = ok & in_coh(first_ind)
            for kind, trm, T in (("spillover", spill, T5), ("conversion", conv, first_ind)):
                for yset, ys in (("dry", dry), ("all", YEARS)):
                    if not mask_emrp and (kind == "conversion" or yset == "all"):
                        continue
                    key = f"{kind}_{soil}_{yset}" + ("" if mask_emrp else "_with_emrp")
                    tab, s = _event_study(trm, T, ctrl, P, strata, block, ys, rng)
                    runs[key] = {"summary": s, "bins": tab.to_dict("records")}
                    print(f"\n{key}: {s}")
                    print(tab[["bin", "cell_years", "burned_pct", "control_pct", "ratio", "ci_lo", "ci_hi"]]
                          .to_string(index=False))
    runs["meta"] = {"dry_years": dry, "near_km": NEAR_KM, "control_far_km": FAR_KM, "cohorts": COHORTS,
                    "strata": "1 deg tile x peat depth bin x 2000 undisturbed-forest bin",
                    "did": "burned/expected in event years +3..+9 over -9..-3", "nboot": NBOOT,
                    "emrp_cells": int(emrp.sum())}
    json.dump(runs, open(os.path.join(OUT, "event_study.json"), "w"), indent=1)
    print("\nSaved:", os.path.join(OUT, "event_study.json"))


# -------------------------------------------------------------------- VIIRS
# Landscape classes for the fire-behaviour comparison (2012-2025), assigned per cell and year
# in this order (first match wins):
LANDSCAPES = {1: "industrial palm", 2: "clearing for industrial palm (planted within 3 yr)",
              3: "peat, outside permits", 4: "other land in permits (oil palm / HTI)",
              5: "rotational mosaic, mineral (swidden-like)", 6: "other mineral land"}
VIIRS_YEARS = list(range(2012, 2026))
EVENT_KM, EVENT_DAYS = 0.75, 2         # detections this close in space and time are one fire
MOSAIC_REG = 5                         # % TMF regrowth that marks a fallow rotation


def stage_viirs(a):
    """VIIRS 375 m detections grouped into fire events; per landscape class: how often fire
    occurs, how big events get, whether they reach undisturbed forest, whether they recur in the
    same cells, and how strongly they respond to drought."""
    import glob
    import numpy as np
    import pandas as pd
    import rasterio
    import rasterio.transform
    from pyproj import CRS, Transformer
    from sklearn.cluster import DBSCAN

    g = json.load(open(os.path.join(DATA, "grid.json")))
    tr, shape = rasterio.transform.Affine(*g["transform"]), tuple(g["shape"])
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    idx = np.full(shape, -1, np.int32)
    idx[cells.r, cells.c] = cells.cell
    with rasterio.open(os.path.join(DATA, "reg.tif")) as ds:
        reg = {d: ds.read(i + 1) for i, d in enumerate(ds.descriptions)}
    P = pd.read_parquet(os.path.join(DATA, "panel.parquet"),
                        columns=["cell", "year", "ind", "d_ind", "und", "deg"])
    P = P[P.year >= VIIRS_YEARS[0]]
    rr, cc_ = cells.r.to_numpy(), cells.c.to_numpy()
    P["reg"] = np.concatenate([reg[f"reg_{min(y, 2024)}"][rr, cc_] for y in sorted(P.year.unique())])
    peat, perm = cells.peat.to_numpy(), (cells.conc | cells.hti).to_numpy()
    fi = cells.first_ind.to_numpy()
    c, y = P.cell.to_numpy(), P.year.to_numpy()
    cls = np.full(len(P), 6, np.uint8)
    mosaic = (~peat[c]) & (~perm[c]) & (P.d_ind.to_numpy() > NEAR_KM) & (P.und.to_numpy() < 70) \
        & (P.reg.to_numpy() >= MOSAIC_REG)
    for k, m in ((5, mosaic), (4, perm[c]), (3, peat[c] & ~perm[c]),
                 (2, (fi[c] >= y) & (fi[c] <= y + 3) & (P.ind.to_numpy() < PALM_MIN)),
                 (1, P.ind.to_numpy() >= PALM_MIN)):
        cls[m] = k                                   # reverse order: higher priority overwrites
    P["cls"] = cls
    lookup = P.set_index(["cell", "year"])

    # detections
    t = Transformer.from_crs(4326, CRS.from_wkt(g["crs"]), always_xy=True)
    frames = []
    for f in sorted(glob.glob(os.path.join(DATA, "viirs", "viirs-snpp_*_Indonesia.csv"))):
        v = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "confidence", "frp", "type"])
        v = v[(v.longitude.between(KAL[0], KAL[2])) & (v.latitude.between(KAL[1], KAL[3]))
              & (v.type == 0) & (v.confidence != "l")]
        x, yy = t.transform(v.longitude.to_numpy(), v.latitude.to_numpy())
        r, cl = rasterio.transform.rowcol(tr, x, yy)
        r, cl = np.asarray(r), np.asarray(cl)
        ok = (r >= 0) & (r < shape[0]) & (cl >= 0) & (cl < shape[1])
        v, x, yy, r, cl = v[ok], x[ok], yy[ok], r[ok], cl[ok]
        v = v.assign(x=x / 1000, y=yy / 1000, cell=idx[r, cl])
        frames.append(v[v.cell >= 0])
    V = pd.concat(frames, ignore_index=True)
    V["date"] = pd.to_datetime(V.acq_date)
    V["year"] = V.date.dt.year
    V = V[V.year.isin(VIIRS_YEARS)]
    V["doy"] = (V.date - pd.Timestamp("2012-01-01")).dt.days
    j = lookup.reindex(pd.MultiIndex.from_arrays([V.cell, V.year]))
    V["cls"], V["und"] = j.cls.to_numpy(), j.und.to_numpy()
    print(f"{len(V):,} detections on Kalimantan land, {V.year.min()}-{V.year.max()}")

    # events: connected detections within EVENT_KM and EVENT_DAYS (time scaled into km)
    V["event"] = -1
    nxt = 0
    for yr, grp in V.groupby("year"):
        X = np.c_[grp.x, grp.y, grp.doy * (EVENT_KM / EVENT_DAYS)]
        lab = DBSCAN(eps=EVENT_KM, min_samples=1, n_jobs=-1).fit_predict(X)
        V.loc[grp.index, "event"] = lab + nxt
        nxt += lab.max() + 1
    V = V.sort_values(["event", "date"])
    first = V.groupby("event").first()
    E = V.groupby("event").agg(n=("cell", "size"), cells=("cell", "nunique"), year=("year", "first"),
                               days=("doy", lambda s: s.max() - s.min() + 1),
                               und_max=("und", "max"), frp=("frp", "sum"))
    E["cls"] = first.cls                              # where the fire started
    E["start_und"] = first.und
    E["month"] = first.date.dt.month
    E["escaped"] = (E.start_und < 50) & (E.und_max >= 90)     # started outside forest, reached intact forest
    E["large"] = E.cells >= 10                                # >= ~215 ha of 500 m cells touched
    dry = [yy for yy in json.load(open(os.path.join(OUT, "describe.json")))["dry_years"] if yy >= 2012]
    E["dry"] = E.year.isin(dry)

    # area of each class per year (km2) for densities
    area = (P.groupby(["cls", "year"]).size() * CELL_KM ** 2).rename("km2")
    # recurrence: fire cells (cell-years with a detection) that also burned in any of the 3 previous years
    fc = V[["cell", "year"]].drop_duplicates()
    fc["cls"] = lookup.reindex(pd.MultiIndex.from_arrays([fc.cell, fc.year])).cls.to_numpy()
    prev = set(zip(fc.cell, fc.year))
    fc["repeat3"] = [any((ce, yr - k) in prev for k in (1, 2, 3)) for ce, yr in zip(fc.cell, fc.year)]
    fc = fc[fc.year >= VIIRS_YEARS[0] + 3]

    rows = []
    for k, name in LANDSCAPES.items():
        e = E[E.cls == k]
        a_ = area.xs(k, level="cls") if k in area.index.get_level_values(0) else pd.Series(dtype=float)
        det = V[V.cls == k].groupby("year").size().reindex(VIIRS_YEARS, fill_value=0)
        dens = det / a_.reindex(VIIRS_YEARS) * 100                     # detections per 100 km2
        wet = [yy for yy in VIIRS_YEARS if yy not in dry]
        f_ = fc[fc.cls == k]
        rows.append({
            "class": k, "landscape": name, "km2_mean": round(float(a_.mean()), 0),
            "detections": int(det.sum()), "events": int(len(e)),
            "det_per_100km2_wet_yr": round(float(dens[wet].median()), 2),
            "det_per_100km2_dry_yr": round(float(dens[dry].mean()), 2),
            "dry_over_wet": round(float(dens[dry].mean() / dens[wet].median()), 1) if dens[wet].median() > 0 else None,
            "event_median_det": float(e.n.median()), "event_p90_det": float(e.n.quantile(0.9)),
            "large_pct": round(100 * float(e.large.mean()), 2),
            "large_pct_dry": round(100 * float(e[e.dry].large.mean()), 2),
            "large_pct_wet": round(100 * float(e[~e.dry].large.mean()), 2),
            "escaped_pct": round(100 * float(e.escaped.mean()), 2),
            "share_of_det_in_large_events_pct": round(100 * float(e[e.large].n.sum() / max(e.n.sum(), 1)), 1),
            "repeat_within_3yr_pct": round(100 * float(f_.repeat3.mean()), 1),
            "peak_month": int(e.month.mode().iloc[0]) if len(e) else None,
        })
    out = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    out.to_csv(os.path.join(OUT, "viirs_landscapes.csv"), index=False)
    E.to_parquet(os.path.join(DATA, "viirs_events.parquet"))
    json.dump({"dry_years": dry, "event_rule": f"{EVENT_KM} km and {EVENT_DAYS} days (DBSCAN, min 1)",
               "large": ">= 10 MODIS cells touched", "escaped": "start in cell <50% undisturbed forest, "
               "reach a cell >= 90%", "mosaic": f"mineral, outside permits, > {NEAR_KM} km from industrial "
               f"palm, < 70% undisturbed forest, >= {MOSAIC_REG}% TMF regrowth",
               "landscapes": LANDSCAPES, "detections": int(len(V)), "events": int(len(E))},
              open(os.path.join(OUT, "viirs_meta.json"), "w"), indent=1)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(out.drop(columns=["landscape"]).to_string(index=False))
    for k, name in LANDSCAPES.items():
        print(k, name)


# --------------------------------------------------------------- 1990s
def stage_nineties(a):
    """Landsat 5 burn scars for 1991, 1994 and 1997 by peat and distance to industrial palm
    (palm planted by that year), after checking the Landsat rule against MCD64A1 in 2006."""
    import numpy as np
    import pandas as pd
    import rasterio
    from scipy import ndimage
    from shapely import contains_xy
    from shapely.geometry import Polygon
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    rr, cc_ = cells.r.to_numpy(), cells.c.to_numpy()

    def rd(part):
        with rasterio.open(os.path.join(DATA, f"{part}.tif")) as ds:
            return {d: ds.read(i + 1) for i, d in enumerate(ds.descriptions)}
    L = {}
    for y in L5_YEARS:
        L |= rd(f"l5burn_{y}")
    N, B = rd("nineties"), rd("burn")
    lon, lat = _cell_lonlat(cells)
    emrp = contains_xy(Polygon(EMRP), lon, lat)
    peat = cells.peat.to_numpy()
    res = {}

    # calibration, 2006: Landsat cell burned = >= 50% of its valid 30 m pixels burned
    ok = L["lok_2006"][rr, cc_] >= 50
    lb = (L["lb_2006"][rr, cc_] * 2 >= L["lok_2006"][rr, cc_]) & ok
    mb = B["burn_2006"][rr, cc_] == 1
    tp = int((lb & mb & ok).sum())
    res["calibration_2006"] = {
        "valid_cells_pct": round(100 * float(ok.mean()), 1),
        "landsat_burned_cells": int(lb.sum()), "mcd64_burned_cells_in_valid": int((mb & ok).sum()),
        "agree_cells": tp, "precision_vs_mcd64": round(tp / max(int(lb.sum()), 1), 3),
        "recall_vs_mcd64": round(tp / max(int((mb & ok).sum()), 1), 3),
        "landsat_burned_pct_peat": round(100 * float(lb[ok & peat].mean()), 2),
        "mcd64_burned_pct_peat": round(100 * float(mb[ok & peat].mean()), 2),
        "landsat_burned_pct_mineral": round(100 * float(lb[ok & ~peat].mean()), 2),
        "mcd64_burned_pct_mineral": round(100 * float(mb[ok & ~peat].mean()), 2)}
    print("2006 calibration:", res["calibration_2006"])

    rows = []
    for y in L5_YEARS:
        ok = L[f"lok_{y}"][rr, cc_] >= 50
        lb = (L[f"lb_{y}"][rr, cc_] * 2 >= L[f"lok_{y}"][rr, cc_]) & ok
        ip = N[f"ind_{y}"] >= PALM_MIN
        d = (ndimage.distance_transform_edt(~ip) * CELL_KM)[rr, cc_] if ip.any() else np.full(len(cells), 1e9)
        ring = pd.cut(d, [-0.1, 0.01] + RINGS_KM[1:] + [1e9],
                      labels=["in palm", "0-1 km", "1-2 km", "2-5 km", "5-10 km", ">10 km"])
        und = N[f"und_{y}"][rr, cc_]
        df = pd.DataFrame({"peat": peat, "emrp": emrp, "ring": ring, "ok": ok, "lb": lb,
                           "forest": np.where(und >= 90, "intact", np.where(und >= 30, "partial", "open"))})
        df = df[df.ok & ~df.emrp]
        for keys in (["peat"], ["peat", "ring"], ["peat", "forest"]):
            g = df.groupby(keys, observed=True).agg(cells=("lb", "size"), burned_pct=("lb", "mean"))
            g["burned_pct"] *= 100
            for idx_, r_ in g.reset_index().iterrows():
                rows.append({"year": y, "by": "+".join(keys), **{k: r_[k] for k in keys},
                             "cells": int(r_.cells), "burned_pct": round(float(r_.burned_pct), 2)})
        res[f"valid_cells_pct_{y}"] = round(100 * float(ok.mean()), 1)
        res[f"palm_cells_{y}"] = int(ip.sum())
        ek = (L[f"lok_{y}"][rr, cc_] >= 50) & emrp
        res[f"emrp_burned_pct_{y}"] = round(100 * float(lb[ek].mean()), 2) if ek.any() else None
    out = pd.DataFrame(rows)
    out["peat"] = out.peat.map({True: "peat", False: "mineral"})
    out.to_csv(os.path.join(OUT, "nineties_burn.csv"), index=False)
    json.dump(res, open(os.path.join(OUT, "nineties.json"), "w"), indent=1)
    pd.set_option("display.width", 200)
    for by in ("peat", "peat+ring", "peat+forest"):
        t = out[out.by == by]
        cols = [c for c in ("peat", "ring", "forest") if c in by.split("+")]
        print(f"\n-- by {by}\n", t.pivot_table(index=cols, columns="year", values="burned_pct",
                                                observed=True).round(2))
    print(json.dumps({k: v for k, v in res.items() if k != "calibration_2006"}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", required=True, choices=["export", "download", "panel", "describe", "event", "robust", "viirs", "nineties"])
    ap.add_argument("--parts", default="", help="export/download only: comma list, e.g. reg,nineties,l5burn")
    a = ap.parse_args()
    {"export": stage_export, "download": stage_download, "panel": stage_panel,
     "describe": stage_describe, "event": stage_event, "robust": stage_robust,
     "viirs": stage_viirs, "nineties": stage_nineties}[a.stage](a)


if __name__ == "__main__":
    main()
