"""Block until named HyP3 jobs reach a terminal state, then report.

Exists so a submission can be walked away from. Polls the two job IDs and
exits when both are SUCCEEDED or FAILED, printing which. Exit code is non-zero
if any job failed, so a caller can branch on it.

    python3 scripts/wait_hyp3_jobs.py <job_id> [<job_id> ...]
    python3 scripts/wait_hyp3_jobs.py --project flores-coseismic-2026
"""

import argparse
import sys
import time

TERMINAL = {"SUCCEEDED", "FAILED"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("job_ids", nargs="*")
    ap.add_argument("--interval", type=int, default=120,
                    help="seconds between polls; HyP3 takes 20-40 min, so "
                         "polling faster only adds load")
    ap.add_argument("--max-minutes", type=int, default=180)
    a = ap.parse_args()

    if not a.job_ids:
        sys.exit("give at least one job id")

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()

    deadline = time.time() + a.max_minutes * 60
    seen = {}
    while time.time() < deadline:
        states = {}
        for jid in a.job_ids:
            try:
                j = hyp3.get_job_by_id(jid)
                states[jid] = (j.status_code, j.name)
            except Exception as exc:                      # noqa: BLE001
                # A transient API error must not end the wait -- the job is
                # still running regardless of whether we could ask about it.
                states[jid] = (f"query-failed:{exc.__class__.__name__}", "?")
        for jid, (st, nm) in states.items():
            if seen.get(jid) != st:
                print(f"{nm or jid}: {st}", flush=True)
                seen[jid] = st
        if all(st in TERMINAL for st, _ in states.values()):
            failed = [nm for st, nm in states.values() if st == "FAILED"]
            print(f"\nall {len(states)} jobs terminal; "
                  f"{len(failed)} failed", flush=True)
            return 1 if failed else 0
        time.sleep(a.interval)

    print(f"\ngave up after {a.max_minutes} min; jobs may still be running",
          flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
