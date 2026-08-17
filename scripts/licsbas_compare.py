"""Tabulate every LiCSBAS configuration tried on the Flores frame.

Four runs differing only in thresholds and pre-processing. The point is not
which keeps the most interferograms -- loosening loop closure always keeps more
-- but whether the extra data buys a longer, better-fitting time series or just
admits unwrapping errors.

The columns that decide that are maxTlen and resid_rms, not n_ifg.
"""

import os
import sys

import numpy as np

BASE = os.path.expanduser("~/GitHub/rs-change-detection/output/licsbas")

RUNS = [
    ("TS_GEOCml10", "mine: ml10, no mask/clip, all defaults", "1.5"),
    ("TS_GEOCml4maskclip_defaults", "official sample: mask+clip", "1.5"),
    ("TS_GEOCml4_loop2", "your 003D thresholds", "2"),
    ("TS_GEOCml4", "003D thresholds, loop_thre 3", "3"),
]


def par(path):
    d = {}
    if not os.path.exists(path):
        return d
    for line in open(path, errors="ignore"):
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return d


def grid_of(ts):
    p = par(f"{BASE}/{ts}/info/EQA.dem_par")
    if not p:
        return None
    return (int(p["width"].split()[0]), int(p["nlines"].split()[0]))


def read(ts, name, shape):
    p = f"{BASE}/{ts}/results/{name}"
    if not os.path.exists(p) or shape is None:
        return None
    a = np.fromfile(p, dtype=np.float32)
    if a.size != shape[0] * shape[1]:
        return None
    return a.reshape(shape[1], shape[0])


def med(a):
    if a is None:
        return None
    v = a[np.isfinite(a) & (a != 0)]
    return float(np.median(v)) if v.size else None


def main():
    rows = []
    for ts, label, loop in RUNS:
        p13 = par(f"{BASE}/{ts}/info/13parameters.txt")
        if not p13:
            print(f"  ({ts}: not finished)")
            continue
        shape = grid_of(ts)
        vel = read(ts, "vel.filt.mskd", shape)
        if vel is None:
            vel = read(ts, "vel.mskd", shape)

        cov = (float(np.isfinite(vel).mean()) if vel is not None else None)
        rows.append({
            "label": label, "loop": loop,
            "n_ifg": int(p13.get("n_ifg", 0)),
            "n_ifg_all": int(p13.get("n_ifg_all", 0)),
            "n_im": int(p13.get("n_im", 0)),
            "n_im_all": int(p13.get("n_im_all", 0)),
            "maxT": med(read(ts, "maxTlen", shape)),
            "resid": med(read(ts, "resid_rms", shape)),
            "cov": cov,
            "vstd": med(read(ts, "vstd", shape)),
        })

    if not rows:
        raise SystemExit("no completed runs")

    print(f"{'configuration':38} {'loop':>5} {'ifgs':>12} {'epochs':>10} "
          f"{'maxTlen':>8} {'resid':>7} {'cover':>7}")
    print("-" * 92)
    for r in rows:
        pct = 100 * r["n_ifg"] / r["n_ifg_all"] if r["n_ifg_all"] else 0
        print(f"{r['label']:38} {r['loop']:>5} "
              f"{r['n_ifg']:>5}/{r['n_ifg_all']:<5} ({pct:4.1f}%) "
              f"{r['n_im']:>4}/{r['n_im_all']:<4} "
              f"{(f'{r[chr(109)+chr(97)+chr(120)+chr(84)]:.2f} yr' if r['maxT'] else '   -   '):>8} "
              f"{(f'{r[chr(114)+chr(101)+chr(115)+chr(105)+chr(100)]:.2f}' if r['resid'] else '  -  '):>7} "
              f"{(f'{100*r[chr(99)+chr(111)+chr(118)]:.2f}%' if r['cov'] is not None else '  -  '):>7}")

    print("\n=== what changed ===")
    a, b = rows[0], rows[-1]
    print(f"  interferograms: {a['n_ifg']} -> {b['n_ifg']} "
          f"({b['n_ifg']/max(a['n_ifg'],1):.1f}x)")
    print(f"  epochs:         {a['n_im']} -> {b['n_im']}")
    if a["maxT"] and b["maxT"]:
        print(f"  maxTlen:        {a['maxT']:.2f} -> {b['maxT']:.2f} yr "
              f"({b['maxT']/a['maxT']:.2f}x)")
    if a["resid"] and b["resid"]:
        print(f"  resid_rms:      {a['resid']:.2f} -> {b['resid']:.2f} mm "
              f"({'worse' if b['resid'] > a['resid'] else 'better'})")

    print("\n=== reading ===")
    if b["maxT"] and a["maxT"]:
        if b["maxT"] > a["maxT"] * 1.5:
            print("  Loosening loop closure lengthened the time series, so the")
            print("  extra interferograms carry real temporal information.")
        else:
            print("  More interferograms, but maxTlen barely moved: the network")
            print("  still cannot connect epochs across the archive. The extra")
            print("  data adds redundancy inside short windows, not span.")
    if b["resid"] and a["resid"] and b["resid"] > a["resid"] * 1.2:
        print("  Residual RMS rose materially — the admitted interferograms fit")
        print("  the time series worse, which is what a 3 rad closure error is.")
    print("\n  Eleven years of archive is only eleven years of measurement if")
    print("  the network connects. maxTlen is the column that says whether it does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
