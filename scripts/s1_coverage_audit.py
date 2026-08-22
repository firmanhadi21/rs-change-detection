"""What did Sentinel-1 actually record over Flores, and when?

Written after two assumptions turned out to be wrong, both of which were
shaping what this investigation waited for.

ASSUMPTION 1: a M7.7 in a populated area triggers rapid-response tasking, so
better post-event scenes than 18 August (3.5 days late) probably exist. They
do not. In the nine days after the rupture exactly four IW SLC acquisitions
touched the 45 km near-field ring, and they are the two pairs already
processed. There was no emergency acquisition. Every post-event scene that
exists has been used.

ASSUMPTION 2: descending path 163 revisits Flores every 12 days, so the 21
August pass will cover frame 620. Path 163 is flown under two different
segment plans -- one spanning frames 477..630, which includes Flores, and one
spanning 554..704 with a hole from 570 to 659, which excludes it. S1C has used
the second plan on 8 of 8 passes since May and has never recorded frame 620.
S1D alternates and recorded it on 3 of 6. So the effective revisit over this
ground is not 12 days, and the pass being waited for may not cover it at all.

The general lesson is that "the satellite passes overhead every 12 days" is
not the same statement as "the satellite records this ground every 12 days",
and only the archive can tell you which one is true.

    python3 scripts/s1_coverage_audit.py --sweep
    python3 scripts/s1_coverage_audit.py --frames --path 163 --frame 620
"""

import argparse
import collections
import csv
import io
import math
import sys
import urllib.parse
import urllib.request

API = "https://api.daac.asf.alaska.edu/services/search/param"
LAT, LON = -8.3101, 121.3517
EVENT = "2026-08-14T21:58"


def fetch(**q):
    q.setdefault("output", "csv")
    url = f"{API}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "earthchange"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return list(csv.DictReader(io.StringIO(
            r.read().decode("utf-8", "replace"))))


def ring(radius_km, n=36):
    pts = []
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * math.cos(math.radians(LAT)))
        pts.append(f"{LON + dlon*math.cos(th):.5f} "
                   f"{LAT + dlat*math.sin(th):.5f}")
    return f"POLYGON(({','.join(pts)}))"


def sweep(a):
    """Everything that touched the near field since the rupture."""
    rows = fetch(platform="Sentinel-1", processingLevel="SLC", beamMode="IW",
                 intersectsWith=ring(a.radius),
                 start=f"{a.start}T00:00:00Z", end=f"{a.end}T23:59:59Z")
    post = sorted((r for r in rows if r["Start Time"][:16] > EVENT),
                  key=lambda x: x["Start Time"])
    print(f"{len(post)} post-rupture IW SLC intersecting the "
          f"{a.radius:.0f} km ring, {a.start} to {a.end}\n")
    print(f"  {'start':>17}{'sat':>5}{'path':>6}{'frame':>7}{'dir':>5}"
          f"{'after':>9}")
    for r in post:
        t = r["Start Time"][:16]
        d = ((int(t[8:10]) - 14) + (int(t[11:13]) - 21) / 24
             + (int(t[14:16]) - 58) / 1440)
        print(f"  {t:>17}{r['Platform'][-2:]:>5}{r['Path Number']:>6}"
              f"{r['Frame Number']:>7}"
              f"{r['Ascending or Descending?'][:3]:>5}{d:>8.1f}d")
    if not post:
        print("  none")
    return 0


def frames(a):
    """Which passes on a path actually recorded a given frame."""
    rows = fetch(platform="Sentinel-1", processingLevel="SLC", beamMode="IW",
                 relativeOrbit=str(a.path),
                 start=f"{a.hist_start}T00:00:00Z", end=f"{a.end}T23:59:59Z")
    if not rows:
        sys.exit(f"no scenes on path {a.path}")
    by = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in rows:
        by[r["Start Time"][:10]][r["Platform"][-2:]].add(
            int(r["Frame Number"]))

    print(f"path {a.path}, does each pass record frame {a.frame}?\n")
    tally = collections.defaultdict(lambda: [0, 0])
    for date in sorted(by):
        for sat, fs in sorted(by[date].items()):
            f = sorted(fs)
            hit = a.frame in fs
            tally[sat][1] += 1
            tally[sat][0] += int(hit)
            print(f"  {date}  {sat}  {'YES' if hit else ' no'}  "
                  f"{len(f):>3} frames  {f[0]}..{f[-1]}")

    print("\n  satellite   passes recording the frame")
    for sat, (hit, tot) in sorted(tally.items()):
        print(f"  {sat:>9}   {hit} of {tot}")
    worst = [s for s, (h, t) in tally.items() if h == 0]
    if worst:
        print(f"\n  {', '.join(worst)} has NEVER recorded frame {a.frame} on "
              f"this path.\n  Its nominal revisit does not apply to this "
              f"ground.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--frames", action="store_true")
    ap.add_argument("--radius", type=float, default=45.0)
    ap.add_argument("--path", type=int, default=163)
    ap.add_argument("--frame", type=int, default=620)
    ap.add_argument("--start", default="2026-08-14")
    ap.add_argument("--hist-start", default="2026-05-01")
    ap.add_argument("--end", default="2026-08-23")
    a = ap.parse_args()
    if not (a.sweep or a.frames):
        ap.error("pass --sweep or --frames")
    rc = 0
    if a.sweep:
        rc |= sweep(a)
    if a.frames:
        if a.sweep:
            print()
        rc |= frames(a)
    return rc


if __name__ == "__main__":
    sys.exit(main())
