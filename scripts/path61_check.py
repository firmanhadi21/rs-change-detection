"""What is path 61 descending actually doing over the epicentre?

Its nominal pass fell on 2026-08-14 21:35 UTC -- about 23 minutes BEFORE the
M7.7 at 21:58. If that acquisition exists it is an extraordinarily tight
pre-event scene; if it does not, the track still offers a co-seismic pair from
its 2026-08-02 scene once the next pass lands.

Either way it is worth knowing, because path 61 is a THIRD viewing geometry on
top of the ascending and descending tracks already processed -- and a
co-seismic measurement gains more from an extra look direction than from an
extra pair on a geometry already covered.
"""

import argparse
import datetime as dt
import sys

EVENT = dt.datetime(2026, 8, 14, 21, 58, tzinfo=dt.timezone.utc)
EPICENTRE = (-8.3101, 121.3517)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", type=int, default=61)
    ap.add_argument("--days", type=int, default=180)
    a = ap.parse_args()

    import asf_search as asf

    results = asf.geo_search(
        intersectsWith=f"POINT({EPICENTRE[1]} {EPICENTRE[0]})",
        platform=asf.PLATFORM.SENTINEL1,
        processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=asf.BEAMMODE.IW,
        relativeOrbit=a.path,
        start=EVENT - dt.timedelta(days=a.days),
        end=EVENT + dt.timedelta(days=a.days),
    )

    scenes = []
    for r in results:
        p = r.properties
        d = dt.datetime.fromisoformat(
            p["startTime"].replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        scenes.append((d, p))
    scenes.sort()

    print(f"path {a.path}: {len(scenes)} SLC scenes over the epicentre "
          f"in +/- {a.days} days\n")
    if not scenes:
        print("  none — this path may not actually cover the epicentre")
        return 1

    prev = None
    for d, p in scenes:
        gap = f"{(d - prev).days:>3} d" if prev else "  —"
        side = "PRE " if d < EVENT else "POST"
        mark = ""
        if prev and (d - prev).days > 13:
            mark = "   <-- gap, a pass was skipped"
        print(f"  {side} {d:%Y-%m-%d %H:%M}  {gap}  "
              f"{p['sceneName'][-28:]}{mark}")
        prev = d

    pre = [s for s in scenes if s[0] < EVENT]
    post = [s for s in scenes if s[0] >= EVENT]
    print(f"\n  before the event: {len(pre)}    after: {len(post)}")

    if pre:
        last = pre[-1][0]
        delta = EVENT - last
        print(f"  last pre-event scene is {delta.total_seconds()/3600:.1f} h "
              f"before the earthquake")

    # The repeat interval this path is actually flying, from observed gaps.
    gaps = [(scenes[i][0] - scenes[i-1][0]).days for i in range(1, len(scenes))]
    if gaps:
        # MOST COMMON gap, not the smallest. The short gaps here are the
        # S1A -> S1D handover (absolute orbit resets from 065058 to 003427),
        # not the repeat cycle. Taking the minimum predicted a pass on 20 Aug
        # that the constellation was never going to fly.
        from collections import Counter
        common = Counter(g for g in gaps if g > 0).most_common(1)[0][0]
        print(f"  repeat interval: {common} d (most common of "
              f"{sorted(set(gaps))})")
        if pre and not post:
            nxt = pre[-1][0]
            while nxt < dt.datetime.now(dt.timezone.utc):
                nxt += dt.timedelta(days=common)
            left = (nxt - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
            print(f"  next expected: {nxt:%a %Y-%m-%d %H:%M} UTC "
                  f"({left/24:.1f} d)")
            print(f"  would give a co-seismic pair "
                  f"{pre[-1][0]:%Y-%m-%d} -> {nxt:%Y-%m-%d} "
                  f"({(nxt - pre[-1][0]).days} d span)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
