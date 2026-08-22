"""Which Sentinel-1 BURST products cover the Flores near field? Search only.

insardev_pygmtsar cannot read a .SAFE. S1_slc scans for the ASF burst-product
layout -- <fullBurstID>/annotation/S1_*-BURST.xml plus measurement/*.tiff --
which ASF builds server-side. So the 7.6 GB SLCs already on disk are the wrong
shape for this chain and the bursts have to be fetched separately.

That makes "how many, and how big" the first question, and it is worth asking
before downloading rather than after: a full frame is three subswaths of nine
or ten bursts, twice over, and most of those bursts are open ocean. The
deforming ground the previous two chains measured sits in a ring 20-65 km from
an OFFSHORE epicentre, so selecting bursts by "intersects the near-field
ring" rather than "belongs to frame 1148" cuts the download without losing any
pixel that carries signal.

Burst products are free -- no HyP3 credits are involved. The cost is disk and
time, which is why this reports both before anything is fetched.

    python3 scripts/asf_search_bursts.py --radius 70
"""

import argparse
import collections
import csv
import io
import math
import sys
import urllib.parse
import urllib.request

API = "https://api.daac.asf.alaska.edu/services/search/param"
EPI_LAT, EPI_LON = -8.3101, 121.3517


def ring_wkt(lat, lon, radius_km, n=48):
    """A circle on the sphere as a WKT polygon, in lon/lat."""
    pts = []
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
        pts.append(f"{lon + dlon * math.cos(th):.5f} "
                   f"{lat + dlat * math.sin(th):.5f}")
    return f"POLYGON(({','.join(pts)}))"


def search(wkt, start, end, direction, extra=None):
    q = {"platform": "Sentinel-1", "processingLevel": "BURST",
         "beamMode": "IW", "intersectsWith": wkt,
         "start": f"{start}T00:00:00Z", "end": f"{end}T23:59:59Z",
         "output": "csv"}
    if direction:
        q["flightDirection"] = direction
    if extra:
        q.update(extra)
    url = f"{API}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "earthchange"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8",
                                                               "replace"))))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, default=EPI_LAT)
    ap.add_argument("--lon", type=float, default=EPI_LON)
    ap.add_argument("--radius", type=float, default=70.0,
                    help="km. The GMTSAR and MintPy profiles both went to "
                         "zero by ~50 km, so 70 km keeps a margin of quiet "
                         "ground for referencing")
    ap.add_argument("--dates", nargs="+", default=["2026-08-06", "2026-08-18"])
    ap.add_argument("--direction", default="ASCENDING")
    ap.add_argument("--pol", default="VV")
    ap.add_argument("--mission", default=None,
                    help="e.g. S1D, to match the SLCs the other two chains "
                         "already processed")
    ap.add_argument("--out", default=None,
                    help="write the burst-name list here, one per line")
    a = ap.parse_args()

    wkt = ring_wkt(a.lat, a.lon, a.radius)
    print(f"AOI: {a.radius:.0f} km around {a.lat}, {a.lon}")

    keep = []
    for d in a.dates:
        rows = search(wkt, d, d, a.direction)
        # The BURST CSV has no Polarization column -- unlike the SLC CSV --
        # so it has to come out of the granule name. Filtering on a column
        # that does not exist silently returns nothing, which is how this
        # first reported "no bursts" for a scene that plainly has them.
        rows = [r for r in rows
                if r.get("Beam Mode") == "IW"
                and r["Granule Name"].split("_")[4] == a.pol]
        if a.mission:
            rows = [r for r in rows if r["Platform"].endswith(a.mission[-1])]
        if not rows:
            print(f"\n{d}: no bursts")
            continue
        paths = collections.Counter(
            f"{r['Platform'][-1]}/{r['Path Number']}"
            f"/{r['Ascending or Descending?'][:3]}" for r in rows)
        sw = collections.Counter(r["subswath"] for r in rows)
        size = sum(float(r.get("Size (MB)") or 0) for r in rows)
        print(f"\n{d}: {len(rows)} bursts, {size/1024:.2f} GB")
        print(f"  sat/path/dir: {dict(paths)}")
        print(f"  subswaths: {dict(sorted(sw.items()))}")
        keep += rows

    if not keep:
        return 1

    paths = collections.Counter(f"{r['Platform'][-1]}/{r['Path Number']}"
                                for r in keep)
    if len(paths) > 1:
        # Two paths over one point means two different geometries. Mixing them
        # in one stack is not a bigger stack, it is a wrong one.
        print(f"\nWARNING: {len(paths)} paths in the selection {dict(paths)}. "
              f"Pick one before downloading.")

    total = sum(float(r.get("Size (MB)") or 0) for r in keep)
    print(f"\ntotal {len(keep)} bursts, {total/1024:.2f} GB")

    names = sorted(r["Granule Name"] for r in keep)
    if a.out:
        with open(a.out, "w") as f:
            f.write("\n".join(names) + "\n")
        print(f"wrote {a.out}")
    else:
        print()
        for n in names:
            print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
