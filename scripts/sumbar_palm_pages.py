"""Six pages on burnt land in West Sumatra that later became oil palm.

Reads scripts/sumbar_burn_palm_sites.py's output. Renders an English and
an Indonesian edition into pages_en/ and pages_id/, plus a holds.json the
carousel builder reads so the per-page reading times live with the deck
that needs them rather than in the video script.

THE DECK'S ARGUMENT IS THE ORDER OF ITS PAGES. The headline number is
large and sounds damning; page 2 immediately shows that it is almost all
lawful; page 3 gives the one finding that survives that (the one-year
lag); page 4 lists the residue as places to check rather than verdicts;
page 5 handles the case in the news and is mostly about what cannot be
shown. A deck that put the residue first would be a different and worse
document.

    conda run -n base python scripts/sumbar_palm_pages.py
    conda run -n base python scripts/sumbar_palm_pages.py --lang id
"""

import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

import deck_chrome as K                                    # noqa: E402
import sumbar_palm_text as TX                              # noqa: E402

_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.expanduser(_DATA_ROOT + "/output/fire/sumbar")
SITES = os.path.join(OUT, "burn_palm_sites.json")
BURN_FROM, BURN_TO, PLANT_TO, SCALE = 2001, 2018, 2021, 200
TOTAL = 7
C = K.C
PAGE_W, PAGE_H = K.PAGE
ADMIN = os.path.join(OUT, "sumbar_admin.geojson")
CLS_TIF = os.path.join(OUT, "btp_class.tif")
LANG = "en"

# Weakest protection to strongest. The gradient is the argument, so the
# order is legal, not numeric.
ORDER = ["AREA PENGGUNAAN LAIN", "HUTAN PRODUKSI KONVERSI",
         "HUTAN PRODUKSI", "HUTAN PRODUKSI TERBATAS", "HUTAN LINDUNG",
         "CAGAR ALAM", "SUAKA MARGASATWA", "TAMAN NASIONAL"]
SCOL = {"AREA PENGGUNAAN LAIN": C["flame"],
        "HUTAN PRODUKSI KONVERSI": C["hpk"],
        "HUTAN PRODUKSI": C["ember"],
        "HUTAN PRODUKSI TERBATAS": C["deep"],
        "HUTAN LINDUNG": C["canopy"],
        "CAGAR ALAM": C["cons"], "SUAKA MARGASATWA": C["cons"],
        "TAMAN NASIONAL": C["cons"]}
ESTATE = {"HUTAN PRODUKSI", "HUTAN PRODUKSI TERBATAS",
          "HUTAN PRODUKSI KONVERSI", "HUTAN LINDUNG"}


def S(k):
    return TX.T[LANG][k]


def fmt(n):
    return K.ribuan(n, LANG)


def dec(v, d=1):
    return K.desimal(v, LANG, d)


def status_label(k):
    return TX.STATUS[LANG].get(k, k.title())


def foot(fig, n):
    K.footer(fig, n, TOTAL, S("src"))


# ------------------------------------------------------------------ 1
def p_cover(D, out):
    fig = K.page()
    K.header(fig, S("p1_eyebrow").format(y0=BURN_FROM, y1=BURN_TO),
             S("p1_title"), S("p1_sub").format(y0=BURN_FROM, y1=BURN_TO))
    btp = D["total_then_palm_ha"]
    fig.text(0.07, 0.70, fmt(btp), fontsize=132, color=C["ember"],
             family=K.SERIF, va="center")
    fig.text(0.07, 0.605, S("p1_kicker"), fontsize=12, color=C["muted"],
             fontweight="bold")
    fig.text(0.07, 0.575,
             S("p1_of").format(pct=dec(100 * btp / D["total_burnt_ha"], 0)),
             fontsize=13, color=C["ink"])

    # The two-tone bar is the whole argument in one object: how much of
    # the headline sits on land where planting is permitted.
    lawful = sum(r["then_palm_ha"] for r in D["by_status"]
                 if r["status"] in ("AREA PENGGUNAAN LAIN",
                                    "HUTAN PRODUKSI KONVERSI"))
    ax = fig.add_axes([0.07, 0.455, 0.86, 0.05])
    ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    import matplotlib.patches as mp
    f = lawful / btp
    ax.add_patch(mp.Rectangle((0, 0), f, 1, color=C["flame"]))
    ax.add_patch(mp.Rectangle((f, 0), 1 - f, 1, color=C["cons"]))
    ax.text(f / 2, .5, f"{dec(100*f, 0)}%", ha="center", va="center",
            color="white", fontsize=15, fontweight="bold")
    fig.text(0.07, 0.522, "APL + HPK · WHERE PLANTING IS PERMITTED"
             if LANG == "en" else "APL + HPK · TEMPAT PENANAMAN DIIZINKAN",
             fontsize=9, color=C["muted"], fontweight="bold")
    # The dark sliver needs naming, or a reader cannot tell what the
    # hectares beside it are the hectares OF.
    fig.text(0.93, 0.522, f"{S('p1_strict')}   {fmt(btp - lawful)} ha",
             fontsize=9, color=C["cons"], fontweight="bold", ha="right")

    K.quote(fig, S("p1_lead"), 0.400, size=19, width=52)
    fig.text(0.07, 0.290, S("p1_note"), fontsize=12.5, color=C["muted"],
             va="top", style="italic")
    foot(fig, 1)
    K.save(fig, out)


# ------------------------------------------------------------------ 2
def p_status(D, out):
    fig = K.page()
    K.header(fig, S("p2_eyebrow"), S("p2_title"), S("p2_sub"))
    rows = {r["status"]: r for r in D["by_status"]}
    keys = [k for k in ORDER if k in rows]

    ax = fig.add_axes([0.30, 0.44, 0.60, 0.33])
    ax.set_facecolor(C["ground"])
    y = np.arange(len(keys))[::-1]
    share = [100 * rows[k]["share"] for k in keys]
    ax.barh(y, share, color=[SCOL.get(k, C["muted"]) for k in keys],
            height=.66)
    ax.set_yticks(y)
    ax.set_yticklabels([status_label(k) for k in keys], fontsize=11.5)
    ax.set_xlabel(S("p2_xlabel"), fontsize=10, color=C["muted"])
    ax.set_xlim(0, max(share) * 1.25)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True); ax.xaxis.grid(True, color=C["rule"], lw=.7)
    for yi, k in zip(y, keys):
        v = 100 * rows[k]["share"]
        ax.text(v + max(share) * .015, yi, f"{dec(v)}%", va="center",
                fontsize=11, color=C["ink"], fontweight="bold")
        ax.text(-max(share) * .02, yi - .42,
                f"{fmt(rows[k]['burnt_ha'])} ha", va="center", ha="right",
                fontsize=8.5, color=C["muted"])

    est = sum(rows[k]["then_palm_ha"] for k in ESTATE if k in rows)
    hpk = rows.get("HUTAN PRODUKSI KONVERSI", {}).get("then_palm_ha", 0)
    K.quote(fig, S("p2_quote").format(estate=fmt(est), hpk=fmt(hpk)),
            0.375, size=15, width=66)
    fig.text(0.07, 0.235, S("p2_note"), fontsize=11.5, color=C["muted"],
             va="top", style="italic")
    foot(fig, 2)
    K.save(fig, out)


# ------------------------------------------------------------------ 3
def p_timing(D, out):
    fig = K.page()
    K.header(fig, S("p3_eyebrow"), S("p3_title"), S("p3_sub"))
    h = D["lag_hist"]
    labels, counts = [r[0] for r in h], [r[1] for r in h]

    ax = fig.add_axes([0.10, 0.44, 0.83, 0.32])
    ax.set_facecolor(C["ground"])
    x = np.arange(len(labels))
    # The first bar is the finding, so it is the only one in ember.
    cols = [C["ember"]] + [C["flame"]] * (len(labels) - 1)
    ax.bar(x, counts, color=cols, width=.66)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=11)
    ax.set_xlabel(S("p3_xlabel"), fontsize=10.5, color=C["muted"])
    ax.set_title(S("p3_ylabel"), fontsize=10.5, color=C["muted"],
                 loc="left")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True); ax.yaxis.grid(True, color=C["rule"], lw=.7)
    for xi, c in zip(x, counts):
        ax.text(xi, c + max(counts) * .02, fmt(c), ha="center",
                fontsize=10.5, color=C["ink"], fontweight="bold")

    K.quote(fig, S("p3_quote").format(
        median=fmt(D["lag_median"]), n1=fmt(counts[0]),
        ntot=fmt(sum(counts))), 0.375, size=15, width=66)
    fig.text(0.07, 0.235, S("p3_note"), fontsize=11.5, color=C["muted"],
             va="top", style="italic")
    foot(fig, 3)
    K.save(fig, out)


# ------------------------------------------------------------------ 4
# Mainland West Sumatra. The Mentawai islands are part of the province
# and carry none of this, so including them would shrink the part of the
# map that has something on it by half.
EXTENT = [99.8, 102.0, -2.95, 0.95]
CITIES = [("Padang", 100.37, -0.95, 1), ("Bukittinggi", 100.37, -0.31, 0),
          ("Payakumbuh", 100.63, -0.22, 0), ("Solok", 100.66, -0.79, 0),
          ("Sawahlunto", 100.78, -0.68, 0),
          ("Pulau Punjung", 101.55, -0.99, 0)]
# The 2026 case, from the MODIS cluster in scripts/dharmasraya_hpt_site.py
# -- found from the date and the designation, not taken from the article.
CASE = (101.549, -0.903)


def p_map(D, out, admin, cls_tif):
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.lines as ml
    import matplotlib.patheffects as pe
    import rasterio

    fig = K.page()
    K.header(fig, S("pm_eyebrow"), S("pm_title"), S("pm_sub"))
    pc = ccrs.PlateCarree()
    # Size the axes to the data, not the page. Cartopy holds a true
    # aspect inside whatever box it is given, so a box of the wrong
    # shape is paid for in blank margin -- here the province is twice as
    # tall as it is wide, and a full-width box wasted a third of the page
    # on empty Indian Ocean.
    import numpy as _n
    w_deg = (EXTENT[1] - EXTENT[0]) * _n.cos(_n.radians(
        (EXTENT[2] + EXTENT[3]) / 2))
    h_frac = 0.60
    w_frac = h_frac * PAGE_H / PAGE_W * w_deg / (EXTENT[3] - EXTENT[2])
    ax = fig.add_axes([(1 - w_frac) / 2, 0.235, w_frac, h_frac],
                      projection=pc)
    ax.set_extent(EXTENT, crs=pc)
    ax.set_facecolor(C["sea"])
    for feat, kw in (
            (cfeature.OCEAN, dict(facecolor=C["sea"], zorder=0)),
            (cfeature.LAND, dict(facecolor=C["land"], zorder=1)),
            (cfeature.LAKES, dict(facecolor=C["sea"], zorder=2)),
            (cfeature.RIVERS, dict(edgecolor=C["water"], lw=.4, zorder=3)),
            (cfeature.COASTLINE, dict(edgecolor="#7C8C83", lw=.7, zorder=6)),
            (cfeature.BORDERS, dict(edgecolor="#5A6B62", lw=1.0, zorder=7))):
        ax.add_feature(feat.with_scale("10m"), **kw)
    if admin is not None:
        ax.add_geometries(list(admin.geometry), crs=pc, facecolor="none",
                          edgecolor="#9FAEA3", linewidth=.55, zorder=5)
        dh = admin[admin.ADM2_NAME == "Dharmasraya"]
        if len(dh):
            ax.add_geometries(list(dh.geometry), crs=pc, facecolor="none",
                              edgecolor=C["ink"], linewidth=1.3, zorder=8)

    # Cell centres, not the raster: at 200 m on a page this wide a cell
    # is a quarter of a pixel, so imshow would simply lose them.
    with rasterio.open(cls_tif) as s:
        cls = s.read(1)
        tr = s.transform
    import numpy as _np
    for val, col, size, z in ((1, C["flame"], 2.4, 9),
                              (2, C["cons"], 22.0, 10)):
        rr, cc = _np.nonzero(cls == val)
        if not rr.size:
            continue
        xs, ys = rasterio.transform.xy(tr, rr, cc)
        ax.scatter(xs, ys, s=size, c=col, marker="o", linewidths=0,
                   alpha=.85 if val == 1 else .95, zorder=z, transform=pc)

    # The two protection-forest sites get a ring, because at this scale a
    # 20 ha patch is smaller than the dot that marks it.
    for s_ in D["sites"]:
        if s_["status"] != "HUTAN LINDUNG":
            continue
        ax.plot(s_["lon"], s_["lat"], marker="o", ms=13, mfc="none",
                mec=C["ember"], mew=2.0, zorder=12, transform=pc)

    ax.plot(*CASE, marker="X", ms=11, mfc=C["ember"], mec="white",
            mew=1.2, zorder=13, transform=pc)

    for name, lon, lat, cap in CITIES:
        ax.plot(lon, lat, marker="o", ms=4.4 if cap else 3.0, mfc="white",
                mec=C["ink"], mew=1.0 if cap else .7, zorder=14,
                transform=pc)
        ax.text(lon + 0.04, lat + 0.03, name, fontsize=8.4 if cap else 7.6,
                color=C["ink"], zorder=15, transform=pc,
                fontweight="bold" if cap else "normal",
                path_effects=[pe.withStroke(linewidth=2.2,
                                            foreground="white")])
    ax.set_extent(EXTENT, crs=pc)          # pin it after every autoscale

    gl = ax.gridlines(draw_labels=True, lw=.4, color=C["rule"], alpha=.7)
    gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 8.5, "color": C["muted"]}
    # 50 km at this latitude, stated as what it is.
    ax.plot([100.0, 100.449], [-2.80, -2.80], color=C["ink"], lw=2.4,
            zorder=14, transform=pc, solid_capstyle="butt")
    ax.text(100.22, -2.74, S("pm_scale"), ha="center", fontsize=8.5,
            color=C["ink"], zorder=14, transform=pc)

    handles = [
        ml.Line2D([], [], marker="o", ls="", ms=6, mfc=C["flame"],
                  mec="none", label=S("pm_leg1")),
        ml.Line2D([], [], marker="o", ls="", ms=8, mfc=C["cons"],
                  mec="none", label=S("pm_leg2")),
        ml.Line2D([], [], marker="o", ls="", ms=11, mfc="none",
                  mec=C["ember"], mew=2.0, label=S("pm_leg3")),
        ml.Line2D([], [], marker="X", ls="", ms=9, mfc=C["ember"],
                  mec="white", label=S("pm_leg4")),
    ]
    leg = fig.legend(handles=handles, loc="lower center", ncol=2,
                     bbox_to_anchor=(0.5, 0.145), frameon=False,
                     fontsize=10.5)
    for t in leg.get_texts():
        t.set_color(C["ink"])

    n_r = int((cls == 2).sum())
    fig.text(0.07, 0.108,
             S("pm_note").format(n=fmt(n_r), tot=fmt(int((cls > 0).sum()))),
             fontsize=11, color=C["muted"], va="top", style="italic")
    foot(fig, 4)
    K.save(fig, out)


# ------------------------------------------------------------------ 5
def p_sites(D, out):
    fig = K.page()
    K.header(fig, S("p4_eyebrow"), S("p4_title"),
             S("p4_sub").format(minha=fmt(D["min_ha"])))
    sites = D["sites"][:14]
    cols = S("p4_cols")
    x = [0.075, 0.195, 0.325, 0.420, 0.530, 0.640]
    y = 0.800
    for cx, name in zip(x, cols):
        fig.text(cx, y, name.upper(), fontsize=9, color=C["muted"],
                 fontweight="bold",
                 ha="right" if name in (cols[2],) else "left")
    K.section(fig, y, "")
    y -= 0.030
    for s in sites:
        hl = s["status"] == "HUTAN LINDUNG"
        col = C["ember"] if hl else C["ink"]
        w = "bold" if hl else "normal"
        fig.text(x[0], y, dec(s["lon"], 4), fontsize=11.5, color=col,
                 fontweight=w)
        fig.text(x[1], y, dec(s["lat"], 4), fontsize=11.5, color=col,
                 fontweight=w)
        fig.text(x[2], y, fmt(s["ha"]), fontsize=11.5, color=col,
                 fontweight=w, ha="right")
        fig.text(x[3], y, str(s["burn_year"]), fontsize=11.5, color=col,
                 fontweight=w)
        fig.text(x[4], y, str(s["palm_year"]), fontsize=11.5, color=col,
                 fontweight=w)
        fig.text(x[5], y, status_label(s["status"]), fontsize=11.5,
                 color=col, fontweight=w)
        y -= 0.0285

    hl_ha = sum(s["ha"] for s in D["sites"]
                if s["status"] == "HUTAN LINDUNG")
    K.quote(fig, S("p4_hl").format(n=fmt(hl_ha)), y - 0.025, size=15,
            width=66)
    fig.text(0.07, y - 0.155, S("p4_note"), fontsize=11.5,
             color=C["muted"], va="top", style="italic")
    foot(fig, 4)
    K.save(fig, out)


# ------------------------------------------------------------------ 5
def p_case(D, out):
    fig = K.page()
    K.header(fig, S("p5_eyebrow"), S("p5_title"), S("p5_sub"))
    K.section(fig, 0.830, S("p5_found"))
    y = 0.795
    for n, b in (("p5_f1", "p5_f1b"), ("p5_f2", "p5_f2b"),
                 ("p5_f3", "p5_f3b")):
        fig.text(0.092, y, "✓", fontsize=15, color=C["cons"],
                 fontweight="bold")
        fig.text(0.125, y, S(n), fontsize=14.5, color=C["ink"],
                 fontweight="bold")
        fig.text(0.125, y - 0.019, S(b), fontsize=10.5, color=C["muted"],
                 style="italic")
        y -= 0.052

    K.section(fig, y - 0.012, S("p5_cant"))
    # The closing quote follows the notes instead of sitting at a fixed
    # y, so the Indonesian edition -- which runs longer -- does not leave
    # a hole in the middle of the page.
    end = K.notes_block(fig, [("", S("p5_c1")), ("", S("p5_c2")),
                              ("", S("p5_c3"))], y - 0.040, floor=0.30,
                        width=104)
    K.quote(fig, S("p5_close"), end - 0.030, size=14.5, width=68)
    foot(fig, 5)
    K.save(fig, out)


# ------------------------------------------------------------------ 6
def p_method(D, out):
    fig = K.page()
    K.header(fig, S("p6_eyebrow"), S("p6_title"),
             S("p6_sub").format(scale=SCALE))
    K.section(fig, 0.828, S("p6_inputs"))
    y = 0.796
    for n, s in (("p6_i1", "p6_i1s"), ("p6_i2", "p6_i2s"),
                 ("p6_i3", "p6_i3s")):
        fig.text(0.075, y, S(n), fontsize=13.5, color=C["ink"],
                 fontweight="bold")
        fig.text(0.075, y - 0.019,
                 S(s).format(y0=BURN_FROM, y1=BURN_TO), fontsize=10.5,
                 color=C["muted"])
        y -= 0.048

    import textwrap
    K.section(fig, y - 0.004, S("p6_rule"))
    body = textwrap.fill(S("p6_rule_b").format(y1=BURN_TO, py=PLANT_TO), 104)
    fig.text(0.07, y - 0.034, body, fontsize=11, color=C["ink"], va="top")

    K.section(fig, 0.470, S("p6_not"))
    K.notes_block(fig, [(S(f"p6_n{i}_h"), S(f"p6_n{i}_b"))
                        for i in (1, 2, 3, 4)], 0.442)
    foot(fig, 6)
    K.save(fig, out)


# ------------------------------------------------------------------
# Reading time per page. The sites table and the method page carry the
# most text and get the most screen; the cover is one number.
HOLDS = {"01_cover": 7.0, "02_status": 11.0, "03_timing": 10.0,
         "04_map": 11.0, "05_sites": 13.0, "06_case": 12.0,
         "07_method": 13.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sites", default=SITES)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--lang", nargs="+", default=["en", "id"],
                    choices=sorted(TX.T))
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")

    if not os.path.exists(a.sites):
        raise SystemExit(f"missing {a.sites}\nRun: conda run -n base "
                         f"python scripts/sumbar_burn_palm_sites.py")
    D = json.load(open(a.sites))
    D.setdefault("min_ha", 16)
    print(f"{fmt(D['total_then_palm_ha'])} ha burnt-then-palm, "
          f"{len(D['sites'])} estate sites")

    # The map needs two extra inputs. Both are required: a deck whose
    # map page silently disappears when a file is missing would renumber
    # itself, which is the bug this repo has already been bitten by.
    for p, how in ((ADMIN, "the scratchpad boundary cache"),
                   (CLS_TIF, "scripts/sumbar_burn_palm_sites.py")):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}\nWrite it with {how}.")
    import geopandas as gpd
    admin = gpd.read_file(ADMIN)
    print(f"  {len(admin)} kabupaten boundaries")

    global LANG
    names = list(HOLDS)
    pages = [p_cover, p_status, p_timing,
             lambda D_, o: p_map(D_, o, admin, CLS_TIF),
             p_sites, p_case, p_method]
    for lang in a.lang:
        LANG = lang
        dest = os.path.join(a.out, f"pages_{lang}")
        os.makedirs(dest, exist_ok=True)
        print(f"\n[{lang}]")
        for fn, n in zip(pages, names):
            fn(D, os.path.join(dest, f"sumbar_palm_{n}.jpg"))
        # The carousel reads this, so hold times live with the deck.
        with open(os.path.join(dest, "holds.json"), "w") as f:
            json.dump({f"sumbar_palm_{k}": v for k, v in HOLDS.items()},
                      f, indent=1)
        print(f"  {len(names)} pages in {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
