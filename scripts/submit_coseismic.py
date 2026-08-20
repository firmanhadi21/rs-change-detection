"""Submit the co-seismic interferograms for the 14 Aug 2026 M7.7, Flores.

One pair per track, spanning the rupture. This needs none of the machinery the
interseismic study required -- no stacking, no ERA5, no time series. Expected
displacement is 10-30 cm onshore against a few cm of per-pair atmosphere, so a
single interferogram carries the signal.

Choices that differ from the interseismic submissions, and why:

  looks 10x2 rather than 20x4    40 m instead of 80 m. Co-seismic mapping wants
                                 spatial detail; 15 credits instead of 10 is
                                 worth it for one pair per track.
  include_displacement_maps      HyP3 returns displacement in metres directly,
                                 removing a phase-to-range conversion and one
                                 place to get a sign or factor wrong. NOT
                                 include_los_displacement, which is deprecated
                                 and silently ignored -- see JOB_PARAMETERS.
  include_wrapped_phase          Fringes are the clearest evidence that a real
                                 deformation pattern exists rather than noise.
  shared project name            NOT the granule-hash scheme used for the 705
                                 interseismic jobs. That scheme makes
                                 resubmission idempotent, which is worth a lot
                                 on a 705-job network and nothing on four jobs
                                 -- while costing ASF-notebook compatibility,
                                 where each name shows as a separate project.

    python3 scripts/submit_coseismic.py                 # plan only
    python3 scripts/submit_coseismic.py --submit
    python3 scripts/submit_coseismic.py --submit --track asc
"""

import argparse
import datetime as dt
import sys

EVENT = dt.datetime(2026, 8, 14, 21, 58, tzinfo=dt.timezone.utc)
EPICENTRE = (-8.3101, 121.3517)
PROJECT = "flores-coseismic-2026"

TRACKS = {
    "asc": {"path": 112, "direction": "ASCENDING"},
    "desc": {"path": 163, "direction": "DESCENDING"},
    "desc61": {"path": 61, "direction": "DESCENDING"},   # third geometry
}

# include_displacement_maps, NOT include_los_displacement. The latter is
# deprecated in HyP3's API and superseded by the former, and the failure mode
# is silent: HyP3 ACCEPTS include_los_displacement=True, records it on the job,
# and then delivers no displacement band because include_displacement_maps
# defaults to False and wins. The job succeeds, the parameter appears in the
# job record, and the file simply is not there.
#
# That cost a round trip on the one band needed to settle whether positive
# unwrapped phase means motion toward or away from the sensor -- the sign that
# decides uplift versus subsidence. Checking the DELIVERED FILE LIST against
# the requested parameters would have caught it immediately; checking the job
# parameters alone would not, because they looked correct.
#
# This also yields the vertical displacement map, which HyP3 derives under the
# assumption that horizontal motion is zero. Useful as a cross-check on our own
# LOS conversion; not to be published as vertical for a thrust event.
JOB_PARAMETERS = {
    "looks": "10x2",
    "apply_water_mask": True,
    "include_dem": True,
    "include_inc_map": True,
    "include_look_vectors": True,
    "include_displacement_maps": True,
    "include_wrapped_phase": True,
}

# Job names are hand-written here rather than hashed from granules+parameters,
# so a parameter change does NOT produce a new name on its own -- the existing
# job would be found and skipped, and the new bands never arrive. Bump this
# whenever JOB_PARAMETERS changes in a way that alters the delivered product.
PARAM_TAG = "d2"


def find_scenes(path, days=60, frame=None):
    """The two scenes before the event and the first after, on one orbit.

    Two pairs get built from these, and both are needed:

      PRE-PRE   (pre2 -> pre1)  both before the event. Baseline coherence for
                                this ground, in this season, with this
                                temporal baseline.
      PRE-POST  (pre1 -> post)  spans the rupture.

    Coherence change is the damage proxy, and it is a DIFFERENCE. Low
    coherence in the co-event pair means nothing on its own -- much of Flores
    decorrelates over 12 days regardless, as four years of this project
    established. What indicates damage is coherence that was high before and
    collapsed across the event. Without the pre-pre pair there is no
    "before" to subtract, and every steep vegetated slope reads as damage.
    """
    import asf_search as asf

    # Search a box, not a point. Three frames on path 112 contain or nearly
    # contain the epicentre, and a point search returns whichever the API
    # happens to order first -- which is how the first submission ended up on
    # frame 1153 by accident rather than by choice. The frame must be named.
    kwargs = dict(
        intersectsWith=("POLYGON((119.5 -9.8, 123.8 -9.8, 123.8 -7.2, "
                        "119.5 -7.2, 119.5 -9.8))"),
        platform=asf.PLATFORM.SENTINEL1,
        processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=asf.BEAMMODE.IW,
        relativeOrbit=path,
        start=EVENT - dt.timedelta(days=days),
        end=EVENT + dt.timedelta(days=days),
    )
    if frame is not None:
        kwargs["frame"] = frame

    results = asf.geo_search(**kwargs)
    scenes = []
    for r in results:
        p = r.properties
        if frame is not None and p.get("frameNumber") != frame:
            continue
        d = dt.datetime.fromisoformat(
            p["startTime"].replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        scenes.append((d, p["sceneName"]))
    scenes.sort()

    pre = [s for s in scenes if s[0] < EVENT]
    post = [s for s in scenes if s[0] >= EVENT]
    return (pre[-2] if len(pre) >= 2 else None,
            pre[-1] if pre else None,
            post[0] if post else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--track", choices=list(TRACKS) + ["all"], default="all")
    ap.add_argument("--frame", type=int, default=None,
                    help="frame number; required to be explicit, since "
                         "several frames on a track contain the epicentre. "
                         "Path 112: 1148 covers all of Flores, 1153 only "
                         "its north coast and the sea beyond.")
    a = ap.parse_args()

    import hyp3_sdk
    hyp3 = hyp3_sdk.HyP3()

    wanted = list(TRACKS) if a.track == "all" else [a.track]
    plan, waiting = [], []

    for key in wanted:
        info = TRACKS[key]
        pre2, pre1, post = find_scenes(info["path"], frame=a.frame)
        label = f"{key} (path {info['path']}"
        label += f", frame {a.frame})" if a.frame else ")"
        # Frame goes in the job name from now on. The first submission omitted
        # it and is frame 1153; leaving that name alone rather than renaming,
        # since HyP3 names are fixed once submitted.
        tag = f"{key}-f{a.frame}" if a.frame else key

        if pre1 is None:
            print(f"{label}: no pre-event scene found — skipping")
            continue

        # PRE-PRE: submittable now, does not wait for the post-event scene.
        if pre2 is not None:
            span = (pre1[0] - pre2[0]).days
            plan.append((f"{PROJECT}-{tag}-prepre-{PARAM_TAG}",
                         [pre2[1], pre1[1]], key, span, "pre-pre"))
            print(f"{label}  pre-pre : {pre2[0]:%Y-%m-%d} -> "
                  f"{pre1[0]:%Y-%m-%d} ({span} d)")
        else:
            print(f"{label}: only one pre-event scene — no baseline pair")

        if post is None:
            waiting.append((label, pre1[0]))
            print(f"{label}  pre-post: waiting for a scene after "
                  f"{pre1[0]:%Y-%m-%d}")
            continue

        span = (post[0] - pre1[0]).days
        plan.append((f"{PROJECT}-{tag}-prepost-{PARAM_TAG}",
                     [pre1[1], post[1]], key, span, "pre-post"))
        print(f"{label}  pre-post: {pre1[0]:%Y-%m-%d} -> "
              f"{post[0]:%Y-%m-%d} ({span} d)  ← spans the rupture")

    if not plan:
        # Exit 0 on purpose: waiting for an acquisition is the expected answer
        # most days, and a non-zero code makes `conda run` report it as an
        # ERROR, which reads as something being broken.
        print("\nnothing ready to submit yet")
        for label, d in waiting:
            print(f"  {label}: waiting for a scene after {d:%Y-%m-%d}")
        return 0

    credits = hyp3.check_credits()
    # 10x2 costs more than the 20x4 used for the interseismic network.
    est = len(plan) * 15
    print(f"\n{len(plan)} job(s) to submit, ~{est} credits, "
          f"{credits} available")
    print(f"parameters: {JOB_PARAMETERS}")

    if not a.submit:
        print("\nplan only — rerun with --submit")
        return 0

    if credits is not None and credits < est:
        raise SystemExit(f"insufficient credits: need ~{est}, have {credits}")

    # Never resubmit a name that already exists: these are hand-named, so the
    # granule-hash protection used elsewhere does not apply here.
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    existing = {j.name for j in hyp3.find_jobs(start=since) if j.name}

    prepared = []
    for name, granules, key, span, kind in plan:
        if name in existing:
            print(f"  {name}: already submitted, skipping")
            continue
        prepared.append({
            "job_type": "INSAR_GAMMA",
            "name": name,
            "job_parameters": {"granules": granules, **JOB_PARAMETERS},
        })

    if not prepared:
        print("all already submitted")
        return 0

    jobs = hyp3.submit_prepared_jobs(prepared)
    for j in jobs:
        print(f"submitted {j.name}  id={j.job_id}  {j.status_code}")
    print(f"\ncredits now: {hyp3.check_credits()}")
    print("\nHyP3 typically takes 20-40 min. Then:")
    print("  python3 scripts/fetch_coseismic.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
