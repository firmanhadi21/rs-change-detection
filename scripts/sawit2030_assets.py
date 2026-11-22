"""Assets for the 2030 oil-palm scenario film and infographic (video/narasi-karhutla, Sawit2030.tsx).

Reads the outputs of scripts/kalimantan_palm_expansion.py --stage dynamic (version-1 model stepped forward
in 3-year periods from the end of 2021) and scripts/kalimantan_palm_ca.py (cellular-automaton and
ANN + CA-Markov comparisons), and writes:

  src/sawit2030Data.json            every figure the film and the infographic show or speak
  public/sawit2030/film_dasar.jpg   1920x1080 base map, Kalimantan in the right ~56%
  public/sawit2030/film_sawit.png   oil palm by 2021 (transparent layer, same frame)
  public/sawit2030/film_{slow,boom,legal}_{1,2,3}.png   new palm per scenario and period (2022-24, 25-27, 28-30)
  public/sawit2030/peta_ig.jpg      the three scenarios side by side for the infographic

    ~/miniforge3/bin/python -I scripts/sawit2030_assets.py
"""
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output", "fire", "kalimantan_palm_panel")
PANEL = os.path.join(ROOT, "data", "kalimantan_panel")
NE = os.path.join(ROOT, "data", "kalimantan", "ne_countries", "ne_10m_admin_0_countries.zip")
FILM = os.path.join(ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "sawit2030")
JELAGA, DARAT, TETANGGA, KAPUR, ABU = "#0A0C0F", "#1B2029", "#12161C", "#E8EBEE", "#7E8792"
WARNA = {"palm": "#6B7480", "p1": "#2E9E63", "p2": "#3FBF7F", "p3": "#A6E8C3"}
EXTENT = (108.4, 119.4, -4.4, 4.6)          # Indonesian Kalimantan, as public/sawit/
SKEN = ("slow", "boom", "legal")
GAIN = 2.0                                  # layer opacity = min(1, GAIN x share of the display pixel)


def data():
    F = json.load(open(os.path.join(SRC, "palm_dynamic_forecast.json")))
    C = json.load(open(os.path.join(SRC, "palm_ca_calibration.json")))["validation_2016_2019"]
    A = json.load(open(os.path.join(SRC, "palm_ca_ann_markov_calibration.json")))["validation_2016_2019"]
    t = F["test_2010_2016"]
    sk = {}
    for s in SKEN:
        x = F["scenarios"][s]
        sk[s] = {"per_yr_km2": x["demand_km2_per_yr"], "total_km2": x["new_palm_2022_2030_km2"],
                 "by_period_km2": list(x["by_period_km2"].values()),
                 "peat_pct": x["pct_on_peat"], "intact_pct": x["pct_in_intact_forest_2021"],
                 "outside_conc_pct": x["pct_outside_oil_palm_concessions"],
                 "fire_top10_pct": x["pct_in_2027_fire_top10"],
                 "apl_pct": x["pct_by_status"]["APL"], "hp_pct": x["pct_by_status"]["HP"],
                 "kawasan_pct": round(sum(v for k, v in x["pct_by_status"].items()
                                          if k in ("HP", "HPT", "HL", "KSA/KPA")), 1),
                 "same_cells_as_ca_pct": x["pct_also_new_in_ca_version2"]}
        sk[s]["intact_km2"] = round(sk[s]["total_km2"] * sk[s]["intact_pct"] / 100)
        sk[s]["peat_km2"] = round(sk[s]["total_km2"] * sk[s]["peat_pct"] / 100)
    d = {
        "years": [2022, 2030],
        "scenarios": sk,
        "test_2010_2016": {"one_shot": t["static_one_shot"]["2010_2016"]["fom"], "stepped": t["dynamic"]["2010_2016"]["fom"],
                           "ca": t["ca_version2"]["2010_2016"]["fom"], "stepped_second_period": t["dynamic"]["period_2014_2016"]["fom"]},
        "test_2016_2019": {"static": C["static_model_with_closeness"]["fom"], "ca": C["ca"]["fom_mean"],
                           "ann_ca_markov": A["ca"]["fom_mean"], "random": C["random_expected_fom"]},
        "markov_error_pct": A["markov_quantity_check"]["error_pct"],
        "markov_ratio": round(sum(A["markov_quantity_check"]["predicted_cells_per_yr"])
                              / sum(A["markov_quantity_check"]["observed_cells_per_yr"]), 1),
        "warna": WARNA,
    }
    json.dump(d, open(os.path.join(FILM, "src", "sawit2030Data.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(d, indent=1))
    return d


def peta():
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mc
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    import rasterio
    from rasterio import features
    from rasterio.warp import Resampling, reproject
    from shapely.geometry import box
    with rasterio.open(os.path.join(SRC, "palm_dynamic_2030.tif")) as ds:
        names = [x.split(" ")[0].replace("period_converted_", "") for x in ds.descriptions]
        W3 = {n: ds.read(i + 1) for i, n in enumerate(names)}
        tr, crs = ds.transform, ds.crs
    with rasterio.open(os.path.join(PANEL, "palm.tif")) as ds:
        nm = list(ds.descriptions)
        palm = (ds.read(nm.index("ind_2021") + 1).astype(np.int16) + ds.read(nm.index("sh_2021") + 1)) >= 50
    land = W3["slow"] >= 0

    def ke_geo(cls, st, how):
        Wd, Hd = int((EXTENT[1] - EXTENT[0]) / st), int((EXTENT[3] - EXTENT[2]) / st)
        dt = rasterio.transform.from_origin(EXTENT[0], EXTENT[3], st, st)
        dst = np.zeros((Hd, Wd), np.uint8)
        reproject(cls, dst, src_transform=tr, src_crs=crs, src_nodata=0, dst_transform=dt, dst_crs="EPSG:4326",
                  dst_nodata=0, resampling=how)
        return dst, dt

    ne = gpd.read_file(NE)
    bb = box(EXTENT[0], EXTENT[2], EXTENT[1], EXTENT[3])
    idn = ne[ne.ADM0_A3 == "IDN"].clip(bb).explode(index_parts=False)
    b_ = idn.geometry.bounds
    idn = idn[~((b_.minx > 118.6) & (b_.maxy < 0.5))]               # west Sulawesi, not Borneo
    nbr = ne[ne.ADM0_A3.isin(["MYS", "BRN"])].clip(bb)
    ext = (EXTENT[0], EXTENT[1], EXTENT[2], EXTENT[3])
    os.makedirs(PUB, exist_ok=True)

    def batas(a):
        a.set_xlim(EXTENT[0], EXTENT[1]); a.set_ylim(EXTENT[2], EXTENT[3]); a.set_aspect("equal"); a.axis("off")

    # ---- film: base + transparent layers on one 1920x1080 frame (same frame as public/sawit/film_*)
    def kanvas(transparan):
        f = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor="none" if transparan else JELAGA)
        a = f.add_axes([0.42, 0.095, 0.56, 0.79])
        a.set_facecolor("none" if transparan else JELAGA)
        return f, a

    fig, ax = kanvas(False)
    nbr.plot(ax=ax, color=TETANGGA, edgecolor="#2A313B", linewidth=0.8, zorder=0)
    idn.plot(ax=ax, color=DARAT, edgecolor="none", zorder=0)
    batas(ax)
    ax.annotate("MALAYSIA", (114.6, 3.6), ha="center", va="center", fontsize=18, fontweight="bold", color=ABU,
                path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])
    x0, y0, dx = 117.0, -4.1, 200 / 111.0
    ax.plot([x0, x0 + dx], [y0, y0], color=KAPUR, lw=3)
    ax.annotate("200 km", (x0 + dx / 2, y0 + 0.18), ha="center", fontsize=13, color=KAPUR)
    fig.savefig(os.path.join(PUB, "film_dasar.jpg"), facecolor=JELAGA, pil_kwargs={"quality": 92})
    plt.close(fig)

    def frac(mask, st):
        """Share of each display pixel (st degrees) covered by the mask, so areas read true at any zoom."""
        Wd, Hd = int((EXTENT[1] - EXTENT[0]) / st), int((EXTENT[3] - EXTENT[2]) / st)
        dt = rasterio.transform.from_origin(EXTENT[0], EXTENT[3], st, st)
        dst = np.zeros((Hd, Wd), np.float32)
        reproject(mask.astype(np.float32), dst, src_transform=tr, src_crs=crs, src_nodata=-1, dst_transform=dt,
                  dst_crs="EPSG:4326", dst_nodata=0, resampling=Resampling.average)
        return dst

    def rgba(f, warna):
        out = np.zeros(f.shape + (4,), np.float32)
        out[..., :3] = mc.to_rgb(warna)
        out[..., 3] = np.clip(GAIN * f, 0, 1)          # same gain for old and new palm
        return out

    st_film = 11.0 / 1075                               # one display pixel of the film map axes

    def lapis(mask, warna, nama):
        fig, ax = kanvas(True)
        ax.imshow(rgba(frac(mask, st_film), warna), extent=ext, interpolation="nearest")
        batas(ax)
        fig.savefig(os.path.join(PUB, f"film_{nama}.png"), transparent=True)
        plt.close(fig)

    lapis(palm & land, WARNA["palm"], "sawit")
    for s in SKEN:
        for k in (1, 2, 3):
            lapis(W3[s] == k, WARNA[f"p{k}"], f"{s}_{k}")
    print("  film_dasar.jpg, film_sawit.png, film_{slow,boom,legal}_{1,2,3}.png (1920x1080)")

    # ---- infographic: the three scenarios side by side, all new palm 2022-2030 in one colour
    dpi = 200
    fig = plt.figure(figsize=(9.72, 2.9), dpi=dpi, facecolor=JELAGA)
    st = 11.0 / (9.72 * dpi / 3)
    fp = rgba(frac(palm & land, st), WARNA["palm"])
    for i, s in enumerate(SKEN):
        ax = fig.add_axes([i / 3 + 0.004, 0.0, 1 / 3 - 0.008, 1.0])
        ax.set_facecolor(JELAGA)
        nbr.plot(ax=ax, color=TETANGGA, edgecolor="#2A313B", linewidth=0.5, zorder=0)
        idn.plot(ax=ax, color=DARAT, edgecolor="none", zorder=0)
        ax.imshow(fp, extent=ext, interpolation="nearest", zorder=1)
        ax.imshow(rgba(frac(W3[s] > 0, st), WARNA["p2"]), extent=ext, interpolation="nearest", zorder=2)
        batas(ax)
    fig.savefig(os.path.join(PUB, "peta_ig.jpg"), facecolor=JELAGA, pil_kwargs={"quality": 92})
    plt.close(fig)
    print("  peta_ig.jpg (1944x580)")


if __name__ == "__main__":
    data()
    peta()
