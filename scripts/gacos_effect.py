"""Did GACOS reduce atmospheric noise over Flores, or add to it?

LiCSBAS03op writes the one measurement that answers this directly:
phase standard deviation per interferogram, before and after the correction.
No inversion needed, so it survives a network too sparse to invert.

A negative reduction rate means the correction made the interferogram WORSE.
That is not unheard of -- GACOS interpolates a weather model, and where the
model is wrong it injects error rather than removing it -- but if it happens
on most interferograms, the correction is not usable for this frame.
"""

import os
import sys

import numpy as np

PATH = os.path.expanduser("~/GitHub/rs-change-detection/output/licsbas/"
                          "GEOCml4GACOS/GACOS_info.txt")


def main():
    if not os.path.exists(PATH):
        raise SystemExit(f"{PATH} not found — run LiCSBAS03op_GACOS first")

    before, after, rate, names = [], [], [], []
    for line in open(PATH):
        f = line.split()
        if len(f) < 4 or "_" not in f[0]:
            continue
        try:
            b, a = float(f[1]), float(f[2])
            r = float(f[3].rstrip("%"))
        except ValueError:
            continue
        names.append(f[0])
        before.append(b)
        after.append(a)
        rate.append(r)

    before = np.array(before)
    after = np.array(after)
    rate = np.array(rate)
    print(f"{len(rate)} interferograms corrected\n")

    print("=== phase STD (rad) ===")
    print(f"  before  median {np.median(before):5.2f}   "
          f"mean {before.mean():5.2f}")
    print(f"  after   median {np.median(after):5.2f}   "
          f"mean {after.mean():5.2f}")

    print("\n=== reduction rate (%, positive = improved) ===")
    for q in (5, 25, 50, 75, 95):
        print(f"  p{q:<3} {np.percentile(rate, q):+7.1f}%")
    print(f"  mean {rate.mean():+.1f}%")

    improved = (rate > 0).sum()
    worsened = (rate < 0).sum()
    print(f"\n  improved: {improved} ({100*improved/len(rate):.0f}%)")
    print(f"  worsened: {worsened} ({100*worsened/len(rate):.0f}%)")

    print("\n=== reading ===")
    if np.median(rate) > 10:
        print("  GACOS clearly helps here: most interferograms improve, and the")
        print("  median reduction is material. Worth requesting the remaining")
        print("  dates.")
    elif np.median(rate) > 0:
        print("  Marginal: a slight median improvement, but not enough to")
        print("  justify 14 more requests on its own.")
    else:
        print("  GACOS makes these interferograms WORSE on average. The weather")
        print("  model is adding error rather than removing it -- which over a")
        print("  narrow volcanic island is plausible: the model cannot resolve")
        print("  the convection it is being asked to correct, so it subtracts a")
        print("  delay field that does not match the real one.")
        print("  Do NOT request the remaining dates.")

    worst = np.argsort(rate)[:3]
    best = np.argsort(rate)[-3:][::-1]
    print("\n  most improved:")
    for i in best:
        print(f"    {names[i]}  {before[i]:5.2f} -> {after[i]:5.2f}  {rate[i]:+6.1f}%")
    print("  most degraded:")
    for i in worst:
        print(f"    {names[i]}  {before[i]:5.2f} -> {after[i]:5.2f}  {rate[i]:+6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
