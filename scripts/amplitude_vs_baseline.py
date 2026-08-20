"""Is a 17 cm whole-scene LOS range unusual for THIS frame?

A published map shows LOS displacement spanning about -17.5 to +6.7 cm across
Flores, referenced to a point ~160 km east of the epicentre, and reads the
pattern as co-seismic deformation. The amplitude looks large. The question that
decides whether it means anything is not "is 17 cm large" but "is 17 cm larger
than what this frame produces in twelve days with NO earthquake".

That question is answerable, because 13 earthquake-free 12-day pairs on the
same frame, same processor, same parameters are on disk. For each one this
computes the same quantity the map reports: the 1-99 percentile spread of
unwrapped phase converted to centimetres of line-of-sight.

Interpretation is deliberately left to the numbers. If several earthquake-free
pairs reach a comparable spread, a co-event map of that amplitude is not
evidence of anything, however striking it looks -- and however carefully its
caveats are worded.

    conda run -n base python scripts/amplitude_vs_baseline.py --frame 1148
"""

import argparse
import os
import sys

import numpy as np

try:
    import rasterio
except ImportError:                                    # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradient_zscore import COEVENT, products          # noqa: E402

FRINGE_CM = 5.5465 / 2          # half wavelength = one 2-pi cycle in LOS


def spread(unw_path, corr_path, min_coh):
    with rasterio.open(unw_path) as src:
        phi = src.read(1).astype("float64")
    with rasterio.open(corr_path) as src:
        coh = src.read(1)
    if coh.shape != phi.shape:
        return None
    ok = np.isfinite(phi) & (phi != 0) & (coh >= min_coh)
    if ok.sum() < 20000:
        return None
    v = phi[ok] * FRINGE_CM / (2 * np.pi)
    lo, hi = np.percentile(v, [1, 99])
    return dict(p1=lo, p99=hi, span=hi - lo, n=int(ok.sum()),
                full=float(v.max() - v.min()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1148, choices=(1148, 1153))
    ap.add_argument("--min-coh", type=float, default=0.3)
    a = ap.parse_args()

    unw = products(a.frame, "unw_phase")
    corr = products(a.frame, "corr")
    if not unw:
        sys.exit(f"no frame-{a.frame} products found")

    print(f"frame {a.frame}: LOS spread per pair, 1-99 percentile\n")
    print("  pair                    p1 cm    p99 cm    span cm    px")
    base, co = [], None
    for k in sorted(unw):
        if k not in corr:
            continue
        s = spread(unw[k], corr[k], a.min_coh)
        if s is None:
            continue
        tag = "  <- CO-EVENT" if k == COEVENT else ""
        print(f"  {k[:8]}->{k[9:]}  {s['p1']:+8.2f}  {s['p99']:+8.2f}"
              f"  {s['span']:8.2f}  {s['n']:>9,}{tag}")
        if k == COEVENT:
            co = s
        else:
            base.append(s)

    if len(base) < 3:
        sys.exit("\ntoo few baseline pairs")

    spans = np.array([b["span"] for b in base])
    print(f"\n=== {len(spans)} EARTHQUAKE-FREE pairs ===")
    print(f"  span: median {np.median(spans):.2f} cm, "
          f"range {spans.min():.2f} .. {spans.max():.2f} cm")
    print(f"  mean {spans.mean():.2f}, sd {spans.std(ddof=1):.2f}")

    if co:
        z = (co["span"] - spans.mean()) / spans.std(ddof=1)
        bigger = int((spans >= co["span"]).sum())
        print(f"\n  co-event span {co['span']:.2f} cm  ->  z = {z:+.2f}")
        print(f"  earthquake-free pairs with an EQUAL OR LARGER span: "
              f"{bigger} of {len(spans)}")
        if bigger >= 2:
            print("\n  -> An amplitude this size is ordinary for this frame.")
            print("     A map showing it is not showing an earthquake; it is")
            print("     showing what twelve days of atmosphere and residual")
            print("     orbit look like here.")
        elif z > 2:
            print("\n  -> The co-event span is genuinely larger than the")
            print("     baseline population.")
        else:
            print("\n  -> Comparable to the baseline population.")

    print("\nNOTE: span is a whole-scene statistic and says nothing about")
    print("WHERE the signal sits. A pair can have an ordinary span and still")
    print("carry real localised deformation, which is why the gradient test")
    print("near the rupture is a separate measurement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
