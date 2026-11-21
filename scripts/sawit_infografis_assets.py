"""Assets for the "where will oil palm go next?" infographic (video/narasi-karhutla, InfografisSawit).

Reads the outputs of scripts/kalimantan_palm_expansion.py (forecast, map stages) and
scripts/kalimantan_fire_factors.py (forecast stage) and writes:

  public/sawit/peta_sawit_ig.jpg   palm by 2021, top 10% palm-conversion risk, top 10% El Nino 2027 fire
                                   risk, and their overlap, Kalimantan, dark style of the fire films
  src/sawitData.json               every figure the infographic shows

    ~/miniforge3/bin/python -I scripts/sawit_infografis_assets.py
"""
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output", "fire", "kalimantan_palm_panel")
PANEL = os.path.join(ROOT, "data", "kalimantan_panel")
NE = os.path.join(ROOT, "data", "kalimantan", "ne_countries", "ne_10m_admin_0_countries.zip")
FILM = os.path.join(ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "sawit")
JELAGA, DARAT, TETANGGA, KAPUR, ABU = "#0A0C0F", "#1B2029", "#12161C", "#E8EBEE", "#7E8792"
KELAS = {"palm": "#6B7480", "risk": "#3FBF7F", "fire": "#9A6530", "both": "#FF5A1F"}
EXTENT = (108.4, 119.4, -4.4, 4.6)          # Indonesian Kalimantan
KM2 = 0.4633127165 ** 2


def data():
    F = json.load(open(os.path.join(SRC, "palm_expansion_forecast.json")))
    M = json.load(open(os.path.join(SRC, "palm_expansion_model.json")))
    O = json.load(open(os.path.join(SRC, "palm_fire_overlap.json")))
    imp = {}
    import csv
    for r in csv.DictReader(open(os.path.join(SRC, "palm_expansion_importance.csv"))):
        imp[r["group"]] = float(r["perm_pr_auc_loss"])
    f = F["forecast_2022_2024"]
    t = f["top10"]
    tot = f["expected_new_palm_km2"]
    exp = lambda k, c: t[k][c]["expected_new_palm_km2"]  # noqa: E731
    hc = F["hindcast"]
    d = {
        "expected_km2": tot,
        "observed_km2": f["observed_new_palm_km2_per_3yr"],
        "near5_pct": round(t["distance_to_palm"]["<=1 km"]["share_of_top10_pct"]
                           + t["distance_to_palm"]["1-5 km"]["share_of_top10_pct"]),
        "outside_conc_pct": round(100 * exp("concession", "none") / tot),
        "apl_pct": round(100 * exp("status", "APL") / tot),
        "hp_km2": exp("status", "HP"), "hp_pct": round(100 * exp("status", "HP") / tot),
        "peat_km2": exp("soil", "peat"), "intact_km2": exp("forest_2021", "intact"),
        "hindcast": {k: {"model": v["model"]["top10"], "distance": v["baseline_distance_to_palm"]["top10"],
                         "km2": v["converted_km2"]} for k, v in hc.items()},
        "pr_auc": round(M["spatial_block_cv"]["pr_auc"], 2), "base_rate_pct": M["base_rate_pct"],
        "factors": [{"k": k, "v": round(v, 3)} for k, v in sorted(imp.items(), key=lambda x: -x[1])],
        "overlap": {"both_km2": O["both_km2"], "palm_top10_km2": O["top10_palm_km2"],
                    "pct_of_palm_top10": O["pct_of_palm_top10_also_fire_top10"],
                    "apl_pct": O["both_by_status_pct"]["APL"], "hp_pct": O["both_by_status_pct"]["HP"],
                    "peat_pct": O["both_on_peat_pct"]},
        "forest_loss_in_top10_pct": f["forest_loss_2022_2024_in_top10_pct"],
        "warna": KELAS,
    }
    json.dump(d, open(os.path.join(FILM, "src", "sawitData.json"), "w"), indent=1, ensure_ascii=False)
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
    with rasterio.open(os.path.join(SRC, "palm_expansion_risk.tif")) as ds:
        pp, tr, crs = ds.read(1), ds.transform, ds.crs
    with rasterio.open(os.path.join(SRC, "fire_risk_2027.tif")) as ds:
        pf = ds.read([i + 1 for i, s in enumerate(ds.descriptions) if s and "dry" in s][0])
    with rasterio.open(os.path.join(PANEL, "palm.tif")) as ds:
        names = list(ds.descriptions)
        palm = (ds.read(names.index("ind_2021") + 1).astype(np.int16) + ds.read(names.index("sh_2021") + 1)) >= 50
    land = pf >= 0
    rs = pp >= 0
    top_p = rs & (pp >= np.quantile(pp[rs], 0.9))
    top_f = land & (pf >= np.quantile(pf[land], 0.9))
    cls = np.zeros(pp.shape, np.uint8)
    cls[land] = 1
    cls[palm & land] = 2
    cls[top_f & ~top_p] = 4
    cls[top_p & ~top_f] = 3
    cls[top_p & top_f] = 5
    print("both km2 (check):", round(float((top_p & top_f).sum() * KM2)))
    st = 0.006
    W, H = int((EXTENT[1] - EXTENT[0]) / st), int((EXTENT[3] - EXTENT[2]) / st)
    dt = rasterio.transform.from_origin(EXTENT[0], EXTENT[3], st, st)
    dst = np.zeros((H, W), np.uint8)
    reproject(cls, dst, src_transform=tr, src_crs=crs, src_nodata=0, dst_transform=dt, dst_crs="EPSG:4326",
              dst_nodata=0, resampling=Resampling.mode)
    ne = gpd.read_file(NE)
    bb = box(EXTENT[0], EXTENT[2], EXTENT[1], EXTENT[3])
    idn = ne[ne.ADM0_A3 == "IDN"].clip(bb).explode(index_parts=False)
    b_ = idn.geometry.bounds
    idn = idn[~((b_.minx > 118.6) & (b_.maxy < 0.5))]               # west Sulawesi, not Borneo
    nbr = ne[ne.ADM0_A3.isin(["MYS", "BRN"])].clip(bb)
    darat = features.rasterize([(g, 1) for g in idn.geometry], out_shape=dst.shape, transform=dt, all_touched=True)
    dst[darat == 0] = 0
    cmap = mc.ListedColormap([JELAGA, DARAT, KELAS["palm"], KELAS["risk"], KELAS["fire"], KELAS["both"]])
    fig = plt.figure(figsize=(9.72, 9.72 * H / W), dpi=100, facecolor=JELAGA)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(JELAGA)
    nbr.plot(ax=ax, color=TETANGGA, edgecolor="#2A313B", linewidth=0.8, zorder=0)
    idn.plot(ax=ax, color=DARAT, edgecolor="none", zorder=0)
    ax.imshow(np.ma.masked_equal(dst, 0), extent=(EXTENT[0], EXTENT[1], EXTENT[2], EXTENT[3]), cmap=cmap,
              vmin=0, vmax=5, interpolation="nearest", zorder=1)
    ax.set_xlim(EXTENT[0], EXTENT[1]); ax.set_ylim(EXTENT[2], EXTENT[3]); ax.set_aspect("equal"); ax.axis("off")
    ax.annotate("MALAYSIA", (114.6, 3.6), ha="center", va="center", fontsize=17, fontweight="bold", color=ABU,
                path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])
    x0, y0 = 108.8, -4.1                                             # 200 km scale bar at ~-4 deg
    dx = 200 / 111.0
    ax.plot([x0, x0 + dx], [y0, y0], color=KAPUR, lw=3)
    ax.annotate("200 km", (x0 + dx / 2, y0 + 0.18), ha="center", fontsize=12, color=KAPUR)
    os.makedirs(PUB, exist_ok=True)
    fig.savefig(os.path.join(PUB, "peta_sawit_ig.jpg"), facecolor=JELAGA, pil_kwargs={"quality": 92})
    plt.close(fig)
    print(f"  peta_sawit_ig.jpg ({W}x{H} cells -> {int(9.72 * 100)}x{int(9.72 * 100 * H / W)} px)")


if __name__ == "__main__":
    data()
    peta()
