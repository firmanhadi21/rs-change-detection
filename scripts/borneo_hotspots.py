"""Hotspot counts across Borneo -- Kalimantan, Sabah, Sarawak, Labuan, Brunei.

Answers "how bad is this fire season, and where" for the whole island rather
than one country, because smoke does not stop at borders and the Indonesian,
Malaysian and Bruneian shares of Borneo burn on the same monsoon calendar.

WHAT IS COUNTED, because the number is easy to misread. FIRMS in Earth Engine
is MODIS (Terra + Aqua, 1 km), and what this reports is PIXEL-DAYS: for each
1 km pixel, the number of days it was flagged as burning, summed over the
region. That is the same quantity Indonesian agencies call "titik panas", and
it is NOT a count of distinct fires -- one fire burning a week over four pixels
contributes 28. It is comparable across years and regions, which is what
matters here, and that is all it claims.

IT IS ALSO NOT COMPARABLE TO BMKG OR ASEAN FIGURES, which are VIIRS (375 m).
VIIRS detects several times more hotspots than MODIS for the same fires, so
these counts will look low beside a news report. Earth Engine does not carry
VIIRS active fire, so the choice here is MODIS or nothing; the consistency of a
2001-present MODIS record is worth more than matching a headline.

KALIMANTAN UTARA DOES NOT EXIST IN THESE BOUNDARIES. FAO GAUL 2015 predates
its recognition, so the province created in 2012 is still counted inside
Kalimantan Timur. Kaltim's figures below are therefore Kaltim + Kaltara.

    conda run -n base python scripts/borneo_hotspots.py
    conda run -n base python scripts/borneo_hotspots.py --start-year 2015
"""

import argparse
import json
import os
import sys

# GAUL 2015 level-1 units making up Borneo, by country. Labuan is a Malaysian
# federal territory off Sabah -- small, but part of the island's fire regime.
REGIONS = {
    "Indonesia": ["Kalimantan Barat", "Kalimantan Tengah",
                  "Kalimantan Selatan", "Kalimantan Timur"],
    "Malaysia": ["Sabah", "Sarawak", "Labuan"],
    "Brunei Darussalam": None,      # whole country: all four districts
}
SHORT = {
    "Kalimantan Barat": "Kalbar", "Kalimantan Tengah": "Kalteng",
    "Kalimantan Selatan": "Kalsel", "Kalimantan Timur": "Kaltim (+Kaltara)",
}
OUT = os.path.expanduser("~/GitHub/rs-change-detection/output/fire")


def init_gee():
    import ee
    key = os.path.expanduser("~/.config/earthengine/ee-geodetic.json")
    if os.path.exists(key):
        email = json.load(open(key))["client_email"]
        ee.Initialize(ee.ServiceAccountCredentials(email, key_file=key))
    else:
        ee.Initialize()
    return ee


def build_regions(ee):
    """One FeatureCollection, each feature tagged with country and label."""
    l1 = ee.FeatureCollection("FAO/GAUL/2015/level1")
    feats = []
    for country, names in REGIONS.items():
        fc = l1.filter(ee.Filter.eq("ADM0_NAME", country))
        if names is None:
            # Dissolve the whole country to one feature. Brunei's four
            # districts are small enough that per-district counts would be
            # mostly zeros and would not tell anyone anything.
            geom = fc.geometry().dissolve(maxError=100)
            feats.append(ee.Feature(geom, {"label": "Brunei",
                                           "country": "Brunei"}))
            continue
        for n in names:
            sub = fc.filter(ee.Filter.eq("ADM1_NAME", n))
            feats.append(ee.Feature(sub.geometry(),
                                    {"label": SHORT.get(n, n),
                                     "country": country}))
    return ee.FeatureCollection(feats)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=2001,
                    help="first year of the baseline (MODIS starts 2000-11)")
    ap.add_argument("--min-confidence", type=int, default=30,
                    help="FIRMS confidence cut, 0-100. 30 drops the weakest "
                         "detections without discarding the smouldering peat "
                         "fires that matter most here, which are cooler than "
                         "flaming fronts and score low.")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    ee = init_gee()
    os.makedirs(a.out, exist_ok=True)

    firms = ee.ImageCollection("FIRMS")
    latest = firms.limit(1, "system:time_start", False).first()
    end = latest.date()
    end_str = end.format("YYYY-MM-dd").getInfo()
    this_year = int(end_str[:4])
    md_end = end_str[5:]
    print(f"FIRMS (MODIS 1 km) current to {end_str}")
    print(f"window: 1 Jan - {md_end} of each year, {a.start_year}-{this_year}")
    print(f"confidence >= {a.min_confidence}\n")

    regions = build_regions(ee)
    labels = regions.aggregate_array("label").getInfo()
    countries = regions.aggregate_array("country").getInfo()

    def ytd_image(year):
        """Pixel-days with a detection, 1 Jan to md_end of `year`."""
        ic = (firms.filterDate(f"{year}-01-01", f"{year}-{md_end}")
              .select(["T21", "confidence"]))
        hit = ic.map(lambda i: i.select("confidence")
                     .gte(a.min_confidence).rename("n"))
        return hit.sum().unmask(0)

    years = list(range(a.start_year, this_year + 1))
    counts = {}
    for y in years:
        stats = ytd_image(y).reduceRegions(
            collection=regions, reducer=ee.Reducer.sum(), scale=1000,
            tileScale=4)
        vals = stats.aggregate_array("sum").getInfo()
        counts[y] = [int(v or 0) for v in vals]
        print(f"  {y}  total {sum(counts[y]):>7,}")

    # ---- table ----------------------------------------------------------
    import numpy as np
    arr = np.array([counts[y] for y in years], dtype=float)   # years x regions
    cur = arr[-1]
    hist = arr[:-1]

    print(f"\n  hotspot pixel-days, 1 Jan - {md_end}")
    print(f"  {'region':<20}{'country':<12}{str(this_year):>10}"
          f"{'median':>10}{'max':>10}{'yr of max':>11}{'vs median':>11}")
    order = np.argsort(-cur)
    for i in order:
        med = float(np.median(hist[:, i]))
        mx = float(hist[:, i].max())
        ymax = years[int(np.argmax(hist[:, i]))]
        ratio = (cur[i] / med) if med > 0 else float("nan")
        print(f"  {labels[i]:<20}{countries[i]:<12}{int(cur[i]):>10,}"
              f"{med:>10,.0f}{mx:>10,.0f}{ymax:>11}"
              f"{ratio:>10.2f}x")

    print(f"\n  {'BY COUNTRY':<20}{'':<12}{str(this_year):>10}{'median':>10}")
    for c in ("Indonesia", "Malaysia", "Brunei"):
        idx = [i for i, cc in enumerate(countries) if cc.startswith(c)]
        if not idx:
            continue
        cc_cur = cur[idx].sum()
        cc_med = float(np.median(hist[:, idx].sum(axis=1)))
        print(f"  {c:<20}{'':<12}{int(cc_cur):>10,}{cc_med:>10,.0f}")
    tot_cur = cur.sum()
    tot_med = float(np.median(hist.sum(axis=1)))
    rank = int((hist.sum(axis=1) > tot_cur).sum()) + 1
    print(f"  {'BORNEO':<20}{'':<12}{int(tot_cur):>10,}{tot_med:>10,.0f}")
    print(f"\n  {this_year} ranks {rank} of {len(years)} years to this date "
          f"({'above' if tot_cur > tot_med else 'below'} the "
          f"{a.start_year}-{this_year-1} median)")

    np.save(os.path.join(a.out, "borneo_hotspots.npy"), arr)
    with open(os.path.join(a.out, "borneo_hotspots.json"), "w") as f:
        json.dump({"years": years, "labels": labels, "countries": countries,
                   "window_end": md_end, "min_confidence": a.min_confidence,
                   "counts": arr.tolist()}, f, indent=1)
    print(f"\nwrote {a.out}/borneo_hotspots.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
