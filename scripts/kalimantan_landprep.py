#!/usr/bin/env python3
"""WP4, Kalimantan-wide: was concession fire land preparation for planting? Three tests, each
able to come out against it. Scales ketapang_landprep_tests.py to the 200 m grid of
kalimantan_excess_burn.py (sample_200m.parquet; zone 1 unpermitted, 2 pulpwood only, 3 oil palm).

T1 FATE OF EARLIER BURNS. Land burned in 2015 (MCD64A1) that was not yet palm: what share of it
   was planted to palm 2016-2021 (Descals et al. 2024 planting year), against unburned non-palm
   land in the same zone and strata (peat, depth bin, distance to water / settlement; CEM, 5 km
   block bootstrap)? Land preparation predicts burned >> unburned, most inside concessions. The
   comparison is within year, so the palm price is common to burned and unburned land. 2019
   burns are reported too, but palm planted 2020-21 is rarely closed canopy in a 2021 map.
   Also per oil-palm concession: 2015-burned share planted, excess (BH-FDR) units vs the rest.
T2 CLEARING BEFORE THE 2026 FIRE. Sentinel-2 NDVI early (Dec 2025-Mar 2026) vs late pre-fire
   (15 May-10 Jul 2026), 20 m: green early (>= 0.6), open late (< 0.45, drop >= 0.2). A 2026-burned
   cell counts as cleared when >= a quarter of its clear 20 m pixels were; cells with a VIIRS
   detection within ~750 m before 10 July are left out so an early fire is not read as clearing.
   Share of burned cells cleared first, concession vs matched unpermitted (all SEQ strata).
T3 HOW THE FIRES STARTED (VIIRS lineage, Jul-Oct). Day share (06-18 h local solar) of ignitions
   against the day share of all detections in the same tenure (smouldering peat is seen day and
   night alike, so the baseline matters); and multi-point lighting: overpasses with >= 3 new
   ignitions in one concession (open land: 10 km cells), per 100 km2.
The parcel-size test (company blocks vs household plots) needs a new PlanetScope sample; not here.

    python scripts/kalimantan_landprep.py --stage fate     # Earth Engine: MCD64 + Descals, 200 m
    python scripts/kalimantan_landprep.py --stage clear    # Earth Engine: S2 pre-fire clearing, 200 m
    python scripts/kalimantan_landprep.py --stage tests
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import (DATA, NBOOT, OUT, SEQ, STEP, direct_download,  # noqa: E402
                                    matched)

FATE = os.path.join(DATA, "fate_200m.tif")
CLEAR = os.path.join(DATA, "clear_200m.tif")
FATE_BANDS = ["b2015", "b2019", "pre2015", "new2015", "pre2019", "new2019"]
CLEAR_BANDS = ["clr", "okc"]
LINEAGE = os.path.join(os.path.dirname(OUT), "kalimantan_lineage", "lineage.parquet")
UNITS = os.path.join(OUT, "heterogeneity_units.csv")
UNITS_DC = os.path.join(OUT, "per_concession_matched_dc.csv")
DCS = "--dc-stratum" in sys.argv   # review round 2: drought-matched classes; T2 strata + peak-DC band
RES = os.path.join(OUT, "landprep")
GREEN, OPEN, DROP = 0.60, 0.45, 0.20
EARLY, LATE = ("2025-12-01", "2026-04-01"), ("2026-05-15", "2026-07-11")
CUTOFF_DAY = 190                  # 10 July 2026, day of year from 0
SEASON = (181, 305)               # Jul-Oct, day of year from 0
NONPALM_MAX = 50                  # eligible for T1: < 50% of the cell palm before the fire year
FATE_KEYS = ["peat", "depth_bin", "water_bin", "settle_bin"]     # pre-2015 covariates only
ZONES = {3: "oil palm", 2: "pulpwood", 1: "unpermitted"}


def grid():
    import ee
    return ee.Projection("EPSG:4326", [STEP, 0, 0, 0, -STEP, 0])


def fate_image():
    """% of 30 m pixels palm before / planted after each fire year, and MCD64 burned (0/1)."""
    import ee
    from earthchange.fire_national import BURN_IC
    ic = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2")
    cls = ic.select("classification").mosaic().unmask(0)
    py = ic.select("planting_year").mosaic().unmask(0)
    palm, proj = cls.gt(0), ic.first().select("planting_year").projection()
    bands = []
    for y in (2015, 2019):
        bands.append(ee.ImageCollection(BURN_IC).filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("BurnDate")
                     .map(lambda im: im.gt(0)).max().unmask(0).reproject(grid()).rename(f"b{y}"))
    frac = []
    for y, last in ((2015, 2021), (2019, 2021)):
        pre = palm.And(py.lte(y).Or(py.eq(0)))            # planted by the fire year (or year unknown)
        new = palm.And(py.gt(y)).And(py.lte(last))
        frac += [pre.rename(f"pre{y}"), new.rename(f"new{y}")]
    fr = (ee.Image.cat(frac).setDefaultProjection(proj)
          .reduceResolution(ee.Reducer.mean(), maxPixels=128).reproject(grid()).multiply(100))
    return ee.Image.cat(bands + [fr.select(["pre2015", "new2015", "pre2019", "new2019"])]).round().toInt16()


def clear_image():
    """% of clear 20 m pixels cleared before the fire (green early, open late), and % clear."""
    import ee

    def ndvi(lo, hi):
        def one(im):
            scl = im.select("SCL")
            ok = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
            return im.normalizedDifference(["B8", "B4"]).updateMask(ok)
        return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(lo, hi)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80)).map(one).median())
    p20 = ee.Projection("EPSG:4326").atScale(20)
    e, l_ = ndvi(*EARLY), ndvi(*LATE)
    ok = e.mask().And(l_.mask()).unmask(0).setDefaultProjection(p20)
    clr = e.gte(GREEN).And(l_.lt(OPEN)).And(e.subtract(l_).gte(DROP)).unmask(0).setDefaultProjection(p20)
    agg = lambda im: im.reduceResolution(ee.Reducer.mean(), maxPixels=256).reproject(grid()).multiply(100)  # noqa: E731
    return ee.Image.cat([agg(clr).rename("clr"), agg(ok).rename("okc")]).round().toInt16()


def _save(arr, tr, path, bands):
    import rasterio
    with rasterio.open(STACK_REF()) as ref:
        if arr.shape[1:] != (ref.height, ref.width):
            raise SystemExit(f"{path}: grid {arr.shape[1:]} != stack {(ref.height, ref.width)}")
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype="int16",
                crs="EPSG:4326", transform=tr, compress="deflate", tiled=True)
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(arr.astype("int16"))
        ds.descriptions = tuple(bands)
    print(f"Saved: {path} {arr.shape}")


def STACK_REF():                  # noqa: N802
    from kalimantan_excess_burn import STACK
    return STACK


def stage_fate():
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    arr, tr = direct_download(fate_image(), os.path.join(DATA, "fate_tiles"))
    _save(arr, tr, FATE, FATE_BANDS)


def stage_clear():
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    arr, tr = direct_download(clear_image(), os.path.join(DATA, "clear_tiles"))
    _save(arr, tr, CLEAR, CLEAR_BANDS)


# ------------------------------------------------------------------- tests
def ratio_ci(pt, pc, bs):
    import numpy as np
    q = bs[:, 0] / np.where(bs[:, 1] > 0, bs[:, 1], np.nan)
    lo, hi = np.nanpercentile(q, [2.5, 97.5])
    return {"treated": float(pt), "control": float(pc), "ratio": float(pt / pc) if pc > 0 else None,
            "ci": [float(lo), float(hi)], "diff_pp": float(100 * (pt - pc)),
            "diff_ci_pp": [float(x) for x in 100 * np.percentile(bs[:, 0] - bs[:, 1], [2.5, 97.5])]}


def boot_setup(df):
    import numpy as np
    import pandas as pd
    blocks = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    w = np.random.default_rng(42).multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                                              size=NBOOT).astype(float)
    return w, bidx


def t1_fate(df, out):
    import numpy as np
    import pandas as pd
    import rasterio
    from scipy.stats import mannwhitneyu
    with rasterio.open(FATE) as ds:
        F = {b: ds.read(i + 1)[df.r.to_numpy(), df.c.to_numpy()] for i, b in enumerate(FATE_BANDS)}
    w, bidx = boot_setup(df)
    out["T1"] = {}
    print("\nT1 fate of earlier burns: share of non-palm land planted to palm afterwards (Descals, to 2021)")
    for y in (2015, 2019):
        el = F[f"pre{y}"] < NONPALM_MAX
        burned = F[f"b{y}"] > 0
        new = F[f"new{y}"] / 100.0
        out["T1"][y] = {}
        print(f"  {y} burns -> planted {y + 1}-2021        burned    matched unburned   ratio [95% CI]        burned km2")
        for z, name in ZONES.items():
            m = el & (df.zone.to_numpy() == z)
            d = df[m]
            pt, pc, cov, bs = matched(d, burned[m], FATE_KEYS, new[m], w, bidx)
            r = ratio_ci(pt, pc, bs)
            r.update({"coverage": float(cov), "burned_km2": float(0.04 * burned[m].sum()),
                      "raw_unburned": float(new[m][~burned[m]].mean())})
            out["T1"][y][name] = r
            print(f"  {name:<34}{100 * pt:7.1f}%   {100 * pc:9.1f}%      x{r['ratio']:.2f} "
                  f"[{r['ci'][0]:.2f}, {r['ci'][1]:.2f}]   {r['burned_km2']:9,.0f}")
    # per oil-palm concession: 2015-burned share planted, excess units vs the rest
    if os.path.exists(UNITS):
        if DCS:
            U = pd.read_csv(UNITS_DC).assign(excess=lambda d: d.class_fdr.eq("excess"))
        else:
            U = pd.read_csv(UNITS)
        U = U[U.kind == "oil palm"][["id", "excess"]]
        el = (F["pre2015"] < NONPALM_MAX) & (F["b2015"] > 0) & (df.zone.to_numpy() == 3)
        s = pd.DataFrame({"id": df.op.to_numpy()[el], "new": F["new2015"][el] / 100.0})
        g = s.groupby("id").agg(burned_cells=("new", "size"), planted=("new", "mean")).reset_index()
        g = g[g.burned_cells >= 25].merge(U, on="id")     # >= 1 km2 burned in 2015
        a, b = g[g.excess].planted, g[~g.excess].planted
        p = mannwhitneyu(a, b).pvalue if len(a) and len(b) else float("nan")
        out["T1"]["per_unit_2015"] = {"units": int(len(g)), "excess_units": int(len(a)),
                                      "median_planted_excess": float(a.median()), "median_planted_rest": float(b.median()),
                                      "mean_planted_excess": float(a.mean()), "mean_planted_rest": float(b.mean()),
                                      "mannwhitney_p": float(p)}
        print(f"  per oil-palm unit with >= 1 km2 burned in 2015 (n={len(g)}): planted share, excess units "
              f"median {100 * a.median():.1f}% (n={len(a)}) vs rest {100 * b.median():.1f}%, Mann-Whitney p={p:.3f}")


def t2_clearing(df, out):
    import numpy as np
    import pandas as pd
    import rasterio
    from scipy import ndimage
    with rasterio.open(CLEAR) as ds:
        clr, okc = (ds.read(i + 1) for i in range(2))
    grid_ = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, shape = rasterio.Affine(*grid_["transform"]), tuple(grid_["shape"])
    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"))
    day = ((pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)).dt.normalize()
           - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy()))
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1]) & (day <= CUTOFF_DAY)
    early = np.zeros(shape, bool)
    early[rr[ok], cc[ok]] = True
    early = ndimage.binary_dilation(early, np.ones((3, 3), bool), iterations=3)   # ~750 m, as the burn rule
    r, c = df.r.to_numpy(), df.c.to_numpy()
    d = df.assign(clr=clr[r, c], okc=okc[r, c], early=early[r, c])
    d = d[d.burned & (d.okc >= 50) & ~d.early]
    d["cleared"] = (d.clr * 4 >= d.okc).astype(float)
    w, bidx = boot_setup(df)
    out["T2"] = {"burned_cells_used": int(len(d))}
    print(f"\nT2 cleared before the 2026 fire (burned cells with clear pre-fire S2, no VIIRS before 10 Jul; n={len(d):,})")
    print(f"  {'':<28}{'cleared, inside':>16}{'matched outside':>17}   ratio [95% CI]")
    raw = d.groupby("zone").cleared.mean()
    out["T2"]["raw_share"] = {ZONES[k]: float(v_) for k, v_ in raw.items()}
    for z in (3, 2):
        m = d.zone.isin([z, 1]).to_numpy()
        dd = d[m]
        keys = SEQ[-1] + (["dc_bin"] if DCS else [])
        pt, pc, cov, bs = matched(dd, (dd.zone == z).to_numpy(), keys, dd.cleared.to_numpy(), w, bidx)
        res = ratio_ci(pt, pc, bs)
        res["coverage"] = float(cov)
        out["T2"][ZONES[z]] = res
        print(f"  {ZONES[z] + ' vs unpermitted':<28}{100 * pt:15.1f}%{100 * pc:16.1f}%   x{res['ratio']:.2f} "
              f"[{res['ci'][0]:.2f}, {res['ci'][1]:.2f}]")
    print("  raw share cleared first: " + ", ".join(f"{k} {100 * v_:.1f}%" for k, v_ in out["T2"]["raw_share"].items()))


def t3_ignitions(df, out):
    import numpy as np
    import pandas as pd
    L = pd.read_parquet(LINEAGE)
    t = pd.to_datetime(L.acq_epoch, unit="s")
    solar_h = (t.dt.hour + t.dt.minute / 60 + L.lon / 15) % 24
    L["day"] = ((solar_h >= 6) & (solar_h < 18)).to_numpy()
    doy = (t + pd.Timedelta(hours=7)).dt.dayofyear.to_numpy() - 1
    L = L[(doy >= SEASON[0]) & (doy < SEASON[1])].copy()
    n_op = len(pd.read_csv(os.path.join(DATA, "op_index.csv")))
    L["tenure"] = np.select([L.unit.between(0, n_op - 1), L.unit >= n_op, L.unit == -1],
                            ["oil palm", "pulpwood", "open"], "other")
    L = L[L.tenure != "other"]
    L["ign"] = L.parent.to_numpy() == -1
    km2 = {"oil palm": 0.04 * (df.zone == 3).sum(), "pulpwood": 0.04 * (df.zone == 2).sum(),
           "open": 0.04 * (df.zone == 1).sum()}
    # one overpass = satellite pass, binned to 30 min; open land grouped in 10 km cells
    L["pass"] = (L.acq_epoch // 1800).astype(np.int64)
    cell = (np.floor(L.lat / 0.09).astype(np.int64) * 10000 + np.floor(L.lon / 0.09).astype(np.int64))
    L["grp"] = np.where(L.tenure == "open", -cell - 1, L.unit)
    out["T3"] = {}
    print("\nT3 ignitions, Jul-Oct (solar day 06-18 h)")
    print(f"  {'tenure':<10}{'ignitions':>10}{'day share ign.':>16}{'day share all':>15}{'ratio':>7}"
          f"{'multi-ign. passes /100 km2':>28}")
    for k in ("oil palm", "pulpwood", "open"):
        s = L[L.tenure == k]
        ign = s[s.ign]
        dsi, dsa = ign.day.mean(), s.day.mean()
        multi = (ign.groupby(["grp", "pass"]).size() >= 3).sum()
        out["T3"][k] = {"ignitions": int(len(ign)), "detections": int(len(s)), "day_share_ignitions": float(dsi),
                        "day_share_all": float(dsa), "ratio": float(dsi / dsa),
                        "multi_ignition_passes": int(multi), "per_100km2": float(100 * multi / km2[k])}
        print(f"  {k:<10}{len(ign):>10,}{100 * dsi:15.1f}%{100 * dsa:14.1f}%{dsi / dsa:7.2f}{100 * multi / km2[k]:>28.2f}")


def stage_tests():
    import pandas as pd
    os.makedirs(RES, exist_ok=True)
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"))
    out = {"strata_note": "T2 adds the peak-DC band; T1 per-unit uses drought-matched classes" if DCS else None}
    if DCS:
        from kalimantan_dc_stratum import peak_dc_bin
        df["dc_bin"] = peak_dc_bin(df)
    else:
        t3_ignitions(df, out)                 # unchanged by the drought stratum
    if os.path.exists(FATE):
        t1_fate(df, out)
    else:
        print(f"\n(T1 skipped: run --stage fate first; {FATE} missing)")
    if os.path.exists(CLEAR):
        t2_clearing(df, out)
    else:
        print(f"(T2 skipped: run --stage clear first; {CLEAR} missing)")
    name = "landprep_tests_dc.json" if DCS else "landprep_tests.json"
    json.dump(out, open(os.path.join(RES, name), "w"), indent=1, default=float)
    print(f"\nSaved: {RES}/{name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["fate", "clear", "tests"], required=True)
    ap.add_argument("--dc-stratum", action="store_true")
    {"fate": stage_fate, "clear": stage_clear, "tests": stage_tests}[ap.parse_args().stage]()
