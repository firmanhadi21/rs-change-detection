"""Multi-page JPEG infographic: Borneo hotspots, last 7 days.

Five pages, each a standalone JPEG so they can be dropped into a deck or a
WhatsApp thread without a browser:

    page 1  cover -- the headline number and what it is
    page 2  by administrative boundary
    page 3  by forest function (KLHK kawasan hutan)
    page 4  the map
    page 5  season context and method

THE MAP IS THE POINT OF THIS REWRITE. The first version plotted detections on
an empty field, which is unreadable: a reader cannot tell coast from river from
provincial border, and cannot place a cluster without a city to anchor it. Here
the base is drawn first -- ocean, land, coastline, international borders from
Natural Earth 50m, provincial boundaries from GAUL, and the cities people
actually navigate by -- and the hotspots go on top of it.

Natural Earth 50m rather than 10m: cartopy fetches these on demand and only
50m is cached here. At island scale the difference is invisible.

    conda run -n base python scripts/borneo_fire_pages.py
"""

import argparse
import json
import os
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# data/ and output/ are ~63 GB each and live on the external SSD; the internal
# disk has run to 12 GiB free. Resolved at runtime so an unmounted volume
# falls back to this checkout instead of failing.
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.expanduser(_DATA_ROOT + "/output/fire")
PAYLOAD = os.path.join(OUT, "infographic_payload.json")
ADMIN_GEOJSON = os.path.join(OUT, "borneo_admin.geojson")
# Written by scripts/borneo_conservation.py. Optional: without it the
# named-areas page is skipped rather than invented.
CONSERVATION = os.path.join(OUT, "borneo_conservation.json")
# TWO ORDERINGS, AND THEY ARE NOT THE SAME. A GIS bbox is
# [lon_min, lat_min, lon_max, lat_max] -- what ee.Geometry.Rectangle and
# shapely take. cartopy's set_extent takes matplotlib order,
# [lon_min, lon_max, lat_min, lat_max]. Passing the first to the second does
# not raise: it reads lat_min as the second longitude, clamps, and renders a
# map of Eurasia with Borneo off the edge. Named separately so they cannot be
# swapped again.
BBOX_GIS = [108.4, -4.6, 119.6, 7.6]
EXTENT = [108.4, 119.6, -4.6, 7.6]

# Palette: pale green-grey forest paper, deep forest ink, fire in clay and
# amber, protected forest in teal. Chosen against the subject rather than
# inherited.
C = {
    "ground": "#E9EDE8", "surface": "#F5F7F3", "sunk": "#DFE5DE",
    "ink": "#16231D", "muted": "#64756C", "rule": "#C8D2C8",
    "ember": "#C8471B", "flame": "#DE8A22", "canopy": "#2F6A5B",
    "deep": "#1D4A54", "hpk": "#B0533C", "cons": "#1F5140",
    "water": "#7E9AA6", "sea": "#D6E2E6", "land": "#E4EADF",
}
FCOL = {
    "APL (non-forest estate)": C["flame"],
    "HPK (convertible production)": C["hpk"],
    "HP (production)": C["ember"],
    "HPT (limited production)": C["deep"],
    "HL (protection forest)": C["canopy"],
    "Conservation (KSA/KPA)": C["cons"],
    "water": C["water"], "unclassified": C["muted"], "_MY": "#8E9C93",
}
# Weakest legal protection to strongest. Not size order -- the gradient is
# the argument.
ORDER = ["APL (non-forest estate)", "HPK (convertible production)",
         "HP (production)", "HPT (limited production)",
         "HL (protection forest)", "Conservation (KSA/KPA)",
         "water", "unclassified"]

# Cities a reader navigates by. Capitals marked, because "which province is
# this cluster in" is the first question a hotspot map has to answer.
CITIES = [
    ("Pontianak", 109.33, -0.03, 1), ("Singkawang", 108.98, 0.91, 0),
    ("Sintang", 111.50, 0.07, 0), ("Palangka Raya", 113.92, -2.21, 1),
    ("Sampit", 112.95, -2.53, 0), ("Banjarmasin", 114.59, -3.32, 1),
    ("Samarinda", 117.15, -0.50, 1), ("Balikpapan", 116.83, -1.24, 0),
    ("Tanjung Selor", 117.37, 2.84, 1), ("Tarakan", 117.59, 3.31, 0),
    ("Kuching", 110.34, 1.56, 1), ("Sibu", 111.83, 2.29, 0),
    ("Bintulu", 113.03, 3.17, 0), ("Miri", 113.99, 4.40, 0),
    ("Kota Kinabalu", 116.07, 5.98, 1), ("Sandakan", 118.12, 5.84, 0),
    ("Tawau", 117.89, 4.24, 0), ("Bandar Seri Begawan", 114.94, 4.89, 1),
]
PAGE = (11.0, 15.6)          # inches; A4-ish portrait


# These pages are re-rendered every season, and the first version of them
# stated the August window in prose ("Half the Indonesian fires...", "1 JAN -
# 20 AUG 2026", "RANK IN 26 YEARS"). Prose does not move when the payload
# does, so a re-run silently published the new numbers under the old claims.
# Anything that depends on the window is derived from here down.
#
# The same applies across languages: every string lives in
# borneo_fire_text.py and every number is formatted for the language before
# it reaches a template, because Indonesian writes 1.234 and 3,45 where
# English writes 1,234 and 3.45.
import borneo_fire_text as TX                              # noqa: E402

LANG = "en"


def S(key):
    return TX.T[LANG][key]


def fmt(n):
    return TX.ribuan(n, LANG)


def dec(v, d=1):
    return TX.desimal(v, LANG, d)


def bulan(i):
    """Month name, 1-based."""
    return TX.MONTHS[LANG][i - 1]


def fungsi(k):
    return TX.FUNGSI[LANG].get(k, k)


def desig(k):
    return TX.DESIG.get(k, k) if LANG == "id" else k


def ytd_label(D):
    """'1 JAN - 16 OCT 2026' from the payload's own window end."""
    mm, dd = D["ytd_window_end"].split("-")
    return f"1 JAN – {int(dd)} {bulan(int(mm)).upper()} {D['window'][1][:4]}"


def share_word(pct):
    return TX.share_word(pct, LANG)


def page(fig_title=None):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=PAGE, facecolor=C["ground"])
    return fig


def header(fig, eyebrow, title, sub=None, y=0.955):
    fig.text(0.07, y, eyebrow.upper(), fontsize=10.5, color=C["muted"],
             fontweight="bold", family="DejaVu Sans")
    fig.text(0.07, y - 0.032, title, fontsize=30, color=C["ink"],
             family="DejaVu Serif", va="top")
    if sub:
        fig.text(0.07, y - 0.072, sub, fontsize=12.5, color=C["muted"],
                 family="DejaVu Sans", va="top", wrap=True)


def footer(fig, n, total=7):
    fig.text(0.07, 0.028, S("footer_src"), fontsize=9, color=C["muted"])
    fig.text(0.93, 0.028, f"{n} / {total}", fontsize=9, color=C["muted"],
             ha="right")


def notes_block(fig, notes, top, floor=0.044, width=108):
    """A stack of bold-headed notes that always clears the footer.

    Hand-tuned leading worked while there was one language. Indonesian runs
    roughly a fifth longer than the English for the same content, which
    pushed the last note under the footer -- so the block measures itself
    and steps the type down until it fits rather than trusting a constant.
    Returns the y it finished at.
    """
    import textwrap
    for size, lead, wrap in ((11.0, 0.0185, width), (10.5, 0.0175, width + 6),
                             (10.0, 0.0166, width + 12),
                             (9.5, 0.0158, width + 18)):
        bodies = [textwrap.fill(b, wrap) for _, b in notes]
        need = sum(0.0165 + lead * (b.count("\n") + 1) + 0.0075
                   for b in bodies)
        if top - need >= floor:
            break
    y = top
    for (bold, _), body in zip(notes, bodies):
        fig.text(0.07, y, bold, fontsize=size, color=C["ink"],
                 fontweight="bold")
        fig.text(0.07, y - 0.0165, body, fontsize=size - 0.5,
                 color=C["muted"], va="top")
        y -= 0.0165 + lead * (body.count("\n") + 1) + 0.0075
    return y


def save(fig, path, dpi=140):
    fig.savefig(path, dpi=dpi, format="jpg", facecolor=C["ground"],
                pil_kwargs={"quality": 92, "optimize": True})
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"  wrote {os.path.basename(path)} "
          f"({os.path.getsize(path)/1024:.0f} KB)")


# ---------------------------------------------------------------- page 1
def cover(D, out):
    fig = page()
    header(fig, S("p1_eyebrow").format(d0=D["window"][0], d1=D["window"][1]),
           S("p1_title"), S("p1_sub"))

    fig.text(0.07, 0.70, fmt(D["total"]), fontsize=132, color=C["ember"],
             family="DejaVu Serif", va="center")
    fig.text(0.07, 0.605, S("p1_kicker"), fontsize=12,
             color=C["muted"], fontweight="bold")

    idn = next(x["n"] for x in D["by_country"] if x["c"] == "Indonesia")
    mys = next((x["n"] for x in D["by_country"] if x["c"] == "Malaysia"), 0)
    rows = [(S("p1_idn"), idn, C["ember"]),
            (S("p1_mys"), mys, C["muted"]),
            (S("p1_brn"), 0, C["muted"])]
    y = 0.52
    for label, v, col in rows:
        fig.text(0.07, y, label, fontsize=14, color=C["ink"])
        fig.text(0.60, y, fmt(v), fontsize=15, color=col, fontweight="bold",
                 ha="right")
        pct = 100 * v / D["total"] if D["total"] else 0
        fig.text(0.68, y, f"{dec(pct)}%", fontsize=13, color=C["muted"],
                 ha="right")
        ax = fig.add_axes([0.71, y - 0.004, 0.22, 0.016])
        ax.set_axis_off()
        ax.add_patch(__import__("matplotlib").patches.Rectangle(
            (0, 0), 1, 1, color=C["sunk"]))
        ax.add_patch(__import__("matplotlib").patches.Rectangle(
            (0, 0), max(pct / 100, 0.004), 1, color=col))
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        y -= 0.052

    share = 100 * D["total"] / D["ytd_total"]
    fig.text(0.07, 0.315, S("p1_share").format(share=dec(share, 0)),
             fontsize=19, color=C["ink"], family="DejaVu Serif", va="top")
    est_pct = 100 * D["in_estate"] / D["indonesia_total"]
    fig.text(0.07, 0.225,
             S("p1_estate").format(word=share_word(est_pct),
                                   protected=fmt(D["protected"])),
             fontsize=13, color=C["muted"], va="top")
    # The rule brackets the quote, so it has to start where the text starts.
    # Text is drawn va="top" from 0.315 and runs two lines at 19 pt.
    ax = fig.add_axes([0.068, 0.268, 0.004, 0.049]); ax.set_axis_off()
    ax.add_patch(__import__("matplotlib").patches.Rectangle(
        (0, 0), 1, 1, color=C["ember"])); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    footer(fig, 1)
    save(fig, out)


# ---------------------------------------------------------------- page 2
def admin_page(D, out):
    fig = page()
    # Every quantity in this subtitle is measured. It previously asserted a
    # 43/31 split and a "three to five times" range that were true of the
    # August window and of no other.
    import textwrap
    idn_pct = 100 * D["indonesia_total"] / D["total"]
    rat = [r for r in D["ytd_ratio"] if r["ratio"]]
    my = [r for r in rat if r["c"] == "Malaysia"]
    idn = [r for r in rat if r["c"] == "Indonesia"]
    my_below = my and all(r["ratio"] < 1 for r in my)
    sub = S("p2_sub_a").format(pct=dec(idn_pct, 0))
    if my_below and idn:
        sub += S("p2_sub_b").format(
            years=D["ytd_years"] - 1,
            lo=dec(min(r["ratio"] for r in idn)),
            hi=dec(max(r["ratio"] for r in idn)))
    else:
        sub += S("p2_sub_c").format(
            ratio=dec(D["ytd_total"] / D["ytd_median"]),
            years=D["ytd_years"] - 1)
    header(fig, S("p2_eyebrow"), S("p2_title"), textwrap.fill(sub, 64))
    # Left margin fits the longest tick label ("Kaltim (+Kaltara)"), which
    # was being cut in half at 0.07.
    ax = fig.add_axes([0.185, 0.30, 0.745, 0.50])
    ax.set_facecolor(C["ground"])
    regions = D["by_region"]
    names = [r["r"] for r in regions][::-1]
    vals = [r["n"] for r in regions][::-1]
    cols = [C["ember"] if r["c"] == "Indonesia" else C["muted"]
            for r in regions][::-1]
    y = np.arange(len(names))
    ax.barh(y, vals, color=cols, height=.62)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=14)
    d0, d1 = D["window"]
    span = (f"{int(d0[8:])}–{int(d1[8:])} {bulan(int(d1[5:7]))} "
            f"{d1[:4]}" if d0[:7] == d1[:7] else
            f"{int(d0[8:])} {bulan(int(d0[5:7]))} – "
            f"{int(d1[8:])} {bulan(int(d1[5:7]))} {d1[:4]}")
    ax.set_xlabel(S("p2_xlabel").format(span=span), fontsize=11,
                  color=C["muted"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=C["rule"], lw=.7)
    for yi, v, r in zip(y, vals, regions[::-1]):
        ax.text(v + max(vals) * .012, yi, fmt(v), va="center", fontsize=13,
                color=C["ink"], fontweight="bold")
        ax.text(v + max(vals) * .012, yi - .30, r["c"], va="center",
                fontsize=9.5, color=C["muted"])
    # Name whichever two provinces actually lead, and say so only if a
    # region really did record nothing.
    top = regions[:2]
    line = S("p2_lead1").format(region=top[0]["r"],
                                pct=dec(100 * top[0]["n"] / D["total"], 0))
    if len(top) > 1:
        line += S("p2_lead2").format(
            region=top[1]["r"], pct=dec(100 * top[1]["n"] / D["total"], 0))
    line += "."
    silent = [r["r"] for r in D["ytd_ratio"]
              if not any(x["r"] == r["r"] for x in regions)]
    if silent:
        line += "\n" + S("p2_silent").format(regions=", ".join(silent))
    fig.text(0.07, 0.22, line, fontsize=13, color=C["muted"], va="top")
    fig.text(0.07, 0.145, S("p2_note"),
             fontsize=11.5, color=C["muted"], va="top", style="italic")
    footer(fig, 2)
    save(fig, out)


# ---------------------------------------------------------------- page 3
def function_page(D, out):
    import matplotlib.patches as mp
    fig = page()
    header(fig, S("p3_eyebrow"), S("p3_title"), S("p3_sub"))
    byF = {x["f"]: x["n"] for x in D["by_function"]}
    funcs = [k for k in ORDER if byF.get(k)]
    tot = D["indonesia_total"]

    ax = fig.add_axes([0.07, 0.70, 0.86, 0.045])
    ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    x = 0.0
    for k in funcs:
        w = byF[k] / tot
        ax.add_patch(mp.Rectangle((x, 0), w, 1, color=FCOL[k]))
        if w > 0.06:
            ax.text(x + w / 2, .5, f"{dec(100*w, 0)}%", ha="center",
                    va="center", color="white", fontsize=12,
                    fontweight="bold")
        x += w
    fig.text(0.07, 0.755, S("p3_weak"), fontsize=9,
             color=C["muted"], fontweight="bold")
    fig.text(0.93, 0.755, S("p3_strong"), fontsize=9,
             color=C["muted"], fontweight="bold", ha="right")

    y = 0.635
    for k in funcs:
        n = byF[k]
        ax2 = fig.add_axes([0.07, y - 0.002, 0.018, 0.018]); ax2.set_axis_off()
        ax2.add_patch(mp.Rectangle((0, 0), 1, 1, color=FCOL[k]))
        ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
        strong = k in ("HL (protection forest)", "Conservation (KSA/KPA)")
        fig.text(0.105, y, fungsi(k), fontsize=13.5, color=C["ink"],
                 fontweight="bold" if strong else "normal")
        fig.text(0.74, y, fmt(n), fontsize=13.5, ha="right",
                 fontweight="bold", color=C["ink"])
        fig.text(0.83, y, f"{dec(100*n/tot)}%", fontsize=13, ha="right",
                 color=C["muted"])
        y -= 0.042

    # Wrapped, not hand-broken. The figures in this sentence change length
    # every season and fixed newlines left it ragged.
    import textwrap
    quote = textwrap.fill(S("p3_quote").format(
        word=share_word(100 * D["in_estate"] / tot),
        estate=fmt(D["in_estate"]),
        estate_pct=dec(100 * D["in_estate"] / tot),
        protected=fmt(D["protected"]),
        prot_pct=dec(100 * D["protected"] / tot)), 68)
    # Rule height follows the wrap, so it brackets the quote at any length.
    _h3 = (quote.count("\n") + 1) * 15 * 1.32 / 72 / PAGE[1]
    ax3 = fig.add_axes([0.068, 0.278 - _h3, 0.004, _h3]); ax3.set_axis_off()
    ax3.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    ax3.set_xlim(0, 1); ax3.set_ylim(0, 1)
    fig.text(0.09, 0.278, quote,
             fontsize=15, color=C["ink"], family="DejaVu Serif", va="top")
    fig.text(0.07, 0.125, S("p3_note"),
             fontsize=11.5, color=C["muted"], va="top", style="italic")
    footer(fig, 3)
    save(fig, out)


# ---------------------------------------------------------------- page 4
def conservation_page(D, K, out):
    """Which protected areas. Page 3 raises the question; this answers it."""
    import matplotlib.patches as mp
    import textwrap
    fig = page()
    header(fig, S("p4_eyebrow"), S("p4_title"), S("p4_sub"))

    ok = [a for a in K["areas"] if a["corroborated"]]
    iffy = [a for a in K["areas"] if not a["corroborated"]]

    # ---- the concentration --------------------------------------------
    top2 = ok[:2]
    share = 100 * sum(a["n"] for a in top2) / K["total_protected"]
    fig.text(0.07, 0.836,
             f"{dec(share, 0)}%", fontsize=68, color=C["cons"],
             family="DejaVu Serif", va="top", fontweight="bold")
    fig.text(0.295, 0.818,
             S("p4_lead").format(a=top2[0]["name"], b=top2[1]["name"]),
             fontsize=15.5, color=C["ink"], family="DejaVu Serif", va="top")

    # ---- the ranking ---------------------------------------------------
    rows = ok[:10]
    ax = fig.add_axes([0.30, 0.445, 0.52, 0.315])
    ax.set_facecolor(C["ground"])
    y = np.arange(len(rows))[::-1]
    vals = [a["n"] for a in rows]
    # National parks in the darkest green; everything else a step lighter.
    cols = [C["cons"] if a["desig"] == "National Park" else C["canopy"]
            for a in rows]
    ax.barh(y, vals, color=cols, height=.66)
    ax.set_yticks(y)
    ax.set_yticklabels([a["name"][:30] for a in rows], fontsize=11.5)
    ax.set_xlabel(S("p4_xlabel"), fontsize=10.5, color=C["muted"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True); ax.xaxis.grid(True, color=C["rule"], lw=.7)
    for yi, a in zip(y, rows):
        ax.text(a["n"] + max(vals) * .015, yi, fmt(a["n"]), va="center",
                fontsize=11, color=C["ink"], fontweight="bold")
    # Rate, not just count: a small reserve with a few detections can be
    # burning harder than a big park with many.
    for yi, a in zip(y, rows):
        ax.text(-max(vals) * .02, yi - .42,
                S("p4_rate").format(desig=desig(a["desig"]),
                                    rate=dec(a["per_1000km2"], 0)),
                va="center", ha="right", fontsize=8.5, color=C["muted"])

    # ---- provisional ----------------------------------------------------
    fig.text(0.07, 0.400, S("p4_prov_head"), fontsize=10,
             color=C["muted"], fontweight="bold")
    axr = fig.add_axes([0.07, 0.388, 0.86, 0.0012]); axr.set_axis_off()
    axr.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["rule"]))
    axr.set_xlim(0, 1); axr.set_ylim(0, 1)
    listed = ", ".join(f"{a['name']} {fmt(a['n'])}" for a in iffy[:6])
    fig.text(0.07, 0.370, textwrap.fill(S("p4_prov").format(
        n=fmt(K["provisional"]), listed=listed), 104),
        fontsize=10.5, color=C["muted"], va="top")

    # ---- what this is and is not ---------------------------------------
    notes = [
        (S("p4_n1_h"), S("p4_n1_b")),
        (S("p4_n2_h"), S("p4_n2_b").format(
            hl=fmt(D["protected"] - K["total_protected"]))),
        (S("p4_n3_h"), S("p4_n3_b")),
    ]
    notes_block(fig, notes, 0.285, width=110)
    footer(fig, 4)
    save(fig, out)


# ---------------------------------------------------------------- page 5
def map_page(D, admin, out):
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.patches as mp
    import matplotlib.patheffects as pe

    fig = page()
    header(fig, S("p5_eyebrow"), S("p5_title"), S("p5_sub"))

    pc = ccrs.PlateCarree()
    ax = fig.add_axes([0.055, 0.115, 0.89, 0.66], projection=pc)
    ax.set_extent(EXTENT, crs=pc)
    ax.set_facecolor(C["sea"])
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor=C["sea"],
                   zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor=C["land"],
                   zorder=1)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor=C["sea"],
                   zorder=2)
    ax.add_feature(cfeature.RIVERS.with_scale("50m"), edgecolor=C["water"],
                   lw=.45, zorder=3, alpha=.8)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#7C8C83",
                   lw=.7, zorder=6)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#5A6B62",
                   lw=1.15, zorder=7, linestyle="-")

    # Provincial boundaries -- GAUL, so Kalimantan's internal lines are right
    # even though Natural Earth 50m does not carry them.
    #
    # add_geometries, NOT geopandas .plot(): plotting a GeoDataFrame onto a
    # cartopy GeoAxes autoscales it and throws away set_extent, which silently
    # rendered this page as a map of Eurasia with Borneo off the corner.
    if admin is not None:
        ax.add_geometries(list(admin.geometry), crs=pc, facecolor="none",
                          edgecolor="#93A398", linewidth=.6, zorder=6)

    # Hotspots, weakest protection first so protected land is never buried.
    pts = D["pts"]
    for cls in ORDER + ["_MY"]:
        sel = [(p[0], p[1]) for p in pts if p[2] == cls]
        if not sel:
            continue
        strong = cls in ("HL (protection forest)", "Conservation (KSA/KPA)")
        ax.scatter([s[0] for s in sel], [s[1] for s in sel],
                   s=6.5 if strong else 3.0, c=FCOL[cls],
                   marker="o", linewidths=0, alpha=.85 if strong else .62,
                   zorder=9 if strong else 8, transform=pc)

    for name, lon, lat, cap in CITIES:
        ax.plot(lon, lat, marker="o", ms=4.6 if cap else 3.0,
                mfc="white", mec=C["ink"], mew=1.0 if cap else .7,
                zorder=11, transform=pc)
        ax.text(lon + 0.13, lat + 0.09, name, fontsize=8.6 if cap else 7.6,
                color=C["ink"], zorder=12, transform=pc,
                fontweight="bold" if cap else "normal",
                path_effects=[pe.withStroke(linewidth=2.4,
                                            foreground="white")])

    # Pin the extent AFTER everything is drawn. Several of the calls above can
    # autoscale the axes, and the last writer wins.
    ax.set_extent(EXTENT, crs=pc)

    gl = ax.gridlines(draw_labels=True, lw=.4, color=C["rule"], alpha=.7)
    gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 8.5, "color": C["muted"]}

    # Scale bar: one degree of longitude at the equator, stated honestly.
    ax.plot([109.0, 110.8], [-4.05, -4.05], color=C["ink"], lw=2.4,
            zorder=12, transform=pc, solid_capstyle="butt")
    ax.text(109.9, -3.95, S("p5_scale"), ha="center", fontsize=8.5,
            color=C["ink"], zorder=12, transform=pc)

    handles = [mp.Patch(color=FCOL[k], label=fungsi(k)) for k in ORDER if
               any(p[2] == k for p in pts)]
    handles.append(mp.Patch(color=FCOL["_MY"], label=fungsi("_MY")))
    leg = fig.legend(handles=handles, loc="lower center", ncol=3,
                     bbox_to_anchor=(0.5, 0.037), frameon=False, fontsize=10.5)
    for t in leg.get_texts():
        t.set_color(C["ink"])
    footer(fig, 5)
    save(fig, out)


# ---------------------------------------------------------------- page 6
def context_page(D, out):
    import matplotlib.patches as mp
    fig = page()
    lo = int(D["window"][1][:4]) - D["ytd_years"] + 1
    hi = int(D["window"][1][:4]) - 1
    header(fig, S("p6_eyebrow"), S("p6_title"),
           S("p6_sub").format(lo=lo, hi=hi))

    ax = fig.add_axes([0.07, 0.60, 0.86, 0.20])
    days = D["daily"]
    xs = np.arange(len(days))
    ax.bar(xs, [d["n"] for d in days], color=C["flame"], width=.62)
    ax.set_xticks(xs)
    # The month comes from the date, not from a literal. This read " Aug" for
    # every bar, which was invisibly correct in August and wrong thereafter.
    ax.set_xticklabels([f"{int(d['d'][8:])} {bulan(int(d['d'][5:7]))}"
                        for d in days], fontsize=11)
    ax.set_facecolor(C["ground"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True); ax.yaxis.grid(True, color=C["rule"], lw=.7)
    for xi, d in zip(xs, days):
        ax.text(xi, d["n"] * 1.03, fmt(d["n"]), ha="center", fontsize=10.5,
                color=C["ink"], fontweight="bold")
    ax.set_title(S("p6_perday"), fontsize=11, color=C["muted"], loc="left")
    fig.text(0.07, 0.565, S("p6_cloud"),
             fontsize=11, color=C["muted"], style="italic")

    cards = [(fmt(D["ytd_total"]), ytd_label(D), S("p6_card1")),
             (f"{dec(D['ytd_total']/D['ytd_median'], 2)}×",
              S("p6_card2_l").format(lo=lo, hi=hi),
              S("p6_card2_s").format(median=fmt(round(D["ytd_median"])))),
             (f"{D['ytd_rank']} / {D['ytd_years']}",
              S("p6_card3_l").format(years=D["ytd_years"]),
              S("p6_card3_s"))]
    x0 = 0.07
    for val, lab, sub in cards:
        axc = fig.add_axes([x0, 0.395, 0.268, 0.125]); axc.set_axis_off()
        axc.add_patch(mp.FancyBboxPatch((0.01, 0.02), .98, .96,
                                        boxstyle="round,pad=0.02",
                                        fc=C["surface"], ec=C["rule"]))
        axc.set_xlim(0, 1); axc.set_ylim(0, 1)
        axc.text(.08, .62, val, fontsize=27, color=C["ink"],
                 fontweight="bold")
        axc.text(.08, .40, lab, fontsize=9.5, color=C["muted"],
                 fontweight="bold")
        axc.text(.08, .22, sub, fontsize=10, color=C["muted"])
        x0 += 0.288

    # How much a year-to-date ranking is worth depends on where in the season
    # it is cut, because Borneo's fires peak in September and October. Cut in
    # August it is nearly meaningless; cut after October it has seen the peak.
    # The caveat has to move with the window or it argues against its own page.
    cut_month = int(D["ytd_window_end"].split("-")[0])
    caveat = S("p6_caveat_early" if cut_month <= 8 else "p6_caveat_late")
    fig.text(0.07, 0.352, caveat,
             fontsize=14.5, color=C["ink"], family="DejaVu Serif", va="top")
    # The rule brackets the quote, so its height is the quote's height: four
    # lines of 14.5 pt on a 15.6 in page. A fixed 0.10 overhung the text by
    # half a paragraph once the wording changed length.
    _h = 4 * 14.5 * 1.32 / 72 / PAGE[1]
    axb = fig.add_axes([0.068, 0.352 - _h, 0.004, _h]); axb.set_axis_off()
    axb.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    axb.set_xlim(0, 1); axb.set_ylim(0, 1)

    # The source and caveat notes that used to sit here are now the method
    # page, which is about provenance in full. Repeating them would have the
    # deck say the same thing twice, in two places that could drift apart.
    fig.text(0.07, 0.225, S("p6_pointer"),
             fontsize=12.5, color=C["muted"], va="top", style="italic")
    footer(fig, 6)
    save(fig, out)


# ---------------------------------------------------------------- page 7
def method_page(D, out):
    """Provenance. Every figure in the deck, traced to the query behind it."""
    import matplotlib.patches as mp
    import textwrap
    M = D.get("method", {})
    fig = page()
    header(fig, S("p7_eyebrow"), S("p7_title"), S("p7_sub"))

    def section(y, label):
        fig.text(0.07, y, label, fontsize=10, color=C["muted"],
                 fontweight="bold", family="DejaVu Sans")
        ax = fig.add_axes([0.07, y - 0.012, 0.86, 0.0012]); ax.set_axis_off()
        ax.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["rule"]))
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    w = D["window"]
    bbox = M.get("bbox") or BBOX_GIS
    conf = M.get("min_confidence", 30)

    # ---- inputs --------------------------------------------------------
    section(0.828, S("p7_inputs"))
    inputs = [(S(f"p7_i{i}_n"), S(f"p7_i{i}_s"), S(f"p7_i{i}_r"))
              for i in (1, 2, 3)]
    y = 0.796
    for name, spec, role in inputs:
        fig.text(0.075, y, name, fontsize=13.5, color=C["ink"],
                 fontweight="bold")
        fig.text(0.075, y - 0.018, spec, fontsize=10.5, color=C["ink"])
        fig.text(0.075, y - 0.034, role, fontsize=10.5, color=C["muted"],
                 style="italic")
        y -= 0.058

    # ---- the chain -----------------------------------------------------
    # Numbered because this genuinely is a sequence: each step consumes the
    # previous step's output, and the count beside it is what survived.
    section(0.612, S("p7_chain"))
    mm, dd = D["ytd_window_end"].split("-")
    ytd_end = f"{int(dd)} {bulan(int(mm))}"
    start = M.get("ytd_start_year", 2001)
    steps = [
        (S("p7_s1_n"),
         S("p7_s1_b").format(w=f"{bbox[0]}–{bbox[2]}", s=abs(bbox[1]),
                             n=bbox[3], d0=w[0], d1=w[1], conf=conf),
         S("p7_s1_c").format(n=fmt(M["n_fetched"]))
         if M.get("n_fetched") else None),
        (S("p7_s2_n"), S("p7_s2_b"),
         S("p7_s2_c").format(kept=fmt(D["total"]),
                             dropped=fmt(M["n_outside"]))
         if M.get("n_outside") is not None else None),
        (S("p7_s3_n"),
         S("p7_s3_b").format(poly=fmt(M["n_kawasan_polygons"])),
         S("p7_s3_c").format(n=fmt(D["indonesia_total"]))),
        (S("p7_s4_n"),
         S("p7_s4_b").format(end=ytd_end, start=start),
         S("p7_s4_c").format(n=fmt(D["ytd_total"]))),
    ]
    # A fixed slot per step. Letting each one size itself to its own wrap
    # left the counts drifting out of line with the steps they belong to.
    y, SLOT = 0.580, 0.058
    for i, (what, how, count) in enumerate(steps, 1):
        fig.text(0.075, y, f"{i}.", fontsize=12.5, color=C["ember"],
                 fontweight="bold", family="DejaVu Sans")
        fig.text(0.103, y, what, fontsize=12.5, color=C["ink"],
                 fontweight="bold", family="DejaVu Sans")
        if count:
            fig.text(0.93, y, count, fontsize=11.5, color=C["ember"],
                     ha="right", fontweight="bold")
        fig.text(0.103, y - 0.016, textwrap.fill(how, 90), fontsize=10.5,
                 color=C["muted"], va="top")
        y -= SLOT

    fig.text(0.075, y + 0.012, S("p7_foot"),
             fontsize=10.5, color=C["muted"], style="italic", va="top")

    # ---- limits --------------------------------------------------------
    section(0.312, S("p7_not"))
    notes = [
        (S("p7_n1_h"), S("p7_n1_b")),
        (S("p7_n2_h"), S("p7_n2_b").format(start=start)),
        (S("p7_n3_h"), S("p7_n3_b")),
        (S("p7_n4_h"), S("p7_n4_b")),
    ]
    notes_block(fig, notes, 0.292)
    footer(fig, 7)
    save(fig, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--lang", nargs="+", default=["en", "id"],
                    choices=sorted(TX.T),
                    help="which language decks to render (default: both)")
    a = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")

    D = json.load(open(PAYLOAD))
    print(f"{D['total']:,} detections, {D['window'][0]} .. {D['window'][1]}")

    admin = None
    try:
        import geopandas as gpd
        if not os.path.exists(ADMIN_GEOJSON):
            sys.path.insert(0, os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            from scripts.borneo_hotspots import build_regions, init_gee
            ee = init_gee()
            gj = build_regions(ee).getInfo()
            gpd.GeoDataFrame.from_features(gj["features"],
                                           crs="EPSG:4326").to_file(
                ADMIN_GEOJSON, driver="GeoJSON")
        admin = gpd.read_file(ADMIN_GEOJSON)
        print(f"  admin boundaries: {len(admin)} units")
    except Exception as exc:                              # noqa: BLE001
        print(f"  (provincial boundaries skipped: {exc.__class__.__name__}: "
              f"{str(exc)[:80]})")

    # Required, not optional. Making the named-areas page skippable would
    # mean every page after it carries two possible numbers, and a deck
    # that misnumbers itself when an input is missing is the same bug this
    # file has already been fixed for twice.
    if not os.path.exists(CONSERVATION):
        raise SystemExit(
            f"missing {CONSERVATION}\n"
            f"Run:  conda run -n base python scripts/borneo_conservation.py")
    K = json.load(open(CONSERVATION))
    if K["window"] != D["window"]:
        raise SystemExit(
            f"borneo_conservation.json is from a different window:\n"
            f"  pages    {D['window'][0]} .. {D['window'][1]}\n"
            f"  named    {K['window'][0]} .. {K['window'][1]}\n"
            f"Re-run scripts/borneo_conservation.py.")
    print(f"  named areas: {len(K['areas'])} over "
          f"{fmt(K['total_protected'])} detections")

    names = ["01_cover", "02_admin", "03_forest_function", "04_named_areas",
             "05_map", "06_context", "07_method"]
    # Each language gets its own directory. Writing both into one would
    # need a suffix on every filename, and the carousel builder would have
    # to know the suffix rather than just the folder.
    global LANG
    for lang in a.lang:
        LANG = lang
        dest = os.path.join(a.out, f"pages_{lang}")
        os.makedirs(dest, exist_ok=True)
        print(f"\n[{lang}]")
        paths = [os.path.join(dest, f"borneo_fire_{n}.jpg") for n in names]
        cover(D, paths[0])
        admin_page(D, paths[1])
        function_page(D, paths[2])
        conservation_page(D, K, paths[3])
        map_page(D, admin, paths[4])
        context_page(D, paths[5])
        method_page(D, paths[6])
        print(f"  {len(names)} pages in {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
