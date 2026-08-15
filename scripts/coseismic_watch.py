"""Wait for the first post-event Sentinel-1 SLC, then run the co-seismic pair.

Written for the Flores M7.7 of 14 August 2026, but parameterised: point it at
any epicentre and date.

WHY A WATCHER. Sentinel-1 repeats every 12 days per track, and the useful run
cannot start a minute before the post-event scene is in the archive. Checking by
hand means either checking too often or missing a day. This polls ASF, and the
moment a scene later than the event appears on a track that also has pre-event
coverage, it runs both products for that track and stops watching it.

WHAT IT RUNS. Displacement first -- the co-seismic fringe pattern is the primary
measurement, and for a shallow M7.7 with land ~50 km away it is decimetres,
far above the noise that spoils a velocity field. Then coherence change, as a
damage proxy, which needs a pre-event pair as well and is the weaker product of
the two over vegetated terrain.

    python3 scripts/coseismic_watch.py --check      # report and exit
    python3 scripts/coseismic_watch.py              # poll until it fires
"""

import argparse
import datetime as dt
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from earthchange.insar import search_slc, tracks  # noqa: E402

# Onshore, on the north coast of Flores nearest the offshore epicentre
# (~-8.30, 121.35). Checked against the national land layer rather than
# eyeballed: -8.45 looked right on a map and is 4 km out to sea, which would
# have produced an empty run. Land begins at -8.56 on this meridian, so the
# centre sits a little inland of it, ~42 km from the epicentre.
DEFAULTS = {
    "lat": -8.68, "lon": 121.35, "radius": 30.0,
    "event": "2026-08-14", "name": "FloresCoseis",
}
POLL_SECONDS = 3600


def post_event_tracks(lat, lon, event):
    """Tracks that have BOTH pre- and post-event scenes, newest post first."""
    ev = dt.date.fromisoformat(event)
    scenes = search_slc(lat, lon,
                        (ev - dt.timedelta(days=90)).isoformat(),
                        (ev + dt.timedelta(days=60)).isoformat())
    ready = []
    for (path, frame, drn), stack in tracks(scenes).items():
        pre = [s for s in stack if dt.date.fromisoformat(s["date"]) <= ev]
        post = [s for s in stack if dt.date.fromisoformat(s["date"]) > ev]
        if pre and post:
            ready.append({"path": path, "frame": frame, "direction": drn,
                          "pre": pre[-1]["date"], "post": post[0]["date"],
                          "n_pre": len(pre)})
    return sorted(ready, key=lambda r: r["post"])


def run(product, cfg, drn, out_root):
    """One earthchange run. Returns True if it produced a result."""
    out = os.path.join(out_root, f"{cfg['name']}_{drn}_{product}")
    os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, "-m", "earthchange.detect", "-s", "insar",
           "--lat", str(cfg["lat"]), "--lon", str(cfg["lon"]),
           "--radius", str(cfg["radius"]), "-n", cfg["name"],
           "--event-date", cfg["event"], "--product", product,
           "--orbit-pass", drn, "--wait", "-o", out]
    print(f"\n>>> {' '.join(cmd[2:])}\n", flush=True)
    r = subprocess.run(cmd)
    ok = os.path.exists(os.path.join(out, "stats.json"))
    print(f"<<< {product} {drn}: {'wrote results' if ok else 'no result'} "
          f"(exit {r.returncode})", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k}", default=v)
    ap.add_argument("--check", action="store_true",
                    help="report what is available and exit")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"))
    a = ap.parse_args()
    cfg = {k: getattr(a, k) for k in DEFAULTS}
    cfg["lat"], cfg["lon"] = float(cfg["lat"]), float(cfg["lon"])

    done = set()
    while True:
        ready = post_event_tracks(cfg["lat"], cfg["lon"], cfg["event"])
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        if not ready:
            print(f"[{stamp}] no post-event SLC yet on any track", flush=True)
        for r in ready:
            drn, tag = r["direction"], f"{r['path']}/{r['frame']}"
            print(f"[{stamp}] path {tag} {drn}: pre {r['pre']} → "
                  f"post {r['post']}  ({r['n_pre']} pre-event scenes)",
                  flush=True)
            if a.check or drn in done:
                continue
            # Displacement needs one pair; coherence needs two pre-event
            # scenes as well, so it is attempted only when they exist.
            run("displacement", cfg, drn, a.out)
            if r["n_pre"] >= 2:
                run("coherence", cfg, drn, a.out)
            else:
                print(f"    skipping coherence: only {r['n_pre']} pre-event "
                      f"scene on this track", flush=True)
            done.add(drn)

        if a.check:
            return
        if len(done) >= 2:
            print("both passes done; watcher exiting", flush=True)
            return
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
