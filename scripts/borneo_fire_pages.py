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


def fmt(n):
    return f"{int(n):,}"


# These pages are re-rendered every season, and the first version of them
# stated the August window in prose ("Half the Indonesian fires...", "1 JAN -
# 20 AUG 2026", "RANK IN 26 YEARS"). Prose does not move when the payload
# does, so a re-run silently published the new numbers under the old claims.
# Anything that depends on the window is derived from here down.
_BULAN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ytd_label(D):
    """'1 JAN - 16 OCT 2026' from the payload's own window end."""
    mm, dd = D["ytd_window_end"].split("-")
    year = D["window"][1][:4]
    return f"1 JAN – {int(dd)} {_BULAN[int(mm) - 1].upper()} {year}"


def share_word(pct):
    """A fraction in words, for prose that must not contradict its figure."""
    for cut, word in ((88, "Nearly all of"), (72, "Three quarters of"),
                      (60, "Two thirds of"), (44, "Half"),
                      (28, "A third of"), (12, "A fifth of")):
        if pct >= cut:
            return word
    return "A small share of"


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


def footer(fig, n, total=6):
    fig.text(0.07, 0.028, "MODIS FIRMS · KLHK Penunjukan Kawasan Hutan · "
             "FAO GAUL 2015", fontsize=9, color=C["muted"])
    fig.text(0.93, 0.028, f"{n} / {total}", fontsize=9, color=C["muted"],
             ha="right")


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
    header(fig, f"MODIS FIRMS · {D['window'][0]} to {D['window'][1]}",
           "Titik Panas Borneo",
           "Active-fire detections across the whole island — Kalimantan,\n"
           "Sarawak, Sabah, Labuan and Brunei — attributed to province and,\n"
           "on the Indonesian side, to the legal function of the land beneath.")

    fig.text(0.07, 0.70, fmt(D["total"]), fontsize=132, color=C["ember"],
             family="DejaVu Serif", va="center")
    fig.text(0.07, 0.605, "DETECTIONS IN SEVEN DAYS", fontsize=12,
             color=C["muted"], fontweight="bold")

    idn = next(x["n"] for x in D["by_country"] if x["c"] == "Indonesia")
    mys = next((x["n"] for x in D["by_country"] if x["c"] == "Malaysia"), 0)
    rows = [("Indonesia — Kalimantan", idn, C["ember"]),
            ("Malaysia — Sarawak + Sabah", mys, C["muted"]),
            ("Brunei Darussalam", 0, C["muted"])]
    y = 0.52
    for label, v, col in rows:
        fig.text(0.07, y, label, fontsize=14, color=C["ink"])
        fig.text(0.60, y, fmt(v), fontsize=15, color=col, fontweight="bold",
                 ha="right")
        pct = 100 * v / D["total"] if D["total"] else 0
        fig.text(0.68, y, f"{pct:.1f}%", fontsize=13, color=C["muted"],
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
    fig.text(0.07, 0.315,
             f"These seven days are {share:.0f}% of every hotspot detected\n"
             f"on Borneo since 1 January.",
             fontsize=19, color=C["ink"], family="DejaVu Serif", va="top")
    est_pct = 100 * D["in_estate"] / D["indonesia_total"]
    fig.text(0.07, 0.225,
             f"{share_word(est_pct)} the Indonesian fires are inside the "
             f"forest estate, and\n{fmt(D['protected'])} of them are in "
             "protection forest or conservation areas,\nwhere burning is not "
             "permitted under any licence.",
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
    sub = (f"{idn_pct:.0f}% of the island's fires this week are on the "
           f"Indonesian side. ")
    if my_below and idn:
        sub += (f"Sarawak and Sabah are not merely quieter — both run BELOW "
                f"their own {D['ytd_years'] - 1}-year medians for the season "
                f"to date, while every Kalimantan province runs "
                f"{min(r['ratio'] for r in idn):.1f} to "
                f"{max(r['ratio'] for r in idn):.1f} times above.")
    else:
        sub += (f"Island-wide the season stands at "
                f"{D['ytd_total']/D['ytd_median']:.1f}× the "
                f"{D['ytd_years'] - 1}-year median to this date.")
    header(fig, "page 2 · administrative boundary",
           "This is a Kalimantan event", textwrap.fill(sub, 64))
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
    span = (f"{int(d0[8:])}–{int(d1[8:])} {_BULAN[int(d1[5:7]) - 1]} "
            f"{d1[:4]}" if d0[:7] == d1[:7] else
            f"{int(d0[8:])} {_BULAN[int(d0[5:7]) - 1]} – "
            f"{int(d1[8:])} {_BULAN[int(d1[5:7]) - 1]} {d1[:4]}")
    ax.set_xlabel(f"hotspot detections, {span}", fontsize=11,
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
    line = (f"{top[0]['r']} alone carries "
            f"{100*top[0]['n']/D['total']:.0f}% of the island total")
    if len(top) > 1:
        line += (f", and {top[1]['r']} another "
                 f"{100*top[1]['n']/D['total']:.0f}%")
    line += "."
    silent = [r["r"] for r in D["ytd_ratio"]
              if not any(x["r"] == r["r"] for x in regions)]
    if silent:
        line += ("\n" + ", ".join(silent) +
                 (" recorded no detections at all in the window."
                  if len(silent) == 1 else
                  " recorded no detections at all in the window."))
    fig.text(0.07, 0.22, line, fontsize=13, color=C["muted"], va="top")
    fig.text(0.07, 0.145,
             "Kalimantan Utara does not appear: FAO GAUL 2015 predates the "
             "province\ncreated in 2012, so its territory is counted inside "
             "Kalimantan Timur.",
             fontsize=11.5, color=C["muted"], va="top", style="italic")
    footer(fig, 2)
    save(fig, out)


# ---------------------------------------------------------------- page 3
def function_page(D, out):
    import matplotlib.patches as mp
    fig = page()
    header(fig, "page 3 · forest function", "Whose land is burning",
           "Indonesian detections placed on the KLHK Penunjukan Kawasan Hutan\n"
           "designation, ordered by how much legal protection the land carries.")
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
            ax.text(x + w / 2, .5, f"{100*w:.0f}%", ha="center", va="center",
                    color="white", fontsize=12, fontweight="bold")
        x += w
    fig.text(0.07, 0.755, "WEAKEST PROTECTION", fontsize=9,
             color=C["muted"], fontweight="bold")
    fig.text(0.93, 0.755, "STRONGEST PROTECTION", fontsize=9,
             color=C["muted"], fontweight="bold", ha="right")

    y = 0.635
    for k in funcs:
        n = byF[k]
        ax2 = fig.add_axes([0.07, y - 0.002, 0.018, 0.018]); ax2.set_axis_off()
        ax2.add_patch(mp.Rectangle((0, 0), 1, 1, color=FCOL[k]))
        ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
        strong = k in ("HL (protection forest)", "Conservation (KSA/KPA)")
        fig.text(0.105, y, k, fontsize=13.5, color=C["ink"],
                 fontweight="bold" if strong else "normal")
        fig.text(0.74, y, fmt(n), fontsize=13.5, ha="right",
                 fontweight="bold", color=C["ink"])
        fig.text(0.83, y, f"{100*n/tot:.1f}%", fontsize=13, ha="right",
                 color=C["muted"])
        y -= 0.042

    # Wrapped, not hand-broken. The figures in this sentence change length
    # every season and fixed newlines left it ragged.
    import textwrap
    quote = textwrap.fill(
        f"{share_word(100*D['in_estate']/tot)} the Indonesian fires — "
        f"{fmt(D['in_estate'])}, {100*D['in_estate']/tot:.1f}% — are inside "
        "the forest estate rather than on land released for other use. "
        f"{fmt(D['protected'])} of them ({100*D['protected']/tot:.1f}%) are "
        "in protection forest or conservation areas, where burning is not "
        "permitted under any licence.", 68)
    # Rule height follows the wrap, so it brackets the quote at any length.
    _h3 = (quote.count("\n") + 1) * 15 * 1.32 / 72 / PAGE[1]
    ax3 = fig.add_axes([0.068, 0.278 - _h3, 0.004, _h3]); ax3.set_axis_off()
    ax3.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    ax3.set_xlim(0, 1); ax3.set_ylim(0, 1)
    fig.text(0.09, 0.278, quote,
             fontsize=15, color=C["ink"], family="DejaVu Serif", va="top")
    fig.text(0.07, 0.125,
             "Kawasan hutan is an Indonesian legal designation with no "
             "Malaysian or Bruneian\nequivalent, so Sarawak, Sabah, Labuan "
             "and Brunei are left unclassified here rather\nthan mapped onto "
             "a foreign scheme.",
             fontsize=11.5, color=C["muted"], va="top", style="italic")
    footer(fig, 3)
    save(fig, out)


# ---------------------------------------------------------------- page 4
def map_page(D, admin, out):
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.patches as mp
    import matplotlib.patheffects as pe

    fig = page()
    header(fig, "page 4 · location", "Where they are",
           "Every detection in the window, over land, sea, international and\n"
           "provincial boundaries, with the cities the clusters sit near.")

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
    ax.text(109.9, -3.95, "200 km", ha="center", fontsize=8.5,
            color=C["ink"], zorder=12, transform=pc)

    handles = [mp.Patch(color=FCOL[k], label=k) for k in ORDER if
               any(p[2] == k for p in pts)]
    handles.append(mp.Patch(color=FCOL["_MY"],
                            label="Malaysia (no KLHK class)"))
    leg = fig.legend(handles=handles, loc="lower center", ncol=3,
                     bbox_to_anchor=(0.5, 0.037), frameon=False, fontsize=10.5)
    for t in leg.get_texts():
        t.set_color(C["ink"])
    footer(fig, 4)
    save(fig, out)


# ---------------------------------------------------------------- page 5
def context_page(D, out):
    import matplotlib.patches as mp
    fig = page()
    lo = int(D["window"][1][:4]) - D["ytd_years"] + 1
    hi = int(D["window"][1][:4]) - 1
    header(fig, "page 5 · context", "The season so far",
           f"How this week sits against the {lo}–{hi} record, and how much\n"
           "a ranking taken at this point in the year is worth.")

    ax = fig.add_axes([0.07, 0.60, 0.86, 0.20])
    days = D["daily"]
    xs = np.arange(len(days))
    ax.bar(xs, [d["n"] for d in days], color=C["flame"], width=.62)
    ax.set_xticks(xs)
    # The month comes from the date, not from a literal. This read " Aug" for
    # every bar, which was invisibly correct in August and wrong thereafter.
    ax.set_xticklabels([f"{int(d['d'][8:])} {_BULAN[int(d['d'][5:7]) - 1]}"
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
    ax.set_title("detections per day", fontsize=11, color=C["muted"],
                 loc="left")
    fig.text(0.07, 0.565,
             "MODIS sees a place twice a day at best and cloud blocks it "
             "entirely. The dips are as likely to be cloud as calm.",
             fontsize=11, color=C["muted"], style="italic")

    base_lo = int(D["window"][1][:4]) - D["ytd_years"] + 1
    base_hi = int(D["window"][1][:4]) - 1
    cards = [(fmt(D["ytd_total"]), ytd_label(D),
              "total detections, same definition"),
             (f"{D['ytd_total']/D['ytd_median']:.2f}×",
              f"VS {base_lo}–{base_hi} MEDIAN",
              f"median {fmt(round(D['ytd_median']))}"),
             (f"{D['ytd_rank']} / {D['ytd_years']}",
              f"RANK IN {D['ytd_years']} YEARS",
              "to this date in the year")]
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
    if cut_month <= 8:
        caveat = ("2015 sat exactly at the median on 20 August, and became "
                  "the\ncatastrophe everyone remembers — because its fires "
                  "peaked in\nSeptember and October. An August ranking "
                  "systematically\nunderstates El Niño years and cannot tell "
                  "you how a season ends.")
    else:
        caveat = ("Borneo's fires peak in September and October, so a ranking "
                  "cut\nhere has seen the worst of the season rather than "
                  "guessing at it.\nThat is what makes this one worth "
                  "reading: 2015 and 2019 are\nalready in the record it is "
                  "being measured against.")
    fig.text(0.07, 0.352, caveat,
             fontsize=14.5, color=C["ink"], family="DejaVu Serif", va="top")
    # The rule brackets the quote, so its height is the quote's height: four
    # lines of 14.5 pt on a 15.6 in page. A fixed 0.10 overhung the text by
    # half a paragraph once the wording changed length.
    _h = 4 * 14.5 * 1.32 / 72 / PAGE[1]
    axb = fig.add_axes([0.068, 0.352 - _h, 0.004, _h]); axb.set_axis_off()
    axb.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    axb.set_xlim(0, 1); axb.set_ylim(0, 1)

    # The source and caveat notes that used to sit here are now page 6, which
    # is about provenance in full. Repeating them would have the deck say the
    # same thing twice, in two places that could drift apart.
    fig.text(0.07, 0.225,
             "Page 6 sets out the data and the method in full: every input, "
             "the\nquery that produced each figure, and what the counts do "
             "not mean.",
             fontsize=12.5, color=C["muted"], va="top", style="italic")
    footer(fig, 5)
    save(fig, out)


# ---------------------------------------------------------------- page 6
def method_page(D, out):
    """Provenance. Every figure in the deck, traced to the query behind it."""
    import matplotlib.patches as mp
    import textwrap
    M = D.get("method", {})
    fig = page()
    header(fig, "page 6 · data and method", "How this was made",
           "Three public datasets and a four-step chain, run end to end.\n"
           "The counts beside each step are this run's own.")

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
    section(0.828, "INPUTS")
    inputs = [
        ("NASA FIRMS active fire",
         "MODIS Terra + Aqua, 1 km, daily",
         "via Google Earth Engine · the detections themselves"),
        ("FAO GAUL 2015, level 1",
         "administrative boundaries, all three countries",
         "which province, and which country, each detection is in"),
        ("KLHK Penunjukan Kawasan Hutan",
         "1:250,000 (2019) · Indonesia only",
         "the legal function of the land under each Indonesian detection"),
    ]
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
    section(0.612, "THE CHAIN, AND WHAT SURVIVED EACH STEP")
    mm, dd = D["ytd_window_end"].split("-")
    ytd_end = f"{int(dd)} {_BULAN[int(mm) - 1]}"
    steps = [
        ("Query FIRMS",
         f"over {bbox[0]}–{bbox[2]}°E, {abs(bbox[1])}°S–{bbox[3]}°N, "
         f"{w[0]} to {w[1]}, confidence ≥ {conf}",
         f"{fmt(M['n_fetched'])} detections" if M.get("n_fetched") else None),
        ("Join to administrative boundaries",
         "point in polygon against GAUL level 1. Anything at sea or off the "
         "island is dropped, never snapped to the nearest unit",
         f"{fmt(D['total'])} kept · {fmt(M['n_outside'])} dropped"
         if M.get("n_outside") is not None else None),
        ("Join to forest function",
         f"point in polygon against {fmt(M['n_kawasan_polygons'])} kawasan "
         f"polygons read over the fire extent. A point on a shared boundary "
         f"is counted once, so the total is conserved"
         if M.get("n_kawasan_polygons") else
         "point in polygon against the kawasan layer, Indonesian points only",
         f"{fmt(D['indonesia_total'])} attributed"),
        ("Rebuild the whole record",
         f"the same definition for 1 Jan–{ytd_end} of every year from "
         f"{M.get('ytd_start_year', 2001)}, summed per region at 1 km",
         f"{fmt(D['ytd_total'])} this year"),
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

    fig.text(0.075, y + 0.012,
             "borneo_fire_payload.py folds the two runs together and refuses "
             "to write if they came from\ndifferent FIRMS vintages. This "
             "document is borneo_fire_pages.py.",
             fontsize=10.5, color=C["muted"], style="italic", va="top")

    # ---- limits --------------------------------------------------------
    section(0.312, "WHAT THESE NUMBERS ARE NOT")
    notes = [
        ("A detection is not a fire.", "Each count is one 1 km pixel on one "
         "day — a pixel-day. A single fire burning a week across four pixels "
         "contributes 28. The quantity is comparable across regions and "
         "years, and nothing more is claimed of it."),
        ("Not comparable to BMKG or ASEAN figures.", "Those use VIIRS at "
         "375 m, which detects several times more hotspots for the same "
         "fires. Earth Engine carries no VIIRS active fire, so the trade is a "
         "lower count for a record that is consistent back to "
         f"{M.get('ytd_start_year', 2001)}."),
        ("Absence is not calm.", "MODIS sees a place twice a day at best and "
         "cloud blocks it entirely. A quiet day in the chart may be a clouded "
         "one, and smoke over a fire front suppresses detection where it is "
         "thickest."),
        ("Kalimantan Utara is inside Kalimantan Timur.", "GAUL 2015 predates "
         "the province created in 2012. The forest layer is Indonesian law "
         "and has no Malaysian or Bruneian equivalent, so Sabah, Sarawak, "
         "Labuan and Brunei carry no forest-function breakdown rather than a "
         "fabricated one."),
    ]
    # Four notes have to clear the footer at 0.028 whatever the wrap does.
    y = 0.284
    for bold, rest in notes:
        fig.text(0.07, y, bold, fontsize=11, color=C["ink"],
                 fontweight="bold")
        body = textwrap.fill(rest, 108)
        fig.text(0.07, y - 0.0165, body, fontsize=10.5, color=C["muted"],
                 va="top")
        y -= 0.0165 + 0.0185 * (body.count("\n") + 1) + 0.0075
    footer(fig, 6)
    save(fig, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
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

    names = ["01_cover", "02_admin", "03_forest_function", "04_map",
             "05_context", "06_method"]
    paths = [os.path.join(a.out, f"borneo_fire_{n}.jpg") for n in names]
    cover(D, paths[0])
    admin_page(D, paths[1])
    function_page(D, paths[2])
    map_page(D, admin, paths[3])
    context_page(D, paths[4])
    method_page(D, paths[5])
    print(f"\n{len(names)} pages in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
