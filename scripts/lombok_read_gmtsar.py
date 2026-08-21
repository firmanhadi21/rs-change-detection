"""Read the GMTSAR Lombok interferogram and report what is actually in it.

The pair 2018132 -> 2018216 is 12 May to 4 August 2018 on ALOS-2 path
ALOS2214327020 / ALOS2226747020, and it brackets the 2018 Lombok sequence --
the M6.4 of 29 July and the M6.9 of 5 August. Processing in this directory
stopped after filtering and geocoding: there is no unwrapped phase and no
displacement product, so what exists is wrapped phase, coherence and amplitude.

GMTSAR writes NetCDF .grd files. The _ll suffix means geocoded to lon/lat;
without it the grid is still in radar coordinates and cannot be put on a map.

ONE FRINGE IS NOT 2.77 cm HERE. That figure is Sentinel-1 C-band. ALOS-2 is
L-band at 0.242452 m, so one 2-pi cycle is 12.12 cm of line-of-sight motion --
four and a half times more displacement per fringe. It is why L-band survives
large earthquakes that alias C-band into noise, and why a fringe count here
must not be converted with a habit carried over from Sentinel-1.

    python3 scripts/lombok_read_gmtsar.py
"""

import argparse
import os
import sys

import numpy as np

try:
    import xarray as xr
except ImportError:                                    # pragma: no cover
    sys.exit("needs xarray: run under `conda run -n base`")

D = os.path.expanduser(
    "~/Teaching/UNDIP/InSAR/EQ/Pair1/intf/2018132_2018216")
WAVELENGTH_M = 0.242452                # from the CEOS leader, validated
FRINGE_CM = WAVELENGTH_M / 2 * 100     # 12.12 cm


def load(name):
    p = os.path.join(D, name)
    if not os.path.exists(p):
        return None
    ds = xr.open_dataarray(p)
    return ds


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    a = ap.parse_args()

    print(f"ALOS-2 L-band: one fringe = {FRINGE_CM:.2f} cm line-of-sight")
    print(f"(Sentinel-1 C-band would be 2.77 cm -- do not carry that over)\n")

    for name in ("phasefilt_mask_ll.grd", "phasefilt_ll.grd",
                 "phase_mask_ll.grd", "corr_ll.grd", "display_amp_ll.grd"):
        da = load(name)
        if da is None:
            print(f"  {name:<26} absent")
            continue
        v = da.values
        finite = np.isfinite(v)
        dims = dict(zip(da.dims, da.shape))
        print(f"  {name:<26} {da.shape}  {100*finite.mean():5.1f}% finite")
        if finite.any():
            print(f"      range {np.nanmin(v):+.3f} .. {np.nanmax(v):+.3f}")

    da = load("phasefilt_mask_ll.grd")
    if da is None:
        sys.exit("\nno geocoded masked phase; nothing to map")

    ycoord = "lat" if "lat" in da.coords else list(da.coords)[0]
    xcoord = "lon" if "lon" in da.coords else list(da.coords)[1]
    lat, lon = da[ycoord].values, da[xcoord].values
    print(f"\nextent  lon {lon.min():.4f} .. {lon.max():.4f}"
          f"   lat {lat.min():.4f} .. {lat.max():.4f}")
    print(f"pixel   {abs(lon[1]-lon[0])*111.32*np.cos(np.deg2rad(lat.mean())):.1f}"
          f" x {abs(lat[1]-lat[0])*110.57:.1f} m")

    corr = load("corr_ll.grd")
    if corr is not None:
        c = corr.values[np.isfinite(corr.values)]
        print(f"\ncoherence  median {np.median(c):.3f}   "
              f"p25 {np.percentile(c,25):.3f}   p75 {np.percentile(c,75):.3f}")
        print(f"           above 0.3: {100*(c>=0.3).mean():.1f}% of finite")

    print("\nLombok for reference: the island spans about -8.9..-8.1 lat,")
    print("115.8..116.7 lon. The M6.9 of 5 Aug 2018 was in the north, near")
    print("-8.28, 116.55.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
