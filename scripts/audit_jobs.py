"""Count HyP3 jobs and look for duplicate work.

Each interferogram should map to exactly ONE job. Two things could break that:
a date pair appearing under several variant hashes (the same data bought twice),
or the same name submitted repeatedly. Both cost credits silently, so count by
date pair rather than trusting the total.
"""

import argparse
import datetime as dt
import re
import sys
from collections import Counter, defaultdict

PAIR = re.compile(r"earthchange-(\d{8})_(\d{8})-([a-z0-9]+)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=120)
    a = ap.parse_args()

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)
    jobs = [j for j in hyp3.find_jobs(start=since) if j.name]

    mine = [j for j in jobs if j.name.startswith("earthchange-")]
    print(f"{len(jobs)} jobs total, {len(mine)} named earthchange-*\n")

    print("=== by status ===")
    for s, n in Counter(j.status_code for j in mine).most_common():
        print(f"  {s:12} {n}")

    print("\n=== by variant tag ===")
    variants = Counter()
    by_pair = defaultdict(set)
    unparsed = []
    for j in mine:
        m = PAIR.search(j.name)
        if not m:
            unparsed.append(j.name)
            continue
        d1, d2, tag = m.groups()
        variants[tag] += 1
        by_pair[(d1, d2)].add(tag)
    for tag, n in variants.most_common():
        print(f"  {tag:14} {n}")
    if unparsed:
        print(f"  (unparsed: {len(unparsed)}) e.g. {unparsed[:3]}")

    print("\n=== duplication ===")
    print(f"  distinct date pairs: {len(by_pair)}")
    dupes = {p: t for p, t in by_pair.items() if len(t) > 1}
    print(f"  pairs under MORE THAN ONE variant: {len(dupes)}")
    for p, tags in list(dupes.items())[:5]:
        print(f"      {p[0]}_{p[1]}: {sorted(tags)}")

    names = Counter(j.name for j in mine)
    repeats = {n: c for n, c in names.items() if c > 1}
    print(f"  names submitted more than once: {len(repeats)}")
    for n, c in list(repeats.items())[:5]:
        print(f"      {n} x{c}")

    # What a rerun would cost, given the CURRENT variant tag.
    try:
        sys.path.insert(0, ".")
        from earthchange.insar_series import variant
        cur = variant()
        stale = sum(n for t, n in variants.items() if t != cur)
        print(f"\n=== current variant is {cur!r} ===")
        print(f"  jobs under it: {variants.get(cur, 0)}")
        print(f"  jobs under OTHER tags: {stale}")
        if stale:
            print(f"  WARNING: rerunning the pipeline would resubmit those "
                  f"{stale} pairs at ~10 credits each (~{stale*10} credits), "
                  f"because the variant tag changed. Products already on disk "
                  f"are unaffected.")
    except Exception as e:  # noqa: BLE001
        print(f"(could not import variant(): {type(e).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
