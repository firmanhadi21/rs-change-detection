"""What is in the damage reports, and where are they relative to the source?

The InSAR result is that onshore LOS displacement is roughly a tenth of what
the USGS finite-fault model predicts. Damage reports are an independent
observable that bears on it: severe structural damage requires strong shaking,
and strong shaking near a source usually accompanies large slip.

THE BIAS THAT HAS TO BE HANDLED FIRST, or every conclusion drawn from these
points is wrong. Crowd-sourced and agency reports come from where PEOPLE are
and where connectivity exists. Maumere is by far the largest town in the
region. A cluster of reports there is, on its own, evidence about the
population distribution, not the shaking distribution. So this script reports
counts AND the severity mix within each area -- severity mix is far less
sensitive to how many people were there to file a report.

    python3 scripts/eq_reports_survey.py
"""

import argparse
import collections
import json
import math
import os
import sys


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
SRC = os.path.join(REPO, "data/eq_reports.geojson")
EPI_LON, EPI_LAT = 121.3517, -8.3101


def km(lon, lat):
    dx = (lon - EPI_LON) * 111.32 * math.cos(math.radians(EPI_LAT))
    dy = (lat - EPI_LAT) * 111.32
    return math.hypot(dx, dy)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=SRC)
    a = ap.parse_args()

    d = json.load(open(a.src))
    feats = d["features"]
    print(f"{len(feats)} reports")

    rows = []
    bad = 0
    for f in feats:
        p = f["properties"]
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        if not c or len(c) < 2:
            bad += 1
            continue
        lon, lat = float(c[0]), float(c[1])
        rows.append({
            "lon": lon, "lat": lat, "r": km(lon, lat),
            "lvl": p.get("damage_level"),
            "label": (p.get("damage_label") or "").strip(),
            "src": (p.get("source") or "?").strip(),
            "loc": (p.get("location") or "").strip(),
            "when": (p.get("reported_at") or "")[:10],
        })
    if bad:
        print(f"  {bad} without usable coordinates, dropped")

    print("\nsource:")
    for s, n in collections.Counter(r["src"] for r in rows).most_common():
        print(f"  {s:>14}  {n:>4}")

    print("\ndamage level:")
    lv = collections.Counter((r["lvl"], r["label"]) for r in rows)
    for (l, lab), n in sorted(lv.items(), key=lambda kv: (kv[0][0] is None,
                                                          kv[0][0])):
        print(f"  {str(l):>4}  {lab:<12}  {n:>4}")

    print("\nreport date:")
    for s, n in sorted(collections.Counter(r["when"] for r in rows).items()):
        print(f"  {s}  {n:>4}")

    # damage_level == -1 means UNCLASSIFIED, not undamaged, and 383 of the 452
    # reports are that -- every one from source "gik". Leaving them in the
    # denominator of a "% severe" makes the severity fraction a measure of how
    # many gik reports fell in each ring, which is a measure of population and
    # phone coverage. Only classified reports can answer a severity question.
    classified = [r for r in rows
                  if isinstance(r["lvl"], (int, float)) and r["lvl"] >= 0]
    print(f"\n{len(classified)} of {len(rows)} reports carry a damage level; "
          f"the rest are unclassified")

    print("\ndistance from the epicentre "
          "(severity among CLASSIFIED reports only):")
    bins = [(0, 25), (25, 50), (50, 75), (75, 100), (100, 150), (150, 1e9)]
    for lo, hi in bins:
        sel = [r for r in rows if lo <= r["r"] < hi]
        cls = [r for r in classified if lo <= r["r"] < hi]
        if not sel:
            continue
        sev = [r for r in cls if r["lvl"] >= 3]
        name = f"{lo}-{hi} km" if hi < 1e9 else f">{lo} km"
        frac = f"{100*len(sev)/len(cls):.0f}%" if cls else "n/a"
        print(f"  {name:>12}  {len(sel):>4} reports, {len(cls):>3} classified,"
              f" {len(sev):>3} severe ({frac} of classified)")

    print("\nfarthest and nearest severe reports:")
    sev = sorted((r for r in rows if isinstance(r["lvl"], (int, float))
                  and r["lvl"] >= 3), key=lambda r: r["r"])
    if sev:
        for r in sev[:3]:
            print(f"  {r['r']:>6.0f} km  {r['loc'][:58]}")
        print("   ...")
        for r in sev[-3:]:
            print(f"  {r['r']:>6.0f} km  {r['loc'][:58]}")

    lons = [r["lon"] for r in rows]
    lats = [r["lat"] for r in rows]
    print(f"\nextent: lon {min(lons):.3f} .. {max(lons):.3f}, "
          f"lat {min(lats):.3f} .. {max(lats):.3f}")
    print(f"epicentre at {EPI_LON}, {EPI_LAT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
