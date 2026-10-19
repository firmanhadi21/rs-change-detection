"""Did land that burned in West Sumatra later become oil palm?

Prompted by a Kompas report (19 Oct 2026) that police in Dharmasraya found
roughly 5.9 ha of recently burnt limited-production forest (HPT) at Bukit
Lantak, Nagari Tabek, Timpeh, already planted with oil palm seedlings.

THIS SCRIPT CANNOT CORROBORATE THAT PARTICULAR CASE AND DOES NOT TRY.
A 5.9 ha plot of seedlings a month old is invisible to every free sensor:
the plants are centimetres across, the burn is a tenth of one MCD64A1
pixel, and West Sumatra had no Sentinel-2 scene under 40% cloud between
20 Sep and 19 Oct 2026. What follows is the general question the report
raises, which the record can answer: across two decades, is burnt land in
West Sumatra more likely than unburnt land to be carrying oil palm that
was planted after the fire?

HOW THE TEST WORKS. Descals et al.'s global oil-palm map carries a
planting_year per pixel, so "planted after it burned" is directly
checkable rather than inferred. For each 100 m cell the script asks:

    did it burn in 2001-2015 (MCD64A1), and if so in which year first
    is it oil palm, and if so what year was that palm planted

and compares the share of burnt land carrying post-fire palm against the
same share on land that never burned. The ratio of those two shares is
the result. A ratio near 1 would mean fire tells you nothing about
subsequent planting.

WHAT THE RATIO IS NOT. It is an association measured on observational
data, not a finding of intent or of illegality, and the direction of
causation is not settled by it: land may be burnt in order to plant it,
or land already destined for planting may be cleared by burning, or both
may follow from the same thing -- being flat, drained and near a road.
The script reports the association and stops there.

BURN DETECTION IS COARSE AND BIASED TOWARD BIG FIRES. MCD64A1 is 500 m
and misses burns of a few hectares entirely, which is most smallholder
clearing and all of the Dharmasraya case. Everything here therefore
describes large burns only, and the small-fire pathway the report
describes is invisible to it in either direction.

    conda run -n base python scripts/sumbar_burn_to_palm.py
    conda run -n base python scripts/sumbar_burn_to_palm.py --adm2 Dharmasraya
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

# Burns are counted to 2015 and planting to 2021, so every burn has at
# least six years in which planting could appear. Including burns from
# 2016 onward would count land that simply has not had time to be
# replanted as evidence that fire does not lead to planting.
BURN_FROM, BURN_TO = 2001, 2015
PALM_CLASSES = [1, 2]            # 1 industrial, 2 smallholder
SCALE = 100                      # m; palm is 10 m, MCD64A1 500 m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adm1", default="Sumatera Barat")
    ap.add_argument("--adm2", default=None,
                    help="restrict to one kabupaten, e.g. Dharmasraya")
    ap.add_argument("--scale", type=int, default=SCALE)
    ap.add_argument("--lowland", action="store_true",
                    help="restrict BOTH groups to terrain oil palm can "
                         "actually be grown on (below 300 m, under 15 deg). "
                         "West Sumatra is mountainous, so without this the "
                         "comparison may only be recovering the fact that "
                         "fire and plantations are both in the lowlands.")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    sys.path.insert(0, _REPO_ROOT)
    sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
    from scripts.borneo_hotspots import init_gee
    ee = init_gee()

    if a.adm2:
        aoi = (ee.FeatureCollection("FAO/GAUL/2015/level2")
               .filter(ee.Filter.eq("ADM2_NAME", a.adm2))
               .filter(ee.Filter.eq("ADM1_NAME", a.adm1)).geometry())
        label = f"{a.adm2}, {a.adm1}"
    else:
        aoi = (ee.FeatureCollection("FAO/GAUL/2015/level1")
               .filter(ee.Filter.eq("ADM1_NAME", a.adm1)).geometry())
        label = a.adm1

    # --- first burn year per pixel -----------------------------------
    mcd = ee.ImageCollection("MODIS/061/MCD64A1")

    def burned_in(y):
        return (mcd.filterDate(f"{y}-01-01", f"{y}-12-31")
                .select("BurnDate").max().gt(0).unmask(0))

    first = ee.Image(0)
    for y in range(BURN_TO, BURN_FROM - 1, -1):      # later years first
        first = first.where(burned_in(y), y)         # so earliest wins
    first = first.rename("burn_year")
    ever = first.gt(0)

    # --- palm ---------------------------------------------------------
    pm = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2").mosaic()
    is_palm = pm.select("classification").remap(
        PALM_CLASSES, [1] * len(PALM_CLASSES), 0).rename("palm")
    pyear = pm.select("planting_year").rename("pyear")

    # Palm planted AFTER the fire that burnt that pixel. Strictly after,
    # so palm standing when it burnt is not counted as a consequence of
    # the burn.
    post = is_palm.eq(1).And(pyear.gt(first)).And(ever)
    # The control needs the same era: palm planted from the first burn
    # year onward, on land that never burned in the window.
    ctrl = is_palm.eq(1).And(pyear.gte(BURN_FROM)).And(ever.Not())

    # Terrain stratification. The comparison is only fair between places
    # that could carry a plantation at all; comparing burnt lowland against
    # an "unburnt" baseline that includes the Bukit Barisan range measures
    # topography, not land-use conversion.
    if a.lowland:
        dem = ee.Image("USGS/SRTMGL1_003")
        ok = dem.lt(300).And(ee.Terrain.slope(dem).lt(15))
        aoi_mask = ok
        label += "  (below 300 m, under 15 deg)"
    else:
        aoi_mask = ee.Image(1)

    px = ee.Image.pixelArea().divide(1e4).updateMask(aoi_mask)  # hectares
    bands = (px.rename("total")
             .addBands(px.updateMask(ever).rename("burnt"))
             .addBands(px.updateMask(ever.Not()).rename("unburnt"))
             .addBands(px.updateMask(post).rename("burnt_then_palm"))
             .addBands(px.updateMask(ctrl).rename("unburnt_palm"))
             .addBands(px.updateMask(is_palm.eq(1)).rename("palm_any")))
    s = bands.reduceRegion(reducer=ee.Reducer.sum(), geometry=aoi,
                           scale=a.scale, maxPixels=1e11,
                           bestEffort=True).getInfo()

    tot, burnt = s["total"], s["burnt"]
    unb, bp, up = s["unburnt"], s["burnt_then_palm"], s["unburnt_palm"]
    r_burnt = bp / burnt if burnt else float("nan")
    r_unb = up / unb if unb else float("nan")
    ratio = r_burnt / r_unb if r_unb else float("nan")

    print(f"\n{label}   {tot:,.0f} ha, {a.scale} m grid")
    print(f"  oil palm, any planting year   {s['palm_any']:>12,.0f} ha  "
          f"{100*s['palm_any']/tot:5.1f}%")
    print(f"  burnt {BURN_FROM}-{BURN_TO} (MCD64A1) {burnt:>12,.0f} ha  "
          f"{100*burnt/tot:5.1f}%")
    print()
    print(f"  BURNT land carrying palm planted after the fire")
    print(f"    {bp:>12,.0f} ha of {burnt:,.0f} ha   = {100*r_burnt:5.2f}%")
    print(f"  UNBURNT land carrying palm planted {BURN_FROM} or later")
    print(f"    {up:>12,.0f} ha of {unb:,.0f} ha   = {100*r_unb:5.2f}%")
    print()
    print(f"  ratio  {ratio:.2f}x")
    print(f"  Burnt land is {ratio:.2f}x as likely as unburnt land to be "
          f"carrying\n  oil palm planted after that date. Association, "
          f"not intent; see the\n  docstring for what this does and does "
          f"not establish.")

    slug = (a.adm2 or a.adm1).lower().replace(" ", "_")
    slug += "_lowland" if a.lowland else "_all"
    dest = os.path.join(a.out, f"burn_to_palm_{slug}.json")
    os.makedirs(a.out, exist_ok=True)
    with open(dest, "w") as f:
        json.dump({"area": label, "scale_m": a.scale,
                   "burn_window": [BURN_FROM, BURN_TO],
                   "total_ha": tot, "palm_any_ha": s["palm_any"],
                   "burnt_ha": burnt, "unburnt_ha": unb,
                   "burnt_then_palm_ha": bp, "unburnt_palm_ha": up,
                   "share_burnt": r_burnt, "share_unburnt": r_unb,
                   "ratio": ratio}, f, indent=1)
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
