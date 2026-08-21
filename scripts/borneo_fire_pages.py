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

OUT = os.path.expanduser("~/GitHub/rs-change-detection/output/fire")
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


def footer(fig, n, total=5):
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
    fig.text(0.07, 0.225,
             "Half the Indonesian fires are inside the forest estate, and\n"
             f"{fmt(D['protected'])} of them are in protection forest or "
             "conservation areas,\nwhere burning is not permitted under any "
             "licence.",
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
    header(fig, "page 2 · administrative boundary",
           "This is a Kalimantan event",
           "Ninety-nine percent of the island's fires this week are on the\n"
           "Indonesian side. Sarawak and Sabah are not merely quieter — both\n"
           "run BELOW their own 25-year medians for the season to date, while\n"
           "every Kalimantan province runs three to five times above.")
    ax = fig.add_axes([0.07, 0.30, 0.86, 0.50])
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
    ax.set_xlabel("hotspot detections, 14–20 Aug 2026", fontsize=11,
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
    fig.text(0.07, 0.22,
             "Kalbar alone carries 43% of the island total, and Kalteng "
             "another 31%.\nBrunei recorded no detections at all in the window.",
             fontsize=13, color=C["muted"], va="top")
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

    ax3 = fig.add_axes([0.068, 0.175, 0.004, 0.105]); ax3.set_axis_off()
    ax3.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    ax3.set_xlim(0, 1); ax3.set_ylim(0, 1)
    fig.text(0.09, 0.278,
             f"Half the Indonesian fires — {fmt(D['in_estate'])}, "
             f"{100*D['in_estate']/tot:.1f}% — are inside the\n"
             f"forest estate rather than on land released for other use.\n"
             f"{fmt(D['protected'])} of them ({100*D['protected']/tot:.1f}%) "
             "are in protection forest or\nconservation areas, where burning "
             "is not permitted\nunder any licence.",
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
    header(fig, "page 5 · context and method", "The season so far",
           "How this week sits against the 2001–2025 record, and what the\n"
           "numbers can and cannot be asked to do.")

    ax = fig.add_axes([0.07, 0.60, 0.86, 0.20])
    days = D["daily"]
    xs = np.arange(len(days))
    ax.bar(xs, [d["n"] for d in days], color=C["flame"], width=.62)
    ax.set_xticks(xs)
    ax.set_xticklabels([d["d"][8:] + " Aug" for d in days], fontsize=11)
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

    cards = [(fmt(D["ytd_total"]), "1 JAN – 20 AUG 2026",
              "total detections, same definition"),
             (f"{D['ytd_total']/D['ytd_median']:.2f}×", "VS 2001–2025 MEDIAN",
              f"median {fmt(round(D['ytd_median']))}"),
             (f"{D['ytd_rank']} / {D['ytd_years']}", "RANK IN 26 YEARS",
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

    fig.text(0.07, 0.352,
             "2015 sat exactly at the median on 20 August, and became the\n"
             "catastrophe everyone remembers — because its fires peaked in\n"
             "September and October. An August ranking systematically\n"
             "understates El Niño years and cannot tell you how a season ends.",
             fontsize=14.5, color=C["ink"], family="DejaVu Serif", va="top")
    axb = fig.add_axes([0.068, 0.245, 0.004, 0.10]); axb.set_axis_off()
    axb.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    axb.set_xlim(0, 1); axb.set_ylim(0, 1)

    notes = [
        ("Source.", "NASA FIRMS active fire, MODIS Terra + Aqua at 1 km, via "
         "Google Earth Engine, confidence ≥ 30. Boundaries FAO GAUL 2015 "
         "level 1. Forest function from KLHK Penunjukan Kawasan Hutan "
         "1:250,000 (2019)."),
        ("Not comparable to BMKG or ASEAN figures.", "Those use VIIRS at "
         "375 m, which detects several times more hotspots for the same "
         "fires. Earth Engine carries no VIIRS active fire, so the trade is a "
         "lower count for a consistent record back to 2001."),
        ("A detection is not a fire.", "Each count is one 1 km pixel on one "
         "day. A single fire burning a week across four pixels contributes 28. "
         "The quantity is comparable across regions and years, and nothing "
         "more is claimed of it."),
    ]
    y = 0.205
    for bold, rest in notes:
        fig.text(0.07, y, bold, fontsize=11, color=C["ink"],
                 fontweight="bold")
        import textwrap
        body = textwrap.fill(rest, 108)
        fig.text(0.07, y - 0.018, body, fontsize=10.5, color=C["muted"],
                 va="top")
        y -= 0.018 + 0.021 * (body.count("\n") + 1) + 0.012
    footer(fig, 5)
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
             "05_context"]
    paths = [os.path.join(a.out, f"borneo_fire_{n}.jpg") for n in names]
    cover(D, paths[0])
    admin_page(D, paths[1])
    function_page(D, paths[2])
    map_page(D, admin, paths[3])
    context_page(D, paths[4])
    print(f"\n5 pages in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
