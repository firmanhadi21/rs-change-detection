#!/usr/bin/env python3
"""Did the 2026 fires in four Ketapang concessions start inside them, and what
was burning?

The Kalimantan concession analysis (kalimantan_burn_concessions.py) found four
neighbouring concessions on the Ketapang coast holding a disproportionate
share of the year's burn: PT AM (Agro Majusejahtera), PT SKM (Sinar Karya
Mandiri), PT MKK (Mekar Karya Kahuripan) and PT SPAS (Sungai Putri Agro
Sawit). This script asks two follow-up questions.

1. WHERE DID THE FIRE START? VIIRS active-fire detections (375 m, Suomi-NPP
   and NOAA-20, about four overpasses a day between them; 'low' confidence
   dropped) are traced back to their ignitions. Each detection gets one
   parent: the nearest detection within PARENT_KM seen in the PARENT_H hours
   before it (or, failing that, an adjacent detection in the same overpass).
   A detection with no parent is an IGNITION: fire appearing where none had
   been seen nearby for four days. Following parents back gives every
   detection's root ignition, so each detection inside a concession is
   attributed to an ignition inside it, in another concession, or outside.

   Why not cluster detections into events? Peat smoulders for weeks and the
   fronts merge; a 1 km / 48 h single-linkage rule chains one complex of
   80,000 detections over 62 days across three concessions, whose "first
   detection" says nothing about the rest. A parent tree keeps each
   detection's own lineage.

   The parent radius and window are deliberately generous: a long reach makes
   more fire count as having spread in from elsewhere and fewer ignitions,
   which is the cautious direction when the question is whether fire was lit
   inside. SENS re-runs the attribution with tighter and looser settings.

   An ignition is ISOLATED when no other fire was detected within NEAR_KM in
   the NEAR_H hours before it, which rules out a front or a short ember
   throw as its source. It is an EDGE ignition within EDGE_KM (two VIIRS
   pixels) of the boundary, where inside and outside cannot be told apart.

2. WHAT WAS BURNING? On a 25 m grid (nested in the 500 m MCD64A1 lattice):
     burned      Sentinel-2 dNBR (pre Apr - mid Jul, post Sep - Oct 2026)
                 above DNBR_T, kept only within NEAR_BURN_M of a VIIRS
                 detection or an MCD64A1 burned pixel so that harvest or
                 replanting clearance is not counted as fire
     oil palm    Descals et al. (2024), BIOPAMA/GlobalOilPalm/v1_2: closed-
                 canopy industrial / smallholder palm and the establishment
                 year of the current stand as of 2021 (left-censored at 1989;
                 2019-2021 is mostly replanting)
     forest      Hansen GFC v1.12: tree cover 2000 and year of loss to 2024
   Burned land in each concession is broken down by those classes and set
   against the concession's whole composition, which shows whether fire picked
   out old palm, young palm, or land that was not palm at all.

WHAT IT CANNOT SHOW. Satellite detections place a fire and time it to within
a few hours; they do not show who lit it or why. Cloud and thick smoke hide
detections, so an "ignition" can be a fire first seen there rather than first
lit there, and a peat fire smouldering unseen for more than PARENT_H hours
reappears as a new ignition. Concession boundaries are the GFW / Ministry of
Forestry layer of about 2012. The palm map stops at 2021.

    conda run -n base python scripts/ketapang_fire_origin.py
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin")
CONC = os.path.join(_DATA_ROOT, "output", "fire", "kalimantan_concessions",
                    "concessions_kalimantan.gpkg")
# Peat. PRIMARY: the team's own random-forest peat / mineral classification
# of Kalimantan (50 m, EPSG:3857, 1 = peat, nodata elsewhere). Compared with
# the Ministry of Agriculture (BBSDLP) map served by GFW, and PEATGRIDS
# (1 km modelled thickness) for depth only -- neither map carries depth.
PEAT_OWN = os.path.join(_DATA_ROOT, "data", "peat", "Kalimantan_3857.tif")
PEAT = os.path.join(_DATA_ROOT, "data", "peat", "gfw_idn_peat_ketapang.gpkg")
PEAT_URL = ("https://gis-gfw.wri.org/arcgis/rest/services/country_data/asia/"
            "MapServer/10/query")      # GFW "Indonesia Peat Lands" (BBSDLP)
PEATGRIDS_IMG = "projects/sat-io/open-datasets/PEATGRIDS/THICKNESS_CM"
DEEP_CM = 300                  # PP 57/2016: peat >= 3 m is protected
MODIS_TILES = os.path.join(_DATA_ROOT, "output", "fire", "kalimantan_concessions",
                           "tiles_2026_2023_2019")

sys.path.insert(0, _REPO_ROOT)
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

FOUR = {"PT AM": "Agro Majusejahtera", "PT SKM": "Sinar Karya Mandiri",
        "PT MKK": "Mekar Karya Kahuripan", "PT SPAS": "Sungai Putri Agro Sawit"}
BUF_DEG = 0.2                  # AOI = the four's bbox grown by this
GRID = 0.000225                # 25 m; 20 of these make one 0.0045 MCD64A1 cell
TILES = 4
UTM = "EPSG:32749"
VIIRS = ["NASA/LANCE/SNPP_VIIRS/C2", "NASA/LANCE/NOAA20_VIIRS/C2"]
START, END = "2026-01-01", "2026-11-03"
PARENT_KM, PARENT_H = 1.5, 96
SENS = [(1.0, 48), (1.5, 96), (3.0, 168)]
SAME_S = 900                   # detections this close in time = one overpass
NEAR_KM, NEAR_H = 5.0, 72
EDGE_KM = 0.75
RING_KM = 10.0
SEASON = (7, 10)               # months: the main burn
DNBR_T = 0.27                  # Key & Benson low-moderate severity threshold
NEAR_BURN_M = 750
BIG = 20                       # descendants that make an ignition "large"


# ----------------------------- Earth Engine -----------------------------
def viirs_points(aoi_rect):
    import ee
    rows = []
    for cid in VIIRS:
        ic = ee.ImageCollection(cid).filterDate(START, END).filterBounds(aoi_rect)

        def pts(img):
            b = img.select(["confidence", "frp", "acq_epoch", "DayNight"])
            return b.addBands(ee.Image.pixelLonLat()).sample(
                region=aoi_rect, projection=img.select("frp").projection(),
                geometries=False, dropNulls=True)

        fc = ee.FeatureCollection(ic.map(pts)).flatten()
        cols = ["longitude", "latitude", "confidence", "frp", "acq_epoch",
                "DayNight"]
        lst = fc.reduceColumns(ee.Reducer.toList(len(cols)), cols) \
                .get("list").getInfo()
        sat = cid.split("/")[2].split("_")[0]
        rows += [r + [sat] for r in lst]
        print(f"  {cid}: {len(lst):,} detections")
    return rows


def stack_image():
    import ee
    op = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2")
    cls = op.select("classification").mosaic().unmask(0).rename("cls")
    py = op.select("planting_year").mosaic().unmask(0).rename("py")
    gfc = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")

    def nbr(lo, hi):
        def one(im):
            scl = im.select("SCL")
            ok = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
            return im.normalizedDifference(["B8", "B12"]).updateMask(ok)
        return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterDate(lo, hi).filter(ee.Filter.lt(
                    "CLOUDY_PIXEL_PERCENTAGE", 80)).map(one).median())

    dnbr = nbr("2026-04-01", "2026-07-15").subtract(nbr("2026-09-01", "2026-11-01"))
    dnbr = dnbr.multiply(1000).round().unmask(-32768).rename("dnbr")
    return ee.Image.cat([cls, py, gfc.select("treecover2000").rename("tc2000"),
                         gfc.select("lossyear").rename("loss"), dnbr,
                         gfc.select("datamask").rename("land")]).toInt16()


STACK_BANDS = ["cls", "py", "tc2000", "loss", "dnbr", "land"]


def download_stack(bbox, out_dir):
    import ee
    import numpy as np
    import rasterio
    from rasterio.merge import merge
    from earthchange.gee_utils import download_geotiff
    img = stack_image()
    x0, y0, x1, y1 = bbox
    c0, c1 = int(np.floor(x0 / GRID)), int(np.ceil(x1 / GRID))
    r0, r1 = int(np.floor(-y1 / GRID)), int(np.ceil(-y0 / GRID))
    cs = np.linspace(c0, c1, TILES + 1).astype(int)
    rs = np.linspace(r0, r1, TILES + 1).astype(int)
    paths = []
    for i in range(TILES):
        for j in range(TILES):
            p = os.path.join(out_dir, f"stack_{i}{j}.tif")
            if os.path.exists(p):
                with rasterio.open(p) as ds:
                    if ds.count != len(STACK_BANDS):
                        os.remove(p)            # from an older band list
            if not os.path.exists(p):
                reg = ee.Geometry.Rectangle(
                    [cs[j] * GRID, -rs[i + 1] * GRID, cs[j + 1] * GRID,
                     -rs[i] * GRID], None, False)
                if not download_geotiff(img, reg, p, max_scale_mult=1,
                                        crs_transform=[GRID, 0, 0, 0, -GRID, 0]):
                    raise SystemExit(f"download failed for {p}")
            paths.append(p)
    srcs = [rasterio.open(p) for p in paths]
    arr, tr = merge(srcs, method="first")
    for s in srcs:
        s.close()
    return arr, tr


def fetch_peat(bbox, path):
    """GFW 'Indonesia Peat Lands' (Ministry of Agriculture / BBSDLP) polygons
    intersecting bbox. Esri JSON, because the server's GeoJSON output carries
    null coordinates on the large polygons."""
    import geopandas as gpd
    import requests
    from shapely import make_valid
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    def poly(rings):
        def ccw(r):
            return sum((x2 - x1) * (y2 + y1)
                       for (x1, y1), (x2, y2) in zip(r, r[1:])) < 0
        shells = [make_valid(Polygon(r)) for r in rings if len(r) >= 4 and not ccw(r)]
        holes = [make_valid(Polygon(r)) for r in rings if len(r) >= 4 and ccw(r)]
        g = unary_union(shells)
        return g.difference(unary_union(holes)) if holes else g

    feats, off = [], 0
    while True:
        r = requests.get(PEAT_URL, params={
            "where": "1=1", "outFields": "*", "f": "json", "outSR": 4326,
            "inSR": 4326, "geometry": ",".join(map(str, bbox)),
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "resultOffset": off, "resultRecordCount": 1000}, timeout=120)
        r.raise_for_status()
        f = r.json().get("features", [])
        feats += f
        if len(f) < 1000:
            break
        off += len(f)
    rows = [f["attributes"] | {"geometry": poly(
        [[tuple(p[:2]) for p in ring if p[0] is not None]
         for ring in f["geometry"]["rings"]])} for f in feats]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gpd.GeoDataFrame(rows, crs=4326).to_file(path)
    print(f"Saved: {path} ({len(rows)} peat polygons)")


def own_peat_on_grid(path, bbox, tr, shape):
    """The team's 50 m peat raster (EPSG:3857) onto the 25 m lattice, read
    through a window so the 1.9 GB Kalimantan file is not loaded whole."""
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling, transform_bounds
    from rasterio.windows import from_bounds
    with rasterio.open(path) as src:
        b = transform_bounds("EPSG:4326", src.crs, *bbox, densify_pts=21)
        w = from_bounds(*b, src.transform).round_offsets().round_lengths()
        a = src.read(1, window=w, boundless=True, fill_value=0)
        wtr = src.window_transform(w)
        a = (a == 1).astype(np.uint8)
        dst = np.zeros(shape, np.uint8)
        reproject(a, dst, src_transform=wtr, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:4326",
                  resampling=Resampling.nearest)
    return dst > 0


def peatgrids_on_grid(bbox, tr, shape, out_dir):
    """PEATGRIDS thickness (cm, ~1 km) resampled onto the 25 m grid."""
    import ee
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling
    from earthchange.gee_utils import download_geotiff
    p = os.path.join(out_dir, "peatgrids_thickness_cm.tif")
    if not os.path.exists(p):
        img = ee.Image(PEATGRIDS_IMG).select(0).unmask(0).toInt16()
        reg = ee.Geometry.Rectangle(list(bbox), None, False)
        if not download_geotiff(img, reg, p, scale=1000):
            raise SystemExit("PEATGRIDS download failed")
    dst = np.zeros(shape, np.int16)
    with rasterio.open(p) as src:
        reproject(rasterio.band(src, 1), dst, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:4326",
                  resampling=Resampling.nearest)
    return dst


# ------------------------------- lineage --------------------------------
def _by_day(t):
    import numpy as np
    day = np.floor(t / 86400).astype(int)
    return day, {d: np.flatnonzero(day == d) for d in np.unique(day)}


def trace(xy, t, km, hours):
    """Parent of each detection (index into the time-sorted arrays, -1 for an
    ignition) and its root ignition. `t` must be sorted ascending."""
    import numpy as np
    from scipy.spatial import cKDTree
    n = len(t)
    parent = np.full(n, -1)
    day, idx = _by_day(t)
    back = int(np.ceil(hours / 24))
    for d, ii in idx.items():
        cand = np.concatenate([idx[k] for k in range(d - back, d + 1) if k in idx])
        tree = cKDTree(xy[cand])
        for i, nb in zip(ii, tree.query_ball_point(xy[ii], km)):
            if not nb:
                continue
            j = cand[nb]
            dt = t[i] - t[j]
            earlier = (dt > SAME_S) & (dt <= hours * 3600)
            if earlier.any():
                jj = j[earlier]
            else:
                same = (np.abs(dt) <= SAME_S) & (j < i)
                if not same.any():
                    continue
                jj = j[same]
            parent[i] = jj[np.argmin(np.hypot(*(xy[jj] - xy[i]).T))]
    root = np.arange(n)
    for i in range(n):                  # parents always come first
        if parent[i] >= 0:
            root[i] = root[parent[i]]
    return parent, root


def prior_within(xy, t, sel, km, hours):
    """For each index in `sel`: detections within km in the hours before it."""
    import numpy as np
    from scipy.spatial import cKDTree
    day, idx = _by_day(t)
    back = int(np.ceil(hours / 24))
    out = {}
    for d in np.unique(day[sel]):
        ii = sel[day[sel] == d]
        cand = np.concatenate([idx[k] for k in range(d - back, d + 1) if k in idx])
        tree = cKDTree(xy[cand])
        for i, nb in zip(ii, tree.query_ball_point(xy[ii], km)):
            j = cand[nb]
            dt = t[i] - t[j]
            out[i] = int(((dt > SAME_S) & (dt <= hours * 3600)).sum())
    return np.array([out[i] for i in sel])


# ------------------------------- land cover -----------------------------
AGE_BINS = [  # (label, py lo, py hi) -- age is 2026 - planting year
    ("palm, planted ≤2001 (≥25 yr: replanting age)", 1, 2001),
    ("palm, planted 2002-2011 (15-24 yr)", 2002, 2011),
    ("palm, planted 2012-2018 (8-14 yr)", 2012, 2018),
    ("palm, planted 2019-2022 (young / replanted)", 2019, 2100),
]
NONPALM = [
    "not palm: forest in 2000, still standing 2024",
    "not palm: forest cleared 2001-2015",
    "not palm: forest cleared 2016-2024",
    "not palm: non-forest since 2000 (scrub, fern, open peat)",
]
CLASSES = [b[0] for b in AGE_BINS] + NONPALM
COLORS = ["#4a1d0f", "#8c4a20", "#c98a3e", "#ecc46a",
          "#1f5a3a", "#6f9a63", "#a9c48f", "#d9d3c4"]


def classify(cls, py, tc, loss, land):
    import numpy as np
    out = np.full(cls.shape, 255, np.uint8)
    palm = cls > 0
    for k, (_, lo, hi) in enumerate(AGE_BINS):
        out[palm & (py >= lo) & (py <= hi)] = k
    out[palm & (py == 0)] = 2                    # palm without a year: mid bin
    np_ = ~palm
    forest = tc >= 30
    out[np_ & forest & (loss == 0)] = 4
    out[np_ & forest & (loss >= 1) & (loss <= 15)] = 5
    out[np_ & forest & (loss >= 16)] = 6
    out[np_ & ~forest] = 7
    out[land != 1] = 255
    return out


# ------------------------------- figures --------------------------------
def render_map(path, lc, tr, burned, conc4, pts, ign, peat, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    h, w = lc.shape
    ext = (tr.c, tr.c + w * tr.a, tr.f + h * tr.e, tr.f)
    rgba = np.zeros((h, w, 4))
    m = lc < 255
    rgba[m] = ListedColormap(COLORS)(lc[m])
    rgba[m, 3] = 0.6
    fig, ax = plt.subplots(figsize=(12, 12.5), dpi=150)
    ax.set_facecolor("#cfdde3")
    ax.imshow(rgba, extent=ext, interpolation="nearest")
    ax.contour(burned.astype(float), levels=[0.5], colors="#d7301f",
               linewidths=0.4, extent=ext, origin="upper")
    # display only: the RF map is speckled at pixel level, so draw its ~250 m
    # majority outline rather than every pixel edge
    from scipy import ndimage
    smooth = ndimage.uniform_filter(peat[::2, ::2].astype(np.float32), 5) > 0.5
    ax.contour(smooth.astype(float), levels=[0.5], colors="#1d3fbf",
               linewidths=1.3, linestyles="--", extent=ext, origin="upper")
    sc = ax.scatter(pts.lon, pts.lat, c=pts.doy, cmap="plasma", s=1.2, lw=0,
                    vmin=182, vmax=305, alpha=0.6)
    conc4.boundary.plot(ax=ax, color="black", lw=1.5)
    for _, r in conc4.iterrows():
        c = r.geometry.representative_point()
        ax.annotate(r.acr, (c.x, c.y), fontsize=12, weight="bold",
                    ha="center", bbox=dict(fc="white", ec="black", lw=0.6,
                                           boxstyle="round,pad=0.2"))
    ins = ign["in_four"]
    for sel, fc, lab in [(ins & ign.isolated, "white", "isolated"),
                         (ins & ~ign.isolated, "#999999", "not isolated"),
                         (~ins, "#3b6ea8", "outside")]:
        s = ign[sel]
        ax.scatter(s.lon, s.lat, marker="*", s=40 + 4 * np.sqrt(s.size_all),
                   c=fc, edgecolors="black", lw=0.7, zorder=5)
    cb = fig.colorbar(sc, ax=ax, shrink=0.4, pad=0.01)
    cb.set_ticks([182, 213, 244, 274, 305])
    cb.set_ticklabels(["1 Jul", "1 Aug", "1 Sep", "1 Oct", "1 Nov"])
    cb.set_label("VIIRS detection, 2026")
    x0, y0, x1, y1 = conc4.total_bounds
    ax.set_xlim(x0 - 0.06, x1 + 0.06)
    ax.set_ylim(y0 - 0.06, y1 + 0.06)
    ax.set_aspect("equal")
    ax.set_title(title, loc="left", fontsize=13)
    hd = [Patch(fc=c, alpha=0.6, label=l) for c, l in zip(COLORS, CLASSES)]
    hd += [Line2D([], [], color="#d7301f", lw=1, label="burned Jul-Oct 2026 "
                  "(Sentinel-2 dNBR)"),
           Line2D([], [], color="#1d3fbf", lw=1.2, ls="--",
                  label="peat (own RF peat map, 50 m)"),
           Line2D([], [], marker="*", ls="", mfc="white", mec="black", ms=11,
                  label=f"ignition inside, isolated (nothing within "
                        f"{NEAR_KM:.0f} km in {NEAR_H} h before)"),
           Line2D([], [], marker="*", ls="", mfc="#999999", mec="black", ms=11,
                  label="ignition inside, other fire nearby"),
           Line2D([], [], marker="*", ls="", mfc="#3b6ea8", mec="black", ms=11,
                  label="ignition outside that spread in")]
    ax.legend(handles=hd, loc="lower left", fontsize=7.2, framealpha=0.92)
    ax.text(0.99, 0.01, f"Ignitions with ≥{BIG} descendant detections, Jul-Oct; "
            "star size ~ fire size.\nPalm & planting year: Descals et al. 2024 "
            "(to 2021). Forest: Hansen GFC v1.12.\nFire: VIIRS 375 m (S-NPP, "
            "NOAA-20). Concessions: GFW / KLHK c.2012.",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7,
            color="#222", bbox=dict(fc="white", ec="none", alpha=0.8))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


def render_timeline(path, det, acrs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    fig, axes = plt.subplots(len(acrs), 1, figsize=(11, 2.3 * len(acrs)),
                             sharex=True, dpi=150)
    days = pd.date_range("2026-06-15", "2026-10-31")
    for ax, a in zip(axes, acrs):
        dx = det[det["where"] == a]
        own = dx[dx.root_where == a].groupby("date").size() \
            .reindex(days, fill_value=0)
        other = dx[dx.root_where != a].groupby("date").size() \
            .reindex(days, fill_value=0)
        ign = det[(det["where"] == a) & det.is_root].groupby("date").size() \
            .reindex(days, fill_value=0)
        ax.bar(days, own, color="#b3001b", width=1,
               label=f"inside, from ignitions inside {a}")
        ax.bar(days, other, bottom=own, color="#f08a24", width=1,
               label="inside, spread in from outside")
        ax2 = ax.twinx()
        ax2.plot(days, ign, color="black", lw=0.8, drawstyle="steps-mid",
                 label="new ignitions inside (right axis)")
        ax2.set_ylim(0, max(4, ign.max() * 1.6))
        ax.set_ylabel(a, rotation=0, ha="right", weight="bold")
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7, frameon=False)
    axes[0].set_title("VIIRS detections per day inside each concession, by "
                      "where their fire started", loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# --------------------------------- main ---------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from rasterio.merge import merge
    from scipy import ndimage

    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    import ee

    os.makedirs(a.out, exist_ok=True)
    conc = gpd.read_file(CONC).to_crs(4326)
    conc["geometry"] = conc.geometry.make_valid()
    rows = []
    for acr, name in FOUR.items():
        s = conc[conc.company.str.contains(name, case=False, na=False)]
        if len(s) != 1:
            raise SystemExit(f"{name}: {len(s)} polygons")
        rows.append(s.iloc[0].to_dict() | {"acr": acr})
    conc4 = gpd.GeoDataFrame(rows, crs=4326)
    x0, y0, x1, y1 = conc4.total_bounds
    bbox = (x0 - BUF_DEG, y0 - BUF_DEG, x1 + BUF_DEG, y1 + BUF_DEG)
    near = conc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]].copy()
    near["acr"] = near.company
    for acr, name in FOUR.items():
        near.loc[near.company.str.contains(name, case=False, na=False),
                 "acr"] = acr
    aoi = ee.Geometry.Rectangle(list(bbox), None, False)

    # --- VIIRS --------------------------------------------------------------
    vp = os.path.join(a.out, f"viirs_{START}_{END}.csv")
    if os.path.exists(vp):
        det = pd.read_csv(vp)
    else:
        print("VIIRS detections ...")
        det = pd.DataFrame(viirs_points(aoi), columns=[
            "lon", "lat", "confidence", "frp", "acq_epoch", "daynight", "sat"])
        det.to_csv(vp, index=False)
    n_all = len(det)
    det = det[det.confidence >= 1]               # 0 low, 1 nominal, 2 high
    print(f"{n_all:,} VIIRS detections in AOI, {len(det):,} nominal/high")
    det = det.sort_values("acq_epoch", kind="stable").reset_index(drop=True)
    det["time"] = pd.to_datetime(det.acq_epoch, unit="s", utc=True) \
        .dt.tz_convert("Asia/Pontianak")
    det["date"] = det.time.dt.tz_localize(None).dt.normalize()
    det["doy"] = det.time.dt.dayofyear
    det["month"] = det.time.dt.month
    g = gpd.GeoDataFrame(det[["lon", "lat"]],
                         geometry=gpd.points_from_xy(det.lon, det.lat), crs=4326)
    gu = g.to_crs(UTM)
    xy = np.c_[gu.geometry.x, gu.geometry.y] / 1000.0      # km
    t = det.acq_epoch.to_numpy(float)

    j = gpd.sjoin(g[["geometry"]], near[["acr", "geometry"]], how="left",
                  predicate="within")
    j = j[~j.index.duplicated()]
    det["where"] = j["acr"].fillna("outside").to_numpy()
    det.loc[~det["where"].isin(list(FOUR) + ["outside"]), "where"] = "other conc."
    c4u = conc4.to_crs(UTM)
    for _, r in c4u.iterrows():
        d = gu.geometry.distance(r.geometry.boundary).to_numpy() / 1000
        det[f"d_{r.acr}"] = np.where(gu.geometry.within(r.geometry), -d, d)
    dcols = [f"d_{x}" for x in FOUR]
    det["edge"] = det[dcols].abs().min(axis=1) <= EDGE_KM

    # --- lineage ------------------------------------------------------------
    sens = {}
    for km, hh in SENS:
        print(f"tracing lineage, parent within {km} km / {hh} h ...")
        par, root = trace(xy, t, km, hh)
        rw = det["where"].to_numpy()[root]
        sens[f"{km}km_{hh}h"] = {
            x: {"share_inside_from_own_ignitions": float(
                    (rw[det["where"].to_numpy() == x] == x).mean()),
                "ignitions_inside_jul_oct": int(
                    ((par == -1) & (det["where"] == x)
                     & det.month.between(*SEASON)).sum())}
            for x in FOUR}
        if (km, hh) == (PARENT_KM, PARENT_H):
            det["parent"], det["root"] = par, root
    det["is_root"] = det.parent == -1
    det["root_where"] = det["where"].to_numpy()[det.root.to_numpy()]
    det["root_edge"] = det.edge.to_numpy()[det.root.to_numpy()]
    print(json.dumps(sens, indent=1))

    # ignitions: size, isolation, location class
    roots = np.flatnonzero(det.is_root.to_numpy())
    size_all = np.bincount(det.root, minlength=len(det))[roots]
    ign = det.loc[roots, ["lon", "lat", "time", "date", "month", "where",
                          "edge", "frp"] + dcols].copy()
    ign["size_all"] = size_all
    for x in FOUR:
        ign[f"size_in_{x}"] = np.bincount(
            det.root[det["where"] == x], minlength=len(det))[roots]
    ign["prior_within_5km"] = prior_within(xy, t, roots, NEAR_KM, NEAR_H)
    ign["isolated"] = ign.prior_within_5km == 0
    ign["in_four"] = ign["where"].isin(list(FOUR))
    ign["root_index"] = roots

    # --- 25 m stack --------------------------------------------------------
    sdir = os.path.join(a.out, "stack")
    os.makedirs(sdir, exist_ok=True)
    print("25 m stack (palm, forest, dNBR, land) ...")
    arr, tr = download_stack(bbox, sdir)
    cls, py, tc, loss, dnbr, landb = [arr[i] for i in range(len(STACK_BANDS))]
    loss = np.where(loss < 0, 0, loss)   # lossyear is masked where no loss
    shape = cls.shape
    land = landb == 1
    lc = classify(cls, py, tc, loss, landb)

    srcs = [rasterio.open(os.path.join(MODIS_TILES, f))
            for f in sorted(os.listdir(MODIS_TILES)) if f.endswith(".tif")]
    marr, mtr = merge(srcs, bounds=(tr.c, tr.f + shape[0] * tr.e,
                                    tr.c + shape[1] * tr.a, tr.f), method="max")
    for s in srcs:
        s.close()
    rep = int(round(mtr.a / GRID))

    def up(b):
        u = np.kron(b, np.ones((rep, rep), b.dtype))
        oy = int(round((mtr.f - tr.f) / GRID))
        ox = int(round((tr.c - mtr.c) / GRID))
        u = u[max(-oy, 0):, max(ox, 0):][:shape[0], :shape[1]]
        full = np.zeros(shape, b.dtype)      # merge may stop short of an edge
        full[:u.shape[0], :u.shape[1]] = u
        return full
    m26, m23, m19 = (up(marr[i]) > 0 for i in (1, 2, 3))

    season_pts = g[det.month.between(*SEASON).to_numpy()]
    vmask = features.rasterize([(p, 1) for p in season_pts.geometry],
                               out_shape=shape, transform=tr, dtype="uint8") > 0
    r = int(NEAR_BURN_M / 25)
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    evidence = ndimage.binary_dilation(vmask | m26,
                                       structure=(xx ** 2 + yy ** 2) <= r * r)
    burned = (dnbr != -32768) & (dnbr >= DNBR_T * 1000) & evidence & land

    lat = tr.f + (np.arange(shape[0]) + 0.5) * tr.e
    pha = np.broadcast_to((111320.0 * GRID) * (110574.0 * GRID)
                          * np.cos(np.radians(lat))[:, None] / 1e4, shape)
    print(f"burned (S2 dNBR, fire-confirmed): {pha[burned].sum():,.0f} ha in AOI")
    prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=2,
                dtype="uint8", crs="EPSG:4326", transform=tr, compress="deflate")
    with rasterio.open(os.path.join(a.out, "landcover_burned.tif"), "w",
                       **prof) as ds:
        ds.write(lc, 1)
        ds.write(burned.astype(np.uint8), 2)
        ds.descriptions = ("landcover class (see CLASSES; 255 water)",
                           "burned Jul-Oct 2026")

    any_conc = np.zeros(shape, bool)
    for geom in near.geometry:
        any_conc |= features.rasterize([(geom, 1)], out_shape=shape,
                                       transform=tr, dtype="uint8") > 0

    # --- peat -------------------------------------------------------------
    peat = {"own": own_peat_on_grid(PEAT_OWN, bbox, tr, shape) & land}
    if not os.path.exists(PEAT):
        fetch_peat(bbox, PEAT)
    pg = gpd.read_file(PEAT)
    peat["bbsdlp"] = (features.rasterize(
        [(g_, 1) for g_ in pg.geometry if g_ is not None and not g_.is_empty],
        out_shape=shape, transform=tr, dtype="uint8") > 0) & land
    thick = peatgrids_on_grid(bbox, tr, shape, a.out)
    deep = thick >= DEEP_CM
    agree = {
        "own_ha": float(pha[peat["own"]].sum()),
        "bbsdlp_ha": float(pha[peat["bbsdlp"]].sum()),
        "both_ha": float(pha[peat["own"] & peat["bbsdlp"]].sum()),
        "either_ha": float(pha[peat["own"] | peat["bbsdlp"]].sum()),
    }
    agree["iou"] = agree["both_ha"] / agree["either_ha"]
    print("peat maps over AOI land:", {k: round(v) if k != "iou" else round(v, 2)
                                       for k, v in agree.items()})

    comp_rows, dens, peat_stats = [], {}, {}
    n_season_days = 123
    for _, rr in conc4.iterrows():
        inside = (features.rasterize([(rr.geometry, 1)], out_shape=shape,
                                     transform=tr, dtype="uint8") > 0) & land
        valid = inside & (dnbr != -32768)
        for k, name in enumerate(CLASSES):
            sel = inside & (lc == k)
            comp_rows.append({
                "concession": rr.acr, "class": name,
                "area_ha": float(pha[sel].sum()),
                "burned_ha": float(pha[sel & burned].sum()),
                "burned_also_2019_or_2023_ha": float(
                    pha[sel & burned & (m19 | m23)].sum()),
                "s2_valid_ha": float(pha[sel & valid].sum()),
                "area_on_peat_ha": float(pha[sel & peat["own"]].sum()),
                "burned_on_peat_ha": float(pha[sel & burned & peat["own"]].sum()),
            })
        # ignition density inside vs. the unconceded land around it
        dist = ndimage.distance_transform_edt(~inside) * 25 / 1000
        ring = (dist > 0) & (dist <= RING_KM) & land & ~any_conc
        ia = pha[inside].sum() / 100     # km2
        ra = pha[ring].sum() / 100
        si = ign[ign.month.between(*SEASON)]
        n_in = int((si["where"] == rr.acr).sum())
        n_in_int = int(((si["where"] == rr.acr) & ~si.edge).sum())
        rows_, cols_ = rasterio.transform.rowcol(tr, si.lon.to_numpy(),
                                                 si.lat.to_numpy())
        rows_, cols_ = np.asarray(rows_), np.asarray(cols_)
        okp = (rows_ >= 0) & (rows_ < shape[0]) & (cols_ >= 0) & (cols_ < shape[1])
        in_ring = np.zeros(len(si), bool)
        in_ring[okp] = ring[rows_[okp], cols_[okp]]
        n_ring = int(in_ring.sum())

        def h(m):
            return float(pha[m].sum())
        ps = {}
        for key_, pm in peat.items():
            ip, im = inside & pm, inside & ~pm
            rp, rm = ring & pm, ring & ~pm
            ps[key_] = {
                "peat_ha": h(ip), "peat_share_of_concession": h(ip) / h(inside),
                "burned_ha": h(inside & burned),
                "burned_on_peat_ha": h(ip & burned),
                "burn_share_on_peat": h(ip & burned) / max(h(inside & burned), 1e-9),
                "burned_pct_of_peat": 100 * h(ip & burned) / max(h(ip), 1e-9),
                "burned_pct_of_mineral": 100 * h(im & burned) / max(h(im), 1e-9),
                "ring_burned_pct_of_peat": 100 * h(rp & burned) / max(h(rp), 1e-9),
                "ring_burned_pct_of_mineral": 100 * h(rm & burned) / max(h(rm), 1e-9),
                "burned_peat_repeat_2019_2023_ha": h(ip & burned & (m19 | m23)),
            }
        ip = inside & peat["own"]
        ps["depth_peatgrids"] = {
            "burned_on_own_peat_modelled_ge3m_ha": h(ip & burned & deep),
            "median_thickness_cm_burned_own_peat": float(
                np.median(thick[ip & burned])) if (ip & burned).any() else None,
        }
        peat_stats[rr.acr] = ps
        dens[rr.acr] = {
            "area_km2": float(ia), "ring_unconceded_land_km2": float(ra),
            "ignitions_inside_jul_oct": n_in,
            "ignitions_inside_interior_jul_oct": n_in_int,
            "ignitions_in_ring_jul_oct": n_ring,
            "per_100km2_inside": 100 * n_in / ia,
            "per_100km2_ring": 100 * n_ring / ra if ra else None,
            "ratio_inside_to_ring": ((n_in / ia) / (n_ring / ra))
                if n_ring else None,
        }
    comp = pd.DataFrame(comp_rows)
    tot = comp.groupby("concession")[["area_ha", "burned_ha"]].transform("sum")
    comp["share_of_concession"] = comp.area_ha / tot.area_ha
    comp["share_of_burn"] = comp.burned_ha / tot.burned_ha
    comp["burned_pct_of_class"] = 100 * comp.burned_ha / comp.area_ha.where(
        comp.area_ha > 0)
    comp.to_csv(os.path.join(a.out, "burned_by_landcover.csv"), index=False)
    with pd.option_context("display.width", 220, "display.max_colwidth", 50):
        print(comp[["concession", "class", "area_ha", "burned_ha",
                    "share_of_concession", "share_of_burn",
                    "burned_pct_of_class", "burned_also_2019_or_2023_ha"]]
              .round(3).to_string(index=False))

    # land cover at each ignition: majority within 375 m
    rad = int(375 / 25)
    rr_, cc_ = rasterio.transform.rowcol(tr, ign.lon.to_numpy(), ign.lat.to_numpy())
    lcs = []
    for r0, c0 in zip(rr_, cc_):
        win = lc[max(r0 - rad, 0):r0 + rad + 1, max(c0 - rad, 0):c0 + rad + 1]
        win = win[win < 255]
        lcs.append(CLASSES[np.bincount(win).argmax()] if win.size else "")
    ign["landcover_375m"] = lcs
    rr_, cc_ = np.asarray(rr_), np.asarray(cc_)
    okp = (rr_ >= 0) & (rr_ < shape[0]) & (cc_ >= 0) & (cc_ < shape[1])
    for key_, pm in peat.items():
        v = np.zeros(len(ign), bool)
        v[okp] = pm[rr_[okp], cc_[okp]]
        ign[f"on_peat_{key_}"] = v
    ign.to_csv(os.path.join(a.out, "ignitions.csv"), index=False)

    # --- per-concession origin summary --------------------------------------
    per = {}
    for x in FOUR:
        dx = det[(det["where"] == x) & det.month.between(*SEASON)]
        rwx = dx.root_where.where(dx.root_where.isin([x, "outside",
                                                      "other conc."]),
                                  "another of the four")
        own_mask = dx.root_where == x
        ix = ign[(ign["where"] == x) & ign.month.between(*SEASON)]
        big = ix[ix.size_all >= BIG]
        first = dx.iloc[0] if len(dx) else None
        per[x] = {
            "detections_inside_jul_oct": int(len(dx)),
            "by_root": rwx.value_counts().to_dict(),
            "share_from_own_ignitions": float(own_mask.mean()),
            "share_from_own_interior_ignitions": float(
                (own_mask & ~dx.root_edge).mean()),
            "ignitions": int(len(ix)),
            "ignitions_interior": int((~ix.edge).sum()),
            "ignitions_isolated": int(ix.isolated.sum()),
            "ignitions_big": int(len(big)),
            "ignitions_big_isolated": int(big.isolated.sum()),
            "ignitions_big_interior_isolated": int(
                (big.isolated & ~big.edge).sum()),
            "detections_from_big_isolated_ignitions": int(
                big[big.isolated][f"size_in_{x}"].sum()),
            "ignition_landcover": ix.landcover_375m.value_counts().to_dict(),
            "ignitions_on_peat_own": int(ix.on_peat_own.sum()),
            "ignitions_big_isolated_on_peat_own": int(
                (big.isolated & big.on_peat_own).sum()),
            "peat": peat_stats[x],
            "big_ignition_landcover": big.landcover_375m.value_counts().to_dict(),
            "first_detection_jul_oct": None if first is None else {
                "time": str(first.time), "root_where": first.root_where},
            "density": dens[x],
        }
    summary = {
        "params": {"parent_km": PARENT_KM, "parent_h": PARENT_H,
                   "near_km": NEAR_KM, "near_h": NEAR_H, "edge_km": EDGE_KM,
                   "ring_km": RING_KM, "season_months": SEASON,
                   "dnbr_t": DNBR_T, "period": [START, END],
                   "viirs_conf": "nominal+high"},
        "sensitivity": sens,
        "per_concession": per,
        "burned_ha_aoi": float(pha[burned].sum()),
        "peat_maps": {"own": os.path.basename(PEAT_OWN),
                      "bbsdlp": "GFW Indonesia Peat Lands (BBSDLP)",
                      "depth": PEATGRIDS_IMG, "agreement_aoi": agree},
    }
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps(per, indent=1, default=str))

    # --- figures ------------------------------------------------------------
    pts = det[det.month.between(*SEASON)]
    show = ign[ign.month.between(*SEASON) & (ign.size_all >= BIG)].copy()
    render_map(os.path.join(a.out, "map_origin_landcover.png"), lc, tr, burned,
               conc4, pts, show, peat["own"],
               "Ketapang coast, Jul–Oct 2026: where the fires started, and "
               "what burned")
    render_timeline(os.path.join(a.out, "timeline.png"), det, list(FOUR))


if __name__ == "__main__":
    main()
