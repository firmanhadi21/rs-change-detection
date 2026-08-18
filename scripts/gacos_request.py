"""Assemble everything the GACOS web form needs for this frame.

GACOS (http://www.gacos.net) is a higher-resolution tropospheric correction
than ERA5, and it is the lever most likely to matter here: the Flores result is
atmosphere-limited, and ERA5's ~30 km grid cannot resolve convection over a
narrow volcanic island. The LiCSAR portal does not publish GACOS for frame
112A_09831_050508, so it must be requested by hand.

The form wants a bounding box, an acquisition time, and a date list. All three
are already on disk after LiCSBAS step 02 -- reading them beats reading them
off a web page and mistyping one.

    python3 scripts/gacos_request.py
"""

import glob
import os
import re
import sys

TS = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/licsbas/TS_GEOCml10/info")
GEOC = os.path.expanduser("~/GitHub/rs-change-detection/output/licsbas/GEOC")


def read_par(path):
    par = {}
    if not os.path.exists(path):
        return par
    for line in open(path, errors="ignore"):
        if ":" in line:
            k, _, v = line.partition(":")
            par[k.strip()] = v.strip()
    return par


def main():
    dem = read_par(f"{TS}/EQA.dem_par")
    mli = read_par(f"{TS}/slc.mli.par")
    if not dem:
        raise SystemExit(f"{TS}/EQA.dem_par not found — run LiCSBAS step 02 first")

    # Corner is the NW pixel; the box extends south and east from it.
    lat0 = float(dem["corner_lat"].split()[0])
    lon0 = float(dem["corner_lon"].split()[0])
    dlat = float(dem["post_lat"].split()[0])
    dlon = float(dem["post_lon"].split()[0])
    nlat = int(dem["nlines"].split()[0])
    nlon = int(dem["width"].split()[0])

    north, west = lat0, lon0
    south = lat0 + dlat * nlat          # post_lat is negative
    east = lon0 + dlon * nlon

    print("=== GACOS request for frame 112A_09831_050508 ===\n")
    print("Area of interest (decimal degrees):")
    print(f"  North  {north:9.4f}")
    print(f"  South  {south:9.4f}")
    print(f"  West   {west:9.4f}")
    print(f"  East   {east:9.4f}")
    print(f"  ({nlon} x {nlat} px at {abs(dlon):.6f} deg)")

    # GACOS needs the acquisition time of day, not the date.
    # GAMMA writes center_time as seconds-of-day; LiCSBAS's slc.mli.par carries
    # it already formatted as HH:MM:SS. Accept either rather than assume.
    t = mli.get("center_time", "").split()[0] if mli.get("center_time") else ""
    if ":" in t:
        h, m, s = (t.split(":") + ["0", "0"])[:3]
        h, m, s = int(h), int(m), float(s)
    elif t:
        secs = float(t)
        h, m, s = int(secs // 3600), int((secs % 3600) // 60), secs % 60
    else:
        h = None

    if h is None:
        print("\nAcquisition time: not found in slc.mli.par")
    else:
        print(f"\nAcquisition time (UTC): {h:02d}:{m:02d}:{s:04.1f}")
        print(f"  form usually wants  {h:02d}:{m:02d}")

    # Every epoch present, which is what GACOS corrects -- one file per date.
    dates = set()
    for d in glob.glob(f"{GEOC}/*"):
        m = re.match(r"(\d{8})_(\d{8})$", os.path.basename(d))
        if m:
            dates.update(m.groups())
    dates = sorted(dates)
    print(f"\nEpochs needing correction: {len(dates)}")
    if dates:
        print(f"  range {dates[0]} -> {dates[-1]}")

    out = os.path.join(os.path.dirname(GEOC), "gacos_dates.txt")
    with open(out, "w") as f:
        f.write("\n".join(dates) + "\n")
    print(f"  written to {out}")

    print("\n--- what to do ---")
    print("1. http://www.gacos.net  -> fill the form with the box and time above")
    print("2. Paste the date list (or give the range; GACOS accepts either)")
    print("3. They email a tar.gz, usually within hours")
    print(f"4. Extract it into {os.path.dirname(GEOC)}/GACOS/")
    print("5. Then, with the LiCSBAS env active:")
    print("     LiCSBAS03op_GACOS.py -i GEOCml10 -o GEOCml10GACOS "
          "-t TS_GEOCml10 -g GACOS")
    print("     LiCSBAS11_check_unw.py -d GEOCml10GACOS -t TS_GEOCml10GACOS")
    print("     ... then 12, 13, 14, 15, 16 on GEOCml10GACOS")
    print("\nRunning both chains side by side is the point: GACOS-corrected")
    print("against uncorrected, on identical interferograms, isolates how much")
    print("of the disagreement is atmospheric.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
