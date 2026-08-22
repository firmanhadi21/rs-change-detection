"""Do the products we own actually cover the whole of Flores?

The standing note says frame 1148 "covers ALL of Flores", justified by its
latitude range. Latitude is the wrong axis for that claim. Flores runs roughly
340 km east-west and a Sentinel-1 IW frame is about 250 km across, so a single
frame cannot span the island regardless of how much latitude it covers. The
along-track direction is nearly north-south, so it is LONGITUDE that gets cut.

Tested two ways, because each has a blind spot:

  REPORT LOCATIONS. The 452 damage and aid reports span 119.81 to 123.23 and
  are distributed where people live, so they sample the inhabited island well.
  They say nothing about uninhabited ground.

  A LONGITUDE SWEEP of the raster footprints, which is blind to whether the
  ground at a longitude is land or sea but does not depend on where people
  are.

Coverage here means "inside the raster footprint", not "coherent". A pixel can
be covered and still be useless, and on this frame most of it is -- roughly
12% of the DEM area is land and only about 60% of that clears a usable
coherence baseline.

    python3 scripts/island_coverage.py
"""

import argparse
import glob
import json
import os
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
OUT = os.path.join(REPO, "output/coseismic")
REPORTS = os.path.join(REPO, "data/eq_reports.geojson")

PRODUCTS = {
    "asc f1148": "flores-coseismic-2026-asc-f1148-prepost-d2",
    "asc f1153": "flores-coseismic-2026-asc-f1153-prepost",
    "desc61 f620": "flores-coseismic-2026-desc61-f621-prepost-d2",
    "desc163 f620": "flores-coseismic-2026-desc163-f620-prepost-d2",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    a = ap.parse_args()

    import rioxarray  # noqa: F401
    import xarray as xr
    from pyproj import Transformer

    d = json.load(open(REPORTS))
    pts = []
    for f in d["features"]:
        c = (f.get("geometry") or {}).get("coordinates")
        if c:
            pts.append((float(c[0]), float(c[1])))
    lons = np.array([p[0] for p in pts])
    lats = np.array([p[1] for p in pts])
    print(f"{len(pts)} report locations, lon {lons.min():.2f} to "
          f"{lons.max():.2f}, lat {lats.min():.2f} to {lats.max():.2f}")

    inside = {}
    spans = {}
    for label, dirname in PRODUCTS.items():
        hits = glob.glob(os.path.join(OUT, dirname, "*_corr.tif"))
        if not hits:
            print(f"  {label}: product missing")
            continue
        da = xr.open_dataarray(hits[0], engine="rasterio")
        if "band" in da.dims:
            da = da.isel(band=0)
        xs = da[da.dims[-1]].values
        ys = da[da.dims[-2]].values
        fwd = Transformer.from_crs("EPSG:4326", da.rio.crs, always_xy=True)
        inv = Transformer.from_crs(da.rio.crs, "EPSG:4326", always_xy=True)
        x, y = fwd.transform(lons, lats)
        ok = ((x >= xs.min()) & (x <= xs.max())
              & (y >= ys.min()) & (y <= ys.max()))
        inside[label] = ok
        # Footprint corners back in lon/lat. The frame is rotated relative to
        # north, so this is the bounding box of the raster, slightly larger
        # than the imaged swath.
        cx = [xs.min(), xs.max(), xs.min(), xs.max()]
        cy = [ys.min(), ys.min(), ys.max(), ys.max()]
        clon, clat = inv.transform(cx, cy)
        spans[label] = (min(clon), max(clon), min(clat), max(clat))
        print(f"  {label:>13}: {int(ok.sum()):>3}/{len(pts)} reports inside"
              f"   lon {min(clon):.2f}..{max(clon):.2f}"
              f"   lat {min(clat):.2f}..{max(clat):.2f}")

    if not inside:
        sys.exit("no products found")

    asc = np.zeros(len(pts), bool)
    for k in ("asc f1148", "asc f1153"):
        if k in inside:
            asc |= inside[k]
    anyp = np.zeros(len(pts), bool)
    for v in inside.values():
        anyp |= v

    print(f"\n  ascending (1148 + 1153): {int(asc.sum())}/{len(pts)} "
          f"({100*asc.mean():.0f}%)")
    print(f"  any product at all      : {int(anyp.sum())}/{len(pts)} "
          f"({100*anyp.mean():.0f}%)")

    gap = ~anyp
    if gap.any():
        print(f"\n  {int(gap.sum())} report locations covered by NOTHING, "
              f"lon {lons[gap].min():.2f} to {lons[gap].max():.2f}")
    gap_asc = ~asc
    if gap_asc.any():
        print(f"  {int(gap_asc.sum())} not covered by either ascending "
              f"frame, lon {lons[gap_asc].min():.2f} to "
              f"{lons[gap_asc].max():.2f}")

    # Longitude sweep: at each degree of longitude, which products reach it?
    print(f"\n  {'lon':>7}  reports  covered by")
    for lo in np.arange(np.floor(lons.min()), np.ceil(lons.max()) + 0.5, 0.5):
        sel = (lons >= lo) & (lons < lo + 0.5)
        if not sel.any():
            continue
        who = [k for k in inside if inside[k][sel].any()]
        print(f"  {lo:>7.1f}  {int(sel.sum()):>7}  "
              f"{', '.join(who) if who else 'NOTHING'}")

    print("\n  Coverage means inside the raster footprint. It is not the same")
    print("  as usable: about 12% of the scene is land and roughly 60% of")
    print("  that clears a usable coherence baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
