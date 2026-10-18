"""Name the protected areas that are burning.

Page 3 of the Borneo set can say that N detections fell on land where
burning is not permitted under any licence. It cannot say WHERE, because
the KLHK layer carries the legal function of each polygon and not its
name (NAMOBJ is "-" for every feature in it). This joins those same
detections to WDPA, which does carry names, and ranks them.

TWO REGISTRIES, AND THE COUNTS COME FROM ONLY ONE OF THEM.

  KLHK Penunjukan Kawasan Hutan   decides WHETHER a detection is in a
                                  conservation area. Every figure in the
                                  five-page set is sourced from it, and
                                  this script does not revisit that call.
  WDPA (UNEP-WCMC)                supplies the NAME and designation only.

They are different registries drawn at different dates and they do not
agree on every boundary. A KLHK conservation detection that falls in no
WDPA polygon is reported as unnamed rather than dropped, and a detection
outside KLHK conservation is never added just because WDPA covers it.
Doing it the other way round would silently restate the headline figure.

    conda run -n base python scripts/borneo_conservation.py
    conda run -n base python scripts/borneo_conservation.py --include-hl
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.expanduser(_DATA_ROOT + "/output/fire")
BORNEO_BBOX = [108.5, -4.5, 119.5, 7.5]

# WDPA carries proposed and not-reported sites alongside designated ones.
# Only designated and inscribed areas are places where protection is in
# force today, which is the whole point of the question.
STATUS_KEEP = ("Designated", "Inscribed", "Established")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-hl", action="store_true",
                    help="also rank HL (protection forest), which is "
                         "protected but under a different instrument")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import geopandas as gpd
    import pandas as pd

    sys.path.insert(0, _REPO_ROOT)
    sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
    from scripts.borneo_hotspots import init_gee

    csv = os.path.join(a.out, "borneo_hotspots_7d.csv")
    if not os.path.exists(csv):
        raise SystemExit(f"missing {csv}\nRun scripts/borneo_hotspots_7d.py "
                         f"first.")
    df = pd.read_csv(csv)

    want = ["Conservation (KSA/KPA)"]
    if a.include_hl:
        want.append("HL (protection forest)")
    sel = df[df.fungsi_group.isin(want)].copy()
    print(f"{len(df):,} detections in the window, "
          f"{len(sel):,} on protected land per KLHK")
    for k, n in sel.fungsi_group.value_counts().items():
        print(f"  {k:<28}{n:>7,}")
    if sel.empty:
        print("nothing to name")
        return 0

    pts = gpd.GeoDataFrame(
        sel, geometry=gpd.points_from_xy(sel.lon, sel.lat), crs="EPSG:4326")

    # --- WDPA ---------------------------------------------------------
    ee = init_gee()
    fc = (ee.FeatureCollection("WCMC/WDPA/current/polygons")
          .filterBounds(ee.Geometry.Rectangle(BORNEO_BBOX))
          .filter(ee.Filter.eq("ISO3", "IDN"))
          .filter(ee.Filter.inList("STATUS", list(STATUS_KEEP)))
          .select(["NAME", "DESIG_ENG", "IUCN_CAT", "STATUS", "GIS_AREA",
                   "REP_AREA"]))
    gj = fc.getInfo()
    wdpa = gpd.GeoDataFrame.from_features(gj["features"], crs="EPSG:4326")

    # NOT EVERY WDPA RECORD IS A TRUSTWORTHY NAME. Some carry DESIG_ENG
    # "Undesigned" with REP_AREA 0 -- a polygon with no government-reported
    # area behind it -- and at least one (Muara Angke, a Jakarta reserve of
    # about 25 ha) has a geometry in East Kalimantan, so its name does not
    # belong to the land it covers. Ranking those beside Tanjung Puting
    # would lend them a precision they do not have, so they are counted
    # and shown separately rather than quietly mixed in or dropped.
    wdpa["sahih"] = (wdpa.REP_AREA.fillna(0) > 0) & \
                    (wdpa.DESIG_ENG != "Undesigned")
    print(f"\nWDPA: {len(wdpa)} designated Indonesian areas over Borneo, "
          f"{int(wdpa.sahih.sum())} with a reported area and designation")

    j = gpd.sjoin(pts, wdpa, how="left", predicate="within")
    # A point inside two overlapping WDPA polygons (a park inside a wider
    # reserve) is counted once. Prefer a corroborated record over an
    # uncorroborated one, then the smaller unit, whose name is the more
    # specific of the two.
    j = (j.sort_values(["sahih", "GIS_AREA"], ascending=[False, True])
         .loc[lambda d: ~d.index.duplicated("first")])

    named = j[j.NAME.notna()]
    unnamed = len(j) - len(named)
    print(f"  {len(named):,} matched a named area, "
          f"{unnamed:,} fell in none ({100*unnamed/len(j):.1f}%)")

    # --- the ranking --------------------------------------------------
    g = (named.groupby(["NAME", "DESIG_ENG", "IUCN_CAT", "sahih"])
         .agg(n=("lon", "size"), area_km2=("GIS_AREA", "first"))
         .reset_index().sort_values("n", ascending=False))
    g["per_1000km2"] = g.n / g.area_km2 * 1000

    def table(rows, head):
        print(f"\n  {head}")
        print(f"  {'area':<34}{'designation':<26}{'IUCN':>5}"
              f"{'det':>7}{'km2':>9}{'per 1000':>10}")
        for r in rows.itertuples():
            print(f"  {str(r.NAME)[:33]:<34}{str(r.DESIG_ENG)[:25]:<26}"
                  f"{str(r.IUCN_CAT):>5}{r.n:>7,}{r.area_km2:>9,.0f}"
                  f"{r.per_1000km2:>10.1f}")
        print(f"  {'subtotal':<66}{int(rows.n.sum()):>7,}")

    ok, iffy = g[g.sahih], g[~g.sahih]
    table(ok.head(20), f"PROTECTED AREAS BURNING, "
                       f"{df.date.min()} .. {df.date.max()}")
    if len(iffy):
        table(iffy, "NAMED BY WDPA BUT NOT CORROBORATED — no reported area "
                    "or no designation.\n  Treat these names as provisional.")
    if unnamed:
        # With --include-hl this is almost entirely HL, and that is not a
        # gap in the data: protection forest is a KLHK watershed category,
        # not an IUCN protected area, so WDPA does not carry it at all.
        by_cls = named.fungsi_group.value_counts()
        miss = (sel.fungsi_group.value_counts()
                .subtract(by_cls, fill_value=0).astype(int))
        print(f"\n  on KLHK protected land, in no WDPA polygon: {unnamed:,}")
        for k, n in miss[miss > 0].items():
            print(f"    {k:<28}{n:>7,}")
    print(f"\n  {'TOTAL':<66}{len(j):>7,}")

    out_json = os.path.join(a.out, "borneo_conservation.json")
    with open(out_json, "w") as f:
        json.dump({
            "window": [str(df.date.min()), str(df.date.max())],
            "classes": want,
            "total_protected": int(len(sel)),
            "named": int(len(named)), "unnamed": int(unnamed),
            "n_wdpa_units": int(len(wdpa)),
            "corroborated": int(ok.n.sum()),
            "provisional": int(iffy.n.sum()),
            "areas": [{"name": r.NAME, "desig": r.DESIG_ENG,
                       "iucn": r.IUCN_CAT, "n": int(r.n),
                       "area_km2": float(r.area_km2),
                       "per_1000km2": float(r.per_1000km2),
                       "corroborated": bool(r.sahih)}
                      for r in g.itertuples()],
        }, f, indent=1)
    g.to_csv(os.path.join(a.out, "borneo_conservation.csv"), index=False)
    print(f"\nwrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
