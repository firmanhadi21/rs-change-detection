"""Which Sentinel-1 granules actually contain a point? Search, do not download.

Written after three 7.6 GB SLCs turned out to sit 7 km south of the Flores
epicentre. A frame that misses the near field cannot answer a near-field
question however well it processes, so the footprint test belongs BEFORE the
download, not after.

Reports path, frame, direction and size, and says plainly whether each granule
contains the point or merely comes near it. Nothing is fetched.

    python3 scripts/asf_search_frame.py --lat -8.3101 --lon 121.3517 \
        --start 2026-07-01 --end 2026-08-25
"""

import argparse
import csv
import io
import sys
import urllib.parse
import urllib.request

API = "https://api.daac.asf.alaska.edu/services/search/param"


def search(lat, lon, start, end, platform, level, beam, direction):
    q = {
        "platform": platform, "processingLevel": level, "beamMode": beam,
        "intersectsWith": f"POINT({lon} {lat})",
        "start": f"{start}T00:00:00Z", "end": f"{end}T23:59:59Z",
        "output": "csv",
    }
    if direction:
        q["flightDirection"] = direction
    url = f"{API}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "earthchange"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--platform", default="Sentinel-1")
    ap.add_argument("--level", default="SLC")
    ap.add_argument("--beam", default="IW")
    ap.add_argument("--direction", default=None,
                    choices=[None, "ASCENDING", "DESCENDING"])
    a = ap.parse_args()

    rows = search(a.lat, a.lon, a.start, a.end, a.platform, a.level, a.beam,
                  a.direction)
    if not rows:
        print("no granules contain that point in the window")
        return 1

    print(f"{len(rows)} granules contain POINT({a.lon} {a.lat})\n")
    key = lambda r: (r.get("Path Number", ""), r.get("Acquisition Date", ""))
    print(f"  {'date':<12}{'path':>5}{'frame':>7}  {'dir':<5}"
          f"{'size GB':>8}  granule")
    tracks = {}
    for r in sorted(rows, key=key):
        acq = r.get("Acquisition Date", "")[:10]
        path = r.get("Path Number", "")
        frame = r.get("Frame Number", "")
        d = (r.get("Ascending or Descending?") or "")[:4].upper()
        try:
            gb = float(r.get("Size (MB)") or 0) / 1024
        except ValueError:
            gb = 0.0
        print(f"  {acq:<12}{path:>5}{frame:>7}  {d:<5}{gb:>8.1f}  "
              f"{r.get('Granule Name', '')}")
        tracks.setdefault((path, frame, d), []).append(acq)

    print("\n  by track/frame — a pair needs two dates on the SAME one:")
    for (path, frame, d), dates in sorted(tracks.items()):
        print(f"    path {path:>3} frame {frame:>5} {d:<5} "
              f"{len(dates)} acquisitions: {', '.join(sorted(dates))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
