"""How much of the LOS signal is horizontal? The vertical map assumes none.

HyP3's vertical displacement product divides LOS by cos(incidence), which is
exact only if the ground moved straight up or straight down. For a thrust
earthquake that assumption is not conservative: slip on a dipping plane drives
the hanging wall UP AND OUTWARD, and the horizontal component is often
comparable to the vertical one. Ascending Sentinel-1 is strongly sensitive to
east-west motion -- for theta ~ 39 deg the east coefficient (-0.61) nearly
matches the vertical one (+0.78) -- so horizontal motion does not merely scale
the answer, it is misread as uplift or subsidence.

Rather than assert that, measure it. The USGS finite-fault model predicts all
three components, so the horizontal share of the LOS signal can be computed
directly, and the error incurred by the vertical assumption quantified in
centimetres.

    conda run -n base python scripts/vertical_assumption_error.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usgs_finite_fault_los import (displacement, patches,      # noqa: E402
                                   los_away, EPI_LON, EPI_LAT, KM_LAT)

TARGET = dict(name="north coast NW", lon0=120.70, lon1=121.45,
              lat0=-8.62, lat1=-8.35)
FFM = ("/private/tmp/claude-501/-Users-firmanhadi-GitHub-rs-change-detection/"
       "002f025e-d8ee-4126-aa65-97d981ababcf/scratchpad/FFM.geojson")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ffm", default=FFM)
    ap.add_argument("--incidence", type=float, default=39.0)
    ap.add_argument("--heading", type=float, default=-13.0)
    ap.add_argument("--n", type=int, default=24, help="grid per side")
    a = ap.parse_args()

    subs = patches(a.ffm)
    lons = np.linspace(TARGET["lon0"], TARGET["lon1"], a.n)
    lats = np.linspace(TARGET["lat0"], TARGET["lat1"], a.n)
    LO, LA = np.meshgrid(lons, lats)

    print(f"USGS finite fault, {len(subs)} patches")
    print(f"sampling {TARGET['name']}: {a.n}x{a.n} points\n")
    E, N, U = displacement(LO, LA, subs)
    E, N, U = E * 100, N * 100, U * 100          # cm

    th, az = np.deg2rad(a.incidence), np.deg2rad(a.heading + 90.0)
    nE, nN, nU = -np.sin(th) * np.sin(az), -np.sin(th) * np.cos(az), np.cos(th)
    print(f"LOS unit vector (ground->satellite): "
          f"E {nE:+.3f}  N {nN:+.3f}  U {nU:+.3f}")

    los = los_away(E, N, U, a.incidence, a.heading)
    vert_part = -(nU * U)
    horz_part = -(nE * E + nN * N)

    print(f"\n=== predicted motion over {TARGET['name']} (cm) ===")
    for nm, v in (("east  ", E), ("north ", N), ("up    ", U)):
        print(f"  {nm} median {np.median(v):+7.2f}   "
              f"p5 {np.percentile(v,5):+7.2f}   p95 {np.percentile(v,95):+7.2f}")

    print(f"\n=== how the LOS signal is composed ===")
    print(f"  vertical contribution   median {np.median(vert_part):+7.2f} cm")
    print(f"  horizontal contribution median {np.median(horz_part):+7.2f} cm")
    print(f"  total LOS               median {np.median(los):+7.2f} cm")
    share = np.abs(horz_part) / np.maximum(
        np.abs(horz_part) + np.abs(vert_part), 1e-9)
    print(f"  horizontal share of |LOS|: median {100*np.median(share):.0f}%, "
          f"p95 {100*np.percentile(share,95):.0f}%")

    # What the vertical product would report, versus the true vertical.
    apparent_vertical = -los / np.cos(th)     # HyP3's assumption
    err = apparent_vertical - U
    print(f"\n=== the vertical assumption, in centimetres ===")
    print(f"  true vertical (model)      median {np.median(U):+7.2f} cm")
    print(f"  'vertical' from LOS/cos(i) median "
          f"{np.median(apparent_vertical):+7.2f} cm")
    print(f"  error                      median {np.median(err):+7.2f} cm, "
          f"p95 |{np.percentile(np.abs(err),95):.2f}| cm")
    if np.median(U) != 0:
        print(f"  ratio apparent/true        "
              f"{np.median(apparent_vertical)/np.median(U):+.2f}x")
    flip = float(np.mean(np.sign(apparent_vertical) != np.sign(U)))
    print(f"  fraction where the SIGN is wrong: {100*flip:.0f}%")

    print("\n=== reading ===")
    print("  A horizontal share near half means the vertical map is roughly")
    print("  as much a map of east-west motion as of uplift. Where the sign")
    print("  itself flips, the product reports subsidence for ground the")
    print("  model says rose, or the reverse -- which no caveat in a caption")
    print("  repairs, because the map still looks like a subsidence map.")
    print("\n  Ascending and descending together decompose LOS into vertical")
    print("  and east-west properly. One geometry cannot, at any incidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
