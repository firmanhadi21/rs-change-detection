"""Buy the coherence baseline: STRICTLY 12-day pre-event pairs, frame 1148.

The damage z-score needs each pixel's own history of normal 12-day coherence.
That baseline is only meaningful if every pair in it has the SAME temporal
baseline as the co-event pair, because a 24-day pair decorrelates for reasons
having nothing to do with an earthquake. Mixing one in biases the baseline mean
down and inflates its standard deviation, which HIDES damage rather than
inventing it -- the failure direction nobody notices.

So this deliberately does NOT submit the redundant time-series network. That
network is right for measuring a displacement step and wrong here: at four
connections it carries 19-, 24-, 31-, 36-, 43-, 48- and 55-day pairs, every one
of which would corrupt the statistic it is meant to feed.

Two facts about this stack that the plan has to survive rather than ignore:

  THE CADENCE IS NOT CLEAN. 19 May is missing, so 7 May -> 31 May is 24 days,
  and there is a 7-day pair where the satellite changes. Of seven consecutive
  pairs only five are 12-day. Those five are the baseline; the rest are dropped
  rather than quietly accepted.

  THE SATELLITE CHANGES MID-SERIES. May-June is S1A, July-August is S1D, and
  the co-event pair is S1D->S1D. The three S1D pairs match the co-event
  exactly; the two S1A pairs match its baseline but not its satellite. Both
  counts are printed because n=3 is the bare minimum for a standard deviation
  and n=5 is meaningfully better, and that trade is the caller's to make, not
  something to bury in a default.

SEASON IS THE OTHER MATCHING PROBLEM, and it is not solved here on purpose.
Flores is wet roughly November-April and dry May-October; the co-event pair is
August, deep in the dry season. Wet-season pairs decorrelate more, so folding
January-April into the baseline inflates each pixel's standard deviation and
drags its mean down. That makes every z-score smaller -- it hides damage, it
does not invent it -- but it is still wrong.

The resolution is to buy wide and subset narrow. All 13 matched pairs are
purchased because credits are cheap relative to a re-acquisition that cannot
happen (these dates are gone), and coherence_zscore.py takes an explicit list
of baseline pairs, so a dry-season-only baseline (5 pairs, May-August) and a
full one (13 pairs) can both be computed and compared. Deciding that at
analysis time costs nothing; deciding it at purchase time is irreversible.

    python3 scripts/submit_coherence_baseline.py            # plan only
    python3 scripts/submit_coherence_baseline.py --submit
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earthchange.insar_series import (credits_per_job,        # noqa: E402
                                      pick_track, _collect)
from earthchange.insar import search_slc                      # noqa: E402

EVENT = dt.date(2026, 8, 14)
SEARCH_POINT = (-8.65, 121.25)      # on Flores; the epicentre is offshore
FRAME = 1148
GAP_DAYS = 12


def sat(granule):
    return granule[:3]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-01-01")
    # Defaults to the event, so a plain run buys baseline only. Pass a later
    # date to pick up the CO-EVENT pair as well: 6 Aug -> 18 Aug is itself a
    # 12-day S1D->S1D pair, so it passes this filter unchanged and is therefore
    # processed identically to the baseline it will be compared against. That
    # identity is the whole basis of the z-score, and getting it by reusing the
    # same filter is safer than adding a special case for the pair that matters
    # most.
    ap.add_argument("--end", default=None,
                    help="default: the event date (baseline only). Use "
                         "--end today to include the co-event pair.")
    ap.add_argument("--frame", type=int, default=FRAME)
    # ASF only returns frames containing the search point, so the point decides
    # which frames are even visible. Frame 1148 covers central and southern
    # Flores but drops to 72-82% missing north of -8.45, which is where the
    # towns nearest the rupture are. Its northern neighbour 1153 needs a
    # northern search point to appear at all.
    ap.add_argument("--lat", type=float, default=SEARCH_POINT[0])
    ap.add_argument("--lon", type=float, default=SEARCH_POINT[1])
    ap.add_argument("--satellite", default=None,
                    help="restrict to one platform, e.g. S1D, to match the "
                         "co-event pair exactly")
    ap.add_argument("--submit", action="store_true")
    a = ap.parse_args()

    end = a.end or EVENT.isoformat()
    scenes = search_slc(a.lat, a.lon, a.start, end)
    (path, frame, drn), stack = pick_track(scenes, "ascending", a.frame)
    print(f"path {path} frame {frame} {drn}: {len(stack)} scenes "
          f"{stack[0]['date']} .. {stack[-1]['date']}")

    pairs = []
    for i in range(len(stack) - 1):
        A, B = stack[i], stack[i + 1]
        gap = (dt.date.fromisoformat(B["date"])
               - dt.date.fromisoformat(A["date"])).days
        same = sat(A["granule"]) == sat(B["granule"])
        keep = gap == GAP_DAYS and same
        if keep and a.satellite:
            keep = sat(A["granule"]) == a.satellite
        mark = "keep" if keep else "DROP"
        why = ""
        if gap != GAP_DAYS:
            why = f"gap {gap} d, not {GAP_DAYS}"
        elif not same:
            why = f"crosses {sat(A['granule'])}->{sat(B['granule'])}"
        elif a.satellite and sat(A["granule"]) != a.satellite:
            why = f"{sat(A['granule'])}, not {a.satellite}"
        print(f"  {A['date']} -> {B['date']}  {gap:>3} d  "
              f"{sat(A['granule'])}->{sat(B['granule'])}  {mark}"
              + (f"   ({why})" if why else ""))
        if keep:
            pairs.append((A, B))

    if not pairs:
        raise SystemExit("no matched 12-day pair survives the filter")

    by_sat = {}
    for A, _ in pairs:
        by_sat[sat(A["granule"])] = by_sat.get(sat(A["granule"]), 0) + 1
    per = credits_per_job()
    print(f"\nbaseline: {len(pairs)} pairs at {GAP_DAYS} days  "
          f"({', '.join(f'{v} x {k}' for k, v in sorted(by_sat.items()))})")
    print(f"cost: ~{len(pairs)*per} credits at {per}/job")
    if len(pairs) < 3:
        print("  WARNING: fewer than 3 pairs. A standard deviation from n<3 is")
        print("  not a standard deviation; the z-scores would be decorative.")

    if not a.submit:
        print("\nNothing submitted. Re-run with --submit.")
        spans = [p for p in pairs
                 if dt.date.fromisoformat(p[0]["date"]) <= EVENT
                 < dt.date.fromisoformat(p[1]["date"])]
        if spans:
            print(f"Includes the CO-EVENT pair "
                  f"{spans[0][0]['date']} -> {spans[0][1]['date']}, processed "
                  f"identically to the baseline it will be compared against.")
        else:
            print(f"Baseline only. Add --end {dt.date.today()} to pick up the "
                  f"co-event pair.")
        return 0

    run_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "output", "coseismic", "baseline")
    os.makedirs(run_dir, exist_ok=True)
    meta = dict(path=path, frame=frame, direction=drn, pairs=len(pairs),
                credits_per_pair=per, first=stack[0]["date"],
                last=stack[-1]["date"])
    _collect("flores-cohbaseline", pairs, meta, run_dir, False)
    print(f"\nproducts land in {run_dir}")
    print("HyP3 expires products after ~2 weeks, so re-run to download as")
    print("they finish rather than leaving them on the server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
