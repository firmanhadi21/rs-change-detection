"""Fold the two Borneo hotspot runs into the payload the five pages read.

This step existed only in a scratchpad when the August 2026 set was made, so
nothing in the repository could rebuild `infographic_payload.json` and the
pages could not be re-rendered against a newer window. It is a pure adapter:
it performs no Earth Engine work and derives nothing that the two upstream
scripts have not already measured.

    conda run -n base python scripts/borneo_hotspots.py        # year to date
    conda run -n base python scripts/borneo_hotspots_7d.py     # the window
    conda run -n base python scripts/borneo_fire_payload.py    # this
    conda run -n base python scripts/borneo_fire_pages.py      # five pages

TWO DIFFERENT QUANTITIES SHARE THE WORD "HOTSPOT" HERE and the pages print
both. The seven-day figures are DETECTIONS -- one row per pixel per day, from
borneo_hotspots_7d.json. The year-to-date figures are PIXEL-DAYS summed over
a region by Earth Engine, from borneo_hotspots.json. They are the same
definition counted by different machinery, and they agree to rounding, but
the two files must come from the same FIRMS vintage or the page-5 share
("these seven days are N% of the year") is computed across a seam. This
script refuses to write when the window is not inside the year-to-date range.
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

# The forest estate: everything KLHK designates, as against APL, which is
# land released from it. Water and unclassified are neither.
ESTATE = ("HP (production)", "HPK (convertible production)",
          "HPT (limited production)", "HL (protection forest)",
          "Conservation (KSA/KPA)")
# Where burning is not permitted under any licence.
PROTECTED = ("HL (protection forest)", "Conservation (KSA/KPA)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    p7 = os.path.join(a.out, "borneo_hotspots_7d.json")
    pyt = os.path.join(a.out, "borneo_hotspots.json")
    for p in (p7, pyt):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}\nRun the two hotspot scripts first "
                             f"(see this file's docstring).")
    W = json.load(open(p7))
    Y = json.load(open(pyt))

    # --- the seam check -------------------------------------------------
    # Both files carry a window end. If the seven-day run is newer than the
    # year-to-date run, the share on page 5 divides a window by a total that
    # does not contain it, and reads as high as it likes.
    yr = W["date_max"][:4]
    if W["date_max"][5:] > Y["window_end"]:
        raise SystemExit(
            f"the two runs are from different FIRMS vintages:\n"
            f"  7-day window ends {W['date_max']}\n"
            f"  year-to-date ends {yr}-{Y['window_end']}\n"
            f"Re-run scripts/borneo_hotspots.py so both see the same data.")

    # --- year to date ---------------------------------------------------
    import numpy as np
    arr = np.array(Y["counts"], dtype=float)      # years x regions
    totals = arr.sum(axis=1)
    cur, hist = totals[-1], totals[:-1]
    ytd = {
        "ytd_total": int(cur),
        "ytd_median": float(np.median(hist)),
        "ytd_rank": int((hist > cur).sum()) + 1,
        "ytd_years": int(len(totals)),
        "ytd_window_end": Y["window_end"],
    }
    # Per region, this season against its OWN history. Page 2 claims that
    # Malaysian Borneo runs below its median while Kalimantan runs far above
    # it; that claim has to be measured each season, not asserted.
    ytd["ytd_ratio"] = []
    for i, lab in enumerate(Y["labels"]):
        med = float(np.median(arr[:-1, i]))
        ytd["ytd_ratio"].append({
            "r": lab, "c": Y["countries"][i], "n": int(arr[-1, i]),
            "median": med,
            "ratio": (arr[-1, i] / med) if med > 0 else None,
        })

    # --- the window -----------------------------------------------------
    pts = W["points"]
    daily, by_country, by_region, by_function = {}, {}, {}, {}
    for p in pts:
        daily[p["date"]] = daily.get(p["date"], 0) + 1
    for row in W["by_admin"]:
        by_country[row["country"]] = (by_country.get(row["country"], 0)
                                      + row["n"])
        by_region[(row["region"], row["country"])] = row["n"]
    for row in W["by_function"]:
        by_function[row["fungsi"]] = row["n"]

    ind = W["indonesia_total"]
    # Malaysian and Bruneian detections carry no KLHK class, and the map draws
    # them under a key of their own rather than as "unclassified", which means
    # something different: inside Indonesia, no polygon.
    country_of = {r["region"]: r["country"] for r in W["by_admin"]}
    out_pts = [[round(p["lon"], 3), round(p["lat"], 3),
                p["fungsi"] if country_of.get(p["region"]) == "Indonesia"
                else "_MY"]
               for p in pts]

    D = {
        "window": [W["date_min"], W["date_max"]],
        "total": W["total"],
        "daily": [{"d": d, "n": n} for d, n in sorted(daily.items())],
        "by_country": [{"c": c, "n": n} for c, n in
                       sorted(by_country.items(), key=lambda kv: -kv[1])],
        "by_region": [{"r": r, "c": c, "n": n} for (r, c), n in
                      sorted(by_region.items(), key=lambda kv: -kv[1])],
        "by_function": [{"f": f, "n": n} for f, n in
                        sorted(by_function.items(), key=lambda kv: -kv[1])],
        "indonesia_total": ind,
        "protected": sum(by_function.get(k, 0) for k in PROTECTED),
        "in_estate": sum(by_function.get(k, 0) for k in ESTATE),
        # Carried through for the method page, so it describes the run that
        # actually happened rather than the one the scripts default to.
        "method": {
            "days": W["days"],
            "min_confidence": W["min_confidence"],
            "n_fetched": W.get("n_fetched"),
            "n_outside": W.get("n_outside"),
            "bbox": W.get("bbox"),
            "forest_layer": W.get("forest_layer"),
            "n_kawasan_polygons": W.get("n_kawasan_polygons"),
            "ytd_start_year": int(Y["years"][0]),
            "n_regions": len(Y["labels"]),
        },
        **ytd,
    }
    D["pts"] = out_pts

    dest = os.path.join(a.out, "infographic_payload.json")
    with open(dest, "w") as f:
        json.dump(D, f)

    print(f"window      {D['window'][0]} .. {D['window'][1]}")
    print(f"detections  {D['total']:,}  ({ind:,} Indonesian)")
    print(f"in estate   {D['in_estate']:,}  "
          f"({100*D['in_estate']/ind:.1f}% of Indonesian)")
    print(f"protected   {D['protected']:,}  "
          f"({100*D['protected']/ind:.1f}%)")
    print(f"year to date {D['ytd_total']:,} to {yr}-{D['ytd_window_end']}, "
          f"rank {D['ytd_rank']} of {D['ytd_years']}, "
          f"{D['ytd_total']/D['ytd_median']:.2f}x median")
    print(f"this window is {100*D['total']/D['ytd_total']:.1f}% of the year")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
