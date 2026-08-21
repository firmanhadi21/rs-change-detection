#!/usr/bin/env python3
"""Fire-hotspot scenario — a printable brief on the last N days of active fire.

Answers the three questions asked whenever smoke appears: how many, where, and
whose land. Output is a set of standalone JPEG pages, so the answer travels in
a WhatsApp thread or a slide deck without a browser or a GIS.

    1  cover — the headline count and the country split
    2  by administrative boundary
    3  by forest function, where a forest-estate map is supplied
    4  the map
    5  season context against the multi-year record, and method

WHY A SEPARATE SCENARIO FROM `fire-history`. That one answers "where does this
area burn, and when in the year" over two decades of burned area. This one is
operational: what is alight this week, in which province, on which legal class
of land. Different question, different cadence, different audience.

WHAT IS COUNTED. FIRMS in Earth Engine is MODIS (Terra + Aqua, 1 km). Each
count is one 1 km pixel on one day — "titik panas" in the Indonesian sense —
NOT a distinct fire. One fire burning a week across four pixels contributes 28.
The quantity is comparable across regions and years, which is what is asked of
it, and nothing more.

NOT COMPARABLE TO BMKG OR ASEAN FIGURES, which use VIIRS at 375 m and detect
several times more hotspots for the same fires. Earth Engine carries no VIIRS
active fire, so the trade is a lower count for a record consistent back to
2001. Say which sensor you used whenever you quote a number.

FOREST FUNCTION IS OPTIONAL AND JURISDICTIONAL. Pass --forest-file with a
polygon layer carrying a class field: in Indonesia the KLHK *Penunjukan Kawasan
Hutan* (field FUNGSI_HTN). Detections outside the layer's coverage are reported
as unclassified rather than assigned, so a cross-border AOI does not silently
map one country's land onto another country's law.

Backend: needs --backend gee.
"""

import datetime as _dt
import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

FIRMS_IC = "FIRMS"
DEFAULT_DAYS = 7
DEFAULT_MIN_CONF = 30
BASELINE_START = 2001            # first full year of the MODIS record
GAUL_L1 = "FAO/GAUL/2015/level1"

# Palette: pale green-grey forest paper, deep forest ink, fire in clay and
# amber, protected forest in teal. Picked against the subject rather than
# inherited from a chart default.
C = {
    "ground": "#E9EDE8", "surface": "#F5F7F3", "sunk": "#DFE5DE",
    "ink": "#16231D", "muted": "#64756C", "rule": "#C8D2C8",
    "ember": "#C8471B", "flame": "#DE8A22", "canopy": "#2F6A5B",
    "deep": "#1D4A54", "hpk": "#B0533C", "cons": "#1F5140",
    "water": "#7E9AA6", "sea": "#D6E2E6", "land": "#E4EADF",
}

# KLHK classes collapsed to the functions people actually name. Conservation
# is spread across many legal instruments that all mean "protected" for fire
# reporting, so they are grouped.
FUNGSI_GROUP = {
    "AREA PENGGUNAAN LAIN": "APL (non-forest estate)",
    "HUTAN LINDUNG": "HL (protection forest)",
    "HUTAN PRODUKSI": "HP (production)",
    "HUTAN PRODUKSI TERBATAS": "HPT (limited production)",
    "HUTAN PRODUKSI KONVERSI": "HPK (convertible production)",
    "LAUT/AIR": "water",
}
CONSERVATION = {
    "CAGAR ALAM", "TAMAN NASIONAL", "TAMAN NASIONAL LAUT", "SUAKA MARGASATWA",
    "HUTAN WISATA", "HUTAN SUAKA ALAM DAN MARGASATWA", "KSA/KPA", "TAMAN BURU",
    "TAMAN HUTAN RAYA", "TAMAN WISATA ALAM", "TAMAN WISATA ALAM LAUT",
    "CAGAR ALAM LAUT", "SUAKA MARGASATWA LAUT",
}
# Weakest legal protection to strongest. NOT size order: the gradient is the
# argument page 3 makes, so the ordering carries meaning and must not be
# re-sorted by value.
ORDER = ["APL (non-forest estate)", "HPK (convertible production)",
         "HP (production)", "HPT (limited production)",
         "HL (protection forest)", "Conservation (KSA/KPA)",
         "water", "unclassified"]
FCOL = {
    "APL (non-forest estate)": C["flame"],
    "HPK (convertible production)": C["hpk"],
    "HP (production)": C["ember"],
    "HPT (limited production)": C["deep"],
    "HL (protection forest)": C["canopy"],
    "Conservation (KSA/KPA)": C["cons"],
    "water": C["water"], "unclassified": C["muted"], "_OUT": "#8E9C93",
}

# Cities a reader navigates by, across the Indonesian fire regions and their
# neighbours. Filtered to the map extent at draw time; a fire map without a
# familiar name on it cannot be placed by the person who has to act on it.
# (name, lon, lat, is_capital)
CITIES = [
    # Kalimantan
    ("Pontianak", 109.33, -0.03, 1), ("Singkawang", 108.98, 0.91, 0),
    ("Sintang", 111.50, 0.07, 0), ("Palangka Raya", 113.92, -2.21, 1),
    ("Sampit", 112.95, -2.53, 0), ("Banjarmasin", 114.59, -3.32, 1),
    ("Samarinda", 117.15, -0.50, 1), ("Balikpapan", 116.83, -1.24, 0),
    ("Tanjung Selor", 117.37, 2.84, 1), ("Tarakan", 117.59, 3.31, 0),
    # Malaysian Borneo + Brunei
    ("Kuching", 110.34, 1.56, 1), ("Sibu", 111.83, 2.29, 0),
    ("Bintulu", 113.03, 3.17, 0), ("Miri", 113.99, 4.40, 0),
    ("Kota Kinabalu", 116.07, 5.98, 1), ("Sandakan", 118.12, 5.84, 0),
    ("Tawau", 117.89, 4.24, 0), ("Bandar Seri Begawan", 114.94, 4.89, 1),
    # Sumatra — the other haze theatre
    ("Pekanbaru", 101.45, 0.53, 1), ("Dumai", 101.45, 1.67, 0),
    ("Jambi", 103.61, -1.61, 1), ("Palembang", 104.76, -2.98, 1),
    ("Medan", 98.67, 3.59, 1), ("Padang", 100.36, -0.95, 1),
    ("Bengkulu", 102.27, -3.79, 1), ("Banda Aceh", 95.32, 5.55, 1),
    ("Bandar Lampung", 105.27, -5.43, 1), ("Singapore", 103.82, 1.35, 1),
    # Java, Sulawesi, Papua
    ("Jakarta", 106.85, -6.21, 1), ("Semarang", 110.42, -6.97, 1),
    ("Surabaya", 112.75, -7.26, 1), ("Bandung", 107.62, -6.92, 1),
    ("Makassar", 119.43, -5.15, 1), ("Palu", 119.87, -0.90, 1),
    ("Manado", 124.85, 1.47, 1), ("Kendari", 122.51, -3.99, 1),
    ("Jayapura", 140.72, -2.53, 1), ("Merauke", 140.40, -8.49, 0),
    ("Sorong", 131.26, -0.88, 0), ("Kupang", 123.61, -10.18, 1),
    ("Denpasar", 115.22, -8.65, 1), ("Mataram", 116.12, -8.58, 1),
]
PAGE = (11.0, 15.6)              # inches, A4-ish portrait


# ----------------------------- helpers ---------------------------------
def _fmt(n):
    return f"{int(n):,}"


def _regions(ee, areas, admin, bbox, lon, lat, radius):
    """A FeatureCollection of labelled reporting units, plus its geometry.

    `areas` is the useful case: a list of GAUL level-1 names, which may span
    countries. Country comes from the layer rather than being asserted, so a
    mixed list reports itself correctly.
    """
    from .gee_utils import square_aoi
    l1 = ee.FeatureCollection(GAUL_L1)

    names = []
    if areas:
        names = [a.strip() for a in areas if a and a.strip()]
    elif admin:
        names = [admin]

    if names:
        feats = []
        for n in names:
            sub = l1.filter(ee.Filter.eq("ADM1_NAME", n))
            if sub.size().getInfo() == 0:
                # A country name is a reasonable thing to pass; accept it and
                # dissolve, rather than failing on a technicality.
                sub = l1.filter(ee.Filter.eq("ADM0_NAME", n))
                if sub.size().getInfo() == 0:
                    raise SystemExit(
                        f"area {n!r} not found in FAO GAUL 2015 level-1 "
                        f"(ADM1_NAME or ADM0_NAME). Use the official spelling, "
                        f"e.g. 'Kalimantan Tengah' or 'Brunei Darussalam'.")
                feats.append(ee.Feature(sub.geometry().dissolve(maxError=100),
                                        {"label": n, "country": n}))
                continue
            feats.append(ee.Feature(
                sub.geometry(),
                {"label": n,
                 "country": ee.Feature(sub.first()).get("ADM0_NAME")}))
        fc = ee.FeatureCollection(feats)
        return fc, fc.geometry()

    geom = (ee.Geometry.Rectangle(list(bbox)) if bbox
            else square_aoi(lon, lat, radius))
    # No admin split asked for: report the AOI as one unit rather than
    # inventing a breakdown.
    fc = ee.FeatureCollection([ee.Feature(geom, {"label": "area of interest",
                                                 "country": "—"})])
    return fc, geom


def _window(ee, days):
    firms = ee.ImageCollection(FIRMS_IC)
    end = firms.limit(1, "system:time_start", False).first().date()
    start = end.advance(-(days - 1), "day")
    return firms, start, end


def _points(ee, firms, start, end, geom, min_conf):
    """Detections as (lon, lat, confidence, date), one row per pixel-day."""
    def to_points(img):
        d = img.date().format("YYYY-MM-dd")
        conf = img.select("confidence")
        return conf.updateMask(conf.gte(min_conf)).addBands(
            ee.Image.pixelLonLat()).sample(
            region=geom, scale=1000, geometries=False, dropNulls=True
        ).map(lambda f: f.set("date", d))

    ic = firms.filterDate(start, end.advance(1, "day"))
    fc = ee.FeatureCollection(ic.map(to_points)).flatten()
    n = fc.size().getInfo()
    if n == 0:
        return []
    return fc.reduceColumns(
        ee.Reducer.toList(4),
        ["longitude", "latitude", "confidence", "date"]).get("list").getInfo()


def _baseline(ee, firms, regions, end, start_year, min_conf):
    """Year-to-date totals for each year, on the same month-day window."""
    md = end.format("MM-dd").getInfo()
    this_year = int(end.format("YYYY").getInfo())
    out = {}
    for y in range(start_year, this_year + 1):
        ic = (firms.filterDate(f"{y}-01-01", f"{y}-{md}")
              .select("confidence"))
        img = ic.map(lambda i: i.gte(min_conf).rename("n")).sum().unmask(0)
        v = img.reduceRegion(ee.Reducer.sum(), regions.geometry(), 1000,
                             maxPixels=int(1e10), tileScale=4).get("n")
        try:
            out[y] = int(ee.Number(v).getInfo() or 0)
        except Exception:                                 # noqa: BLE001
            out[y] = 0
        print(f"    {y}  {out[y]:>9,}")
    return out, md


def _classify(fungsi):
    """Map a raw class value to a reporting group.

    A NULL join is not an unclassified area -- it means no polygon contained
    the point, i.e. the detection is OUTSIDE the layer's coverage. Those two
    must not be merged: a forest-estate map is jurisdictional, so on a
    cross-border AOI every foreign detection joins to null, and calling them
    "unclassified" silently pulls them into the denominator of the host
    country's percentages.
    """
    if not isinstance(fungsi, str) or not fungsi.strip():
        return "_OUT"
    v = fungsi.strip().upper()
    if v in CONSERVATION:
        return "Conservation (KSA/KPA)"
    return FUNGSI_GROUP.get(v, v.title())


def _attach_forest(pts, forest_file, forest_layer, forest_field):
    """Join detections to a forest-estate polygon layer, where one is given."""
    import geopandas as gpd
    minx, miny, maxx, maxy = pts.total_bounds
    pad = 0.2
    kw = {"bbox": (minx - pad, miny - pad, maxx + pad, maxy + pad)}
    if forest_layer:
        kw["layer"] = forest_layer
    forest = gpd.read_file(forest_file, **kw)
    if forest_field not in forest.columns:
        raise SystemExit(
            f"--forest-field {forest_field!r} not in {os.path.basename(forest_file)}; "
            f"columns are {[c for c in forest.columns if c != 'geometry'][:12]}")
    print(f"  forest layer: {len(forest)} polygons over the fire extent")
    forest = forest[[forest_field, "geometry"]].copy()
    forest["geometry"] = forest.geometry.force_2d()
    j = gpd.sjoin(pts, forest, how="left", predicate="within")
    # A point exactly on a shared boundary lands in two polygons; keep the
    # first so the total is conserved instead of inflated by double counting.
    j = j[~j.index.duplicated(keep="first")]
    return j[forest_field]


# ----------------------------- pages -----------------------------------
def _page():
    import matplotlib.pyplot as plt
    return plt.figure(figsize=PAGE, facecolor=C["ground"])


def _header(fig, eyebrow, title, sub=None, y=0.955):
    fig.text(0.07, y, eyebrow.upper(), fontsize=10.5, color=C["muted"],
             fontweight="bold")
    fig.text(0.07, y - 0.032, title, fontsize=30, color=C["ink"],
             family="DejaVu Serif", va="top")
    if sub:
        fig.text(0.07, y - 0.072, sub, fontsize=12.5, color=C["muted"],
                 va="top")


def _footer(fig, n, total, source):
    fig.text(0.07, 0.028, source, fontsize=9, color=C["muted"])
    fig.text(0.93, 0.028, f"{n} / {total}", fontsize=9, color=C["muted"],
             ha="right")


def _rule(fig, x, y0, h):
    import matplotlib.patches as mp
    ax = fig.add_axes([x, y0, 0.004, h]); ax.set_axis_off()
    ax.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["ember"]))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def _save(fig, path, dpi=140):
    import matplotlib.pyplot as plt
    fig.savefig(path, dpi=dpi, format="jpg", facecolor=C["ground"],
                pil_kwargs={"quality": 92, "optimize": True})
    plt.close(fig)
    print(f"  {os.path.basename(path)}  {os.path.getsize(path)/1024:.0f} KB")


def _p_cover(S, path, src):
    import matplotlib.patches as mp
    fig = _page()
    _header(fig, f"MODIS FIRMS · {S['w0']} to {S['w1']}", S["title"],
            S["subtitle"])
    fig.text(0.07, 0.70, _fmt(S["total"]), fontsize=132, color=C["ember"],
             family="DejaVu Serif", va="center")
    fig.text(0.07, 0.605, f"DETECTIONS IN {S['days']} DAYS", fontsize=12,
             color=C["muted"], fontweight="bold")
    y = 0.52
    for label, v in S["by_country"]:
        pct = 100 * v / S["total"] if S["total"] else 0
        col = C["ember"] if v == max(x[1] for x in S["by_country"]) \
            else C["muted"]
        fig.text(0.07, y, label, fontsize=14, color=C["ink"])
        fig.text(0.60, y, _fmt(v), fontsize=15, color=col,
                 fontweight="bold", ha="right")
        fig.text(0.68, y, f"{pct:.1f}%", fontsize=13, color=C["muted"],
                 ha="right")
        ax = fig.add_axes([0.71, y - 0.004, 0.22, 0.016]); ax.set_axis_off()
        ax.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["sunk"]))
        ax.add_patch(mp.Rectangle((0, 0), max(pct / 100, 0.004), 1, color=col))
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        y -= 0.052
    if S.get("ytd_total"):
        share = 100 * S["total"] / S["ytd_total"]
        fig.text(0.07, 0.315,
                 f"These {S['days']} days are {share:.0f}% of every hotspot\n"
                 f"detected here since 1 January.",
                 fontsize=19, color=C["ink"], family="DejaVu Serif", va="top")
        _rule(fig, 0.068, 0.268, 0.049)
    if S.get("protected") is not None:
        fig.text(0.07, 0.225,
                 f"{_fmt(S['in_estate'])} are inside the forest estate, and\n"
                 f"{_fmt(S['protected'])} of those are in protection forest or\n"
                 "conservation areas, where burning is not permitted\n"
                 "under any licence.",
                 fontsize=13, color=C["muted"], va="top")
    _footer(fig, 1, S["npages"], src)
    _save(fig, path)


def _p_admin(S, path, src):
    import numpy as np
    fig = _page()
    _header(fig, "administrative boundary", "Where the fires are counted",
            "Detections attributed to the reporting units requested, with the\n"
            "country each belongs to taken from the boundary layer.")
    regions = S["by_region"]
    ax = fig.add_axes([0.07, 0.28, 0.86, 0.52])
    names = [r[0] for r in regions][::-1]
    vals = [r[2] for r in regions][::-1]
    cols = [C["ember"] if r[2] == max(x[2] for x in regions) else C["muted"]
            for r in regions][::-1]
    y = np.arange(len(names))
    ax.barh(y, vals, color=cols, height=.62)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=13)
    ax.set_xlabel(f"detections, {S['w0']} to {S['w1']}", fontsize=11,
                  color=C["muted"])
    ax.set_facecolor(C["ground"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True); ax.xaxis.grid(True, color=C["rule"], lw=.7)
    mx = max(vals) if vals else 1
    for yi, v, r in zip(y, vals, regions[::-1]):
        ax.text(v + mx * .012, yi, _fmt(v), va="center", fontsize=12.5,
                color=C["ink"], fontweight="bold")
        ax.text(v + mx * .012, yi - .30, r[1], va="center", fontsize=9.5,
                color=C["muted"])
    if S.get("admin_note"):
        fig.text(0.07, 0.20, S["admin_note"], fontsize=11.5, color=C["muted"],
                 va="top", style="italic")
    _footer(fig, 2, S["npages"], src)
    _save(fig, path)


def _p_function(S, path, src):
    import matplotlib.patches as mp
    fig = _page()
    _header(fig, "forest function", "Whose land is burning",
            S["forest_note"])
    byF = dict(S["by_function"])
    funcs = [k for k in ORDER if byF.get(k)] + \
            [k for k in byF if k not in ORDER and byF[k]]
    tot = S["classified_total"]
    ax = fig.add_axes([0.07, 0.70, 0.86, 0.045]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    x = 0.0
    for k in funcs:
        w = byF[k] / tot
        ax.add_patch(mp.Rectangle((x, 0), w, 1, color=FCOL.get(k, C["muted"])))
        if w > 0.06:
            ax.text(x + w / 2, .5, f"{100*w:.0f}%", ha="center", va="center",
                    color="white", fontsize=12, fontweight="bold")
        x += w
    fig.text(0.07, 0.755, "WEAKEST PROTECTION", fontsize=9, color=C["muted"],
             fontweight="bold")
    fig.text(0.93, 0.755, "STRONGEST PROTECTION", fontsize=9,
             color=C["muted"], fontweight="bold", ha="right")
    y = 0.635
    for k in funcs:
        n = byF[k]
        a2 = fig.add_axes([0.07, y - 0.002, 0.018, 0.018]); a2.set_axis_off()
        a2.add_patch(mp.Rectangle((0, 0), 1, 1, color=FCOL.get(k, C["muted"])))
        a2.set_xlim(0, 1); a2.set_ylim(0, 1)
        strong = k in ("HL (protection forest)", "Conservation (KSA/KPA)")
        fig.text(0.105, y, k, fontsize=13.5, color=C["ink"],
                 fontweight="bold" if strong else "normal")
        fig.text(0.74, y, _fmt(n), fontsize=13.5, ha="right",
                 fontweight="bold", color=C["ink"])
        fig.text(0.83, y, f"{100*n/tot:.1f}%", fontsize=13, ha="right",
                 color=C["muted"])
        y -= 0.042
    _rule(fig, 0.068, 0.175, 0.105)
    fig.text(0.09, 0.278,
             f"{_fmt(S['in_estate'])} of {_fmt(tot)} classified detections "
             f"({100*S['in_estate']/tot:.1f}%)\nare inside the forest estate "
             f"rather than on land released\nfor other use. "
             f"{_fmt(S['protected'])} ({100*S['protected']/tot:.1f}%) are in "
             "protection forest or\nconservation areas, where burning is not "
             "permitted\nunder any licence.",
             fontsize=15, color=C["ink"], family="DejaVu Serif", va="top")
    fig.text(0.07, 0.125, S["forest_caveat"], fontsize=11.5, color=C["muted"],
             va="top", style="italic")
    _footer(fig, 3, S["npages"], src)
    _save(fig, path)


def _p_map(S, path, src, admin_gdf, page_no):
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.patches as mp
    import matplotlib.patheffects as pe

    fig = _page()
    _header(fig, "location", "Where they are",
            "Every detection in the window, over land, sea, international and\n"
            "reporting boundaries, with the cities the clusters sit near.")
    pc = ccrs.PlateCarree()
    ax = fig.add_axes([0.055, 0.115, 0.89, 0.66], projection=pc)
    ax.set_facecolor(C["sea"])
    for feat, kw, z in (
        (cfeature.OCEAN, {"facecolor": C["sea"]}, 0),
        (cfeature.LAND, {"facecolor": C["land"]}, 1),
        (cfeature.LAKES, {"facecolor": C["sea"]}, 2),
        (cfeature.RIVERS, {"edgecolor": C["water"], "linewidth": .45,
                           "facecolor": "none"}, 3),
        (cfeature.COASTLINE, {"edgecolor": "#7C8C83", "linewidth": .7,
                              "facecolor": "none"}, 6),
        (cfeature.BORDERS, {"edgecolor": "#5A6B62", "linewidth": 1.15,
                            "facecolor": "none"}, 7),
    ):
        try:
            ax.add_feature(feat.with_scale("50m"), zorder=z, **kw)
        except Exception as exc:                          # noqa: BLE001
            print(f"  (basemap layer skipped: {exc.__class__.__name__})")

    # add_geometries, NOT geopandas .plot(): plotting a GeoDataFrame onto a
    # cartopy GeoAxes autoscales the axes and discards set_extent, which
    # silently renders a map of the wrong continent.
    if admin_gdf is not None and len(admin_gdf):
        ax.add_geometries(list(admin_gdf.geometry), crs=pc, facecolor="none",
                          edgecolor="#93A398", linewidth=.6, zorder=6)

    for cls in ORDER + ["_OUT"]:
        sel = [(p[0], p[1]) for p in S["pts"] if p[2] == cls]
        if not sel:
            continue
        strong = cls in ("HL (protection forest)", "Conservation (KSA/KPA)")
        ax.scatter([s[0] for s in sel], [s[1] for s in sel],
                   s=6.5 if strong else 3.0, c=FCOL.get(cls, C["muted"]),
                   marker="o", linewidths=0, alpha=.85 if strong else .62,
                   zorder=9 if strong else 8, transform=pc)

    e = S["extent"]
    for nm, lon, lat, cap in CITIES:
        if not (e[0] < lon < e[1] and e[2] < lat < e[3]):
            continue
        ax.plot(lon, lat, marker="o", ms=4.6 if cap else 3.0, mfc="white",
                mec=C["ink"], mew=1.0 if cap else .7, zorder=11, transform=pc)
        ax.text(lon + 0.13, lat + 0.09, nm, fontsize=8.6 if cap else 7.6,
                color=C["ink"], zorder=12, transform=pc,
                fontweight="bold" if cap else "normal",
                path_effects=[pe.withStroke(linewidth=2.4,
                                            foreground="white")])

    # Pin the extent AFTER everything: several calls above can autoscale, and
    # the last writer wins. `extent` is in cartopy order (x0, x1, y0, y1),
    # which is NOT the GIS bbox order (x0, y0, x1, y1) -- swapping them does
    # not raise, it just draws the wrong part of the world.
    ax.set_extent(e, crs=pc)
    gl = ax.gridlines(draw_labels=True, lw=.4, color=C["rule"], alpha=.7)
    gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": 8.5, "color": C["muted"]}

    present = {p[2] for p in S["pts"]}
    handles = [mp.Patch(color=FCOL.get(k, C["muted"]), label=k)
               for k in ORDER if k in present]
    if "_OUT" in present:
        handles.append(mp.Patch(color=FCOL["_OUT"],
                                label="outside the forest layer"))
    if handles:
        leg = fig.legend(handles=handles, loc="lower center", ncol=3,
                         bbox_to_anchor=(0.5, 0.037), frameon=False,
                         fontsize=10.5)
        for t in leg.get_texts():
            t.set_color(C["ink"])
    _footer(fig, page_no, S["npages"], src)
    _save(fig, path)


def _p_context(S, path, src, page_no):
    import numpy as np
    import matplotlib.patches as mp
    import textwrap
    fig = _page()
    _header(fig, "context and method", "The season so far",
            "How this window sits against the multi-year record, and what the\n"
            "numbers can and cannot be asked to do.")
    ax = fig.add_axes([0.07, 0.60, 0.86, 0.20])
    days = S["daily"]
    xs = np.arange(len(days))
    ax.bar(xs, [d[1] for d in days], color=C["flame"], width=.62)
    ax.set_xticks(xs)
    ax.set_xticklabels([d[0][5:] for d in days], fontsize=10.5)
    ax.set_facecolor(C["ground"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C["rule"])
    ax.tick_params(colors=C["muted"], length=0)
    ax.set_axisbelow(True); ax.yaxis.grid(True, color=C["rule"], lw=.7)
    for xi, d in zip(xs, days):
        ax.text(xi, d[1] * 1.03, _fmt(d[1]), ha="center", fontsize=10.5,
                color=C["ink"], fontweight="bold")
    ax.set_title("detections per day", fontsize=11, color=C["muted"],
                 loc="left")
    fig.text(0.07, 0.565,
             "MODIS sees a place twice a day at best and cloud blocks it "
             "entirely. The dips are as likely to be cloud as calm.",
             fontsize=11, color=C["muted"], style="italic")

    if S.get("ytd_total"):
        cards = [(_fmt(S["ytd_total"]), f"1 JAN – {S['md_end']}",
                  "total detections, same definition"),
                 (f"{S['ytd_total']/S['ytd_median']:.2f}×",
                  f"VS {S['baseline_start']}–{S['ytd_year']-1} MEDIAN",
                  f"median {_fmt(round(S['ytd_median']))}"),
                 (f"{S['ytd_rank']} / {S['ytd_years']}", "RANK IN THE RECORD",
                  "to this date in the year")]
        x0 = 0.07
        for val, lab, sub in cards:
            axc = fig.add_axes([x0, 0.395, 0.268, 0.125]); axc.set_axis_off()
            axc.add_patch(mp.FancyBboxPatch((0.01, 0.02), .98, .96,
                                            boxstyle="round,pad=0.02",
                                            fc=C["surface"], ec=C["rule"]))
            axc.set_xlim(0, 1); axc.set_ylim(0, 1)
            axc.text(.08, .62, val, fontsize=26, color=C["ink"],
                     fontweight="bold")
            axc.text(.08, .40, lab, fontsize=9, color=C["muted"],
                     fontweight="bold")
            axc.text(.08, .22, sub, fontsize=10, color=C["muted"])
            x0 += 0.288
        fig.text(0.07, 0.352,
                 "A ranking taken mid-season is the weakest claim on these\n"
                 "pages. In Indonesia 2015 sat at the median in August and\n"
                 "became the worst year on record, because its fires peaked in\n"
                 "September and October. Mid-year rankings understate El Niño\n"
                 "years and cannot tell you how a season ends.",
                 fontsize=14, color=C["ink"], family="DejaVu Serif", va="top")
        _rule(fig, 0.068, 0.235, 0.11)

    y = 0.205
    for bold, rest in S["notes"]:
        fig.text(0.07, y, bold, fontsize=11, color=C["ink"], fontweight="bold")
        body = textwrap.fill(rest, 108)
        fig.text(0.07, y - 0.018, body, fontsize=10.5, color=C["muted"],
                 va="top")
        y -= 0.018 + 0.021 * (body.count("\n") + 1) + 0.012
    _footer(fig, page_no, S["npages"], src)
    _save(fig, path)


# ----------------------------- entry point ------------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        days=DEFAULT_DAYS, admin=None, areas=None, bbox=None,
        min_confidence=DEFAULT_MIN_CONF, forest_file=None, forest_layer=None,
        forest_field="FUNGSI_HTN", baseline_start=BASELINE_START,
        no_baseline=False):
    """Hotspot brief for the last `days` days, as JPEG pages (GEE)."""
    for mod in ("numpy", "matplotlib", "geopandas", "cartopy"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(
                f"fire-hotspot needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("fire-hotspot currently needs --backend gee (FIRMS).")

    import ee
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    from .gee_utils import initialize_ee
    initialize_ee(config_key)

    days = max(1, int(days))
    regions, geom = _regions(ee, areas, admin, bbox, lon, lat, radius)
    firms, start, end = _window(ee, days)
    w0 = start.format("YYYY-MM-dd").getInfo()
    w1 = end.format("YYYY-MM-dd").getInfo()
    print(f"FIRMS (MODIS 1 km) {w0} .. {w1}, confidence >= {min_confidence}")

    rows = _points(ee, firms, start, end, geom, min_confidence)
    if not rows:
        print("  no detections in the window — nothing to report")
        return
    pts = gpd.GeoDataFrame(
        pd.DataFrame(rows, columns=["lon", "lat", "confidence", "date"]),
        geometry=gpd.points_from_xy([r[0] for r in rows],
                                    [r[1] for r in rows]), crs="EPSG:4326")
    print(f"  {len(pts):,} detections over {pts.date.nunique()} days")

    gj = regions.getInfo()
    admin_gdf = gpd.GeoDataFrame.from_features(gj["features"], crs="EPSG:4326")
    pts = gpd.sjoin(pts, admin_gdf[["label", "country", "geometry"]],
                    how="left", predicate="within").drop(columns="index_right")
    dropped = int(pts.label.isna().sum())
    pts = pts[pts.label.notna()].copy()
    if dropped:
        print(f"  {dropped} fell outside the reporting units (sea or edge)")

    # --- forest function, optional ---------------------------------------
    S = {}
    if forest_file and os.path.exists(os.path.expanduser(forest_file)):
        pts["fungsi_raw"] = _attach_forest(
            pts, os.path.expanduser(forest_file), forest_layer, forest_field)
        pts["cls"] = pts["fungsi_raw"].map(_classify)
    else:
        if forest_file:
            print(f"  (forest layer not found: {forest_file})")
        pts["cls"] = "_OUT"

    classified = pts[pts.cls != "_OUT"]
    if len(classified):
        prot = classified[classified.cls.isin(
            ["HL (protection forest)", "Conservation (KSA/KPA)"])]
        est = classified[~classified.cls.isin(
            ["APL (non-forest estate)", "water", "unclassified"])]
        S["protected"] = int(len(prot))
        S["in_estate"] = int(len(est))
        S["classified_total"] = int(len(classified))
        S["by_function"] = [(k, int(v)) for k, v in
                            classified.cls.value_counts().items()]

    # --- baseline ---------------------------------------------------------
    if not no_baseline:
        print("  year-to-date baseline:")
        ytd, md_end = _baseline(ee, firms, regions, end, int(baseline_start),
                                min_confidence)
        years = sorted(ytd)
        vals = np.array([ytd[y] for y in years], float)
        S.update(ytd_total=int(vals[-1]),
                 ytd_median=float(np.median(vals[:-1])) if len(vals) > 1
                 else float(vals[-1]),
                 ytd_rank=int((vals[:-1] > vals[-1]).sum()) + 1,
                 ytd_years=len(years), ytd_year=years[-1], md_end=md_end,
                 baseline_start=int(baseline_start))

    # --- assemble ---------------------------------------------------------
    by_region = [(r, pts[pts.label == r].country.iloc[0], int(n))
                 for r, n in pts.label.value_counts().items()]
    by_country = [(c, int(n)) for c, n in
                  pts.country.value_counts().items()]
    b = pts.total_bounds
    pad = max(0.35, 0.06 * max(b[2] - b[0], b[3] - b[1]))
    S.update(
        title=name or "Hotspot brief", days=days, w0=w0, w1=w1,
        subtitle=("Active-fire detections over the reporting area, attributed\n"
                  "to administrative unit" +
                  (" and to the legal function of the land beneath."
                   if "by_function" in S else ".")),
        total=int(len(pts)), by_region=by_region, by_country=by_country,
        daily=[(d, int(n)) for d, n in pts.date.value_counts().sort_index()
               .items()],
        # cartopy order, deliberately distinct from a GIS bbox
        extent=[b[0] - pad, b[2] + pad, b[1] - pad, b[3] + pad],
        pts=[[round(float(r.lon), 3), round(float(r.lat), 3), r.cls]
             for r in pts.itertuples()],
        admin_note=("Boundaries are FAO GAUL 2015. Provinces created after "
                    "that date — Kalimantan Utara among them — are still "
                    "counted inside their parent."),
        forest_note=("Detections placed on the supplied forest-estate layer,\n"
                     "ordered by how much legal protection the land carries."),
        forest_caveat=("Detections outside the layer's coverage are reported "
                       "as outside it, not assigned:\na forest-estate "
                       "designation is jurisdictional and does not cross a "
                       "border."),
        notes=[
            ("Source.", f"NASA FIRMS active fire, MODIS Terra + Aqua at 1 km, "
             f"via Google Earth Engine, confidence ≥ {min_confidence}. "
             f"Boundaries FAO GAUL 2015 level 1." +
             (f" Forest function from {os.path.basename(forest_file)}."
              if "by_function" in S else "")),
            ("Not comparable to VIIRS-based figures.", "BMKG and ASEAN "
             "hotspot counts use VIIRS at 375 m, which detects several times "
             "more hotspots for the same fires. Earth Engine carries no VIIRS "
             "active fire, so the trade is a lower count for a record "
             "consistent back to 2001. Always say which sensor a number came "
             "from."),
            ("A detection is not a fire.", "Each count is one 1 km pixel on "
             "one day. A single fire burning a week across four pixels "
             "contributes 28. The quantity is comparable across regions and "
             "years, and nothing more is claimed of it."),
        ],
    )
    S["npages"] = 5 if "by_function" in S else 4

    src = ("MODIS FIRMS · FAO GAUL 2015" +
           (" · forest estate layer" if "by_function" in S else ""))
    os.makedirs(run_dir, exist_ok=True)
    stem = os.path.join(run_dir, f"{run_id}_hotspot")
    print("\n  pages:")
    n = 1
    _p_cover(S, f"{stem}_01_cover.jpg", src); n += 1
    _p_admin(S, f"{stem}_02_admin.jpg", src); n += 1
    if "by_function" in S:
        _p_function(S, f"{stem}_03_function.jpg", src); n += 1
    _p_map(S, f"{stem}_{n:02d}_map.jpg", src, admin_gdf, n); n += 1
    _p_context(S, f"{stem}_{n:02d}_context.jpg", src, n)

    pts.drop(columns="geometry").to_csv(f"{stem}.csv", index=False)
    with open(f"{stem}.json", "w") as f:
        json.dump({k: v for k, v in S.items() if k != "pts"}, f, indent=1,
                  default=str)
    print(f"\n  {S['npages']} pages + {os.path.basename(stem)}.csv in {run_dir}")
