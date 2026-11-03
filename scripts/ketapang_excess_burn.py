#!/usr/bin/env python3
"""Why did the four Ketapang concessions burn more than their surroundings?

Step 1 establishes the excess on a fair footing; step 2 tests mechanisms.
All inputs come from ketapang_fire_origin.py and ketapang_landprep_tests.py
(25 m grid), plus GHSL built-up for settlements.

(a) BOUNDARY DISCONTINUITY. Burn probability against signed distance to each
    concession's boundary (negative inside), outside restricted to land in no
    concession. Weather, peat and terrain vary smoothly across a line drawn on
    a map; a jump AT the line says the land inside differs. Local linear fits
    within BW_KM each side give the jump; a donut version drops |d| < 500 m,
    since the c.2012 boundaries are not exact.

(b) LIKE-FOR-LIKE. Coarsened exact matching: every concession pixel is
    compared with unconceded pixels in the same stratum of
        peat (own map) x modelled depth bin x land-cover class x
        times burned 2015/2019/2023 x distance to water x distance to
        settlement x local ignition density
    The matched gap is the excess that land type, history, access and
    ignitions do not explain. Covariates are added one at a time to show
    which closes the gap.

(d) FUEL. The matched gap by land-cover class.

(e) PERSISTENCE (a proxy for suppression). On the 500 m lattice: distinct days
    with VIIRS detections per burning cell, inside vs unconceded, matched on
    week of first detection x peat x land-cover group. Fires left burning
    show up as more days per cell.

Uncertainty: 5 km block bootstrap (neighbouring pixels burn together, so
pixel-level errors would be far too narrow).

    conda run -n base python scripts/ketapang_excess_burn.py
"""

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import (CONC, FOUR, OUT as ORIGIN, GRID, BUF_DEG,  # noqa: E402
                                  SEASON, START, END, CLASSES, PEAT_OWN,
                                  own_peat_on_grid)
from ketapang_landprep_tests import on_grid, ee_download  # noqa: E402

OUT = os.path.join(ORIGIN, "excess")
STEP = 4                     # sample every 4th 25 m pixel -> 100 m
BLOCK_KM = 5.0
NBOOT = 300
RD_KM, BW_KM, BIN_KM = 5.0, 2.0, 0.25
GHSL = "JRC/GHSL/P2023A/GHS_BUILT_S/2020"
BUILT_M2 = 500               # of 10,000 m2 per 100 m cell (5%)


PEAT_SRC = "old"


def peat_on_grid(bbox, tr, shape):
    """Peat mask on the 25 m grid from the chosen source (PEAT_SRC)."""
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling
    if PEAT_SRC == "old":
        return own_peat_on_grid(PEAT_OWN, bbox, tr, shape)
    if PEAT_SRC == "bbsdlp":
        import geopandas as gpd
        from rasterio import features
        from ketapang_fire_origin import PEAT
        g = gpd.read_file(PEAT)
        return features.rasterize([(x, 1) for x in g.geometry if x is not None and not x.is_empty],
                                  out_shape=shape, transform=tr, dtype="uint8") > 0
    rf = os.path.normpath(os.path.join(ORIGIN, "..", "..", "peat_rf"))
    thr = json.load(open(os.path.join(rf, "final_report.json")))["threshold"]
    prob = np.zeros(shape, np.int16)
    with rasterio.open(os.path.join(rf, "peat_prob_ketapang_25m.tif")) as src:
        reproject(rasterio.band(src, 1), prob, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:4326", resampling=Resampling.nearest)
    return prob >= thr * 1000


def km_per_px(lat):
    return GRID * 111.32 * (1 + 0 * lat)


def main():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from rasterio.merge import merge
    from scipy import ndimage
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    import ee

    os.makedirs(OUT, exist_ok=True)
    srcs = [rasterio.open(p) for p in sorted(glob.glob(os.path.join(ORIGIN, "stack", "stack_*.tif")))]
    stack, tr = merge(srcs, method="first")
    for s in srcs:
        s.close()
    landb = stack[5]
    shape = landb.shape
    land = landb == 1
    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as ds:
        lc, burned = ds.read(1), ds.read(2).astype(bool)

    conc = gpd.read_file(CONC).to_crs(4326)
    conc["geometry"] = conc.geometry.make_valid()
    rows = []
    for acr, name in FOUR.items():
        s = conc[conc.company.str.contains(name, case=False, na=False)]
        rows.append(s.iloc[0].to_dict() | {"acr": acr})
    conc4 = gpd.GeoDataFrame(rows, crs=4326)
    x0, y0, x1, y1 = conc4.total_bounds
    bbox = (x0 - BUF_DEG, y0 - BUF_DEG, x1 + BUF_DEG, y1 + BUF_DEG)
    near = conc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    anyc = features.rasterize([(g, 1) for g in near.geometry], out_shape=shape,
                              transform=tr, dtype="uint8") > 0
    ins = {r.acr: features.rasterize([(r.geometry, 1)], out_shape=shape,
                                     transform=tr, dtype="uint8") > 0
           for _, r in conc4.iterrows()}
    four = np.any(list(ins.values()), axis=0)
    zone = np.full(shape, 0, np.uint8)            # 0 water/none
    zone[land & ~anyc] = 1                        # unconceded
    zone[land & anyc & ~four] = 2                 # other concessions
    zone[land & four] = 3                         # the four

    # ---- covariates on the 25 m grid
    peat = peat_on_grid(bbox, tr, shape) & land
    print(f"peat covariate: {PEAT_SRC} ({peat.sum() / land.sum():.0%} of land)")
    with rasterio.open(os.path.join(ORIGIN, "peatgrids_thickness_cm.tif")) as src:
        from rasterio.warp import reproject, Resampling
        thick = np.zeros(shape, np.int16)
        reproject(rasterio.band(src, 1), thick, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:4326",
                  resampling=Resampling.nearest)
    with rasterio.open(os.path.join(ORIGIN, "landprep", "mcd64", "mcd_00.tif")) as ds:
        marr, mtr = ds.read(), ds.transform
    hist = sum((on_grid(marr[i], mtr, shape, tr) > 0).astype(np.uint8) for i in range(3))
    px_km = GRID * 111.32
    d_water = ndimage.distance_transform_edt(land) * px_km
    print("GHSL built-up ...")
    gh = ee.Image(GHSL).select("built_surface").unmask(0).toInt16()
    garr, gtr = ee_download(gh, bbox, os.path.join(OUT, "ghsl"), "ghsl", 0.0009, 1)
    built = on_grid((garr[0] > BUILT_M2).astype(np.uint8), gtr, shape, tr) > 0
    d_settle = ndimage.distance_transform_edt(~built) * px_km
    ign = pd.read_csv(os.path.join(ORIGIN, "ignitions.csv"))
    ign = ign[ign.month.between(*SEASON)]
    rr, cc = rasterio.transform.rowcol(tr, ign.lon.to_numpy(), ign.lat.to_numpy())
    rr, cc = np.asarray(rr), np.asarray(cc)
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    cnt = np.zeros((shape[0] // 20 + 1, shape[1] // 20 + 1))   # 500 m
    np.add.at(cnt, (rr[ok] // 20, cc[ok] // 20), 1)
    dens = ndimage.uniform_filter(cnt, 21) * 21 * 21 / (21 * 0.5) ** 2 * 100  # per 100 km2
    ign_dens = np.kron(dens, np.ones((20, 20)))[:shape[0], :shape[1]]

    # signed distance to each concession boundary (km; negative inside)
    sd = {}
    for k, m in ins.items():
        sd[k] = np.where(m, -ndimage.distance_transform_edt(m),
                         ndimage.distance_transform_edt(~m)) * px_km

    # ---- sample at 100 m
    sl = (slice(0, None, STEP), slice(0, None, STEP))
    yy, xx = np.mgrid[0:shape[0]:STEP, 0:shape[1]:STEP]
    df = pd.DataFrame({
        "zone": zone[sl].ravel(), "burned": burned[sl].ravel(),
        "peat": peat[sl].ravel(), "thick": thick[sl].ravel(),
        "lc": lc[sl].ravel(), "hist": hist[sl].ravel(),
        "d_water": d_water[sl].ravel(), "d_settle": d_settle[sl].ravel(),
        "ign": ign_dens[sl].ravel(),
        "block": ((yy * GRID * 111.32 // BLOCK_KM).astype(int) * 1000
                  + (xx * GRID * 111.32 // BLOCK_KM).astype(int)).ravel(),
        **{f"sd_{k}": v[sl].ravel() for k, v in sd.items()},
        **{f"in_{k}": v[sl].ravel() for k, v in ins.items()},
    })
    canal_tif = os.path.join(ORIGIN, "canals", "canal_density_25m.tif")
    has_canals = os.path.exists(canal_tif)
    if has_canals:                      # from ketapang_canals.py
        with rasterio.open(canal_tif) as ds:
            cd = ds.read(1)
        df["canal"] = cd[sl].ravel()
    df = df[(df.zone > 0) & (df.lc < 255)].reset_index(drop=True)
    if has_canals:
        df = df[df.canal >= 0].reset_index(drop=True)   # inside canal-map extent
        df["canal_bin"] = np.digitize(df.canal, [0.25, 0.75, 1.5, 3.0])
    df["depth_bin"] = np.where(df.peat, np.digitize(df.thick, [1, 100, 200, 300]), 9)
    df["water_bin"] = np.digitize(df.d_water, [1, 3, 10])
    df["settle_bin"] = np.digitize(df.d_settle, [1, 3, 10])
    df["ign_bin"] = pd.qcut(df.ign.rank(method="first"), 3, labels=False)
    print(f"sample: {len(df):,} pixels at 100 m; zones",
          df.zone.value_counts().to_dict())

    blocks = df.block.unique()
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    df["bi"] = bidx[df.block].to_numpy()
    rng = np.random.default_rng(42)
    boot_w = rng.multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                             size=NBOOT)                      # NBOOT x nblocks

    # ---------------------------------------------------------------- (b)
    def cem(d, treat, ctrl, keys):
        """ATT burn-rate gap, matched on strata `keys`; block-bootstrap CI."""
        d = d[(d.zone == treat) | (d.zone == ctrl)]
        t = d.zone == treat
        key = d[keys].astype(str).agg("|".join, axis=1) if keys else pd.Series("all", index=d.index)
        codes, uniq = pd.factorize(key)
        ns = len(uniq)
        nb = len(blocks)

        def tab(mask, val):
            a = np.zeros((nb, ns))
            np.add.at(a, (d.bi.to_numpy()[mask], codes[mask]), val[mask])
            return a
        one = np.ones(len(d))
        bt = d.burned.to_numpy().astype(float)
        T_n, T_b = tab(t.to_numpy(), one), tab(t.to_numpy(), bt)
        C_n, C_b = tab(~t.to_numpy(), one), tab(~t.to_numpy(), bt)

        def att(w):
            tn, tb = w @ T_n, w @ T_b
            cn, cb = w @ C_n, w @ C_b
            m = (tn > 0) & (cn > 0)
            pt = tb[m].sum() / tn[m].sum()
            pc = (tn[m] * cb[m] / cn[m]).sum() / tn[m].sum()
            return pt, pc, tn[m].sum() / max(tn.sum(), 1)
        pt, pc, cov = att(np.ones(nb))
        bs = np.array([att(w)[:2] for w in boot_w])
        diff = bs[:, 0] - bs[:, 1]
        ratio = bs[:, 0] / bs[:, 1]
        return {"treated_burn_pct": 100 * pt, "matched_control_burn_pct": 100 * pc,
                "gap_pts": 100 * (pt - pc),
                "gap_ci95": [100 * float(np.percentile(diff, 2.5)),
                             100 * float(np.percentile(diff, 97.5))],
                "ratio": pt / pc if pc else None,
                "ratio_ci95": [float(np.percentile(ratio, 2.5)),
                               float(np.percentile(ratio, 97.5))],
                "treated_share_matched": cov}

    seq = [[], ["peat"], ["peat", "depth_bin"], ["peat", "depth_bin", "lc"],
           ["peat", "depth_bin", "lc", "hist"],
           ["peat", "depth_bin", "lc", "hist", "water_bin"],
           ["peat", "depth_bin", "lc", "hist", "water_bin", "settle_bin"],
           ["peat", "depth_bin", "lc", "hist", "water_bin", "settle_bin", "ign_bin"]]
    names = ["raw", "+ peat", "+ peat depth", "+ land cover", "+ burn history",
             "+ distance to water", "+ distance to settlement", "+ ignition density"]
    if has_canals:
        seq.append(seq[-1] + ["canal_bin"])
        names.append("+ canal density (drainage)")
        # drainage alone, before anything else, to see how much it carries
        seq.insert(1, ["canal_bin"])
        names.insert(1, "canal density only")
    b_rows = []
    for ctrl, cname in ((1, "unconceded"), (2, "other concessions")):
        for nm, keys in zip(names, seq):
            r = cem(df, 3, ctrl, keys)
            b_rows.append({"control": cname, "matched_on": nm, **r})
            print(f"  vs {cname:<17} {nm:<26} inside {r['treated_burn_pct']:5.1f}%  "
                  f"matched {r['matched_control_burn_pct']:5.1f}%  gap {r['gap_pts']:+5.1f} "
                  f"[{r['gap_ci95'][0]:+.1f}, {r['gap_ci95'][1]:+.1f}]  "
                  f"x{r['ratio']:.2f}  coverage {100 * r['treated_share_matched']:.0f}%")
    tb = pd.DataFrame(b_rows)
    tb.to_csv(os.path.join(OUT, "b_matched_gap.csv"), index=False)

    full = seq[-1]
    per_conc = []
    for k in FOUR:
        d = df.copy()
        d.loc[(d.zone == 3) & ~d[f"in_{k}"], "zone"] = 0
        r = cem(d, 3, 1, full)
        per_conc.append({"concession": k, **r})
    pc = pd.DataFrame(per_conc)
    pc.to_csv(os.path.join(OUT, "b_matched_gap_by_concession.csv"), index=False)
    print(pc[["concession", "treated_burn_pct", "matched_control_burn_pct", "gap_pts",
              "ratio", "treated_share_matched"]].round(2).to_string(index=False))

    # ------------------------------------------------- (c) drainage dose-response
    tc = None
    if has_canals:
        c_rows = []
        for z, zn in ((3, "the four"), (2, "other concessions"), (1, "unconceded")):
            for pk, pn in ((True, "peat"), (False, "mineral")):
                d = df[(df.zone == z) & (df.peat == pk)]
                for bnum, g in d.groupby("canal_bin"):
                    c_rows.append({"zone": zn, "soil": pn, "canal_bin": int(bnum),
                                   "n": len(g), "burn_pct": 100 * g.burned.mean(),
                                   "mean_density": float(g.canal.mean())})
        tc = pd.DataFrame(c_rows)
        tc.to_csv(os.path.join(OUT, "c_burn_by_canal_density.csv"), index=False)
        dz = df.groupby("zone").canal.mean().rename({1: "unconceded",
                                                     2: "other concessions",
                                                     3: "the four"})
        print("mean canal density km/km2:", dz.round(2).to_dict())
        print(tc[tc.soil == "peat"].round(1).to_string(index=False))

    # ---------------------------------------------------------------- (d)
    d_rows = []
    keys_wo_lc = [k for k in full if k != "lc"]
    for j, cname in enumerate(CLASSES):
        d = df[df.lc == j]
        if (d.zone == 3).sum() < 200:
            continue
        r = cem(d, 3, 1, keys_wo_lc)
        d_rows.append({"class": cname, "n_inside": int((d.zone == 3).sum()), **r})
    td = pd.DataFrame(d_rows)
    td.to_csv(os.path.join(OUT, "d_gap_by_landcover.csv"), index=False)
    print(td[["class", "n_inside", "treated_burn_pct", "matched_control_burn_pct",
              "gap_pts", "ratio"]].round(2).to_string(index=False))

    # ---------------------------------------------------------------- (a)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rd_rows = []
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), dpi=150, sharey=True)
    panels = list(FOUR) + ["all four (pooled)", "all four, peat only"]
    for ax, k in zip(axes.ravel(), panels):
        if k in FOUR:
            d = df[(df[f"sd_{k}"].abs() <= RD_KM)
                   & ((df[f"in_{k}"]) | (df.zone == 1))].copy()
            d["s"] = d[f"sd_{k}"]
        else:
            parts = []
            for kk in FOUR:
                p = df[(df[f"sd_{kk}"].abs() <= RD_KM)
                       & ((df[f"in_{kk}"]) | (df.zone == 1))].copy()
                p["s"] = p[f"sd_{kk}"]
                parts.append(p)
            d = pd.concat(parts)
            if "peat" in k:
                d = d[d.peat]
        d["side_in"] = d.s < 0

        def jump(dd, donut=0.0):
            out = []
            for side in (True, False):
                q = dd[(dd.side_in == side) & (dd.s.abs() <= BW_KM) & (dd.s.abs() >= donut)]
                if len(q) < 50:
                    return np.nan
                c = np.polyfit(q.s, q.burned.astype(float), 1)
                out.append(np.polyval(c, 0.0))
            return out[0] - out[1]
        j0 = jump(d)
        jd = jump(d, 0.5)
        # block bootstrap
        bl = d.bi.to_numpy()
        js = []
        ub = np.unique(bl)
        for b in range(100):
            pick = rng.choice(ub, len(ub))
            w = pd.Series(pick).value_counts()
            dd = d.loc[np.repeat(d.index[np.isin(bl, w.index)],
                                 pd.Series(bl[np.isin(bl, w.index)]).map(w).to_numpy())]
            js.append(jump(dd))
        js = np.array(js, float)
        rd_rows.append({"panel": k, "n": len(d), "jump_pts": 100 * j0,
                        "jump_ci95": [100 * np.nanpercentile(js, 2.5),
                                      100 * np.nanpercentile(js, 97.5)],
                        "donut500m_jump_pts": 100 * jd,
                        "burn_pct_inside_2km": 100 * d[(d.s < 0) & (d.s > -2)].burned.mean(),
                        "burn_pct_outside_2km": 100 * d[(d.s > 0) & (d.s < 2)].burned.mean()})
        bins = np.arange(-RD_KM, RD_KM + BIN_KM, BIN_KM)
        d["bin"] = pd.cut(d.s, bins)
        g = d.groupby("bin", observed=True).burned.agg(["mean", "size"])
        mids = np.array([b.mid for b in g.index])
        ax.scatter(mids, 100 * g["mean"], s=10 + g["size"] / g["size"].max() * 40,
                   c=np.where(mids < 0, "#b3001b", "#f08a24"))
        for side, col in ((True, "#b3001b"), (False, "#f08a24")):
            q = d[(d.side_in == side) & (d.s.abs() <= BW_KM)]
            if len(q) > 50:
                c = np.polyfit(q.s, q.burned.astype(float), 1)
                xs = np.linspace(-BW_KM, 0, 10) if side else np.linspace(0, BW_KM, 10)
                ax.plot(xs, 100 * np.polyval(c, xs), color=col, lw=2)
        ax.axvline(0, color="black", lw=0.8)
        r = rd_rows[-1]
        ax.set_title(f"{k}: jump {r['jump_pts']:+.0f} pts "
                     f"[{r['jump_ci95'][0]:+.0f}, {r['jump_ci95'][1]:+.0f}]",
                     fontsize=10, loc="left")
        ax.set_xlabel("distance to boundary, km (inside ←  → outside)")
    axes[0, 0].set_ylabel("% burned Jul–Oct 2026")
    axes[1, 0].set_ylabel("% burned Jul–Oct 2026")
    fig.suptitle("Does burning jump at the concession boundary? (outside = land in no "
                 "concession; 5 km block bootstrap)", x=0.01, ha="left", fontsize=12,
                 weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(OUT, "a_boundary_discontinuity.png"))
    plt.close(fig)
    ta = pd.DataFrame(rd_rows)
    ta.to_csv(os.path.join(OUT, "a_boundary_discontinuity.csv"), index=False)
    print(ta.round(1).to_string(index=False))

    # ---------------------------------------------------------------- (e)
    det = pd.read_csv(os.path.join(ORIGIN, f"viirs_{START}_{END}.csv"))
    det = det[det.confidence >= 1].copy()
    det["time"] = pd.to_datetime(det.acq_epoch, unit="s", utc=True).dt.tz_convert("Asia/Pontianak")
    det = det[det.time.dt.month.between(*SEASON)]
    det["date"] = det.time.dt.tz_localize(None).dt.normalize()
    r_, c_ = rasterio.transform.rowcol(tr, det.lon.to_numpy(), det.lat.to_numpy())
    det["cell"] = (np.asarray(r_) // 20) * 10000 + (np.asarray(c_) // 20)
    cells = det.groupby("cell").agg(days=("date", "nunique"), n=("date", "size"),
                                    first=("date", "min")).reset_index()
    cr, ccol = (cells.cell // 10000) * 20 + 10, (cells.cell % 10000) * 20 + 10
    okc = (cr < shape[0]) & (ccol < shape[1])
    cells = cells[okc].copy()
    cr, ccol = cr[okc].to_numpy(), ccol[okc].to_numpy()
    cells["zone"] = zone[cr, ccol]
    cells["peat"] = peat[cr, ccol]
    cells["lcg"] = np.select([lc[cr, ccol] <= 3, lc[cr, ccol] == 4, lc[cr, ccol] <= 6],
                             ["palm", "forest", "cleared"], "nonforest")
    cells["week"] = cells["first"].dt.isocalendar().week.astype(int)
    cells = cells[cells.zone.isin([1, 3])]
    cells["key"] = cells.peat.astype(str) + "|" + cells.lcg + "|" + cells.week.astype(str)
    g = cells.groupby(["key", "zone"]).days.agg(["mean", "size"]).unstack()
    g = g.dropna()
    w = g[("size", 3)]
    pers_in = float((g[("mean", 3)] * w).sum() / w.sum())
    pers_out = float((g[("mean", 1)] * w).sum() / w.sum())
    te = {"cells_inside": int((cells.zone == 3).sum()),
          "cells_unconceded": int((cells.zone == 1).sum()),
          "raw_days_inside": float(cells[cells.zone == 3].days.mean()),
          "raw_days_unconceded": float(cells[cells.zone == 1].days.mean()),
          "matched_days_inside": pers_in, "matched_days_unconceded": pers_out,
          "matched_ratio": pers_in / pers_out,
          "share_inside_cells_matched": float(w.sum() / (cells.zone == 3).sum())}
    print("(e) persistence:", {k: round(v, 2) for k, v in te.items()})

    json.dump({"a_boundary": ta.to_dict("records"), "b_matched": tb.to_dict("records"),
               "b_by_concession": pc.to_dict("records"), "d_by_landcover": td.to_dict("records"),
               "e_persistence": te,
               "c_canals": tc.to_dict("records") if tc is not None else None},
              open(os.path.join(OUT, "summary.json"), "w"),
              indent=2, default=str)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--peat", choices=["old", "rf", "bbsdlp"], default="rf",
                    help="peat covariate: old team map (36%% accurate at field points), "
                         "the field-weighted RF (peat_rf_gee.py), or BBSDLP polygons")
    PEAT_SRC = ap.parse_args().peat
    if PEAT_SRC != "old":
        OUT = os.path.join(ORIGIN, f"excess_peat_{PEAT_SRC}")
    main()
