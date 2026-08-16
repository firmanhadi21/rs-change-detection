"""Re-reference both tracks to the SAME ground point, then recompute velocity.

Each track was referenced to its own automatically-chosen pixel, and the two
landed ~178 km apart. InSAR velocity is relative to its reference, so the two
fields were expressed against different ground -- which is why
asc_desc2horz_vert refuses to combine them.

This does NOT change the agreement test: Pearson correlation is invariant to a
constant offset, so r stays where it is. What it fixes is the decomposition,
where the absolute values have to share an origin to mean anything.

The point is chosen inside the overlap of both tracks and required to be
non-zero in every sampled epoch on BOTH tracks, so it is a pixel that actually
carries a measurement rather than a hole that happens to sit in range.

    python3 common_reference.py stack/insar_asc stack/insar_desc
    python3 common_reference.py stack/insar_asc stack/insar_desc --apply
"""

import argparse
import os
import subprocess
import sys

import h5py
import numpy as np

TS_CANDIDATES = ("timeseries_SET_ERA5_demErr.h5", "timeseries_ERA5_demErr.h5",
                 "timeseries_SET_ERA5.h5", "timeseries_ERA5.h5")


def grid(path):
    with h5py.File(path, "r") as f:
        a = f.attrs
        return {k: float(a[k]) for k in ("X_FIRST", "X_STEP",
                                         "Y_FIRST", "Y_STEP")}


def to_rc(g, easting, northing):
    col = int(round((easting - g["X_FIRST"]) / g["X_STEP"]))
    row = int(round((northing - g["Y_FIRST"]) / g["Y_STEP"]))
    return row, col


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("asc_dir", help="e.g. stack/insar_asc or output/insar_geom_asc")
    ap.add_argument("desc_dir")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    TRACKS = (a.asc_dir, a.desc_dir)

    # Both tracks must use the SAME corrected product, or re-referencing lines
    # up two fields that were processed differently.
    paths, ts_name = {}, None
    for cand in TS_CANDIDATES:
        if all(os.path.exists(f"{t}/mintpy/{cand}") for t in TRACKS):
            ts_name = cand
            paths = {t: f"{t}/mintpy/{cand}" for t in TRACKS}
            break
    if not ts_name:
        raise SystemExit(
            "no corrected time series present on BOTH tracks; looked for "
            + ", ".join(TS_CANDIDATES))
    print(f"using {ts_name} on both tracks")

    grids, data, shapes = {}, {}, {}
    for t, p in paths.items():
        grids[t] = grid(p)
        with h5py.File(p, "r") as f:
            d = f["timeseries"]
            shapes[t] = d.shape[1:]
            # A few epochs is enough to tell a real pixel from a hole.
            idx = [d.shape[0] // 4, d.shape[0] // 2, d.shape[0] - 1]
            data[t] = np.stack([d[i] for i in idx])

    # Overlap in map coordinates.
    west = max(g["X_FIRST"] for g in grids.values())
    north = min(g["Y_FIRST"] for g in grids.values())
    east = min(g["X_FIRST"] + s[1] * g["X_STEP"]
               for g, s in zip(grids.values(), shapes.values()))
    south = max(g["Y_FIRST"] + s[0] * g["Y_STEP"]
                for g, s in zip(grids.values(), shapes.values()))
    print(f"overlap: E {west:.0f}..{east:.0f}  N {south:.0f}..{north:.0f}")

    # Search the overlap on a coarse lattice for a pixel valid on both tracks.
    best = None
    step = 400.0   # metres; 5 px at 80 m posting
    e = west + step
    while e < east - step:
        n = south + step
        while n < north - step:
            ok, score = True, 0.0
            for t in TRACKS:
                r, c = to_rc(grids[t], e, n)
                if not (0 <= r < shapes[t][0] and 0 <= c < shapes[t][1]):
                    ok = False
                    break
                v = data[t][:, r, c]
                if not np.all(np.isfinite(v)) or np.any(v == 0):
                    ok = False
                    break
                score += float(np.abs(v).mean())
            if ok and (best is None or score < best[0]):
                # Prefer the quietest valid pixel: a stable reference should
                # not itself be moving.
                best = (score, e, n)
            n += step
        e += step

    if best is None:
        raise SystemExit("no pixel valid on both tracks in the overlap")

    _, e, n = best
    print(f"common reference: E {e:.0f}  N {n:.0f}")
    for t in TRACKS:
        r, c = to_rc(grids[t], e, n)
        print(f"  {t}: row {r}, col {c}  (grid {shapes[t]})")

    if not a.apply:
        print("\ndry run — pass --apply to re-reference and recompute velocity")
        return 0

    for t in TRACKS:
        r, c = to_rc(grids[t], e, n)
        d = f"{t}/mintpy"
        print(f"\n=== {t} ===")
        env = {k: v for k, v in os.environ.items()
               if k not in ("PROJ_LIB", "GDAL_DATA")}
        for cmd in (
            ["reference_point.py", ts_name, "--row", str(r), "--col", str(c)],
            ["timeseries2velocity.py", ts_name, "-o", "velocityERA5.h5"],
        ):
            # Called directly, not via `conda run -n mintpy`: the environment
            # is named differently in OpenScienceLab
            # (opensarlab_mintpy_recipe_book), so hardcoding it fails there.
            # Whichever env is active must already provide these commands.
            try:
                p = subprocess.run(cmd, cwd=d, env=env,
                                   capture_output=True, text=True, timeout=1800)
            except FileNotFoundError:
                raise SystemExit(
                    f"{cmd[0]} is not on PATH — activate the MintPy "
                    f"environment (in OpenScienceLab, switch the kernel) "
                    f"and rerun.")
            tail = [x for x in p.stdout.splitlines() if x.strip()][-2:]
            print(f"  {cmd[0]}: rc={p.returncode}")
            for x in tail:
                print(f"      {x}")
            if p.returncode != 0:
                print(f"      STDERR {p.stderr.splitlines()[-3:]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
