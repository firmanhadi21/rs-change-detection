"""Fetch the Sentinel-1 orbit files covering given acquisitions.

Precise orbits (POEORB) are published about 20 days after acquisition. For a
scene from this month they do not exist yet, so this falls back to restituted
(RESORB), which appear within hours.

RESORB IS NOT AS GOOD AND THE DIFFERENCE IS WORTH STATING. POEORB is accurate
to a few centimetres; RESORB to roughly 10 cm. For TOPS interferometry that is
usually tolerable -- enhanced spectral diversity re-estimates the azimuth
alignment from the data itself, so orbit error mostly shows up as a
long-wavelength ramp rather than as decorrelation. But a ramp is exactly what
you do NOT want when the question is whether a broad co-seismic fringe pattern
is present, so a run on RESORB should be repeated on POEORB once available and
the two compared.

Selection is by VALIDITY WINDOW, not by filename date: a RESORB file is named
for when it was generated as well as what it covers, and picking by generation
time gets a file that does not span the acquisition at all.

    python3 scripts/fetch_s1_orbits.py --scene S1D_..._20260818T101604_...
    python3 scripts/fetch_s1_orbits.py --platform S1D --time 2026-08-18T10:16:04
"""

import argparse
import datetime as dt
import os
import re
import sys
import urllib.request
import zipfile


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = "https://step.esa.int/auxdata/orbits/Sentinel-1"
OUT = os.path.expanduser(_REPO_ROOT + "/data/orbits")
NAME_RE = re.compile(
    r"(S1[A-D]_OPER_AUX_(?:POEORB|RESORB)_OPOD_\d{8}T\d{6}_"
    r"V(\d{8}T\d{6})_(\d{8}T\d{6})\.EOF)(?:\.zip)?")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "earthchange"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _parse(ts):
    return dt.datetime.strptime(ts, "%Y%m%dT%H%M%S")


def find(platform, when, kind):
    """The orbit file whose validity window contains `when`."""
    listing = _get(f"{STEP}/{kind}/{platform}/{when:%Y}/{when:%m}/").decode(
        "utf-8", "replace")
    best = None
    for m in NAME_RE.finditer(listing):
        name, v0, v1 = m.group(1), _parse(m.group(2)), _parse(m.group(3))
        if v0 <= when <= v1:
            # Several files can cover one instant; prefer the widest margin
            # from either edge, since a scene near a boundary is where
            # interpolation is weakest.
            margin = min((when - v0).total_seconds(),
                         (v1 - when).total_seconds())
            if best is None or margin > best[0]:
                best = (margin, name)
    return best


def fetch(platform, when, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for kind in ("POEORB", "RESORB"):
        try:
            hit = find(platform, when, kind)
        except Exception as exc:                          # noqa: BLE001
            print(f"  {kind}: listing failed ({exc.__class__.__name__})")
            continue
        if not hit:
            print(f"  {kind}: nothing covers {when:%Y-%m-%d %H:%M:%S}"
                  + (" (expected — published ~20 days after acquisition)"
                     if kind == "POEORB" else ""))
            continue
        margin, name = hit
        dest = os.path.join(out_dir, name)
        if os.path.exists(dest):
            print(f"  {kind}: already have {name}")
            return dest, kind
        url = f"{STEP}/{kind}/{platform}/{when:%Y}/{when:%m}/{name}.zip"
        print(f"  {kind}: {name}  ({margin/60:.0f} min from the window edge)")
        blob = _get(url)
        tmp = dest + ".zip"
        with open(tmp, "wb") as f:
            f.write(blob)
        with zipfile.ZipFile(tmp) as z:
            z.extractall(out_dir)
        os.remove(tmp)
        print(f"    -> {dest}  ({os.path.getsize(dest)/1024:.0f} KB)")
        return dest, kind
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", action="append", default=[],
                    help="SAFE name or path; platform and time are read from it")
    ap.add_argument("--platform")
    ap.add_argument("--time", help="YYYY-MM-DDTHH:MM:SS")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    jobs = []
    for s in a.scene:
        base = os.path.basename(s)
        m = re.match(r"(S1[A-D])_\w+_(\d{8}T\d{6})_", base)
        if not m:
            sys.exit(f"cannot read platform/time from {base!r}")
        jobs.append((m.group(1), _parse(m.group(2))))
    if a.platform and a.time:
        jobs.append((a.platform,
                     dt.datetime.fromisoformat(a.time.replace("Z", ""))))
    if not jobs:
        sys.exit("give --scene or --platform/--time")

    got = []
    for platform, when in jobs:
        print(f"\n{platform} {when:%Y-%m-%d %H:%M:%S}")
        path, kind = fetch(platform, when, os.path.expanduser(a.out))
        if path:
            got.append((path, kind))
        else:
            print("  NO ORBIT FOUND — do not process without one")
    kinds = {k for _, k in got}
    if kinds == {"RESORB"}:
        print("\nAll restituted. Fine for a first pass; repeat on POEORB when "
              "published (~20 days after acquisition) before trusting any "
              "long-wavelength signal.")
    return 0 if len(got) == len(jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
