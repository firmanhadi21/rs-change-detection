"""Build the dem.grd GMTSAR needs, with ELLIPSOIDAL heights.

GMTSAR's topo_ra removal expects heights above the WGS84 ELLIPSOID. SRTM and
most public DEMs are orthometric — heights above the EGM96 geoid — and the two
differ by tens of metres. Over Flores the undulation runs about +55 m and
varies across the frame, so handing GMTSAR an orthometric DEM does not shift
the interferogram by a constant that a reference pixel would absorb; it leaves
a smooth, terrain-uncorrelated ramp of exactly the kind a co-seismic search is
trying to detect.

    ellipsoidal = orthometric + geoid undulation

The undulation comes from the EGM96 grid bundled with insardev_pygmtsar
(data/geoid_egm96_icgem.grd), so no extra download and no second opinion about
which geoid model is meant.

Resolution: 3 arcsec (~90 m) by default. Topographic phase error scales with
the perpendicular baseline, and at the ~100 m baselines typical here a 90 m
DEM contributes far less than the atmosphere does. Pass --arcsec 1 if the
baseline turns out large.

    conda run -n base python scripts/make_gmtsar_dem.py \
        --bbox 120.0 -8.9 123.1 -6.3 --out data/dem/flores/dem.grd
"""

import argparse
import io
import json
import os
import sys
import urllib.request

import numpy as np

GEOID = os.path.expanduser(
    "~/GitHub/InSARdev/insardev_pygmtsar/insardev_pygmtsar/data/"
    "geoid_egm96_icgem.grd")


def init_gee():
    import ee
    key = os.path.expanduser("~/.config/earthengine/ee-geodetic.json")
    if os.path.exists(key):
        email = json.load(open(key))["client_email"]
        ee.Initialize(ee.ServiceAccountCredentials(email, key_file=key))
    else:
        ee.Initialize()
    return ee


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bbox", type=float, nargs=4, required=True,
                    metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    ap.add_argument("--arcsec", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--geoid", default=GEOID)
    a = ap.parse_args()

    import subprocess
    ee = init_gee()
    lon0, lat0, lon1, lat1 = a.bbox
    scale = a.arcsec * 30.87           # metres per arcsec at the equator
    aoi = ee.Geometry.Rectangle([lon0, lat0, lon1, lat1])
    print(f"SRTM over lon {lon0}..{lon1}, lat {lat0}..{lat1} "
          f"at {a.arcsec}\" (~{scale:.0f} m)")

    # void_fill: SRTM has holes in steep terrain, and a NaN in the DEM becomes
    # a NaN in topo_ra and then a hole in the interferogram.
    srtm = ee.Image("USGS/SRTMGL1_003").select("elevation")
    srtm = srtm.unmask(0).clip(aoi)
    url = srtm.getDownloadURL({"scale": scale, "region": aoi, "format": "NPY"})
    with urllib.request.urlopen(url, timeout=600) as r:
        buf = io.BytesIO(r.read())
    ortho = np.load(buf, allow_pickle=True)["elevation"].astype(np.float32)
    ny, nx = ortho.shape
    print(f"  grid {ny} x {nx}, {ortho.min():.0f}..{ortho.max():.0f} m "
          f"orthometric")

    if not os.path.exists(a.geoid):
        sys.exit(f"geoid grid not found: {a.geoid}\n"
                 "Without it the DEM would be orthometric, which GMTSAR does "
                 "not want. Point --geoid at an EGM96 grid.")

    # The grid work goes through GMT rather than xarray. Partly because this
    # environment's xarray cannot open GMT's classic netCDF at all, but mainly
    # because it is the same path GMTSAR itself uses -- the Lombok dem.grd in
    # this project records "grdmath dem_ortho.grd egm96.grd ADD = dem.grd" in
    # its own history. Matching that removes a whole class of doubt about
    # registration and axis order.
    out = os.path.abspath(a.out)
    d = os.path.dirname(out)
    os.makedirs(d, exist_ok=True)
    ortho_bin = os.path.join(d, "_srtm_ortho.f32")
    ortho_grd = os.path.join(d, "dem_ortho.grd")
    egm_grd = os.path.join(d, "egm96_on_dem.grd")

    # getDownloadURL returns the region top-down, left-to-right, which is
    # exactly xyz2grd's -ZTLf.
    ortho.astype("<f4").tofile(ortho_bin)
    inc = f"{a.arcsec}s"
    region = f"{lon0}/{lon1}/{lat0}/{lat1}"

    def gmt(*args):
        r = subprocess.run(["gmt", *args], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"gmt {' '.join(args[:2])} failed:\n{r.stderr[:400]}")
        return r.stdout

    gmt("xyz2grd", ortho_bin, "-ZTLf", f"-R{region}", f"-I{nx}+n/{ny}+n",
        f"-G{ortho_grd}")
    # Resample the geoid ONTO the DEM grid so grdmath has matching nodes;
    # adding grids of different registration silently interpolates or fails.
    gmt("grdsample", a.geoid, f"-R{ortho_grd}", f"-G{egm_grd}")
    gmt("grdmath", ortho_grd, egm_grd, "ADD", "=", out)
    os.remove(ortho_bin)

    info = gmt("grdinfo", out)
    print(f"\nwrote {out}  ({os.path.getsize(out)/1e6:.1f} MB)")
    for line in info.splitlines():
        if any(k in line for k in ("x_min", "y_min", "v_min", "registration")):
            print("  " + line.split(": ", 1)[-1].strip())
    print(f"  intermediates kept for inspection: "
          f"{os.path.basename(ortho_grd)}, {os.path.basename(egm_grd)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
