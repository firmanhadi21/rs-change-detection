#!/usr/bin/env python3
"""WP6 context for the Kalimantan concession effect: the Indonesia-Malaysia border, and fire weather.

BORDER (B). Every 200 m cell of the stack within 20 km of the Indonesia-Malaysia land border on
Borneo (Natural Earth 1:10m; Brunei left out), with S2 burned as in kalimantan_excess_burn.py.
Peat is the Greifswald Global Peatland Map 2.0 on both sides (BBSDLP stops at the border); other
strata as in the main match (PEATGRIDS depth bin, land cover, burn history, distance to water and
settlement). Malaysian tenure: GFW gfw_oil_palm v2025 (iso3 MYS).
  B1 border effect, unpermitted land only: Indonesia vs Malaysia within 5 / 10 / 20 km, matched
     within 1 km distance-to-border bins (a discrete regression discontinuity).
  B2 concession effect on each side within 20 km, and across all Malaysian cells on the grid
     (the grid stops at 4.5 N, so northern Sabah is not covered).
  B3 burned share by signed distance (1 km bins), unpermitted land, for the figure.

FIRE WEATHER (W). Drought Code (Van Wagner 1987, equatorial Lf 1.4, as ketapang_fire_danger.py)
run day by day on the ERA5-Land 0.1 deg grid from 2 m temperature at 05 UTC (local noon) and the
24 h rain ending then, 1 Nov 2025 - 31 Oct 2026 (the wet season resets DC before July).
  W1 matched concession ratio within bands of the cell's peak Jul-Oct DC.
  W2 DC on the first-fire day (VIIRS, Jun-Oct), concession vs matched unpermitted burned cells:
     do concessions start burning at lower drought?
  W3 ignitions (lineage roots, Jul-Oct) per 1,000 km2-day against that day's DC, by tenure.

    python scripts/kalimantan_border_weather.py --stage myconc   # GFW data API
    python scripts/kalimantan_border_weather.py --stage dem      # Earth Engine: SRTM elevation, slope
    python scripts/kalimantan_border_weather.py --stage border
    python scripts/kalimantan_border_weather.py --stage mydata   # Earth Engine: stack, GPM, DEM over Malaysian Borneo
    python scripts/kalimantan_border_weather.py --stage national # after era5 + dc
    python scripts/kalimantan_border_weather.py --stage era5     # Earth Engine, ~30 MB
    python scripts/kalimantan_border_weather.py --stage weather
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import (BANDS, BLOCK_KM, CONC, DATA, HTI, KAL, NBOOT, NEAR_BURN_M,  # noqa: E402
                                    OUT, SEQ, STACK, STEP, matched)

from kalimantan_robustness import GPM  # noqa: E402  (Greifswald GPM 2.0 asset)

MYCONC = os.path.join(DATA, "gfw_oil_palm_2025_malaysia_borneo.gpkg")
EXTRA = os.path.join(DATA, "robust_200m.tif")          # kalimantan_robustness.py: b2023, b2026, gpm
ERA5_DIR = os.path.join(DATA, "era5_dc")
DC_NPY = os.path.join(DATA, "dc_2026.npz")
RES_B = os.path.join(OUT, "border.json")
RES_W = os.path.join(OUT, "fire_weather.json")
PX_KM = STEP * 111.32
BANDS_KM = (5, 10, 20)
E5 = (108.45, 4.55, 0.1, 109, 90)                      # ERA5-Land grid: x0, y_top, step, nx, ny
D0, D1 = "2025-01-01", "2026-11-01"     # spin-up from Jan 2025: the 2025-26 wet season does not reset DC fully
NOON_UTC = 5
DC_BANDS = (0, 300, 400, 500, 600, 700, 2000)
GPM_KEYS = ["gpm", "depth_bin_gpm", "lc", "hist", "water_bin", "settle_bin"]
TERRAIN = ["elev_bin", "slope_bin"]
ELEV_BINS = (50, 100, 200, 400, 700)                   # m
SLOPE_BINS = (2, 5, 10, 20)                            # deg
DEM = os.path.join(DATA, "dem_200m.tif")
MY_STACK = os.path.join(DATA, "stack_my_200m.tif")
MY_GPM = os.path.join(DATA, "gpm_my_200m.tif")
MY_DEM = os.path.join(DATA, "dem_my_200m.tif")
RES_N = os.path.join(OUT, "national.json")


def boot(blocks):
    import numpy as np
    import pandas as pd
    u = np.unique(blocks)
    w = np.random.default_rng(42).multinomial(len(u), np.ones(len(u)) / len(u), size=NBOOT).astype(float)
    return w, pd.Series(np.arange(len(u)), index=u)


def est(d, treat, keys, val, label, rows, **extra):
    import numpy as np
    w, bidx = boot(d.block.to_numpy())
    pt, pc, cov, bs = matched(d, treat, keys, val, w, bidx)
    q = bs[:, 0] / np.where(bs[:, 1] > 0, bs[:, 1], np.nan)
    lo, hi = np.nanpercentile(q, [2.5, 97.5])
    rows.append({"label": label, "treated_pct": 100 * pt, "control_pct": 100 * pc, "ratio": pt / pc,
                 "ci": [float(lo), float(hi)], "coverage": float(cov), "n_treated": int(treat.sum()),
                 "n_control": int((~treat).sum()), **extra})
    print(f"  {label:<52}{100 * pt:6.2f}% vs {100 * pc:6.2f}%  x{pt / pc:.2f} [{lo:.2f}, {hi:.2f}]"
          f"  cov {100 * cov:.0f}%  n {int(treat.sum()):,}/{int((~treat).sum()):,}", flush=True)


# ------------------------------------------------------------------ border
def stage_myconc():
    import geopandas as gpd
    import requests
    import shapely
    from shapely.geometry import shape
    from kalimantan_heterogeneity import gfw_key
    x0, y0, x1, y1 = KAL
    sql = ("SELECT conc_name, company, comp_group, conc_type, conc_stat, source, source_yr, "
           "ST_AsGeoJSON(geom) AS gj FROM data WHERE iso3 = 'MYS' AND "
           f"ST_Intersects(geom, ST_MakeEnvelope({x0}, {y0}, {x1}, {y1}, 4326))")
    r = requests.get("https://data-api.globalforestwatch.org/dataset/gfw_oil_palm/v2025/query/json",
                     headers={"x-api-key": gfw_key()}, params={"sql": sql}, timeout=900)
    r.raise_for_status()
    rows = r.json()["data"]
    for x in rows:
        x["geometry"] = shapely.force_2d(shape(json.loads(x.pop("gj"))))
    g = gpd.GeoDataFrame(rows, crs=4326)
    g.to_file(MYCONC)
    print(f"Saved: {MYCONC} ({len(g)} polygons, {g.to_crs(6933).area.sum() / 1e6:,.0f} km2)")
    for c in ("source", "source_yr", "conc_type", "conc_stat"):
        print(g[c].value_counts().head(6).to_string())


def dem_image():
    import ee
    grid = ee.Projection("EPSG:4326", [STEP, 0, 0, 0, -STEP, 0])
    dem = ee.Image("USGS/SRTMGL1_003")
    slope = ee.Terrain.slope(dem).multiply(10)
    return (dem.rename("elev").addBands(slope.rename("slope")).setDefaultProjection(dem.projection())
            .reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(grid).round().toInt16())


def gpm_image():
    import ee
    grid = ee.Projection("EPSG:4326", [STEP, 0, 0, 0, -STEP, 0])
    return ee.Image(GPM).gte(1).unmask(0).reproject(grid).rename("gpm").toInt16()


def _write(arr, tr, path, names):
    import rasterio
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype="int16",
                crs="EPSG:4326", transform=tr, compress="deflate", tiled=True)
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(arr.astype("int16"))
        ds.descriptions = tuple(names)
    print(f"Saved: {path} {arr.shape}")


def stage_dem():
    """Elevation (m) and slope (0.1 deg) on the 200 m grid; the border follows the watershed."""
    from earthchange.gee_utils import initialize_ee
    from kalimantan_excess_burn import direct_download
    initialize_ee()
    arr, tr = direct_download(dem_image(), os.path.join(DATA, "dem_tiles"))
    _write(arr, tr, DEM, ("elev", "slope"))


def stage_mydata():
    """The stack, GPM peat and terrain over Malaysian Borneo (the IDN-only download skipped most of it).
    Separate files: re-merging the main stack's tiles would undo its land-cover fix (lcfix)."""
    from earthchange.gee_utils import initialize_ee
    from kalimantan_excess_burn import direct_download, stack_image
    initialize_ee()
    for img, tdir, path, names in ((stack_image(), "stack_tiles_my", MY_STACK, BANDS),
                                   (gpm_image(), "gpm_tiles_my", MY_GPM, ("gpm",)),
                                   (dem_image(), "dem_tiles_my", MY_DEM, ("elev", "slope"))):
        if os.path.exists(path):
            print(f"exists: {path}")
            continue
        arr, tr = direct_download(img, os.path.join(DATA, tdir), countries=("MYS",))
        _write(arr, tr, path, names)


def grid_table():
    """Cells within 20 km of the border on both sides, with outcome, strata, tenure."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from scipy import ndimage
    with rasterio.open(STACK) as ds:
        S = {b: ds.read(i + 1) for i, b in enumerate(BANDS)}
        tr, shape = ds.transform, (ds.height, ds.width)
    with rasterio.open(EXTRA) as ds:
        gpm = ds.read(3) > 0
    with rasterio.open(DEM) as ds:
        elev, slope = ds.read(1), ds.read(2) / 10.0
    ne = gpd.read_file(os.path.join(DATA, "ne_countries", "ne_10m_admin_0_countries.zip"))
    ras = lambda gs: features.rasterize([(g, 1) for g in gs if g is not None], out_shape=shape,  # noqa: E731
                                        transform=tr, dtype="uint8") > 0
    my, idn = ras(ne[ne.ADM0_A3 == "MYS"].geometry), ras(ne[ne.ADM0_A3 == "IDN"].geometry)
    land = (S["land"] >= 50) & (S["lc"] != 255)
    d_my = ndimage.distance_transform_edt(~my) * PX_KM
    d_idn = ndimage.distance_transform_edt(~idn) * PX_KM
    band = land & ((idn & (S["kal"] == 1) & (d_my <= max(BANDS_KM))) | (my & (d_idn <= max(BANDS_KM))))
    allmy = land & my
    keep = band | allmy

    # burned exactly as stage_sample: valid S2 pair, half the cell, VIIRS within ~750 m
    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"), columns=["lon", "lat", "acq_epoch"])
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy()))
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    seen = np.zeros(shape, bool)
    seen[rr[ok], cc[ok]] = True
    near = ndimage.binary_dilation(seen, np.ones((3, 3), bool), iterations=int(np.ceil(NEAR_BURN_M / 200)) - 1)
    valid = S["okfrac"] >= 50
    burned = valid & (S["bfrac"] * 2 >= S["okfrac"]) & near
    d_water = ndimage.distance_transform_edt(S["land"] >= 50) * PX_KM
    d_settle = ndimage.distance_transform_edt(S["built"] < 5) * PX_KM

    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]]
    conc_idn = ras(op.geometry.make_valid()) | ras(gpd.read_file(HTI).to_crs(4326).geometry.make_valid())
    conc_my = ras(gpd.read_file(MYCONC).geometry.make_valid())

    yy, xx = np.nonzero(keep)
    df = pd.DataFrame({
        "side": np.where(idn[yy, xx], "IDN", "MYS"),
        "dist": np.where(idn[yy, xx], d_my[yy, xx], d_idn[yy, xx]).astype(np.float32),
        "in_band": band[yy, xx], "valid": valid[yy, xx], "burned": burned[yy, xx],
        "conc": np.where(idn[yy, xx], conc_idn[yy, xx], conc_my[yy, xx]),
        "gpm": gpm[yy, xx], "thick": S["depth"][yy, xx], "lc": S["lc"][yy, xx].astype(np.uint8),
        "hist": S["hist"][yy, xx].astype(np.uint8),
        "water_bin": np.digitize(d_water[yy, xx], [1, 3, 10]).astype(np.uint8),
        "settle_bin": np.digitize(d_settle[yy, xx], [1, 3, 10]).astype(np.uint8),
        "block": ((yy * PX_KM // BLOCK_KM).astype(np.int32) * 10000 + (xx * PX_KM // BLOCK_KM).astype(np.int32)),
    })
    df["elev_bin"] = np.digitize(elev[yy, xx], ELEV_BINS).astype(np.uint8)
    df["slope_bin"] = np.digitize(slope[yy, xx], SLOPE_BINS).astype(np.uint8)
    df["depth_bin_gpm"] = np.where(df.gpm, np.digitize(df.thick, [1, 100, 200, 300]), 9).astype(np.uint8)
    df["dist_bin"] = np.minimum(df.dist // 1, 19).astype(np.uint8)
    return df[df.valid].reset_index(drop=True)


def stage_border():
    import numpy as np
    import pandas as pd
    df = grid_table()
    rows = []
    print(f"border table: {len(df):,} valid cells "
          f"(IDN band {int(((df.side == 'IDN') & df.in_band).sum()):,}, MYS {int((df.side == 'MYS').sum()):,})")
    print("B1 border effect, unpermitted land, Indonesia vs Malaysia (matched within 1 km distance bins)")
    for b in BANDS_KM:
        d = df[df.in_band & ~df.conc & (df.dist <= b)].reset_index(drop=True)
        est(d, (d.side == "IDN").to_numpy(), GPM_KEYS + ["dist_bin"], d.burned.to_numpy(float),
            f"IDN vs MYS unpermitted, <= {b} km", rows, check="B1", band_km=b)
        est(d, (d.side == "IDN").to_numpy(), GPM_KEYS + ["dist_bin"] + TERRAIN, d.burned.to_numpy(float),
            f"  + elevation and slope, <= {b} km", rows, check="B1", band_km=b, terrain=True)
        if b == max(BANDS_KM):
            est(d, (d.side == "IDN").to_numpy(), [], d.burned.to_numpy(float),
                f"  (raw, <= {b} km)", rows, check="B1", band_km=b, raw=True)
    print("B2 concession vs unpermitted, each side (GPM strata)")
    for side in ("IDN", "MYS"):
        d = df[df.in_band & (df.side == side)].reset_index(drop=True)
        est(d, d.conc.to_numpy(), GPM_KEYS + TERRAIN, d.burned.to_numpy(float), f"{side} concession, <= 20 km",
            rows, check="B2", side=side)
    d = df[df.side == "MYS"].reset_index(drop=True)
    est(d, d.conc.to_numpy(), GPM_KEYS + TERRAIN, d.burned.to_numpy(float), "MYS concession, all cells on grid",
        rows, check="B2", side="MYS", scope="all")
    print("terrain balance within 20 km, unpermitted: median elevation / slope")
    d = df[df.in_band & ~df.conc]
    print(d.groupby("side").agg(cells=("burned", "size"), elev_bin=("elev_bin", "mean"),
                                slope_bin=("slope_bin", "mean"), peat=("gpm", "mean")).round(2).to_string())
    print("B3 burned share by signed distance, unpermitted land")
    d = df[df.in_band & ~df.conc].copy()
    d["signed_km"] = np.where(d.side == "IDN", -1, 1) * (d.dist // 1 + 0.5)
    curve = d.groupby("signed_km").agg(cells=("burned", "size"), burned_pct=("burned", "mean"))
    curve["burned_pct"] *= 100
    print(curve.round(2).to_string())
    curve.to_csv(os.path.join(OUT, "border_curve.csv"))
    json.dump(rows, open(RES_B, "w"), indent=1, default=float)
    print(f"Saved: {RES_B}, border_curve.csv")


def stage_national():
    """Indonesian Kalimantan vs Malaysian Borneo, all land on the grid, matched on peat (GPM), depth,
    land cover, burn history, access, terrain AND peak Jul-Oct Drought Code band."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from scipy import ndimage
    rd = lambda p: rasterio.open(p).read()                                    # noqa: E731
    with rasterio.open(STACK) as ds:
        tr, shape = ds.transform, (ds.height, ds.width)
    S, SM = rd(STACK), rd(MY_STACK)
    have = S[BANDS.index("land")] > 0                                         # IDN-tile coverage
    C = {b: np.where(have, S[i], SM[i]) for i, b in enumerate(BANDS)}
    del S, SM
    gpm = np.where(have, rd(EXTRA)[2], rd(MY_GPM)[0]) > 0
    dI, dM = rd(DEM), rd(MY_DEM)
    elev, slope = np.where(have, dI[0], dM[0]), np.where(have, dI[1], dM[1]) / 10.0
    del dI, dM
    ne = gpd.read_file(os.path.join(DATA, "ne_countries", "ne_10m_admin_0_countries.zip"))
    ras = lambda gs: features.rasterize([(g, 1) for g in gs if g is not None], out_shape=shape,  # noqa: E731
                                        transform=tr, dtype="uint8") > 0
    my, idn = ras(ne[ne.ADM0_A3 == "MYS"].geometry), ras(ne[ne.ADM0_A3 == "IDN"].geometry)
    land = (C["land"] >= 50) & (C["lc"] != 255)
    keep = land & ((idn & (C["kal"] == 1)) | my)

    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"), columns=["lon", "lat"])
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy()))
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    seen = np.zeros(shape, bool)
    seen[rr[ok], cc[ok]] = True
    near = ndimage.binary_dilation(seen, np.ones((3, 3), bool), iterations=int(np.ceil(NEAR_BURN_M / 200)) - 1)
    valid = C["okfrac"] >= 50
    burned = valid & (C["bfrac"] * 2 >= C["okfrac"]) & near
    d_water = ndimage.distance_transform_edt(C["land"] >= 50) * PX_KM
    d_settle = ndimage.distance_transform_edt(C["built"] < 5) * PX_KM
    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]]
    conc = (ras(op.geometry.make_valid()) | ras(gpd.read_file(HTI).to_crs(4326).geometry.make_valid())) & idn
    conc |= ras(gpd.read_file(MYCONC).geometry.make_valid()) & my

    z = np.load(DC_NPY, allow_pickle=True)
    dc, dates = z["dc"], pd.to_datetime(z["dates"])
    x0, yt, st = z["grid"]
    peak = dc[(dates >= "2026-07-01") & (dates < "2026-11-01")].max(axis=0)
    yy, xx = np.nonzero(keep & valid)
    lon, lat = tr.c + (xx + 0.5) * STEP, tr.f - (yy + 0.5) * STEP
    ey = np.clip(((yt - lat) / st).astype(int), 0, peak.shape[0] - 1)
    ex = np.clip(((lon - x0) / st).astype(int), 0, peak.shape[1] - 1)
    df = pd.DataFrame({
        "idn": idn[yy, xx], "conc": conc[yy, xx], "burned": burned[yy, xx], "gpm": gpm[yy, xx],
        "thick": C["depth"][yy, xx], "lc": C["lc"][yy, xx].astype(np.uint8), "hist": C["hist"][yy, xx].astype(np.uint8),
        "water_bin": np.digitize(d_water[yy, xx], [1, 3, 10]).astype(np.uint8),
        "settle_bin": np.digitize(d_settle[yy, xx], [1, 3, 10]).astype(np.uint8),
        "elev_bin": np.digitize(elev[yy, xx], ELEV_BINS).astype(np.uint8),
        "slope_bin": np.digitize(slope[yy, xx], SLOPE_BINS).astype(np.uint8),
        "dc_peak": peak[ey, ex].astype(np.float32),
        "block": ((yy * PX_KM // BLOCK_KM).astype(np.int32) * 10000 + (xx * PX_KM // BLOCK_KM).astype(np.int32)),
    })
    del C
    df["depth_bin_gpm"] = np.where(df.gpm, np.digitize(df.thick, [1, 100, 200, 300]), 9).astype(np.uint8)
    df["dc_bin"] = np.digitize(df.dc_peak, DC_BANDS[1:-1]).astype(np.uint8)
    keys = GPM_KEYS + TERRAIN + ["dc_bin"]
    rows = []
    print(f"valid land cells: IDN {int(df.idn.sum()):,}, MYS {int((~df.idn).sum()):,} "
          f"(MYS peat {int((~df.idn & df.gpm).sum()):,})")
    print("burned share by side, peat and peak-DC band (raw):")
    t = df.groupby(["idn", "gpm", "dc_bin"]).burned.agg(["size", "mean"]).unstack("idn")
    t.columns = [f"{a}_{'IDN' if b else 'MYS'}" for a, b in t.columns]
    t = t.rename(index={k: f"{lo}-{hi}" for k, (lo, hi) in enumerate(zip(DC_BANDS[:-1], DC_BANDS[1:]))}, level="dc_bin")
    for c in t.columns:
        if c.startswith("mean"):
            t[c] = (100 * t[c]).round(3)
    print(t.to_string())
    print("N national comparison, Indonesia vs Malaysia (treated = Indonesian cells)")
    w = df.burned.to_numpy(float)
    est(df, df.idn.to_numpy(), [], w, "all land, raw", rows, check="N")
    est(df, df.idn.to_numpy(), keys, w, "all land, all strata + terrain + DC band", rows, check="N")
    for name, m in (("unpermitted land", ~df.conc), ("concessions", df.conc), ("peat (GPM)", df.gpm),
                    ("peat, unpermitted", df.gpm & ~df.conc), ("not peat", ~df.gpm)):
        d = df[m.to_numpy()].reset_index(drop=True)
        est(d, d.idn.to_numpy(), keys, d.burned.to_numpy(float), f"{name}, all strata", rows, check="N", subset=name)
    for k, (lo, hi) in enumerate(zip(DC_BANDS[:-1], DC_BANDS[1:])):
        d = df[df.dc_bin == k].reset_index(drop=True)
        if (~d.idn).sum() >= 5000 and d.idn.sum() >= 5000:
            est(d, d.idn.to_numpy(), keys, d.burned.to_numpy(float), f"peak DC {lo}-{hi}", rows, check="N", dc_band=[lo, hi])
        else:
            print(f"  peak DC {lo}-{hi}: too few cells (IDN {int(d.idn.sum()):,}, MYS {int((~d.idn).sum()):,})")
    json.dump(rows, open(RES_N, "w"), indent=1, default=float)
    print(f"Saved: {RES_N}")


# ------------------------------------------------------------- fire weather
def stage_era5():
    import glob
    import ee
    import rasterio
    from earthchange.gee_utils import download_geotiff, initialize_ee
    initialize_ee()
    os.makedirs(ERA5_DIR, exist_ok=True)
    x0, yt, st, nx, ny = E5
    reg = ee.Geometry.Rectangle([x0, yt - ny * st, x0 + nx * st, yt], None, False)
    import pandas as pd
    ic = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
    have = set(pd.to_datetime(ic.filterDate("2026-09-01", D1).aggregate_array("system:time_start").getInfo(),
                              unit="ms"))
    last_noon = (max(have) - pd.Timedelta(hours=NOON_UTC)).normalize()
    while not all(last_noon + pd.Timedelta(hours=NOON_UTC - h) in have for h in range(24)):
        last_noon -= pd.Timedelta(days=1)       # the newest days are published hour by hour, with gaps
    print(f"ERA5-Land hourly to {max(have):%Y-%m-%d %H:%M} UTC -> last complete day {last_noon:%Y-%m-%d}")
    months = pd.date_range(D0, D1, freq="MS")
    for a, b in zip(months[:-1], months[1:]):
        b = min(b, last_noon + pd.Timedelta(days=1))
        if b <= a:
            break
        partial = b < a + pd.offsets.MonthBegin(1)
        p = os.path.join(ERA5_DIR, f"era5_{a:%Y-%m}{'_partial' if partial else ''}.tif")
        if os.path.exists(p):
            continue
        for old in glob.glob(os.path.join(ERA5_DIR, f"era5_{a:%Y-%m}_partial.tif")):
            os.remove(old)                                                    # superseded partial month
        a, b = f"{a:%Y-%m-%d}", f"{b:%Y-%m-%d}"
        days = ee.List.sequence(0, ee.Date(b).difference(ee.Date(a), "day").subtract(1))

        def one(k):
            noon = ee.Date(a).advance(k, "day").advance(NOON_UTC, "hour")
            t = ic.filterDate(noon, noon.advance(1, "hour")).first().select("temperature_2m").subtract(273.15)
            r = ic.filterDate(noon.advance(-23, "hour"), noon.advance(1, "hour")) \
                .select("total_precipitation_hourly").sum().multiply(1000)
            return t.rename("t").addBands(r.rename("r"))
        img = ee.ImageCollection(days.map(one)).toBands().unmask(-999).toFloat()
        if not download_geotiff(img, reg, p, max_scale_mult=1, crs_transform=[st, 0, x0, 0, -st, yt]):
            raise SystemExit(f"download failed: {p}")
        with rasterio.open(p) as ds:
            print(f"  {a[:7]}: {ds.count // 2} days, {ds.width}x{ds.height}")


def stage_dc():
    """Drought Code per ERA5 cell per day (local, vectorised over the grid)."""
    import glob
    import numpy as np
    import pandas as pd
    import rasterio
    from scipy import ndimage
    from earthchange.fire_danger import DC_LF_EQ, DC_START
    T, R, trs = [], [], set()
    for p in sorted(glob.glob(os.path.join(ERA5_DIR, "era5_*.tif"))):
        with rasterio.open(p) as ds:
            a = ds.read().astype(np.float64)
            trs.add(tuple(round(x, 6) for x in ds.transform[:6]))
        T.append(a[0::2]), R.append(a[1::2])
    if len(trs) != 1:
        raise SystemExit(f"ERA5 files on different grids: {trs}")
    tr = trs.pop()
    ny = min(a.shape[1] for a in T)                  # downloads differ by one bottom row; same origin
    T, R = np.concatenate([a[:, :ny] for a in T]), np.concatenate([a[:, :ny] for a in R])
    bad = (T <= -998) | (R <= -998)
    if bad.all(axis=0).any():                      # sea cells: nearest land value
        land = ~bad.all(axis=0)
        _, (iy, ix) = ndimage.distance_transform_edt(~land, return_indices=True)
        T, R = T[:, iy, ix], R[:, iy, ix]
    T, R = np.where(np.isfinite(T), T, 27.0), np.where(np.isfinite(R) & (R > -998), R, 0.0)
    dc = np.empty_like(T, dtype=np.float32)
    d0 = np.full(T.shape[1:], DC_START)
    for k in range(T.shape[0]):
        t = np.maximum(T[k], -2.8)
        pe = np.maximum((0.36 * (t + 2.8) + DC_LF_EQ) / 2, 0)
        rw = 0.83 * R[k] - 1.27
        smi = 800 * np.exp(-d0 / 400)
        dr = np.where(R[k] > 2.8, np.maximum(d0 - 400 * np.log1p(3.937 * np.maximum(rw, 0) / smi), 0), d0)
        d0 = np.maximum(dr + pe, 0)
        dc[k] = d0
    dates = pd.date_range(D0, periods=dc.shape[0]).strftime("%Y-%m-%d").to_numpy()
    x0, yt, st = tr[2], tr[5], tr[0]
    np.savez_compressed(DC_NPY, dc=dc, dates=dates, grid=np.array([x0, yt, st]))
    # validation against the Ketapang point series (ketapang_fire_danger.py)
    from ketapang_fire_danger import POINTS
    for name, (lon, lat) in POINTS.items():
        s = dc[:, int((yt - lat) / st), int((lon - x0) / st)]
        k = int(np.argmax(s))
        print(f"  {name}: peak DC {s[k]:.0f} on {dates[k]}")
    sea = dc[:, :, :]
    print(f"Saved: {DC_NPY} {dc.shape}; Kalimantan-wide peak DC median "
          f"{np.median(sea[(dates >= '2026-07-01') & (dates < '2026-11-01')].max(axis=0)):.0f}")


def stage_weather():
    import numpy as np
    import pandas as pd
    if not os.path.exists(DC_NPY):
        stage_dc()
    z = np.load(DC_NPY, allow_pickle=True)
    dc, dates = z["dc"], pd.to_datetime(z["dates"])
    doy0 = (dates[0] - pd.Timestamp("2026-01-01")).days           # dc index = doy - doy0
    x0, yt, st = z["grid"]                                        # actual origin of the ERA5 downloads
    ny, nx = dc.shape[1:]
    grid_ = json.load(open(os.path.join(DATA, "sample_grid.json")))
    gx0, _, gy0 = grid_["transform"][2], None, grid_["transform"][5]
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"))
    lon = gx0 + (df.c.to_numpy() + 0.5) * STEP
    lat = gy0 - (df.r.to_numpy() + 0.5) * STEP
    df["ex"] = np.clip(((lon - x0) / st).astype(int), 0, nx - 1)
    df["ey"] = np.clip(((yt - lat) / st).astype(int), 0, ny - 1)
    season = (dates >= "2026-07-01") & (dates < "2026-11-01")
    peak = dc[season].max(axis=0)
    df["dc_peak"] = peak[df.ey, df.ex]
    print(f"peak Jul-Oct DC over land cells: median {df.dc_peak.median():.0f}, "
          f"5-95% {df.dc_peak.quantile(.05):.0f}-{df.dc_peak.quantile(.95):.0f}")
    out = {"W1": [], "W2": [], "W3": {}}

    print("W1 matched ratio by peak-DC band (S2 burned, all strata)")
    v = df[df.valid]
    for lo, hi in zip(DC_BANDS[:-1], DC_BANDS[1:]):
        b = v[(v.dc_peak >= lo) & (v.dc_peak < hi)]
        for z_, name in ((3, "oil palm"), (2, "pulpwood")):
            d = b[b.zone.isin([1, z_])].reset_index(drop=True)
            if (d.zone == z_).sum() < 2000:
                continue
            est(d, (d.zone == z_).to_numpy(), SEQ[-1], d.burned.to_numpy(float),
                f"DC {lo}-{hi}: {name}", out["W1"], dc_band=[lo, hi], treated=name)

    print("W2 DC on the first-fire day, burned cells (VIIRS Jun-Oct)")
    last_doy = len(dates) - 1 + doy0                              # ERA5 ends before 31 Oct
    b = df[df.burned & (df.day >= 152) & (df.day < 305) & (df.day <= last_doy)].reset_index(drop=True)
    print(f"  (first-fire days after {dates[-1]:%Y-%m-%d} dropped: "
          f"{int((df.burned & (df.day > last_doy) & (df.day < 305)).sum()):,} cells)")
    b["dc_first"] = dc[b.day.to_numpy() - doy0, b.ey.to_numpy(), b.ex.to_numpy()]
    for z_, name in ((3, "oil palm"), (2, "pulpwood")):
        d = b[b.zone.isin([1, z_])].reset_index(drop=True)
        w, bidx = boot(d.block.to_numpy())
        for nm, keys in (("raw", []), ("all strata", SEQ[-1])):
            pt, pc, cov, bs = matched(d, (d.zone == z_).to_numpy(), keys, d.dc_first.to_numpy(float), w, bidx)
            g = bs[:, 0] - bs[:, 1]
            lo, hi = np.percentile(g, [2.5, 97.5])
            out["W2"].append({"treated": name, "matched_on": nm, "dc_treated": pt, "dc_control": pc,
                              "gap": pt - pc, "ci": [float(lo), float(hi)], "coverage": float(cov)})
            print(f"  {name:<9} {nm:<11} DC at first fire {pt:5.0f} vs {pc:5.0f}  gap {pt - pc:+5.0f} "
                  f"[{lo:+.0f}, {hi:+.0f}]")

    print("W3 ignitions per 1,000 km2-day by DC band (Jul-Oct)")
    from kalimantan_landprep import LINEAGE
    L = pd.read_parquet(LINEAGE)
    t = pd.to_datetime(L.acq_epoch, unit="s") + pd.Timedelta(hours=7)
    L["k"] = (t.dt.normalize() - dates[0]).dt.days.to_numpy()
    L = L[(L.parent == -1) & season[np.clip(L.k, 0, len(dates) - 1)] & (L.k >= 0) & (L.k < len(dates))]
    n_op = len(pd.read_csv(os.path.join(DATA, "op_index.csv")))
    L["tenure"] = np.select([L.unit.between(0, n_op - 1), L.unit >= n_op, L.unit == -1],
                            ["oil palm", "pulpwood", "open"], "other")
    L = L[L.tenure != "other"]
    ex = np.clip(((L.lon.to_numpy() - x0) / st).astype(int), 0, nx - 1)
    ey = np.clip(((yt - L.lat.to_numpy()) / st).astype(int), 0, ny - 1)
    L["dc"] = dc[L.k.to_numpy(), ey, ex]
    edges = np.array(DC_BANDS, float)
    sk = np.flatnonzero(season)
    tab = []
    for zc, name in ((3, "oil palm"), (2, "pulpwood"), (1, "open")):
        area = np.zeros((ny, nx))                                     # km2 per ERA5 cell
        s = df[df.zone == zc]
        np.add.at(area, (s.ey.to_numpy(), s.ex.to_numpy()), 0.04)
        expo = np.array([sum(area[(dc[k] >= lo) & (dc[k] < hi)].sum() for k in sk)
                         for lo, hi in zip(edges[:-1], edges[1:])])
        n = np.histogram(L[L.tenure == name].dc, edges)[0]
        for (lo, hi), ni, e in zip(zip(DC_BANDS[:-1], DC_BANDS[1:]), n, expo):
            tab.append({"tenure": name, "dc_band": f"{lo}-{hi}", "ignitions": int(ni), "km2_days": float(e),
                        "per_1000km2_day": 1000 * ni / e if e > 0 else np.nan})
    T = pd.DataFrame(tab).pivot(index="dc_band", columns="tenure", values="per_1000km2_day")
    T = T.reindex([f"{lo}-{hi}" for lo, hi in zip(DC_BANDS[:-1], DC_BANDS[1:])])
    T["oil palm / open"] = T["oil palm"] / T["open"]
    T["pulpwood / open"] = T["pulpwood"] / T["open"]
    print(T.round(3).to_string())
    out["W3"] = tab
    pd.DataFrame(tab).to_csv(os.path.join(OUT, "fire_weather_ignitions.csv"), index=False)
    json.dump(out, open(RES_W, "w"), indent=1, default=float)
    print(f"Saved: {RES_W}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["myconc", "dem", "border", "mydata", "national", "era5", "dc", "weather"],
                    required=True)
    {"myconc": stage_myconc, "dem": stage_dem, "border": stage_border, "mydata": stage_mydata,
     "national": stage_national, "era5": stage_era5, "dc": stage_dc,
     "weather": stage_weather}[ap.parse_args().stage]()
