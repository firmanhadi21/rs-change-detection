"""How many extra baseline pairs are already bought, and what would the rest cost?

Extending the earthquake-free baseline is the cheapest way to strengthen the
claim that the co-event pair is anomalous. With 13 pairs the parametric z is
decisive but the DISTRIBUTION-FREE statement is weak: "larger than all 13"
carries p ~ 1/14 = 0.07 by rank alone. Thirty pairs would take that to ~0.03,
sixty to ~0.016, without assuming normality anywhere.

The cost is not 10 credits per pair. Job names hash the two granules plus the
parameter set, so any pair already submitted -- under the current variant tag
or the legacy one -- is found by name and costs nothing to collect. That is how
the first 13 came back free. This reports the split before any credits move.

Nothing is submitted here. Report only.

    conda run -n mintpy python scripts/baseline_cost_check.py --start 2024-01-01
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earthchange.insar import _client, job_name, search_slc      # noqa: E402
from earthchange.insar_series import (LEGACY_VARIANTS,           # noqa: E402
                                      credits_per_job, pick_track,
                                      variant)

EVENT = dt.date(2026, 8, 14)
SEARCH_POINT = (-8.65, 121.25)
GAP_DAYS = 12


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-08-19")
    ap.add_argument("--frame", type=int, default=1148)
    ap.add_argument("--lat", type=float, default=SEARCH_POINT[0])
    ap.add_argument("--lon", type=float, default=SEARCH_POINT[1])
    a = ap.parse_args()

    scenes = search_slc(a.lat, a.lon, a.start, a.end)
    (path, frame, drn), stack = pick_track(scenes, "ascending", a.frame)

    pairs = []
    for i in range(len(stack) - 1):
        A, B = stack[i], stack[i + 1]
        gap = (dt.date.fromisoformat(B["date"])
               - dt.date.fromisoformat(A["date"])).days
        if gap == GAP_DAYS and A["granule"][:3] == B["granule"][:3]:
            pairs.append((A, B))
    print(f"path {path} frame {frame}: {len(stack)} scenes "
          f"{stack[0]['date']} .. {stack[-1]['date']}")
    print(f"{len(pairs)} matched {GAP_DAYS}-day pairs\n")

    hyp3 = _client()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)
    known = {j.name for j in hyp3.find_jobs(start=since) if j.name}
    print(f"{len(known):,} named jobs visible in the last 365 days")

    cur = variant()
    have, missing = [], []
    for p in pairs:
        names = [job_name("", "ts", p, cur)]
        names += [job_name("", "ts", p, v) for v in LEGACY_VARIANTS]
        (have if any(n in known for n in names) else missing).append(p)

    per = credits_per_job()
    pre = [p for p in missing
           if dt.date.fromisoformat(p[1]["date"]) <= EVENT]
    print(f"\n  already submitted (free to collect): {len(have)}")
    print(f"  not yet submitted                  : {len(missing)}")
    print(f"    of which earthquake-free         : {len(pre)}")
    print(f"\n  cost to buy the missing ones: ~{len(missing)*per} credits "
          f"at {per}/job")
    bal = hyp3.check_credits()
    print(f"  balance: {bal}")

    n_free = len(have)
    print(f"\n=== what each option buys, statistically ===")
    for n, label in ((13, "current baseline"),
                     (n_free, "everything already paid for"),
                     (len(pairs) - 1, "all matched pairs")):
        if n < 2:
            continue
        print(f"  {n:3d} pairs ({label}): rank-only p if the co-event exceeds "
              f"all = {1/(n+1):.3f}")

    if missing:
        print(f"\n  first few not yet submitted:")
        for p in missing[:6]:
            print(f"    {p[0]['date']} -> {p[1]['date']}")
    print("\nNothing submitted. This is a report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
