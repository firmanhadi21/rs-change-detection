#!/usr/bin/env python3
"""Assets for the Kalimantan fire film ("Api" / "ApiEN", "Api, Gambut, dan Sawit") and its
infographic pages (InfografisApi1/2, InfografisApiEN1/2).

Reads only the 500 m MODIS-grid panel results in output/fire/kalimantan_palm_panel/:
  fire_carbon_by_year.csv, fire_carbon_by_category.csv, fire_carbon.json   carbon cost 2001-2026, expected 2027
  fire_loss_area_by_year.csv                                              palm / intact forest burned
  fire_factors_importance.csv, fire_factors.json                          factor-group ranking (spatial-block CV)
  fire_rates_status.csv                                                   peat / mineral land area
  event_study.json                                                        fire around the planting year
  viirs_landscapes.csv, viirs_meta.json                                   swidden-like mosaic vs peat fires
  fire_forecast_2027.json, fire_risk_2027.tif                             2026 test, 2027 scenarios and map
(scripts/kalimantan_palm_fire_panel.py, kalimantan_fire_factors.py, kalimantan_fire_carbon.py), plus the
Natural Earth coastline already in data/kalimantan/ne_countries/.

Writes into video/narasi-karhutla:
  public/api/peta_risiko.jpg      2027 El Nino-scenario fire probability, Borneo, map in the right 60%
  public/api/peta_risiko_ig.jpg   the same map, full frame, for the infographic
  src/apiData.json                every figure the film and the infographic show or speak

    conda run -n base python -I scripts/api_film_assets.py
"""
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output", "fire", "kalimantan_palm_panel")
NE = os.path.join(ROOT, "data", "kalimantan", "ne_countries", "ne_10m_admin_0_countries.zip")
FILM = os.path.join(ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "api")
JELAGA, DARAT, TETANGGA, KAPUR, ABU = "#0A0C0F", "#1B2029", "#12161C", "#E8EBEE", "#7E8792"
BARA, NYALA = "#FF5A1F", "#FFB020"
EXTENT = (108.3, 119.3, -4.6, 7.5)          # Borneo, as in the Pulau film


def data():
    import pandas as pd
    J = lambda n: json.load(open(os.path.join(SRC, n)))      # noqa: E731
    cy = pd.read_csv(os.path.join(SRC, "fire_carbon_by_year.csv"))
    cc = pd.read_csv(os.path.join(SRC, "fire_carbon_by_category.csv"))
    lo = pd.read_csv(os.path.join(SRC, "fire_loss_area_by_year.csv"))
    fi = pd.read_csv(os.path.join(SRC, "fire_factors_importance.csv"))
    rs = pd.read_csv(os.path.join(SRC, "fire_rates_status.csv"))
    vl = pd.read_csv(os.path.join(SRC, "viirs_landscapes.csv"))
    C, FF, FC, E = J("fire_carbon.json"), J("fire_factors.json"), J("fire_forecast_2027.json"), J("event_study.json")

    full = cy[cy.year <= 2025]
    tot = C["total_2001_2025_MtCO2e"]
    ss = cc[cc.by == "status_soil"].copy()
    ss["soil"] = ss.category.str.split(" / ").str[1]
    peat_e, all_e = ss[ss.soil == "peat"].MtCO2e_2001_2025.sum(), ss.MtCO2e_2001_2025.sum()
    peat_km2 = float(rs[(rs.status == "all") & (rs.soil == "peat")].km2.iloc[0])
    min_km2 = float(rs[(rs.status == "all") & (rs.soil == "mineral")].km2.iloc[0])
    per_peat = peat_e * 1e6 / peat_km2 / 25
    per_min = (all_e - peat_e) * 1e6 / min_km2 / 25
    st = cc[cc.by == "status"].set_index("category")
    con = cc[cc.by == "concession"].set_index("category")

    f = fi[fi.model == "with fire history"].sort_values("perm_pr_auc_loss", ascending=False)
    factors = [{"k": r.group, "v": round(float(r.perm_pr_auc_loss), 4)} for r in f.itertuples()]

    def bins(key):
        return [{"bin": b["bin"], "ratio": b["ratio"], "lo": b["ci_lo"], "hi": b["ci_hi"]} for b in E[key]["bins"]]

    V = vl.set_index("class")
    sw, pe = V.loc[5], V.loc[3]
    vrow = lambda r: {k: float(r[k]) for k in ("dry_over_wet", "large_pct", "escaped_pct",       # noqa: E731
                                               "share_of_det_in_large_events_pct", "det_per_100km2_wet_yr",
                                               "det_per_100km2_dry_yr", "events")}
    T26 = FC["test_2026"]
    F27 = FC["forecast_2027"]
    ex = C["expected_2027"]
    pk = full.loc[full.total_MtCO2e_central.idxmax()]
    D = {
        "tahun": [int(y) for y in full.year],
        "co2_tahun": [float(v) for v in full.total_MtCO2e_central],
        "co2_2026_jan_sep": float(cy[cy.year == 2026].total_MtCO2e_central.iloc[0]),
        "puncak": {"tahun": int(pk.year), "mt": float(pk.total_MtCO2e_central)},
        "total_gt": {k: round(v / 1000, 2) for k, v in tot.items()},
        "harga": C["params"]["prices_usd"],
        "total_usd_bn": {str(p): round(tot["central"] * p / 1000, 0) for p in C["params"]["prices_usd"]},
        "gambut": {"land_pct": round(100 * peat_km2 / (peat_km2 + min_km2), 1),
                   "emis_pct": round(100 * peat_e / all_e, 1),
                   "t_per_km2_peat": round(per_peat), "t_per_km2_mineral": round(per_min, 1),
                   "kali": round(per_peat / per_min)},
        "status_share_pct": {k: float(st.loc[k, "share_pct"]) for k in ("APL", "HP", "HL", "KSA/KPA", "HPK", "HPT")},
        "outside_concessions_pct": float(con.loc["outside concessions", "share_pct"]),
        "oil_palm_concessions_pct": float(con.loc["oil palm concession", "share_pct"]),
        "factors": factors,
        "roc_auc": round(FF["with fire history"]["full"]["roc_auc"], 2),
        "block_km": FF["block_cv_km"],
        "sawit": {"peat": bins("conversion_peat_dry"), "mineral": bins("conversion_mineral_dry")},
        "palm_burned_max": {"tahun": int(lo.loc[lo.industrial_palm_km2.idxmax(), "year"]),
                            "km2": int(lo.industrial_palm_km2.max())},
        "ladang": vrow(sw), "gambut_viirs": vrow(pe),
        "viirs_detections": J("viirs_meta.json")["detections"],
        "uji2026": {"rain_ratio": T26["jun_sep_rain_ratio_2026_median"],
                    "dry": T26["dry vs MCD64A1 Jan-Sep 2026"],
                    "observed": T26["observed rain vs MCD64A1 Jan-Sep 2026"],
                    "peat_only": T26["baseline peat only vs MCD64A1 Jan-Sep 2026"],
                    "peat_recent": T26["baseline peat+recent fire vs MCD64A1 Jan-Sep 2026"],
                    "burned_cells": T26["mcd64_burned_cells"]},
        "lead_2023": {"L1": FC["lead_time"]["L1_2023"], "L2": FC["lead_time"]["L2_2023"]},
        "p2027": {"km2": F27["expected_burned_km2"],
                  "mt": {s: ex[s]["MtCO2e"] for s in ("normal", "dry")},
                  "usd_bn": {s: {str(p): ex[s][f"USD_bn_at_{p}"] for p in C["params"]["prices_usd"]} for s in ("normal", "dry")},
                  "overlap_pct": F27["top5_overlap_normal_dry_pct"],
                  "top5_status": {k: F27["top5_dry_by_status"][k]["share_of_top5_pct"] for k in ("APL", "HP", "KSA/KPA", "HL", "HPK")},
                  "top5_peat_pct": F27["top5_dry_by_soil"]["peat"]["share_of_top5_pct"],
                  "peat_in_top5_pct": F27["top5_dry_by_soil"]["peat"]["pct_of_class_in_top5"],
                  "top5_open_pct": F27["top5_dry_by_forest"]["open"]["share_of_top5_pct"],
                  "top5_intact_pct": F27["top5_dry_by_forest"]["intact"]["share_of_top5_pct"],
                  "top5_not_burned_pct": F27["top5_dry_by_burned_2024_26"]["no"]["share_of_top5_pct"],
                  "top5_far_palm_pct": F27["top5_dry_by_near_palm"][">5 km"]["share_of_top5_pct"]},
    }
    json.dump(D, open(os.path.join(FILM, "src", "apiData.json"), "w"), indent=1, ensure_ascii=False, default=float)
    return D


def peta():
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mc
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    import rasterio
    from rasterio.warp import Resampling, reproject
    from shapely.geometry import box
    st = 0.01
    W, H = int((EXTENT[1] - EXTENT[0]) / st), int((EXTENT[3] - EXTENT[2]) / st)
    dst = np.full((H, W), np.nan, np.float32)
    with rasterio.open(os.path.join(SRC, "fire_risk_2027.tif")) as ds:
        src = ds.read(2).astype(np.float32)                         # band 2 = dry (El Nino) scenario
        src[src < 0] = np.nan
        q95 = float(np.nanquantile(src, 0.95))
        reproject(src, dst, src_transform=ds.transform, src_crs=ds.crs, src_nodata=np.nan,
                  dst_transform=rasterio.transform.from_origin(EXTENT[0], EXTENT[3], st, st),
                  dst_crs="EPSG:4326", dst_nodata=np.nan, resampling=Resampling.average)
    ne = gpd.read_file(NE)
    bb = box(EXTENT[0], EXTENT[2], EXTENT[1], EXTENT[3])
    idn = ne[ne.ADM0_A3 == "IDN"].clip(bb).explode(index_parts=False)
    b_ = idn.geometry.bounds
    idn = idn[~((b_.minx > 118.6) & (b_.maxy < 0.5))]               # west Sulawesi, not Borneo
    nbr = ne[ne.ADM0_A3.isin(["MYS", "BRN"])].clip(bb)
    from rasterio import features
    darat = features.rasterize([(g, 1) for g in idn.geometry], out_shape=dst.shape,
                               transform=rasterio.transform.from_origin(EXTENT[0], EXTENT[3], st, st), all_touched=True)
    dst[darat == 0] = np.nan                                         # keep the coastline true; no stray sea cells
    cmap =mc.LinearSegmentedColormap.from_list("risiko", [DARAT, "#3A424D", "#9A6530", BARA, NYALA])
    norm = mc.PowerNorm(0.5, vmin=0, vmax=q95 * 2)

    def gambar(fig, ax):
        ax.set_facecolor(JELAGA)
        nbr.plot(ax=ax, color=TETANGGA, edgecolor="#2A313B", linewidth=0.8, zorder=0)
        idn.plot(ax=ax, color=DARAT, edgecolor="none", zorder=0)
        ax.imshow(np.ma.masked_invalid(dst), extent=EXTENT, cmap=cmap, norm=norm, interpolation="nearest", zorder=1)
        ax.set_xlim(EXTENT[0], EXTENT[1]); ax.set_ylim(EXTENT[2], EXTENT[3]); ax.set_aspect("equal"); ax.axis("off")
        for x, y, t, c in ((114.0, 5.4, "MALAYSIA", ABU), (113.6, 0.2, "KALIMANTAN", KAPUR)):
            ax.annotate(t, (x, y), ha="center", va="center", fontsize=20, fontweight="bold", color=c,
                        path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])

    os.makedirs(PUB, exist_ok=True)
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    gambar(fig, fig.add_axes([0.40, 0.02, 0.58, 0.96]))
    fig.savefig(os.path.join(PUB, "peta_risiko.jpg"), facecolor=JELAGA, pil_kwargs={"quality": 90})
    plt.close(fig)
    fig = plt.figure(figsize=(9.72, 8.6), dpi=100, facecolor=JELAGA)
    gambar(fig, fig.add_axes([0, 0, 1, 1]))
    fig.savefig(os.path.join(PUB, "peta_risiko_ig.jpg"), facecolor=JELAGA, pil_kwargs={"quality": 90})
    plt.close(fig)
    json.dump({"cmap": [DARAT, "#3A424D", "#9A6530", BARA, NYALA], "q95": q95, "vmax": q95 * 2, "gamma": 0.5},
              open(os.path.join(PUB, "peta_risiko.json"), "w"), indent=1)
    print(f"  peta_risiko.jpg, peta_risiko_ig.jpg (top-5% threshold p = {q95:.4f})")


if __name__ == "__main__":
    D = data()
    print(json.dumps({k: D[k] for k in ("total_gt", "gambut", "puncak", "uji2026", "p2027")}, indent=1, default=float))
    peta()
