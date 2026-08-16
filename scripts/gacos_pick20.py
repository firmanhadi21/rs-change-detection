"""Choose the 20 dates that let GACOS correct the most interferograms.

The GACOS form takes 20 dates per request, and this frame has 298 epochs --
15 submissions to cover it all. Before committing to that, it is worth spending
one request on the subset that yields the largest self-contained sub-network,
so the effect of the correction can be measured and the remaining 14 requests
justified or dropped.

LiCSBAS03op_GACOS corrects an interferogram only when BOTH its epochs have
GACOS data, so scattered dates are nearly useless: 20 dates spread across 11
years correct almost nothing, while 20 consecutive epochs correct every pair
inside that window. This maximises that count explicitly rather than assuming
consecutive is best.

Only dates after 2022-08-01 are considered -- GACOS notes that earlier requests
may still be affected by the ECMWF Data Handling System move.

    python3 scripts/gacos_pick20.py
"""

import datetime as dt
import os
import re
import sys
import urllib.request

FRAME = "112A_09831_050508"
URL = ("https://gws-access.jasmin.ac.uk/public/nceo_geohazards/"
       f"LiCSAR_products/112/{FRAME}/interferograms/")
CACHE = "/tmp/ifgs.html"
CUTOFF = "20220801"      # GACOS: requests after this date are processed normally
N = 20


def load_pairs():
    if not os.path.exists(CACHE):
        print("fetching interferogram list from COMET ...")
        with urllib.request.urlopen(URL, timeout=120) as r:
            open(CACHE, "wb").write(r.read())
    html = open(CACHE, errors="ignore").read()
    return sorted(set(re.findall(r'href="(20\d{6})_(20\d{6})"', html)))


def main():
    pairs = load_pairs()
    if not pairs:
        raise SystemExit("no interferograms parsed")

    usable = [p for p in pairs if p[0] >= CUTOFF]
    epochs = sorted({d for p in usable for d in p})
    print(f"{len(pairs)} interferograms total")
    print(f"{len(usable)} with both epochs after {CUTOFF} "
          f"({len(epochs)} distinct epochs)")

    if len(epochs) <= N:
        best_set, best_n = epochs, len(usable)
    else:
        # Slide a window of N consecutive epochs; count pairs fully inside it.
        best_set, best_n = None, -1
        for i in range(len(epochs) - N + 1):
            window = set(epochs[i:i + N])
            n = sum(1 for a, b in usable if a in window and b in window)
            if n > best_n:
                best_set, best_n = sorted(window), n

    span = (dt.datetime.strptime(best_set[-1], "%Y%m%d")
            - dt.datetime.strptime(best_set[0], "%Y%m%d")).days
    print(f"\nbest {N}-date window: {best_set[0]} -> {best_set[-1]} "
          f"({span} days)")
    print(f"  interferograms fully covered: {best_n}")
    print(f"  (a scattered choice of 20 would cover far fewer;")
    print(f"   consecutive epochs share pairs, isolated ones do not)")

    out = os.path.expanduser(
        "~/GitHub/rs-change-detection/output/licsbas/gacos_request_20.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(best_set) + "\n")

    print(f"\n--- paste these into the GACOS form ---")
    for d in best_set:
        print(d)
    print(f"\nsaved to {out}")
    print("\nArea:  N -7.2547  S -9.1647  W 120.4072  E 122.9772")
    print("Time:  10:17 UTC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
