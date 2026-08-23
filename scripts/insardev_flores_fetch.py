"""Fetch the Flores frame-1148 bursts, orbits and DEM for the insardev chain.

Third chain on the same earthquake. GMTSAR and MintPy agreed to within 1 cm
ring by ring; insardev_pygmtsar is an independent implementation of the same
GMTSAR algorithms with its own alignment, its own unwrapper and its own
geocoding, so a third answer tests the processing rather than the geophysics.
It cannot break the circularity -- all three chains consume the same two
acquisitions -- and saying so up front is the honest framing.

WHY BURSTS AND NOT THE SAFEs ALREADY ON DISK. insardev_pygmtsar's S1_slc
scans for the ASF burst-product layout (<fullBurstID>/annotation/*-BURST.xml,
measurement/*.tiff) which ASF builds server-side. It has no SAFE reader. The
7.6 GB SLCs here are the wrong shape, and hand-rolling a SAFE->burst splitter
would put my own converter inside the very chain that is supposed to be
independent.

CREDENTIALS. ASF() with no arguments routes downloads through the third-party
cache proxy s1-cache-asf.insar.dev and asks for a licence for funded or
institutional use. Reading ~/.netrc and authenticating straight to ASF avoids
both the proxy and the licence question. The credentials are read at runtime
and never written anywhere.

    python3 scripts/insardev_flores_fetch.py --bursts data/insardev_flores/bursts.txt
"""

import argparse
import netrc
import os
import sys


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
DATADIR = os.path.join(REPO, "data/insardev_flores/data")
EARTHDATA = "urs.earthdata.nasa.gov"


def creds():
    try:
        n = netrc.netrc()
    except Exception as e:                                  # noqa: BLE001
        sys.exit(f"cannot read ~/.netrc: {e}")
    auth = n.authenticators(EARTHDATA)
    if not auth:
        sys.exit(f"no {EARTHDATA} entry in ~/.netrc")
    return auth[0], auth[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bursts", required=True,
                    help="file of burst names, one per line, from "
                         "scripts/asf_search_bursts.py --out")
    ap.add_argument("--datadir", default=DATADIR)
    ap.add_argument("--n-jobs", type=int, default=4,
                    help="S1_slc raises on XML corrupted by a parallel "
                         "download race, so this stays modest on purpose")
    ap.add_argument("--skip-dem", action="store_true")
    a = ap.parse_args()

    from insardev_toolkit import ASF, EOF, Tiles
    from insardev_pygmtsar import S1

    names = [l.strip() for l in open(a.bursts) if l.strip()]
    print(f"{len(names)} bursts requested")
    os.makedirs(a.datadir, exist_ok=True)

    user, pwd = creds()
    print(f"authenticating to ASF as {user}")
    asf = ASF(user, pwd)
    print(asf.download(a.datadir, "\n".join(names), n_jobs=a.n_jobs))

    # Scan before fetching orbits: S1_slc is what decides which orbit each
    # burst needs, and it is also the first thing that will complain if a
    # download landed short.
    s1 = S1(a.datadir)
    df = s1.to_dataframe()
    print(f"\nscanned {len(df)} bursts")
    print(df[["startTime", "flightDirection", "pathNumber",
              "subswath", "orbit"]].to_string(max_rows=8))

    print("\nfetching orbits")
    EOF().download(a.datadir, df)

    if not a.skip_dem:
        dem = os.path.join(os.path.dirname(a.datadir), "dem.nc")
        if os.path.exists(dem):
            print(f"DEM already present: {dem}")
        else:
            print("downloading Copernicus GLO-30 DEM")
            Tiles().download_dem(df, provider="GLO", filename=dem)
            print(f"wrote {dem}")

    # Re-scan so the orbit column is populated in what gets reported.
    s1 = S1(a.datadir)
    missing = s1.to_dataframe().orbit.isna().sum()
    if missing:
        print(f"\nWARNING: {missing} bursts have no matching orbit file")
    else:
        print("\nevery burst has an orbit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
