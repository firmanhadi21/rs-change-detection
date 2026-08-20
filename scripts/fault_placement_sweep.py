"""Where must the slip have been, to leave only ~5 cm on the north coast?

Two nodal planes centred on the epicentre both predict tens of centimetres of
UPLIFT on the north coast, while the interferogram shows ~5 cm AWAY from the
satellite. Rather than declare a contradiction, ask the inverse question: over
what fault placements is the observation actually reproduced?

The epicentre is where rupture NUCLEATED. Surface deformation depends on where
slip CONCENTRATED, which can be tens of kilometres away and is what a
finite-fault inversion solves for. Fixing the centroid at the epicentre was my
assumption, not USGS's, and it is the assumption most likely to be wrong.

The geometry that matters is simple. For a south-dipping thrust the surface
trace of the up-dip edge separates hanging wall from footwall:

    up-dip edge NORTH of the coast  -> coast on the HANGING WALL -> uplift
                                       -> motion TOWARD the satellite
    up-dip edge SOUTH of the coast  -> coast on the FOOTWALL    -> subsidence
                                       -> motion AWAY from the satellite

So the sign observed on the coast is a statement about where the rupture sat
relative to it, not only about which nodal plane is the fault. This sweeps
centroid latitude and depth and reports the predicted north-coast LOS for each,
marking placements consistent with the observation.

    conda run -n base python scripts/fault_placement_sweep.py
"""

import argparse
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                    # pragma: no cover
    sys.exit("needs rasterio + okada-wrapper under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradient_zscore import COEVENT, products                  # noqa: E402
from nodal_plane_los import (HYP3_REF, KM_LAT, TARGET,         # noqa: E402
                             EPI_LON, EPI_LAT, FRINGE_CM,
                             okada_surface, los_away)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1148)
    ap.add_argument("--stride", type=int, default=25)
    ap.add_argument("--strike", type=float, default=90.0)
    ap.add_argument("--dip", type=float, default=20.0)
    ap.add_argument("--rake", type=float, default=90.0)
    ap.add_argument("--length", type=float, default=104.0)
    ap.add_argument("--width", type=float, default=48.0)
    ap.add_argument("--slip", type=float, default=3.0)
    ap.add_argument("--incidence", type=float, default=39.0)
    ap.add_argument("--heading", type=float, default=-13.0)
    ap.add_argument("--tol", type=float, default=3.0,
                    help="cm; how close counts as consistent")
    a = ap.parse_args()

    unw = products(a.frame, "unw_phase")
    corr = products(a.frame, "corr")
    if COEVENT not in unw:
        sys.exit("co-event product not on disk")

    with rasterio.open(unw[COEVENT]) as src:
        phi = src.read(1).astype("float64")[::a.stride, ::a.stride]
        tr, crs = src.transform, src.crs
    with rasterio.open(corr[COEVENT]) as src:
        coh = src.read(1)[::a.stride, ::a.stride]

    rows, cols = np.mgrid[0:phi.shape[0], 0:phi.shape[1]]
    xs = tr.c + (cols * a.stride + .5) * tr.a
    ys = tr.f + (rows * a.stride + .5) * tr.e
    lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(phi.shape)
    lat = np.array(lat).reshape(phi.shape)

    ok = np.isfinite(phi) & (phi != 0) & (coh >= 0.3)
    obs = phi * FRINGE_CM / (2 * np.pi)
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dref = np.hypot((lon - HYP3_REF[0]) * kx, (lat - HYP3_REF[1]) * KM_LAT)
    refsel = ok & (dref <= 8.0)
    obs = obs - np.median(obs[refsel])
    tgt = (ok & (lon >= TARGET["lon0"]) & (lon <= TARGET["lon1"])
           & (lat >= TARGET["lat0"]) & (lat <= TARGET["lat1"]))
    obs_med = float(np.median(obs[tgt]))

    print(f"observed north coast: {obs_med:+.2f} cm "
          f"(positive = away from satellite)")
    print(f"plane: strike {a.strike:.0f}, dip {a.dip:.0f}, rake {a.rake:.0f}; "
          f"slip {a.slip:.1f} m over {a.length:.0f}x{a.width:.0f} km")
    print(f"grid {phi.shape}, {int(ok.sum()):,} px, "
          f"consistent = within {a.tol:.0f} cm\n")

    lats = np.arange(-8.05, -8.85, -0.10)
    depths = [10.0, 15.0, 20.0, 30.0, 40.0]
    print("  centroid lat   " + "".join(f"{d:>9.0f} km" for d in depths))
    hits = []
    for clat in lats:
        row = f"  {clat:+8.2f}      "
        for dep in depths:
            E, N, U = okada_surface(lon, lat, EPI_LON, clat, dep,
                                    a.strike, a.dip, a.rake,
                                    a.length, a.width, a.slip)
            mod = los_away(E, N, U, a.incidence, a.heading) * 100.0
            mod = mod - np.median(mod[refsel])
            med = float(np.median(mod[tgt]))
            mark = "*" if abs(med - obs_med) <= a.tol else " "
            row += f"{med:>+9.1f}{mark}"
            if mark == "*":
                hits.append((clat, dep, med))
        print(row)

    print("\n  * = within tolerance of the observation")
    print(f"\n  epicentre latitude {EPI_LAT:+.3f}; north coast ~ -8.45")
    if hits:
        print(f"\n  {len(hits)} placement(s) reproduce the observed sign and "
              f"magnitude:")
        for clat, dep, med in hits[:8]:
            north_of_coast = "north of the coast" if clat > -8.45 \
                else "SOUTH of the coast, i.e. beneath the island"
            print(f"    centroid {clat:+.2f}, {dep:.0f} km  -> {med:+.1f} cm "
                  f"({north_of_coast})")
    else:
        print("\n  NO placement in this sweep reproduces the observation.")
        print("  With uniform slip of this size, a thrust here cannot leave")
        print("  only a few cm on the coast. Either the slip is much smaller")
        print("  or much deeper than assumed, or the observed signal is not")
        print("  predominantly co-seismic.")

    print("\n  Caveat that governs everything above: uniform slip on one")
    print("  rectangle. A real rupture tapers, and a tapered rupture leaves")
    print("  far less at its edges than this predicts. Only the USGS")
    print("  finite-fault distribution settles it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
