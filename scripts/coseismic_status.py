"""Status of the Flores co-seismic HyP3 jobs.

Small and reusable, because this gets asked repeatedly while waiting: which
pairs exist, what state they are in, and what is still missing.
"""

import datetime as dt
import sys

PROJECT = "flores-coseismic-2026"


def main():
    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    jobs = [j for j in hyp3.find_jobs(start=since)
            if j.name and j.name.startswith(PROJECT)]

    if not jobs:
        print(f"no jobs named {PROJECT}* found")
        return 1

    print(f"{len(jobs)} co-seismic job(s)\n")
    for j in sorted(jobs, key=lambda x: x.name):
        gran = (j.job_parameters or {}).get("granules", [])
        dates = []
        for g in gran:
            for part in g.split("_"):
                if len(part) == 15 and part[8] == "T":
                    dates.append(part[:8])
                    break
        span = ""
        if len(dates) == 2:
            d1 = dt.datetime.strptime(dates[0], "%Y%m%d")
            d2 = dt.datetime.strptime(dates[1], "%Y%m%d")
            span = f"  {dates[0]} -> {dates[1]}  ({(d2-d1).days} d)"

        print(f"  {j.name}")
        print(f"      {j.status_code}{span}")
        if j.status_code == "SUCCEEDED":
            files = getattr(j, "files", None) or []
            for f in files:
                print(f"      ready: {f.get('filename')}")
        exp = getattr(j, "expiration_time", None)
        if exp:
            print(f"      expires {exp:%Y-%m-%d} "
                  f"({(exp - dt.datetime.now(dt.timezone.utc)).days} d)")

    print(f"\ncredits remaining: {hyp3.check_credits()}")

    have = {j.name.rsplit("-", 1)[-1] for j in jobs}
    for kind in ("prepre", "prepost"):
        mark = "yes" if kind in have else "NOT YET"
        print(f"  {kind:8} {mark}")
    if "prepost" not in have:
        print("\n  The co-event pair needs the post-event scene "
              "(ascending, expected 18 Aug 10:16 UTC).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
