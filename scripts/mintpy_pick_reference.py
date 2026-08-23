"""Choose a MintPy reference point from the data, not off the footprint.

A reference point is subtracted from every epoch, so whatever it does is
imposed on the whole time series with the opposite sign. Two requirements
pull against each other:

  FAR from the epicentre, or the co-seismic field is zeroed at exactly the
  place being measured -- the reference absorbs the signal and the map shows
  the deformation relative to deformed ground.

  COHERENT and inside maskConnComp, or its own noise is injected into every
  epoch. My first attempt picked -8.25, 122.60 by eye off the frame footprint
  and smallbaselineApp refused it: "input reference point is in masked OUT
  area". Choosing a point on a map is choosing it without evidence.

So: search the actual mask and the actual average coherence, take the most
coherent pixel beyond a distance floor, and report what it is before using it.

    conda run -n mintpy python scripts/mintpy_pick_reference.py
"""

import argparse
import os
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# data/ and output/ are ~63 GB each and live on the external SSD; the internal
# disk has run to 12 GiB free. Resolved at runtime so an unmounted volume
# falls back to this checkout instead of failing.
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
WORK = os.path.expanduser(_DATA_ROOT + "/data/mintpy_flores")
EPI = (121.3517, -8.3101)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--min-km", type=float, default=90.0,
                    help="minimum distance from the epicentre. The co-seismic "
                         "field decayed to zero by ~50 km in the GMTSAR "
                         "result, so 90 km is comfortably outside it")
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()

    from mintpy.utils import readfile
    from pyproj import Transformer

    coh, atr = readfile.read(os.path.join(a.work, "avgSpatialCoh.h5"))
    mask, _ = readfile.read(os.path.join(a.work, "maskConnComp.h5"))
    try:
        water, _ = readfile.read(os.path.join(a.work, "waterMask.h5"))
    except Exception:                                     # noqa: BLE001
        water = np.ones_like(mask)

    x0 = float(atr["X_FIRST"]); y0 = float(atr["Y_FIRST"])
    dx = float(atr["X_STEP"]); dy = float(atr["Y_STEP"])
    ny, nx = coh.shape
    epsg = atr.get("EPSG", "32751")
    print(f"grid {ny}x{nx}, EPSG:{epsg}, origin ({x0:.0f}, {y0:.0f}), "
          f"step {dx:.0f}")

    fwd = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    inv = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    ex, ey = fwd.transform(*EPI)
    X = x0 + dx * np.arange(nx)
    Y = y0 + dy * np.arange(ny)
    R = np.hypot(X[None, :] - ex, Y[:, None] - ey) / 1000.0

    ok = (mask > 0) & (water > 0) & np.isfinite(coh) & (R >= a.min_km)
    print(f"\ncandidates: {int(ok.sum()):,} pixels beyond {a.min_km:.0f} km, "
          f"in maskConnComp, on land")
    if not ok.any():
        sys.exit("no candidate -- relax --min-km")

    # Prefer a pixel whose NEIGHBOURHOOD is coherent, not a lone bright one:
    # a single good pixel surrounded by noise is a bad reference, because any
    # small misregistration lands you on its neighbours.
    from scipy.ndimage import uniform_filter
    local = uniform_filter(np.where(np.isfinite(coh), coh, 0), size=9)
    score = np.where(ok, local, -1)

    flat = np.argsort(score.ravel())[::-1][:a.top]
    print(f"\n  {'coh(9x9)':>9}{'coh':>7}{'dist km':>9}"
          f"{'lat':>10}{'lon':>10}")
    best = None
    for f in flat:
        iy, ix = np.unravel_index(f, coh.shape)
        lon, lat = inv.transform(X[ix], Y[iy])
        print(f"  {local[iy, ix]:>9.3f}{coh[iy, ix]:>7.3f}{R[iy, ix]:>9.0f}"
              f"{lat:>10.4f}{lon:>10.4f}")
        if best is None:
            best = (lat, lon, iy, ix, local[iy, ix], R[iy, ix])

    lat, lon, iy, ix, sc, dist = best
    print(f"\n  chosen: {lat:.4f}, {lon:.4f}  "
          f"(row {iy}, col {ix}, 9x9 coherence {sc:.3f}, {dist:.0f} km out)")
    print(f"\n  set in the template:")
    print(f"    mintpy.reference.lalo = {lat:.4f}, {lon:.4f}")
    print(f"  or by pixel, which cannot be misread by a projection:")
    print(f"    mintpy.reference.yx   = {iy}, {ix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
