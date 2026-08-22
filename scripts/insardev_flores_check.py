"""Did every burst actually land? S1_slc will not tell you.

S1_slc builds its record list from annotation XMLs, which are a few hundred KB
and essentially always download. The measurement TIFF is 125-150 MB and is
what actually fails. So "NOTE: Loaded 34 bursts" is consistent with half the
imagery being missing, and the first symptom would otherwise appear hours
later inside transform().

ASF extracts burst products on demand: the first request returns HTTP 202
Accepted while the server builds the file, and the downloader records that as
a failure. Re-running the fetch usually succeeds because by then the product
exists. So this reports what is missing in a form that can be fed straight
back to the fetcher.

    python3 scripts/insardev_flores_check.py --write-missing missing.txt
"""

import argparse
import glob
import os
import sys


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
DATADIR = os.path.join(REPO, "data/insardev_flores/data")
MIN_MB = 50.0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--datadir", default=DATADIR)
    ap.add_argument("--bursts", default=os.path.join(
        REPO, "data/insardev_flores/bursts.txt"))
    ap.add_argument("--write-missing", default=None)
    a = ap.parse_args()

    wanted = [l.strip() for l in open(a.bursts) if l.strip()]
    ok, bad = [], []
    for b in wanted:
        # <fullBurstID>/measurement/<burst>.tiff, fullBurstID unknown here, so
        # search rather than reconstruct it.
        hits = glob.glob(os.path.join(a.datadir, "*", "measurement",
                                      f"{b}.tiff"))
        if not hits:
            bad.append((b, "absent"))
            continue
        mb = os.path.getsize(hits[0]) / 1e6
        if mb < MIN_MB:
            # 22-byte files are what a 202 response leaves behind. They must be
            # deleted, not just re-requested: skip_exist would otherwise treat
            # them as done.
            bad.append((b, f"{mb:.3f} MB"))
        else:
            ok.append(b)

    print(f"{len(ok)}/{len(wanted)} bursts have a full TIFF")
    if bad:
        print(f"\n{len(bad)} incomplete:")
        for b, why in bad:
            print(f"  {why:>10}  {b}")

    stubs = 0
    for f in glob.glob(os.path.join(a.datadir, "*", "measurement", "*.tiff")):
        if os.path.getsize(f) < MIN_MB * 1e6:
            os.remove(f)
            stubs += 1
    if stubs:
        print(f"\ndeleted {stubs} truncated stub TIFFs so skip_exist will "
              f"re-fetch them")

    if a.write_missing:
        with open(a.write_missing, "w") as f:
            f.write("\n".join(b for b, _ in bad) + "\n" if bad else "")
        print(f"wrote {a.write_missing}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
