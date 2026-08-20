"""Which IW subswath and bursts cover Flores, in these SLC zips?

A Sentinel-1 IW scene holds three subswaths of nine or ten bursts each. Running
the interferogram over all of them takes hours and produces mostly sea. Reading
the annotation XML inside the zip costs seconds and narrows it to the few
bursts that matter -- and TOPSAR-Split takes exactly those numbers.

No extraction: the annotation files are read straight out of the zip, so this
touches none of the 7 GB.

    python3 scripts/snap_find_burst.py ~/Downloads/S1D_*.zip
"""

import argparse
import glob
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

# Flores, and the epicentre it must contain.
AOI = {"west": 120.4, "east": 123.0, "south": -8.95, "north": -8.15}
EPI = (-8.3101, 121.3517)


def burst_footprints(zf, name):
    """Approximate lat/lon span of each burst, from the geolocation grid."""
    with zf.open(name) as f:
        root = ET.parse(f).getroot()

    swath = root.findtext(".//adsHeader/swath")
    lines_per_burst = int(root.findtext(".//linesPerBurst"))

    pts = []
    for p in root.findall(".//geolocationGridPointList/geolocationGridPoint"):
        pts.append((int(p.findtext("line")),
                    float(p.findtext("latitude")),
                    float(p.findtext("longitude"))))
    if not pts:
        return swath, []

    n_bursts = len(root.findall(".//burstList/burst"))
    out = []
    for b in range(n_bursts):
        lo, hi = b * lines_per_burst, (b + 1) * lines_per_burst
        sel = [(la, lo_) for ln, la, lo_ in pts if lo <= ln <= hi]
        if not sel:
            continue
        lats = [s[0] for s in sel]
        lons = [s[1] for s in sel]
        out.append((b + 1, min(lats), max(lats), min(lons), max(lons)))
    return swath, out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zips", nargs="+")
    a = ap.parse_args()

    paths = []
    for pat in a.zips:
        paths.extend(sorted(set(glob.glob(os.path.expanduser(pat)))))
    if not paths:
        raise SystemExit("no zips matched")

    for zp in paths:
        print(f"\n=== {os.path.basename(zp)[:62]} ===")
        with zipfile.ZipFile(zp) as zf:
            # Product annotations only. calibration-*.xml and noise-*.xml sit
            # in the same directory and also contain "-vv-", so filtering on
            # polarisation alone picks them up -- and they carry no
            # linesPerBurst, which is what made the first attempt fail.
            anns = [n for n in zf.namelist()
                    if "/annotation/" in n and n.endswith(".xml")
                    and os.path.basename(n).startswith("s1")
                    and "-vv-" in os.path.basename(n).lower()]
            if not anns:
                print("  no VV annotation found")
                continue

            for ann in sorted(anns):
                swath, bursts = burst_footprints(zf, ann)
                hits = [b for b in bursts
                        if not (b[2] < AOI["south"] or b[1] > AOI["north"]
                                or b[4] < AOI["west"] or b[3] > AOI["east"])]
                epi = [b for b in bursts
                       if b[1] <= EPI[0] <= b[2] and b[3] <= EPI[1] <= b[4]]
                if not hits:
                    print(f"  {swath}: {len(bursts)} bursts, none over Flores")
                    continue
                first, last = hits[0][0], hits[-1][0]
                print(f"  {swath}: bursts {first}-{last} of {len(bursts)} "
                      f"cover the AOI"
                      + (f"   <- epicentre in burst {epi[0][0]}" if epi else ""))
                for b in hits:
                    print(f"      burst {b[0]:>2}  lat {b[1]:7.3f}..{b[2]:7.3f}"
                          f"  lon {b[3]:8.3f}..{b[4]:8.3f}")
    print("\nFeed the subswath and first/last burst to TOPSAR-Split.")
    print("Use the SAME numbers for every scene in a pair, or coregistration "
          "has nothing to match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
