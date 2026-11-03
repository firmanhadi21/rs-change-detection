#!/usr/bin/env python3
"""Maps, panels and figures for Part 2 of the concessions film ("Mengapa
lebih parah?"): why the four Ketapang concessions burned worse.

Reads what the Ketapang analysis wrote (output/fire/ketapang_origin and its
landprep/, danger/, excess/, planet/ folders) and writes, into
video/narasi-karhutla:

  public/telusur/peta_api.png      2026 burn, the four outlined, ignitions
  public/telusur/planet.png        PlanetScope before the fire: 3 burned
                                   windows and a planted-palm block
  public/telusur/peta_izin.png     PT AM against the pulpwood (HTI) permits
  public/telusur/peta_gambut.png   peat (own RF map) under the burn
  src/telusurData.json             every figure the film shows or speaks

Same rules as Part 1 (kalimantan_concession_film_assets.py): 1920x1080 on
the film's soot ground, map in the right column, concessions by acronym.

    conda run -n base python scripts/ketapang_film2_assets.py
"""

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
sys.path.insert(0, _REPO_ROOT)
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import (CONC, FOUR, OUT as O, BUF_DEG, SEASON,  # noqa: E402
                                  PEAT_OWN, own_peat_on_grid)
from kalimantan_concession_film_assets import (JELAGA, KAPUR, BARA, NYALA,  # noqa: E402
                                               ABU, KONSESI, ucap)

FILM = os.path.join(_REPO_ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "telusur")
GAMBUT = "#9A6530"
DARAT = "#1B2029"
STRIDE = 3                      # 25 m -> 75 m for drawing
PEAT_FILM = "rf"                # peat source for the film: rf | bbsdlp | old


def load():
    import geopandas as gpd
    import numpy as np
    import rasterio
    with rasterio.open(os.path.join(O, "landcover_burned.tif")) as ds:
        lc, burned, tr = ds.read(1), ds.read(2).astype(bool), ds.transform
    conc = gpd.read_file(CONC).to_crs(4326)
    rows = []
    for acr, name in FOUR.items():
        s = conc[conc.company.str.contains(name, case=False, na=False)]
        rows.append({"acr": acr, "geometry": s.geometry.iloc[0]})
    conc4 = gpd.GeoDataFrame(rows, crs=4326)
    return lc, burned, tr, conc4


def figure(extent):
    """Soot frame with an axes box in the right 62%, aspect kept, clear of the
    header (y<130 px) and the source line (y>960 px)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x0, x1, y0, y1 = extent
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    bw, bh = 0.62, 0.72
    aspect = (x1 - x0) / (y1 - y0) * (10.8 / 19.2)
    ww, hh = (bw, bw / aspect) if aspect > bw / bh else (bh * aspect, bh)
    ax = fig.add_axes([0.97 - ww, 0.5 - hh / 2, ww, hh])
    ax.set_facecolor(JELAGA)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.axis("off")
    return fig, ax


def label(ax, x, y, t, size=24):
    import matplotlib.patheffects as pe
    ax.annotate(t, (x, y), ha="center", va="center", fontsize=size,
                fontweight="bold", color=KAPUR, fontfamily="DejaVu Sans",
                path_effects=[pe.withStroke(linewidth=6, foreground=JELAGA)])


def save(fig, name):
    import matplotlib.pyplot as plt
    p = os.path.join(PUB, name)
    fig.savefig(p, facecolor=JELAGA)
    plt.close(fig)
    print(f"Saved: {p}")


def base_rgb(lc, burned, peat=None):
    import numpy as np
    from matplotlib.colors import to_rgb
    land = lc[::STRIDE, ::STRIDE] < 255
    b = burned[::STRIDE, ::STRIDE]
    img = np.zeros(land.shape + (3,))
    img[:] = to_rgb(JELAGA)
    img[land] = to_rgb(DARAT)
    if peat is not None:
        img[peat[::STRIDE, ::STRIDE] & land] = to_rgb(GAMBUT) * np.array(0.55)
    img[b & land] = to_rgb(BARA)
    return img


def main():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    os.makedirs(PUB, exist_ok=True)
    lc, burned, tr, conc4 = load()
    h, w = lc.shape
    full = (tr.c, tr.c + w * tr.a, tr.f + h * tr.e, tr.f)
    x0, y0, x1, y1 = conc4.total_bounds
    ext = (x0 - 0.07, x1 + 0.07, y0 - 0.06, y1 + 0.06)

    def outlines(ax, lw=1.8):
        conc4.boundary.plot(ax=ax, color=KAPUR, lw=lw)
        for _, r in conc4.iterrows():
            p = r.geometry.representative_point()
            label(ax, p.x, p.y, r.acr)

    # ---- ignitions
    ign = pd.read_csv(os.path.join(O, "ignitions.csv"))
    ign = ign[ign.month.between(*SEASON)]
    fig, ax = figure(ext)
    ax.imshow(base_rgb(lc, burned), extent=full, interpolation="nearest")
    out_ = ign[~ign.in_four]
    in_ = ign[ign.in_four]
    ax.scatter(out_.lon, out_.lat, s=16, c=ABU, alpha=0.55, lw=0)
    ax.scatter(in_.lon, in_.lat, s=46, c=NYALA, edgecolors=JELAGA, lw=0.8)
    outlines(ax)
    save(fig, "peta_api.png")

    # ---- peat
    x_0, y_0, x_1, y_1 = x0 - BUF_DEG, y0 - BUF_DEG, x1 + BUF_DEG, y1 + BUF_DEG
    # the final field-weighted RF (peat_rf_gee.py); the team's old 50 m map
    # scored 36% at field points and calls 2.8x the BBSDLP peat area
    import ketapang_excess_burn as XB
    XB.PEAT_SRC = PEAT_FILM
    peat = XB.peat_on_grid((x_0, y_0, x_1, y_1), tr, lc.shape) & (lc < 255)
    fig, ax = figure(ext)
    ax.imshow(base_rgb(lc, burned, peat), extent=full, interpolation="nearest")
    outlines(ax)
    save(fig, "peta_gambut.png")

    # ---- PT AM and the pulpwood permits
    hti = gpd.read_file(os.path.join(O, "hti_wood_fibre_aoi.gpkg"))
    am = conc4[conc4.acr == "PT AM"]
    ax0, ay0, ax1, ay1 = am.total_bounds
    ext_am = (ax0 - 0.05, ax1 + 0.05, ay0 - 0.05, ay1 + 0.05)
    fig, ax = figure(ext_am)
    ax.imshow(base_rgb(lc, burned), extent=full, interpolation="nearest")
    hti.plot(ax=ax, facecolor="none", edgecolor="#5FA8D3", hatch="///", lw=1.2)
    am.boundary.plot(ax=ax, color=KAPUR, lw=2.4)
    p = am.geometry.iloc[0].representative_point()
    label(ax, p.x, p.y, "PT AM", 30)
    save(fig, "peta_izin.png")

    # ---- PlanetScope before the fire: three burned windows + palm control
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ketapang_planet_check import OUT as PLANET, read_ps, rgb
    plan = {s["site"]: s for s in json.load(open(os.path.join(PLANET, "plan.json")))}
    for berkas, palm_label in (("planet.png", "kebun sawit"), ("planet_en.png", "oil palm")):
        planet_panel(plan, read_ps, rgb, berkas, palm_label)

    data_json()
    return 0


def planet_panel(plan, read_ps, rgb, berkas, palm_label):
    import matplotlib.pyplot as plt
    tiles = [("SKM-unplanted", "PT SKM"), ("MKK-unplanted", "PT MKK"),
             ("SPAS-unplanted", "PT SPAS"), ("FOUR-control-palm", palm_label)]
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    S, G = 0.335, 0.012                       # tile side (height frac), gap
    side_w = S * 10.8 / 19.2
    left0 = 0.97 - 2 * side_w - G * 10.8 / 19.2
    for k, (site, cap) in enumerate(tiles):
        r, c = divmod(k, 2)
        bottom = (0.5 + G / 2) if r == 0 else (0.5 - G / 2 - S)
        ax = fig.add_axes([left0 + c * (side_w + G * 10.8 / 19.2), bottom,
                           side_w, S])
        a, *_ = read_ps(plan[site]["pre"]["tif"])
        ax.imshow(rgb(a), interpolation="nearest")
        ax.axis("off")
        ax.text(0.03, 0.05, cap, transform=ax.transAxes, fontsize=22,
                fontweight="bold", color=NYALA if site.startswith("FOUR") else KAPUR,
                fontfamily="DejaVu Sans",
                bbox=dict(fc=JELAGA, ec="none", alpha=0.75, pad=4))
    save(fig, berkas)


def data_json():
    import numpy as np  # noqa: F401
    import pandas as pd
    S_ = json.load(open(os.path.join(O, "summary.json")))
    per = S_["per_concession"]
    comp = pd.read_csv(os.path.join(O, "burned_by_landcover.csv"))
    burned_ha = float(comp.burned_ha.sum())
    palm_ha = float(comp[comp["class"].str.startswith("palm")].burned_ha.sum())
    P3 = json.load(open(os.path.join(O, "peat_stats_three_maps.json")))
    peat_burn = sum(P3[x][PEAT_FILM]["burned_on_peat_ha"] for x in FOUR)
    LP = json.load(open(os.path.join(O, "landprep", "summary.json")))
    t1 = {(r["burn_year"], r["zone"]): r for r in LP["test1"]}
    t4 = pd.DataFrame(LP["test4"])
    mkk_med = t4[(t4.site == "MKK-unplanted") & (t4.date == "pre-fire 2026")].median_parcel_ha.iloc[0]
    by_year = pd.read_csv(os.path.join(O, "danger", "by_year.csv")).set_index("year")
    fwi = pd.read_csv(os.path.join(O, "danger", "fwi_daily_mean.csv"), parse_dates=["date"])
    EX = json.load(open(os.path.join(O, "excess" if PEAT_FILM == "old" else f"excess_peat_{PEAT_FILM}",
                                     "summary.json")))
    bm = [r for r in EX["b_matched"] if r["control"] == "unconceded"]
    raw, full_m = bm[0], [r for r in bm if r["matched_on"] == "+ ignition density"][0]
    forest = next(r for r in EX["d_by_landcover"] if r["class"].startswith("not palm: forest in 2000"))
    PO = json.load(open(os.path.join(O, "permit_overlap.json")))

    def dc_series(y):
        s = fwi[fwi.date.dt.year == y].set_index("date").DC
        s = s.resample("3D").mean()
        return [{"h": int(d.dayofyear), "v": round(float(v), 1)} for d, v in s.items()]

    D = {
        "_comment": ["Ditulis oleh scripts/ketapang_film2_assets.py dari keluaran",
                     "analisis Ketapang. Jangan ketik angka di sini dengan tangan."],
        "konsesi": [{"akronim": x, "ucap": ucap(x),
                     "dari_dalam_pct": 100 * per[x]["share_from_own_ignitions"],
                     "titik_awal": per[x]["ignitions"],
                     "rasio_titik": per[x]["density"]["ratio_inside_to_ring"]}
                    for x in FOUR],
        "titik_awal_total": int(sum(per[x]["ignitions"] for x in FOUR)),
        "rasio_titik_min": min(per[x]["density"]["ratio_inside_to_ring"] for x in FOUR),
        "rasio_titik_maks": max(per[x]["density"]["ratio_inside_to_ring"] for x in FOUR),
        "terbakar_ha": burned_ha,
        "sawit_ha": palm_ha,
        "sawit_pct": 100 * palm_ha / burned_ha,
        "jadi_sawit_2015": {"empat": t1[(2015, "the four")]["pct_burned_now_palm_by_2021"],
                            "konsesi_lain": t1[(2015, "other concessions")]["pct_burned_now_palm_by_2021"],
                            "luar_konsesi": t1[(2015, "unconceded ≤10 km")]["pct_burned_now_palm_by_2021"]},
        "petak_mkk_median_ha": float(mkk_med),
        "am_hti_pct": 100 * PO["PT AM"]["in_hti_ha"] / PO["PT AM"]["area_ha"],
        "am_hti_bakar_pct": 100 * PO["PT AM"]["burned_in_hti_ha"] / PO["PT AM"]["burned_ha"],
        "hujan_jul_sep": {str(y): float(by_year.loc[y, "chirps_jul1_sep15_mm"]) for y in (2015, 2019, 2023, 2026)},
        "dc_puncak": {str(y): float(by_year.loc[y, "DC_peak"]) for y in (2015, 2019, 2023, 2026)},
        "dc_seri": {str(y): dc_series(y) for y in (2015, 2019, 2023, 2026)},
        "dc_ekstrem": 350,
        "gambut_pct": 100 * peat_burn / burned_ha,
        "gambut_dalam_luar": [{"akronim": x,
                               "dalam": P3[x][PEAT_FILM]["burned_pct_of_peat"],
                               "luar": P3[x][PEAT_FILM]["ring_burned_pct_of_peat"]}
                              for x in FOUR],
        "setara": {"mentah": raw["ratio"], "setara": full_m["ratio"],
                   "setara_ci": full_m["ratio_ci95"],
                   "dalam_pct": full_m["treated_burn_pct"],
                   "luar_pct": full_m["matched_control_burn_pct"],
                   "hutan": forest["ratio"],
                   "lama": EX["e_persistence"]["matched_ratio"]},
    }
    with open(os.path.join(FILM, "src", "telusurData.json"), "w") as f:
        json.dump(D, f, indent=1, ensure_ascii=False)
    show = {k: v for k, v in D.items() if k not in ("dc_seri", "_comment")}
    print(json.dumps(show, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
