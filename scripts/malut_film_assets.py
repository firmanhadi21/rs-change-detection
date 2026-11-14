#!/usr/bin/env python3
"""Assets for the North Maluku forest film ("Hutan" / "HutanEN") and infographic.

Reads output/malut_forest/ (Earth Engine runs, Nov 2026):
  stats.json            Hansen GFC v1.13 loss 2001-2025 (tree cover >=30% in 2000) by regency and year,
                        WRI/Google 1 km dominant-driver classes (2001-2024), Turubanova primary forest
  open_ground_dw.json   Dynamic World annual-mode bare + built area, Weda Bay box, Sagea box, 3.7 km disc
  sagea_near.json       open ground near the Sagea Lake shore (Dynamic World), lake area from S2 MNDWI
  province_grid.npz     ~300 m grid: land, forest-2000 fraction, loss fraction per year
  frames/{wide,close}/  annual true-colour composites (Landsat; Sentinel-2 from 2019 for the close-up)

Writes into video/narasi-karhutla:
  public/hutan/peta_provinsi.jpg       province map, loss coloured by period, text column left free
  public/hutan/weda/<year>.jpg         Weda Bay timelapse frames (1150 px wide)
  public/hutan/sagea/<year>.jpg        Sagea Lake close-up frames
  src/hutanData.json                   every figure the film and the infographic show or speak

    conda run -n base python scripts/malut_film_assets.py
"""
import json
import os
import glob

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "output", "malut_forest")
FILM = os.path.join(ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "hutan")
JELAGA, DARAT, KAPUR, ABU = "#0A0C0F", "#1B2029", "#E8EBEE", "#7E8792"
BARA, NYALA = "#FF5A1F", "#FFB020"
HUTAN = "#1E3A2B"
MINING = "Hard commodities (mining, energy)"


def data():
    S = json.load(open(os.path.join(SRC, "stats.json")))
    O = json.load(open(os.path.join(SRC, "open_ground_dw.json")))
    N = json.load(open(os.path.join(SRC, "sagea_near.json")))
    P = S["province"]
    years = list(range(2001, 2026))
    by = [round(P["loss_by_year_ha"][str(y)]) for y in years]
    drv = P["loss_by_driver_ha"]
    attributed = sum(drv.values())
    order = ["Permanent agriculture", "Shifting cultivation", "Logging", "Wildfire", MINING,
             "Settlements & infrastructure", "Other natural disturbances"]
    dy = P["loss_by_driver_year_ha"]
    mining_year = [round(dy[MINING].get(str(y), 0)) for y in range(2001, 2025)]
    m_early = sum(mining_year[:18]); m_late = sum(mining_year[18:])          # 2001-18 vs 2019-24
    loss_early = sum(by[:18]); loss_late = sum(by[18:24])
    reg = []
    for n, r in S["regencies"].items():
        reg.append({"nama": n, "loss": round(r["loss_total_ha"]), "f2000": round(r["forest2000_ha"]),
                    "pct": round(100 * r["loss_total_ha"] / r["forest2000_ha"], 1),
                    "mining": round(r["loss_by_driver_ha"].get(MINING, 0))})
    reg.sort(key=lambda x: -x["loss"])
    og = {k: {y: round(O[str(y)][k]["bare"] + O[str(y)][k]["built"]) for y in range(2016, 2027)}
          for k in ("weda", "sagea", "lake3km")}
    D = {
        "loss_total": round(P["loss_total_ha"]),
        "forest2000": round(P["forest2000_ha"]),
        "loss_pct": round(100 * P["loss_total_ha"] / P["forest2000_ha"], 1),
        "primary2001": round(P["primary2001_ha"]),
        "loss_primary": round(P["loss_primary_ha"]),
        "tahun": years, "loss_tahun": by,
        "puncak": {"tahun": years[int(np.argmax(by))], "ha": max(by)},
        "drivers": [{"k": k, "ha": round(drv.get(k, 0)), "pct": round(100 * drv.get(k, 0) / attributed, 1)} for k in order],
        "driver_year_by_class": {k: [round(dy.get(k, {}).get(str(y), 0)) for y in range(2001, 2025)] for k in order},
        "mining_year": mining_year,
        "mining": {"early_ha": m_early, "early_per_yr": round(m_early / 18), "late_ha": m_late, "late_per_yr": round(m_late / 6),
                   "early_share_pct": round(100 * m_early / loss_early, 1), "late_share_pct": round(100 * m_late / loss_late, 1),
                   "peak_year": 2001 + int(np.argmax(mining_year)), "peak_ha": max(mining_year)},
        "kabupaten": reg,
        "open_ground": og,
        "weda_box": S["weda_box"]["loss_total_ha"],
        "sagea": {"lake_ha": N["lake_ha"],
                  "within_1km": {y: N["years"][str(y)]["open_within_1km_ha"] for y in range(2016, 2027)},
                  "nearest_m_2026": N["years"]["2026"]["nearest_open_m"],
                  "nearest_m_2025": N["years"]["2025"]["nearest_open_m"]},
    }
    os.makedirs(os.path.join(FILM, "src"), exist_ok=True)
    json.dump(D, open(os.path.join(FILM, "src", "hutanData.json"), "w"), indent=1, ensure_ascii=False)
    return D


def peta():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    g = np.load(os.path.join(SRC, "province_grid.npz"))
    x0, x1, y0, y1 = g["extent"]
    from rasterio import features
    from rasterio.transform import from_bounds
    from shapely.geometry import shape
    f = g["f2000"] / 250.0
    loss = {y: g[f"l{y:02d}"] / 250.0 for y in range(1, 26)}
    H, W = f.shape
    reg = json.load(open(os.path.join(SRC, "regencies.geojson")))["features"]
    prov = features.rasterize([(shape(r["geometry"]), 1) for r in reg], out_shape=(H, W),
                              transform=from_bounds(x0, y0, x1, y1, W, H))
    land = (g["land"] / 250.0) * prov
    img = np.zeros((H, W, 3))
    img[:] = to_rgb(JELAGA)
    base = np.array(to_rgb(DARAT)); hut = np.array(to_rgb(HUTAN))
    img = np.where(land[..., None] > 0.3, base + (hut - base) * np.clip(f, 0, 1)[..., None], img)
    for (a, b), col in [((1, 10), "#9AA3AD"), ((11, 20), NYALA), ((21, 25), BARA)]:
        frac = sum(loss[y] for y in range(a, b + 1))
        al = (np.clip(frac * 2.2, 0, 0.95) * (land > 0.3))[..., None]
        img = img * (1 - al) + np.array(to_rgb(col)) * al
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    ax = fig.add_axes([0.44, 0.02, 0.54, 0.96]); ax.set_facecolor(JELAGA)
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation="bilinear")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")
    import matplotlib.patheffects as pe
    lab = [(127.75, 1.55, "Halmahera"), (128.32, 2.25, "Morotai"), (127.36, 0.78, "Ternate–Tidore"),
           (127.5, -1.47, "Obi"), (124.75, -1.62, "Taliabu"), (125.95, -2.05, "Sula"), (127.7, -0.62, "Bacan")]
    for x, y, t in lab:
        ax.annotate(t, (x, y), ha="center", va="center", fontsize=17, color=KAPUR, fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])
    ax.plot([127.80, 128.30, 128.30, 127.80, 127.80], [0.30, 0.30, 0.75, 0.75, 0.30], color=KAPUR, lw=1.6)
    ax.annotate("Teluk Weda", (128.33, 0.52), ha="left", va="center", fontsize=16, color=KAPUR,
                path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])
    os.makedirs(PUB, exist_ok=True)
    fig.savefig(os.path.join(PUB, "peta_provinsi.jpg"), facecolor=JELAGA, pil_kwargs={"quality": 90})
    plt.close(fig)
    print("  peta_provinsi.jpg")


def bingkai():
    from PIL import Image
    for box, nama in [("wide", "weda"), ("close", "sagea")]:
        out = os.path.join(PUB, nama); os.makedirs(out, exist_ok=True)
        for p in sorted(glob.glob(os.path.join(SRC, "frames", box, "*.png"))):
            im = Image.open(p).convert("RGB")
            h = 1080; w = round(im.width * h / im.height)
            im.resize((w, h), Image.LANCZOS).save(os.path.join(out, os.path.basename(p)[:-4] + ".jpg"), quality=88)
        print(f"  {nama}: {len(os.listdir(out))} frames")


if __name__ == "__main__":
    D = data()
    print(json.dumps({k: D[k] for k in ("loss_total", "loss_pct", "loss_primary", "puncak", "mining")}, indent=1))
    peta()
    bingkai()
