"""What Sentinel-1 imagery exists on each side of the earthquake?

A co-seismic interferogram needs one scene before the event and one after, on
the same relative orbit. This lists what is actually available, per orbit, so a
pair can be chosen rather than assumed -- and so the wait for a missing
post-event acquisition is a known number of days rather than a guess.

    python3 scripts/coseismic_scenes.py
"""

import argparse
import datetime as dt
import sys
from collections import defaultdict

EVENT = dt.datetime(2026, 8, 14, tzinfo=dt.timezone.utc)
EPICENTRE = (-8.3101, 121.3517)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, default=EPICENTRE[0])
    ap.add_argument("--lon", type=float, default=EPICENTRE[1])
    ap.add_argument("--days", type=int, default=40,
                    help="window each side of the event")
    a = ap.parse_args()

    try:
        import asf_search as asf
    except ImportError:
        raise SystemExit("pip install asf_search")

    start = EVENT - dt.timedelta(days=a.days)
    end = EVENT + dt.timedelta(days=a.days)
    print(f"epicentre {a.lat}, {a.lon}   event {EVENT:%Y-%m-%d}")
    print(f"searching {start:%Y-%m-%d} .. {end:%Y-%m-%d}\n")

    results = asf.geo_search(
        intersectsWith=f"POINT({a.lon} {a.lat})",
        platform=asf.PLATFORM.SENTINEL1,
        processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=asf.BEAMMODE.IW,
        start=start, end=end,
    )
    print(f"{len(results)} SLC scenes intersect the epicentre\n")

    by_orbit = defaultdict(list)
    for r in results:
        p = r.properties
        d = dt.datetime.fromisoformat(
            p["startTime"].replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        by_orbit[(p["pathNumber"], p["flightDirection"])].append((d, p))

    for (path, direction), scenes in sorted(by_orbit.items()):
        scenes.sort()
        pre = [s for s in scenes if s[0] < EVENT]
        post = [s for s in scenes if s[0] >= EVENT]
        print(f"=== path {path}  {direction} ===")
        print(f"  {len(pre)} before, {len(post)} after the event")

        if pre:
            d, p = pre[-1]
            print(f"  last  pre-event: {d:%Y-%m-%d %H:%M}  {p['sceneName'][:52]}")
        if post:
            d, p = post[0]
            span = (d - pre[-1][0]).days if pre else None
            print(f"  first post-event: {d:%Y-%m-%d %H:%M}  {p['sceneName'][:52]}")
            if span:
                print(f"  -> co-seismic pair spans {span} days "
                      f"{'  READY TO SUBMIT' if span <= 36 else ''}")
        else:
            # No post-event scene yet: say when one is due, from the cadence.
            if len(pre) >= 2:
                cadence = (pre[-1][0] - pre[-2][0]).days or 12
                nxt = pre[-1][0] + dt.timedelta(days=cadence)
                while nxt < EVENT:
                    nxt += dt.timedelta(days=cadence)
                # timedelta.days truncates: 1.9 days reads as "1", which turns
                # a Tuesday into "tomorrow". Report hours and the weekday.
                delta = nxt - dt.datetime.now(dt.timezone.utc)
                hours = delta.total_seconds() / 3600
                print(f"  no post-event scene yet; next pass "
                      f"~{nxt:%a %Y-%m-%d %H:%M} UTC "
                      f"({hours/24:.1f} days / {hours:.0f} h)")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
