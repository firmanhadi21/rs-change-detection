"""ERA5 tropospheric correction on the frame-1148 co-seismic interferogram.

The frame-1148 result rests on two claims that my own tests could only weakly
support, and this addresses one of them properly.

WHAT THE ELEVATION TEST CANNOT DO. Regressing phase on height (R^2 = 0.065
here, against 0.81 on Lombok where the answer WAS atmosphere) detects only the
STRATIFIED component of tropospheric delay -- the part that is a function of
elevation. It is blind to turbulent and horizontally varying water vapour,
which over a tropical coast in the wet season is not a small residual. A low
R^2 rules out the Lombok failure mode; it does not rule out atmosphere.

ERA5 does. It is a weather reanalysis, so it carries the horizontal structure
of the water vapour field on the two acquisition days, not just its vertical
profile. PyAPS integrates it along the slant path.

    delay(t) = integral of refractivity along the line of sight
    correction = delay(2026-08-18) - delay(2026-08-06)

and the interferometric phase already IS a difference, so the differential
delay is what has to come off.

Acquisition is 10:16 UTC, so ERA5 hour 10 -- 16 minutes, against a model with
hourly output. Incidence comes from the HyP3 product for the same frame rather
than being assumed constant: it runs 30 to 46 degrees across an IW swath, and
1/cos(inc) varies by 20% over that, which is larger than the signal being
argued about.

    conda run -n mintpy python scripts/flores_1148_era5.py
"""

import argparse
import os
import subprocess
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
REPO = _DATA_ROOT          # alias used only for data/ and output/
MERGE = os.path.join(REPO, "data/flores_gmtsar_1148/merge")
DEM = os.path.join(REPO, "data/dem/flores/dem_1148.grd")
HYP3 = os.path.join(REPO, "output/coseismic",
                    "flores-coseismic-2026-asc-f1148-prepost-d2")
INC = os.path.join(REPO, "data/dem/flores/inc_1148_ll.tif")
GRIB = os.path.join(REPO, "data/era5")
OUT = os.path.join(REPO, "output/coseismic/flores_1148_era5.png")
EPI = (121.3517, -8.3101)
KM_LAT = 110.57
DATES = ["20260806", "20260818"]
HOUR = "10"


def load_grd(path):
    info = subprocess.run(["gmt", "grdinfo", "-C", path],
                          capture_output=True, text=True)
    if info.returncode != 0:
        return None, None, None
    f = info.stdout.split()
    x0, y0 = float(f[1]), float(f[3])
    dx, dy = float(f[7]), float(f[8])
    nx, ny = int(f[9]), int(f[10])
    raw = subprocess.run(["gmt", "grd2xyz", path, "-ZTLf"],
                         capture_output=True)
    arr = np.frombuffer(raw.stdout, dtype="<f4").astype(np.float32)
    arr = arr.reshape(ny, nx)[::-1]
    lon = x0 + dx * np.arange(nx)
    lat = y0 + dy * np.arange(ny)
    if lon.max() < 0:
        lon = lon + 360.0
    return arr, lat, lon


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.2)
    ap.add_argument("--decimate", type=int, default=4,
                    help="ERA5 is ~31 km; the delay field has no structure "
                         "below that, so computing it at full 40 m resolution "
                         "wastes an hour to interpolate smoothness")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import pyaps3 as pa

    los, lat, lon = load_grd(os.path.join(MERGE, "los_ll.grd"))
    coh, clat, clon = load_grd(os.path.join(MERGE, "corr_ll.grd"))
    dem, dlat, dlon = load_grd(DEM)
    if los is None:
        sys.exit("no los_ll.grd")

    d = a.decimate
    los = los[::d, ::d]
    lat_s, lon_s = lat[::d], lon[::d]

    def match(arr, alat, alon):
        iy = np.clip(np.searchsorted(alat, lat_s), 1, len(alat) - 1) - 1
        ix = np.clip(np.searchsorted(alon, lon_s), 1, len(alon) - 1) - 1
        return arr[np.ix_(iy, ix)]

    C = match(coh, clat, clon)
    Z = match(dem, dlat, dlon).astype(np.float32)
    LON, LAT = np.meshgrid(lon_s.astype(np.float32),
                           lat_s.astype(np.float32))
    print(f"grid {los.shape} (decimated {d}x), "
          f"lon {lon_s.min():.2f}..{lon_s.max():.2f}, "
          f"lat {lat_s.min():.2f}..{lat_s.max():.2f}")

    # --- incidence, from the HyP3 product for the same frame --------------
    # Read through GMT rather than rasterio: the mintpy environment has no
    # rasterio, and GMT reads GeoTIFF through GDAL anyway. Reproject once with
    #   gdalwarp -t_srs EPSG:4326 -r bilinear <hyp3>_inc_map.tif inc_1148_ll.tif
    if not os.path.exists(INC):
        sys.exit(f"no {INC}\nMake it with:\n  gdalwarp -t_srs EPSG:4326 "
                 f"-r bilinear -dstnodata 0 \\\n    "
                 f"{HYP3}/*_inc_map.tif {INC}")
    inc_a, ilat, ilon = load_grd(INC)
    inc = np.degrees(match(inc_a, ilat, ilon).astype(np.float32))

    # VALIDATE AGAINST PHYSICS, NOT AGAINST ZERO. The HyP3 incidence map
    # itself contains values from 0.03 to 107.6 degrees -- edge artefacts in
    # about 5% of its pixels. This is NOT a resampling problem: nearest
    # neighbour gives the same range as bilinear, so the bad values are in the
    # source product. A guard of "inc > 0.1 rad" catches the exact zeros and
    # lets everything else through.
    #
    # The values above 90 are the dangerous ones. cos(107.6) is NEGATIVE, so
    # those pixels would have the slant delay divided by a negative number --
    # flipping the correction's sign across part of the scene rather than
    # merely weakening it, which adds the error twice instead of removing it.
    #
    # Sentinel-1 IW spans 29-47 degrees end to end. Anything outside that is
    # not a marginal measurement, and is replaced by the median of the pixels
    # that are physically possible.
    IW_MIN, IW_MAX = 25.0, 50.0
    good_inc = np.isfinite(inc) & (inc > IW_MIN) & (inc < IW_MAX)
    frac = good_inc.mean()
    if frac < 0.2:
        sys.exit(f"only {100*frac:.1f}% of the incidence map is within "
                 f"{IW_MIN}-{IW_MAX} deg — check the reprojection")
    inc[~good_inc] = np.median(inc[good_inc])
    print(f"incidence: {100*frac:.1f}% physically plausible, "
          f"{100*(1-frac):.1f}% replaced by the median")

    # --- ERA5 --------------------------------------------------------------
    os.makedirs(GRIB, exist_ok=True)
    snwe = (int(np.floor(lat_s.min())) - 1, int(np.ceil(lat_s.max())) + 1,
            int(np.floor(lon_s.min())) - 1, int(np.ceil(lon_s.max())) + 1)
    print(f"\ndownloading ERA5 for {DATES} at {HOUR}:00 UTC, snwe={snwe}")
    try:
        flist = pa.ECMWFdload(DATES, HOUR, GRIB, model="ERA5",
                              snwe=snwe, humidity="Q")
    except Exception as exc:                              # noqa: BLE001
        print(f"\nERA5 download failed: {exc.__class__.__name__}: {exc}")
        print("\nERA5 has about five days of latency, so 2026-08-18 may not")
        print("be published yet. This is a delay, not a dead end -- rerun in")
        print("a few days. Nothing about the interferogram changes meanwhile.")
        return 1
    print(f"  got {len(flist)} grib files")

    delays = []
    for f in flist:
        print(f"  computing delay: {os.path.basename(f)}")
        obj = pa.PyAPS(f, grib="ERA5", Del="comb", dem=Z, inc=inc,
                       lat=LAT, lon=LON, verb=False)
        pha = np.zeros((obj.ny, obj.nx), dtype=np.float32)
        obj.getdelay(pha)          # default wvl=4pi -> METRES of slant delay
        delays.append(pha)

    # Differential: later minus earlier, matching the interferogram's own
    # convention. Getting this backwards flips the correction's sign and would
    # double the apparent signal instead of removing anything.
    dd = (delays[1] - delays[0]) * 1000.0        # mm
    print(f"\ndifferential ERA5 delay: {np.nanmin(dd):+.1f} .. "
          f"{np.nanmax(dd):+.1f} mm, std {np.nanstd(dd):.1f} mm")

    good = np.isfinite(los) & (C >= a.min_coh) & np.isfinite(dd)
    v_raw = los[good] / 10.0                     # cm
    v_cor = (los[good] - dd[good]) / 10.0
    print(f"{int(good.sum()):,} coherent pixels")
    print(f"  scatter {v_raw.std():.2f} -> {v_cor.std():.2f} cm after ERA5")

    kx = 111.32 * np.cos(np.deg2rad(EPI[1]))
    R = np.hypot((LAT - EPI[1]) * KM_LAT, (LON - EPI[0]) * kx)[good]
    edges = [20, 30, 40, 50, 65, 80, 100, 150]
    print(f"\n  radial profile about the epicentre (cm, median)")
    print(f"    {'ring':<14}{'n':>9}{'raw':>9}{'ERA5-corrected':>17}")
    prof = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = (R >= lo) & (R < hi)
        if s.sum() < 500:
            print(f"    {lo:>3}-{hi:<10}{int(s.sum()):>9}   -- too few --")
            continue
        m0, m1 = float(np.median(v_raw[s])), float(np.median(v_cor[s]))
        prof.append((lo, hi, int(s.sum()), m0, m1))
        print(f"    {lo:>3}-{hi:<6} km {int(s.sum()):>9}{m0:>9.2f}"
              f"{m1:>17.2f}")

    if prof:
        sw0 = max(p[3] for p in prof) - min(p[3] for p in prof)
        sw1 = max(p[4] for p in prof) - min(p[4] for p in prof)
        print(f"\n  radial swing: {sw0:.2f} cm raw -> {sw1:.2f} cm corrected")
        print()
        if sw1 < 0.4 * sw0:
            print("  ERA5 removes most of the radial signal: it was largely")
            print("  atmospheric, and the elevation test missed it because the")
            print("  delay was horizontally structured rather than stratified.")
        elif sw1 > 0.8 * sw0:
            print("  The radial signal SURVIVES the ERA5 correction almost")
            print("  intact. Combined with the elevation test, atmosphere is")
            print("  now a poor explanation for it.")
        else:
            print("  ERA5 removes part of it. The signal is real but its")
            print("  amplitude is less certain than the raw profile suggests.")

    np.save(os.path.join(REPO, "output/coseismic/era5_diff_delay_mm.npy"), dd)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ext = [lon_s.min(), lon_s.max(), lat_s.min(), lat_s.max()]
    full = [np.where(good, los / 10.0, np.nan),
            np.where(good, dd / 10.0, np.nan),
            np.where(good, (los - dd) / 10.0, np.nan)]
    lim = np.nanpercentile(np.abs(full[0]), 98)
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.0))
    for axi, arr, ttl in zip(ax, full, (
            "LOS as processed (cm)",
            "ERA5 differential delay (cm)\n18 Aug minus 6 Aug",
            "LOS after ERA5 correction (cm)")):
        im = axi.imshow(arr, extent=ext, origin="lower", cmap="RdBu_r",
                        vmin=-lim, vmax=lim, interpolation="nearest")
        axi.plot(*EPI, "*", ms=16, mfc="#ffdd00", mec="black", mew=1.0,
                 zorder=5)
        for rk in (20, 30, 50):
            th = np.linspace(0, 2 * np.pi, 200)
            axi.plot(EPI[0] + rk / kx * np.cos(th),
                     EPI[1] + rk / KM_LAT * np.sin(th), "-", lw=.7,
                     color="#333", alpha=.6, zorder=4)
        axi.set_title(ttl, fontsize=10.5, loc="left")
        axi.set_xlabel("lon")
        fig.colorbar(im, ax=axi, shrink=.8, pad=.02, label="cm")
    ax[0].set_ylabel("lat")
    fig.suptitle("Flores frame 1148 — ERA5 tropospheric correction "
                 "(PyAPS, via MintPy's machinery)", fontsize=12.5, y=.98)
    fig.tight_layout(rect=[0, 0, 1, .92])
    fig.savefig(a.out, dpi=125)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
