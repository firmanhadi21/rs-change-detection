"""Post-event time series on ascending 112: detect the co-seismic STEP.

A single pair cannot see this earthquake. Measured on the 6->18 Aug
interferogram, turbulent troposphere writes about +/-1.4 cm of line-of-sight
signal at 10-30 km scales -- the same scale a co-seismic pattern occupies -- so
anything smaller is under the floor, and nothing was detected above it.

A time series beats that floor by repetition rather than by cleverness.
Atmosphere is independent between acquisitions 12 days apart, so averaging N
epochs on each side of the event shrinks its contribution as 1/sqrt(N) while
the step, being permanent, does not shrink at all:

    sigma_step ~ sigma_epoch * sqrt(1/N_pre + 1/N_post)

sigma_epoch here is not a textbook value. It is derived from what this scene
actually showed: a pair's atmosphere is the difference of two epochs, so
sigma_epoch = sigma_pair / sqrt(2) ~ 1.0 cm.

WHY THIS IS AN EASIER PROBLEM THAN THE INTERSEISMIC WORK THAT FAILED HERE.
Four years of stacking on this frame produced no usable velocity (r = +0.09,
and LiCSBAS rejected 92% of pairs on loop closure). None of that condemns step
detection. A velocity needs coherence maintained over YEARS and is corrupted by
any slow systematic drift; a step needs coherence over WEEKS and is a jump
between two dates. The failure mode that killed the velocity -- long-baseline
decorrelation -- does not apply across a 12-day pair.

NETWORK REDUNDANCY IS THE THING TO GET RIGHT. That 92% loop-closure rejection
is the warning. A chain of consecutive 12-day pairs has no loops at all, so an
unwrapping error cannot be detected and propagates into every later epoch.
Pairing each scene with the next FOUR gives 12/24/36/48-day connections and
many closing triangles, which is what lets MintPy find and reject bad
unwrapping instead of believing it.

    python3 scripts/postevent_stack.py                 # plan and forecast
    python3 scripts/postevent_stack.py --submit
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earthchange.insar import search_slc                      # noqa: E402
from earthchange.insar_series import (credits_per_job,        # noqa: E402
                                      network, pick_track)

EVENT = dt.date(2026, 8, 14)
EPICENTRE = (-8.3101, 121.3517)

# Search from central Flores, NOT from the epicentre. The epicentre is offshore
# and sits in frame 1153; searching there never returns frame 1148, which is
# the one covering the whole island. The search point decides which frames are
# even visible, so it has to sit on the ground being measured.
SEARCH_POINT = (-8.65, 121.25)

# Measured on this scene, not assumed. See the module docstring.
SIGMA_PAIR_CM = 1.4
SIGMA_EPOCH_CM = SIGMA_PAIR_CM / (2 ** 0.5)

# Frame 1148 rather than 1153: it covers all of Flores, 5.9x more usable land.
DEFAULT_FRAME = 1148
DEFAULT_PATH = 112

# Four connections, not the three used for the interseismic stack. See above --
# redundancy is what makes unwrapping errors detectable.
CONNECTIONS = 4

REPEAT_DAYS = 12


def split(stack):
    pre = [s for s in stack if dt.date.fromisoformat(s["date"]) <= EVENT]
    post = [s for s in stack if dt.date.fromisoformat(s["date"]) > EVENT]
    return pre, post


def sigma_step(n_pre, n_post):
    if n_pre < 1 or n_post < 1:
        return float("nan")
    return SIGMA_EPOCH_CM * (1.0 / n_pre + 1.0 / n_post) ** 0.5


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-05-01",
                    help="pre-event anchor; earlier gives a better 'before' "
                         "level but risks seasonal decorrelation")
    ap.add_argument("--end", default=None, help="default: today")
    ap.add_argument("--frame", type=int, default=DEFAULT_FRAME)
    ap.add_argument("--path", type=int, default=DEFAULT_PATH)
    ap.add_argument("--connections", type=int, default=CONNECTIONS)
    ap.add_argument("--submit", action="store_true")
    a = ap.parse_args()

    end = a.end or dt.date.today().isoformat()
    print(f"Post-event stack — path {a.path} ascending, frame {a.frame}")
    print(f"window {a.start} .. {end}, event {EVENT}\n")

    scenes = search_slc(SEARCH_POINT[0], SEARCH_POINT[1], a.start, end)
    if not scenes:
        raise SystemExit("ASF returned no SLC for that window")

    # ASF reports direction lowercase and pick_track compares it verbatim, so
    # passing "ASCENDING" silently matches nothing -- including in the fallback,
    # which made a missing frame look like a missing track.
    try:
        track_key, stack = pick_track(scenes, "ascending", a.frame)
    except SystemExit:
        avail = sorted({(s["path"], s["frame"]) for s in scenes
                        if s["direction"] == "ascending"})
        print(f"frame {a.frame} not returned for this search point; "
              f"ascending frames available: {avail}")
        print("falling back to the busiest ascending track")
        track_key, stack = pick_track(scenes, "ascending")
    path, frame, drn = track_key

    pre, post = split(stack)
    print(f"track {path} {drn} frame {frame}: {len(stack)} scenes "
          f"({len(pre)} pre-event, {len(post)} post-event)")
    if pre:
        print(f"  pre : {pre[0]['date']} .. {pre[-1]['date']}")
    if post:
        print(f"  post: {post[0]['date']} .. {post[-1]['date']}")
    else:
        print("  post: NONE yet on this frame in ASF")

    pairs, skipped = network(stack, a.connections)
    spanning = [p for p in pairs
                if dt.date.fromisoformat(p[0]["date"]) <= EVENT
                < dt.date.fromisoformat(p[1]["date"])]
    per_job = credits_per_job()
    print(f"\nnetwork: {len(pairs)} pairs at {a.connections} connections "
          f"({skipped} dropped over the baseline limit)")
    print(f"  event-spanning pairs: {len(spanning)}")
    print(f"  cost if all submitted: ~{len(pairs)*per_job} credits "
          f"at {per_job}/job")

    # ---- when does this become worth inverting? --------------------------
    print(f"\n=== projected step sensitivity ===")
    print(f"  sigma_epoch {SIGMA_EPOCH_CM:.2f} cm, from the measured "
          f"{SIGMA_PAIR_CM:.1f} cm single-pair floor")
    print(f"  a step is DETECTABLE at ~2 sigma\n")
    print("   date         N_post   sigma_step   2-sigma detection limit")
    n_pre = max(len(pre), 1)
    last = (dt.date.fromisoformat(post[-1]["date"]) if post else EVENT)
    for k in range(1, 13):
        d = last + dt.timedelta(days=REPEAT_DAYS * (k - len(post))) \
            if post else EVENT + dt.timedelta(days=REPEAT_DAYS * k)
        if d < dt.date.today():
            d = dt.date.today()
        s = sigma_step(n_pre, k)
        flag = ""
        if k == len(post):
            flag = "   <- today"
        print(f"  {d.isoformat()}    {k:3d}      {s:.2f} cm      "
              f"{2*s:.2f} cm{flag}")

    n_needed = None
    for k in range(1, 40):
        if 2 * sigma_step(n_pre, k) <= 1.0:
            n_needed = k
            break
    if n_needed:
        when = EVENT + dt.timedelta(days=REPEAT_DAYS * n_needed)
        print(f"\n  To resolve a 1 cm step needs ~{n_needed} post-event "
              f"scenes -> about {when.isoformat()}")
    print("  Caveat: this assumes atmosphere is independent between epochs,")
    print("  which holds at 12 days, and that coherence survives. It ignores")
    print("  unwrapping error, which is the real risk on this frame and is")
    print("  why the network carries redundancy rather than a bare chain.")

    if not a.submit:
        print(f"\nNothing submitted. --submit would spend "
              f"~{len(pairs)*per_job} credits.")
        print("Re-run after each new acquisition; job names are deterministic,")
        print("so already-submitted pairs are found rather than re-bought.")
        return 0

    if not post:
        print("\nRefusing to submit: no post-event scene on this frame yet.")
        print("Every pair would be pre-event only, which measures nothing "
              "about the earthquake.")
        return 1

    from earthchange.insar_series import _collect
    run_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "output", "coseismic", "stack")
    os.makedirs(run_dir, exist_ok=True)
    meta = dict(path=path, frame=frame, direction=drn,
                pairs=len(pairs), first=stack[0]["date"],
                last=stack[-1]["date"])
    _collect("flores-postevent", pairs, meta, run_dir, False)
    print(f"\nsubmitted//found; products land in {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
