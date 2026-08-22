"""Does the descending path-61 pair cover the ground that actually moved?

This is the check that was skipped once already in this investigation, at a
cost of three 7.6 GB downloads: a frame was chosen because it contained the
EPICENTRE, which is offshore, and it turned out to hold almost no land within
20 km. "Intersects a ring around the epicentre" is not the same test as
"covers the coast where the ascending chains measured displacement".

The ascending result puts the signal in the 20-40 km ring, on land, decaying
to zero by ~50 km. So the question is what fraction of the LAND in that ring
falls inside the intersection of the two path-61 footprints -- intersection,
because an interferogram only exists where both scenes do.

    python3 scripts/desc61_footprint_check.py
"""

import argparse
import csv
import io
import math
import os
import sys
import urllib.parse
import urllib.request


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.daac.asf.alaska.edu/services/search/param"
EPI_LON, EPI_LAT = 121.3517, -8.3101
REF_DATE = "2026-08-02"          # S1D, last pre-event path-61 acquisition
SEC_DATE = "2026-08-20"          # S1C, first post-event path-61 acquisition
PATH_NO = "61"
DEM = os.path.expanduser(
    _REPO_ROOT + "/data/insardev_flores/dem.nc")


def fetch(**q):
    q.setdefault("output", "csv")
    url = f"{API}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "earthchange"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return list(csv.DictReader(io.StringIO(
            r.read().decode("utf-8", "replace"))))


def poly_of(row):
    from shapely.geometry import Polygon
    pts = [(float(row["Near Start Lon"]), float(row["Near Start Lat"])),
           (float(row["Far Start Lon"]), float(row["Far Start Lat"])),
           (float(row["Far End Lon"]), float(row["Far End Lat"])),
           (float(row["Near End Lon"]), float(row["Near End Lat"]))]
    return Polygon(pts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inner", type=float, default=20.0)
    ap.add_argument("--outer", type=float, default=40.0)
    ap.add_argument("--path", default=PATH_NO)
    ap.add_argument("--ref-date", default=REF_DATE)
    ap.add_argument("--sec-date", default=SEC_DATE,
                    help="for a path whose post-event scene has not mirrored "
                         "yet, pass a second PRE-event date: the footprint of "
                         "a repeat pass is the same, so the coverage answer "
                         "carries over")
    a = ap.parse_args()

    import numpy as np
    import xarray as xr
    from shapely.geometry import Point

    rows = fetch(platform="Sentinel-1", processingLevel="SLC", beamMode="IW",
                 relativeOrbit=a.path, flightDirection="DESCENDING",
                 start="2026-07-25T00:00:00Z", end="2026-08-23T23:59:59Z")
    # Path 61 covers this area with two frames on each date, and the frame
    # numbering shifts between the two acquisitions (621 pre, 620 post). So
    # rather than guess which granules pair up, evaluate every pre/post
    # combination and report the best -- the choice of frame is exactly what
    # went wrong the first time.
    ref = [r for r in rows if r["Start Time"].startswith(a.ref_date)]
    sec = [r for r in rows if r["Start Time"].startswith(a.sec_date)]
    if not ref or not sec:
        sys.exit(f"missing granule: ref={len(ref)} sec={len(sec)}")
    print(f"{len(ref)} scenes on {a.ref_date}, {len(sec)} on {a.sec_date}")

    # The land test. DEM finite and above sea level is the land proxy; it is
    # the same DEM the ascending chain used, so the two are comparable.
    if not os.path.exists(DEM):
        sys.exit(f"no DEM at {DEM} -- cannot test land coverage")
    dem = xr.open_dataarray(DEM)
    lon = dem[dem.dims[-1]].values
    lat = dem[dem.dims[-2]].values
    step = max(1, int(round(0.002 / abs(lon[1] - lon[0]))))   # ~200 m grid
    lon, lat = lon[::step], lat[::step]
    v = dem.values[::step, ::step]

    dlat = (lat[:, None] - EPI_LAT) * 111.32
    dlon = (lon[None, :] - EPI_LON) * 111.32 * math.cos(math.radians(EPI_LAT))
    R = np.hypot(dlon, dlat)

    land = np.isfinite(v) & (v > 0)
    ring = land & (R >= a.inner) & (R < a.outer)
    n_ring = int(ring.sum())
    print(f"\nland pixels in the {a.inner:.0f}-{a.outer:.0f} km ring: "
          f"{n_ring:,}")
    if n_ring == 0:
        sys.exit("no land in the ring -- check the DEM extent")

    iy, ix = np.nonzero(ring)
    pts = [Point(lon[x], lat[y]) for y, x in zip(iy, ix)]

    print(f"\n  {'reference':>12}{'secondary':>12}{'overlap%':>10}"
          f"{'epicentre':>11}{'ring land%':>12}")
    best = (None, -1.0)
    for r in ref:
        for s in sec:
            both = poly_of(r).intersection(poly_of(s))
            if both.is_empty:
                continue
            inside = sum(both.contains(p) for p in pts)
            pct = 100.0 * inside / n_ring
            print(f"  {r['Frame Number']:>12}{s['Frame Number']:>12}"
                  f"{100*both.area/poly_of(r).area:>9.0f}%"
                  f"{str(both.contains(Point(EPI_LON, EPI_LAT))):>11}"
                  f"{pct:>11.1f}%")
            if pct > best[1]:
                best = ((r, s, both), pct)

    if best[0] is None:
        sys.exit("no pre/post combination overlaps at all")
    r, s, both = best[0]
    pct = best[1]
    print(f"\nbest pair: {r['Granule Name']}")
    print(f"        -> {s['Granule Name']}")
    print()
    if pct >= 60:
        print(f"  {pct:.0f}% of the deforming ground is covered. This pair can")
        print("  answer the same question the ascending chains answered.")
    elif pct >= 25:
        print(f"  Only {pct:.0f}% of the deforming ground is covered. Usable,")
        print("  but the near-field profile will be partial -- decide whether")
        print("  a partial independent look is worth the credits.")
    else:
        print(f"  Just {pct:.0f}% coverage. This is the frame-1153 mistake")
        print("  again: it reaches the epicentre without holding the ground")
        print("  that moved. Not worth submitting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
