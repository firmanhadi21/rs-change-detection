"""The Dharmasraya HPT fire of 15 September 2026, seen from orbit.

Kompas, 19 Oct 2026: police and the KPHP forest unit found roughly 5.9 ha
of recently burnt LIMITED PRODUCTION FOREST (HPT) at Bukit Lantak, Nagari
Tabek, Timpeh, already planted with oil palm seedlings. The land is
reported to have burnt on 15 September 2026.

MODIS put six 1 km pixels on fire in Dharmasraya HPT on exactly that
date, centred near 101.549E 0.903S, and no other HPT fire in the regency
that month. That is the site this script looks at. It is corroboration of
WHERE AND WHEN, arrived at from the date and the designation
independently -- not a location taken from the article.

WHAT THIS CAN AND CANNOT SETTLE:

  can    that something burnt there, how much, and how severely
         (Sentinel-2 dNBR, 10 m, against a pre-fire baseline)
  can    whether the ground was worked afterwards -- cleared, ploughed,
         terraced -- which changes radar backscatter and roughness
         (Sentinel-1 C-band, ~20 m, immune to the smoke and cloud that
         made most optical scenes here unusable)
  CANNOT that the seedlings are oil palm, or that they are seedlings.
         A month-old palm is a few centimetres of frond at 9 m spacing.
         Nothing in orbit resolves that, and this script never claims it.

The patrol's own finding is the evidence for the planting. What follows
is only the part the satellites can carry.

    conda run -n base python scripts/dharmasraya_hpt_site.py
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.expanduser(_DATA_ROOT + "/output/fire/dharmasraya")

# The MODIS cluster of 15 Sep 2026, padded to give the scar room and the
# eye some unburnt context to judge it against.
SITE = [101.515, -0.930, 101.585, -0.875]
FIRE_DATE = "2026-09-15"

# Key & Benson / USGS dNBR severity bins.
BINS = [(0.10, "unburnt"), (0.27, "low"), (0.44, "moderate-low"),
        (0.66, "moderate-high"), (99., "high")]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    sys.path.insert(0, _REPO_ROOT)
    sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
    from scripts.borneo_hotspots import init_gee
    ee = init_gee()
    aoi = ee.Geometry.Rectangle(SITE)

    def mask_s2(img):
        scl = img.select("SCL")
        keep = (scl.neq(3).And(scl.neq(8)).And(scl.neq(9))
                .And(scl.neq(10)).And(scl.neq(11)))
        return img.updateMask(keep)

    def nbr(img):
        return img.normalizedDifference(["B8", "B12"]).rename("nbr")

    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
    pre = s2.filterDate("2026-06-01", FIRE_DATE).map(mask_s2)
    post = s2.filterDate("2026-09-16", "2026-11-01").map(mask_s2)
    print(f"S2 scenes: {pre.size().getInfo()} pre, "
          f"{post.size().getInfo()} post")

    # Median of the cloud-masked stack, not a single date. One scene here
    # is half cloud; the stack has a clear look at almost every pixel.
    nbr_pre = nbr(pre.median())
    nbr_post = nbr(post.median())
    dnbr = nbr_pre.subtract(nbr_post).rename("dnbr")

    px = ee.Image.pixelArea().divide(1e4)
    valid = dnbr.mask()
    cover = px.updateMask(valid).reduceRegion(
        ee.Reducer.sum(), aoi, 10, maxPixels=1e10).get("area").getInfo()
    total = px.reduceRegion(
        ee.Reducer.sum(), aoi, 10, maxPixels=1e10).get("area").getInfo()
    print(f"AOI {total:,.0f} ha, dNBR valid on {cover:,.0f} ha "
          f"({100*cover/total:.0f}%)")

    print("\ndNBR severity over the site")
    res, lo = {}, -99.0
    for hi, name in BINS:
        m = dnbr.gte(lo).And(dnbr.lt(hi))
        ha = px.updateMask(m).reduceRegion(
            ee.Reducer.sum(), aoi, 10, maxPixels=1e10).get("area").getInfo()
        res[name] = ha or 0.0
        print(f"  {name:<16}{res[name]:>10,.1f} ha")
        lo = hi
    burnt = sum(v for k, v in res.items() if k != "unburnt")
    mod_plus = sum(res[k] for k in
                   ("moderate-low", "moderate-high", "high"))
    print(f"  {'burnt (>0.10)':<16}{burnt:>10,.1f} ha")
    print(f"  {'moderate+':<16}{mod_plus:>10,.1f} ha   "
          f"<- compare with the 5.9 ha reported")

    # --- Sentinel-1: was the ground worked after the fire? ------------
    def s1(d0, d1, orbit):
        c = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi)
             .filterDate(d0, d1)
             .filter(ee.Filter.eq("instrumentMode", "IW"))
             .filter(ee.Filter.eq("orbitProperties_pass", orbit))
             .filter(ee.Filter.listContains(
                 "transmitterReceiverPolarisation", "VH")))
        return c.select(["VV", "VH"]).mean(), c.size().getInfo()

    print("\nSentinel-1 VH change (dB), same orbit both sides")
    s1out = {}
    for orbit in ("ASCENDING", "DESCENDING"):
        a_img, na = s1("2026-08-01", FIRE_DATE, orbit)
        b_img, nb = s1("2026-09-16", "2026-10-19", orbit)
        if not na or not nb:
            print(f"  {orbit}: {na} pre / {nb} post — skipped")
            continue
        # Burn scar only: asking about the whole AOI dilutes the signal
        # with land that never burnt.
        scar = dnbr.gt(0.27)
        d = b_img.select("VH").subtract(a_img.select("VH"))
        stat = d.updateMask(scar).reduceRegion(
            ee.Reducer.mean().combine(ee.Reducer.stdDev(), None, True),
            aoi, 20, maxPixels=1e10).getInfo()
        ctrl = d.updateMask(scar.Not()).reduceRegion(
            ee.Reducer.mean(), aoi, 20, maxPixels=1e10).getInfo()
        s1out[orbit] = {"scar_mean": stat.get("VH_mean"),
                        "scar_sd": stat.get("VH_stdDev"),
                        "offscar_mean": ctrl.get("VH"),
                        "n_pre": na, "n_post": nb}
        print(f"  {orbit}: {na} pre, {nb} post")
        print(f"    on scar  {stat.get('VH_mean'):+.2f} dB "
              f"(sd {stat.get('VH_stdDev'):.2f})")
        print(f"    off scar {ctrl.get('VH'):+.2f} dB")

    dest = os.path.join(a.out, "site.json")
    with open(dest, "w") as f:
        json.dump({"site": SITE, "fire_date": FIRE_DATE,
                   "aoi_ha": total, "dnbr_valid_ha": cover,
                   "severity_ha": res, "burnt_ha": burnt,
                   "moderate_plus_ha": mod_plus, "s1_vh": s1out}, f,
                  indent=1)
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
