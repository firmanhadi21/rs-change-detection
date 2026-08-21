"""Last 7 days of Borneo hotspots, joined to admin and forest function.

Pulls FIRMS detections as POINTS rather than reducing a raster, because the
question is "how many fires, and whose land are they on" -- which needs each
detection attributed individually, not a regional sum.

TWO BOUNDARY SETS, AND THEY DO NOT COVER THE SAME GROUND:

  admin          FAO GAUL 2015 level-1, all three countries. Note GAUL predates
                 Kalimantan Utara (created 2012), so its territory still counts
                 inside Kalimantan Timur.
  forest function  KLHK Penunjukan Kawasan Hutan 1:250k (2019), from
                 data/forest.gpkg. INDONESIA ONLY -- it is an Indonesian legal
                 designation and has no Malaysian or Bruneian equivalent, so
                 Sabah, Sarawak, Labuan and Brunei get no forest-function
                 breakdown here rather than a fabricated one.

MODIS, NOT VIIRS. Earth Engine's FIRMS collection is MODIS at 1 km. VIIRS
(375 m) detects several times more hotspots for the same fires, so these counts
sit well below BMKG and ASEAN figures. Consistent, but not interchangeable.

    conda run -n base python scripts/borneo_hotspots_7d.py
    conda run -n base python scripts/borneo_hotspots_7d.py --days 7
"""

import argparse
import json
import os
import sys

BORNEO_BBOX = [108.5, -4.5, 119.5, 7.5]
FOREST_GPKG = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/forest.gpkg")
FOREST_LAYER = "pnunjukkwshutan_ar_250k"
OUT = os.path.expanduser("~/GitHub/rs-change-detection/output/fire")

# KLHK classes collapsed to the six functions people actually talk about.
# Conservation is split across many legal instruments (national park, nature
# reserve, wildlife sanctuary...) that all mean "protected" for fire reporting.
FUNGSI_GROUP = {
    "AREA PENGGUNAAN LAIN": "APL (non-forest estate)",
    "HUTAN LINDUNG": "HL (protection forest)",
    "HUTAN PRODUKSI": "HP (production)",
    "HUTAN PRODUKSI TERBATAS": "HPT (limited production)",
    "HUTAN PRODUKSI KONVERSI": "HPK (convertible production)",
    "LAUT/AIR": "water",
}
CONSERVATION = {
    "CAGAR ALAM", "TAMAN NASIONAL", "TAMAN NASIONAL LAUT",
    "SUAKA MARGASATWA", "HUTAN WISATA", "HUTAN SUAKA ALAM DAN MARGASATWA",
    "KSA/KPA", "TAMAN BURU", "TAMAN HUTAN RAYA", "TAMAN WISATA ALAM",
    "TAMAN WISATA ALAM LAUT", "CAGAR ALAM LAUT", "SUAKA MARGASATWA LAUT",
}


def init_gee():
    import ee
    key = os.path.expanduser("~/.config/earthengine/ee-geodetic.json")
    if os.path.exists(key):
        email = json.load(open(key))["client_email"]
        ee.Initialize(ee.ServiceAccountCredentials(email, key_file=key))
    else:
        ee.Initialize()
    return ee


def fetch_points(ee, days, min_conf):
    """FIRMS detections in the last `days`, as (lon, lat, confidence, date)."""
    firms = ee.ImageCollection("FIRMS")
    end = firms.limit(1, "system:time_start", False).first().date()
    start = end.advance(-(days - 1), "day")
    aoi = ee.Geometry.Rectangle(BORNEO_BBOX)
    print(f"FIRMS window: {start.format('YYYY-MM-dd').getInfo()} .. "
          f"{end.format('YYYY-MM-dd').getInfo()}  (MODIS 1 km)")

    def to_points(img):
        d = img.date().format("YYYY-MM-dd")
        masked = img.select("confidence").updateMask(
            img.select("confidence").gte(min_conf))
        return masked.addBands(ee.Image.pixelLonLat()).sample(
            region=aoi, scale=1000, geometries=False, dropNulls=True
        ).map(lambda f: f.set("date", d))

    ic = firms.filterDate(start, end.advance(1, "day"))
    fc = ee.FeatureCollection(ic.map(to_points)).flatten()
    n = fc.size().getInfo()
    print(f"  {n} detections at confidence >= {min_conf}")
    if n == 0:
        return []
    rows = fc.reduceColumns(
        ee.Reducer.toList(4),
        ["longitude", "latitude", "confidence", "date"]).get("list").getInfo()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-confidence", type=int, default=30)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import box

    os.makedirs(a.out, exist_ok=True)
    ee = init_gee()
    rows = fetch_points(ee, a.days, a.min_confidence)
    if not rows:
        print("no detections in the window")
        return 0

    pts = gpd.GeoDataFrame(
        pd.DataFrame(rows, columns=["lon", "lat", "confidence", "date"]),
        geometry=gpd.points_from_xy([r[0] for r in rows],
                                    [r[1] for r in rows]),
        crs="EPSG:4326")
    print(f"  {len(pts)} points, {pts.date.nunique()} distinct days")

    # --- admin join -------------------------------------------------------
    from scripts.borneo_hotspots import build_regions
    gj = build_regions(ee).getInfo()
    adm = gpd.GeoDataFrame.from_features(gj["features"], crs="EPSG:4326")
    pts = gpd.sjoin(pts, adm[["label", "country", "geometry"]],
                    how="left", predicate="within").drop(columns="index_right")
    inside = pts.label.notna()
    print(f"  {int(inside.sum())} fall inside a Borneo admin unit "
          f"({len(pts) - int(inside.sum())} at sea or outside)")
    pts = pts[inside].copy()

    # --- forest function join, Indonesia only ----------------------------
    # Read only the Kalimantan window out of a 1.1 GB file; reading it whole
    # is minutes of I/O for polygons that are mostly elsewhere in Indonesia.
    kal = pts[pts.country == "Indonesia"]
    print(f"\nforest function: {len(kal)} Indonesian detections to attribute")
    if len(kal):
        minx, miny, maxx, maxy = kal.total_bounds
        pad = 0.2
        forest = gpd.read_file(
            FOREST_GPKG, layer=FOREST_LAYER,
            bbox=(minx - pad, miny - pad, maxx + pad, maxy + pad))
        print(f"  read {len(forest)} kawasan polygons over the fire extent")
        forest = forest[["FUNGSI_HTN", "geometry"]].copy()
        # 3D multipolygons; the join only needs 2D and shapely is faster on it.
        forest["geometry"] = forest.geometry.force_2d()
        j = gpd.sjoin(kal, forest, how="left", predicate="within")
        # A point on a boundary can land in two polygons; keep the first so
        # the total is conserved rather than inflated by double counting.
        j = j[~j.index.duplicated(keep="first")]
        pts.loc[j.index, "fungsi"] = j["FUNGSI_HTN"]

    def group(v):
        if not isinstance(v, str):
            return "unclassified"
        v = v.strip().upper()
        if v in CONSERVATION:
            return "Conservation (KSA/KPA)"
        return FUNGSI_GROUP.get(v, v.title())

    pts["fungsi_group"] = pts["fungsi"].map(group) if "fungsi" in pts \
        else "unclassified"

    # --- report -----------------------------------------------------------
    print(f"\n  HOTSPOTS BY ADMIN, last {a.days} days")
    by_adm = (pts.groupby(["country", "label"]).size()
              .sort_values(ascending=False))
    for (c, l), n in by_adm.items():
        print(f"    {l:<22}{c:<20}{n:>7,}")
    print(f"    {'TOTAL':<42}{len(pts):>7,}")

    print(f"\n  HOTSPOTS BY FOREST FUNCTION (Indonesia only)")
    ind = pts[pts.country == "Indonesia"]
    by_f = ind.groupby("fungsi_group").size().sort_values(ascending=False)
    for k, n in by_f.items():
        print(f"    {k:<42}{n:>7,}  {100*n/len(ind):>5.1f}%")
    print(f"    {'TOTAL Indonesia':<42}{len(ind):>7,}")

    out_csv = os.path.join(a.out, "borneo_hotspots_7d.csv")
    pts.drop(columns="geometry").to_csv(out_csv, index=False)
    payload = {
        "days": a.days,
        "min_confidence": a.min_confidence,
        "date_min": str(pts.date.min()), "date_max": str(pts.date.max()),
        "total": int(len(pts)),
        "by_admin": [{"country": c, "region": l, "n": int(n)}
                     for (c, l), n in by_adm.items()],
        "by_function": [{"fungsi": k, "n": int(n)} for k, n in by_f.items()],
        "indonesia_total": int(len(ind)),
        "points": [{"lon": float(r.lon), "lat": float(r.lat),
                    "conf": int(r.confidence), "date": r.date,
                    "region": r.label,
                    "fungsi": r.fungsi_group}
                   for r in pts.itertuples()],
    }
    with open(os.path.join(a.out, "borneo_hotspots_7d.json"), "w") as f:
        json.dump(payload, f)
    print(f"\nwrote {out_csv}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
