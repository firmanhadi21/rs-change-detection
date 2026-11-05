#!/usr/bin/env python3
"""Maps and figures for Part 4 of the concessions film, "Benarkah Sawit Membakar Kalimantan?"
(Is oil palm really burning Kalimantan?): the Kalimantan-wide results.

Reads the Kalimantan runs in output/fire/kalimantan_excess/ and writes into video/narasi-karhutla:

  public/pulau/peta_semua.jpg     every analysed concession, oil palm and wood fibre, on Borneo
  public/pulau/peta_berlebih.jpg  the same, with the BH-FDR "excess" units in ember and the
                                  Ketapang four marked
  public/pulau/peta_kemarau.jpg   peak Jul-Oct 2026 Drought Code (ERA5-Land), Borneo, with the
                                  Indonesia-Malaysia border
  src/pulauData.json              every figure the film shows or speaks

No company is named on screen; the Ketapang four appear as one marked group, as in Parts 1-3.
Maps leave the left ~40% of the frame for the film's text column (Parts 1-3 layout).

    conda run -n base python scripts/kalimantan_film4_assets.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
sys.path.insert(0, _REPO_ROOT)
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from kalimantan_concession_film_assets import ABU, BARA, JELAGA, KAPUR, NYALA  # noqa: E402
from kalimantan_excess_burn import CONC, DATA, HTI, KAL, OUT, PEAT  # noqa: E402

FILM = os.path.join(_REPO_ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "pulau")
DATAJ = os.path.join(FILM, "src", "pulauData.json")
DARAT, TETANGGA, KONSESI, GAMBUT = "#1B2029", "#12161C", "#3A424D", "#3B2A1A"
EXTENT = (108.3, 119.3, -4.6, 7.5)          # Borneo (stops short of Sulawesi)
JPG = dict(pil_kwargs={"quality": 90})


def frame():
    """1920x1080 on soot, map axes in the right 60%."""
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    ax = fig.add_axes([0.40, 0.02, 0.58, 0.96])
    ax.set_facecolor(JELAGA)
    ax.set_xlim(EXTENT[0], EXTENT[1])
    ax.set_ylim(EXTENT[2], EXTENT[3])
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def save(fig, name):
    import matplotlib.pyplot as plt
    os.makedirs(PUB, exist_ok=True)
    p = os.path.join(PUB, name)
    fig.savefig(p, facecolor=JELAGA, **JPG)
    plt.close(fig)
    print(f"  {p}")


def label(ax, x, y, t, size=20, color=KAPUR, ha="center"):
    import matplotlib.patheffects as pe
    ax.annotate(t, (x, y), ha=ha, va="center", fontsize=size, fontweight="bold", color=color,
                fontfamily="DejaVu Sans", path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])


def data():
    import pandas as pd
    J = lambda n: json.load(open(os.path.join(OUT, n)))      # noqa: E731
    m = {(r["treated"], r["matched_on"]): r for r in J("matched.json") if r["test"] == "burn"}
    rob = J("robustness.json")
    seasons = {f"{x['variant'][:4]}|{x['treated']}": x for x in rob if x.get("check") == "R3" and "MCD64" in x["variant"]}
    gpm = {x["treated"]: x for x in rob if x.get("check") == "R2"}
    P = pd.read_csv(os.path.join(OUT, "per_concession_matched.csv"))
    per = {}
    for kind, g in P.groupby("kind"):
        ex = g[g.class_fdr == "excess"]
        per[kind] = {"units": int(len(g)), "excess": int(len(ex)), "excess_pct": 100 * len(ex) / len(g),
                     "burned_km2": float(g.burned_km2.sum()), "excess_km2": float(ex.burned_km2.sum()),
                     "excess_share_pct": 100 * ex.burned_km2.sum() / g.burned_km2.sum()}
    H = pd.read_csv(os.path.join(OUT, "heterogeneity_units.csv")).merge(
        pd.read_csv(os.path.join(DATA, "peat_check_covariates.csv"))[["kind", "id", "peat_share"]]
        .rename(columns={"peat_share": "ps"}), on=["kind", "id"])
    O = H[H.kind == "oil palm"]
    bins = [(-0.01, 0.01, "<1"), (0.01, 0.25, "1–25"), (0.25, 0.5, "25–50"), (0.5, 0.75, "50–75"), (0.75, 1.01, "75–100")]
    peat_bins = [{"label": lab, "units": int(((O.ps > lo) & (O.ps <= hi)).sum()),
                  "excess_pct": 100 * float(O[(O.ps > lo) & (O.ps <= hi)].excess.mean())} for lo, hi, lab in bins]
    het = J("heterogeneity.json")["models"]["oil palm"]["logit"]
    pk = J("peat_depth_checks.json")["oil palm"]
    lp = J("landprep/landprep_tests.json")
    fw = J("fire_weather.json")
    w3 = pd.DataFrame(fw["W3"]).pivot(index="dc_band", columns="tenure", values="per_1000km2_day")
    order = ["0-300", "300-400", "400-500", "500-600", "600-700", "700-2000"]
    w3 = w3.reindex(order)
    nat = {x["label"]: x for x in J("national.json")}
    two = J("two_seasons.json")
    D = {
        "units_total": per["oil palm"]["units"] + per["pulpwood"]["units"],
        "cells_millions": 13.3,
        "matched": {k: {"ratio": m[(k, "+ distance to settlement")]["ratio"],
                        "ci": m[(k, "+ distance to settlement")]["ratio_ci95"],
                        "raw": m[(k, "raw")]["ratio"]} for k in ("oil palm", "pulpwood")},
        "seasons": {y: {k: {"ratio": seasons[f"{y}|{k}"]["ratio"], "ci": seasons[f"{y}|{k}"]["ci"]}
                        for k in ("oil palm", "pulpwood")} for y in ("2015", "2019", "2023")},
        "gpm": {k: {"ratio": gpm[k]["ratio"], "ci": gpm[k]["ci"]} for k in gpm},
        "per_concession": per,
        "peat_bins": peat_bins,
        "null_traits": {k: het[k] for k in ("grouped", "st_location_permit", "rspo_cert_share_10pp")},
        "peat_share_effect": {"bbsdlp": pk["V3 BBSDLP peat share only"]["peat_share_10pp"]["logit"],
                              "gpm": pk["V4 Greifswald peat share only"]["gpm_share_10pp"]["logit"]},
        "landprep": {"planted_burned_pct": 100 * lp["T1"]["2015"]["oil palm"]["treated"],
                     "planted_unburned_pct": 100 * lp["T1"]["2015"]["oil palm"]["control"],
                     "planted_ratio_ci": lp["T1"]["2015"]["oil palm"]["ci"],
                     "cleared_pct": 100 * lp["T2"]["oil palm"]["treated"],
                     "cleared_ctl_pct": 100 * lp["T2"]["oil palm"]["control"]},
        "drought_first_fire": next(x for x in fw["W2"] if x["treated"] == "oil palm" and x["matched_on"] == "all strata"),
        "ignitions_by_dc": {"bands": order, "oil palm": w3["oil palm"].tolist(), "pulpwood": w3["pulpwood"].tolist(),
                            "open": w3["open"].tolist(),
                            "ratio_oil_palm": (w3["oil palm"] / w3["open"]).tolist()},
        "national": {"raw": nat["all land, raw"]["ratio"],
                     "same_drought_lt300": {"ratio": nat["peak DC 0-300"]["ratio"], "ci": nat["peak DC 0-300"]["ci"]},
                     "same_drought_300_400": {"ratio": nat["peak DC 300-400"]["ratio"], "ci": nat["peak DC 300-400"]["ci"]}},
        "rain": two["chirps"],
        "dc_by_latitude": two["dc_by_latitude"],
    }
    os.makedirs(os.path.dirname(DATAJ), exist_ok=True)
    json.dump(D, open(DATAJ, "w"), indent=1, ensure_ascii=False, default=float)
    print(f"  {DATAJ}")
    return D


def maps():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    from shapely.geometry import box
    ne = gpd.read_file(os.path.join(DATA, "ne_countries", "ne_10m_admin_0_countries.zip"))
    bb = box(EXTENT[0], EXTENT[2], EXTENT[1], EXTENT[3])
    idn = ne[ne.ADM0_A3 == "IDN"].clip(bb).explode(index_parts=False)
    b_ = idn.geometry.bounds
    idn = idn[~((b_.minx > 118.6) & (b_.maxy < 0.5))]          # west Sulawesi, not Borneo
    nbr = ne[ne.ADM0_A3.isin(["MYS", "BRN"])].clip(bb)
    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]].reset_index(drop=True)
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    P = pd.read_csv(os.path.join(OUT, "per_concession_matched.csv"))
    geo = lambda k, i: (op if k == "oil palm" else hti).geometry.iloc[i - 1]      # noqa: E731
    P["geometry"] = [geo(k, i) for k, i in zip(P.kind, P.id)]
    U = gpd.GeoDataFrame(P, crs=4326)
    U["geometry"] = U.geometry.make_valid()
    from ketapang_fire_origin import FOUR
    four = U[U.label.fillna("").str.contains("|".join(FOUR.values()), case=False)]

    def base(ax):
        nbr.plot(ax=ax, color=TETANGGA, edgecolor="#2A313B", linewidth=0.8)
        idn.plot(ax=ax, color=DARAT, edgecolor="#2A313B", linewidth=0.8)
        label(ax, 114.0, 5.3, "MALAYSIA", 18, ABU)
        label(ax, 112.9, 0.6, "KALIMANTAN", 22, ABU)

    fig, ax = frame()
    base(ax)
    U.plot(ax=ax, color=KONSESI, edgecolor="none")
    save(fig, "peta_semua.jpg")

    fig, ax = frame()
    base(ax)
    U[U.class_fdr != "excess"].plot(ax=ax, color=KONSESI, edgecolor="none")
    U[U.class_fdr == "excess"].plot(ax=ax, color=BARA, edgecolor="none")
    c = four.union_all().centroid
    ax.add_patch(__import__("matplotlib").patches.Circle((c.x, c.y), 0.45, fill=False, edgecolor=NYALA, linewidth=3))
    label(ax, c.x - 0.6, c.y - 0.75, "Ketapang", 20, NYALA, ha="right")
    save(fig, "peta_berlebih.jpg")

    # peak DC, Jul-Oct 2026
    import matplotlib.colors as mc
    z = np.load(os.path.join(DATA, "dc_2026.npz"), allow_pickle=True)
    dc, dates = z["dc"], pd.to_datetime(z["dates"])
    x0, yt, st = z["grid"]
    peak = dc[(dates >= "2026-07-01") & (dates < "2026-11-01")].max(axis=0)
    land = pd.concat([idn, nbr]).union_all()
    sea = gpd.GeoSeries([bb.difference(land)], crs=4326)
    cmap = mc.LinearSegmentedColormap.from_list("kemarau", ["#1B2A3A", "#3A424D", "#9A6530", BARA, NYALA])
    fig, ax = frame()
    gpd.GeoSeries([land], crs=4326).plot(ax=ax, color=DARAT, zorder=0)       # north of the grid: no data
    # stage_dc fills sea cells with the nearest land value, so bilinear smoothing does not
    # bleed dark into the coast; the sea is painted over afterwards for a true coastline
    ax.imshow(peak, extent=(x0, x0 + peak.shape[1] * st, yt - peak.shape[0] * st, yt), cmap=cmap,
              vmin=100, vmax=950, interpolation="bilinear", zorder=1)
    sea.plot(ax=ax, color=JELAGA, zorder=2)
    nbr.boundary.plot(ax=ax, color=KAPUR, linewidth=1.4, zorder=3)
    label(ax, 114.0, 5.6, "MALAYSIA", 18, KAPUR)
    label(ax, 117.3, 5.5, f"tanpa data (> {yt:.1f}° LU)", 13, ABU)
    label(ax, 113.3, -2.2, "KALIMANTAN", 22, KAPUR)
    cax = fig.add_axes([0.43, 0.70, 0.12, 0.018])          # open sea west of Sarawak, clear of the source line
    cb = fig.colorbar(__import__("matplotlib").cm.ScalarMappable(norm=mc.Normalize(100, 950), cmap=cmap), cax=cax,
                      orientation="horizontal")
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=ABU, labelsize=14)
    cb.set_ticks([100, 300, 500, 700, 900])
    cax.set_title("Drought Code, puncak Jul–Okt 2026", color=ABU, fontsize=15, loc="left")
    save(fig, "peta_kemarau.jpg")


if __name__ == "__main__":
    print("pulauData.json")
    data()
    print("maps")
    maps()
