"""Damage detection against each pixel's OWN coherence history, not the frame.

The three-scene analysis could only ask "is this pixel's drop large compared to
the island?". That question has a bad failure mode: a pixel that swings 0.2-0.6
every cycle looks alarming when it lands at 0.2, and a pixel that sits rock
steady at 0.55 +/- 0.04 looks fine when it drops to 0.45 -- when the second is
the real anomaly and the first is just noisy ground.

With several pre-event pairs the right question becomes available:

    z = (coh_coevent - mean(coh_baseline)) / std(coh_baseline)

per pixel. Farmland that decorrelates every cycle has a large std and needs a
huge drop to register. A building roof with a tiny std registers on a small
one. This is what the earlier analysis was missing, and no amount of
re-thresholding a single baseline pair substitutes for it.

TWO REQUIREMENTS, both easy to violate silently.

IDENTICAL PROCESSING. Every pair must come from the same processor, the same
looks and the same coherence window. Mixing HyP3 coherence into a SNAP baseline
would put a processing difference into the z-score, and it would dominate the
earthquake. This script checks raster shape but CANNOT check processing, so
that discipline is on the caller.

MATCHED TEMPORAL BASELINE. All pairs 12 days. A 24-day pair has lower coherence
for reasons that have nothing to do with damage, and averaging it into the
baseline biases the mean down and inflates the std, which HIDES damage rather
than inventing it -- the quiet direction of wrong.

    python3 scripts/coherence_zscore.py --coevent prepost_full \\
        --baseline prepre_full [more_full ...]
"""

import argparse
import glob
import os
import sys

for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

import numpy as np  # noqa: E402

SNAP = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/snap")
EPI_LON, EPI_LAT = 121.3517, -8.3101
KM_LAT = 110.57

TOWNS = [("Mbay", 121.3833, -8.4667), ("Riung", 121.0333, -8.4167),
         ("Boawae", 121.1333, -8.7667), ("Bajawa", 120.9856, -8.7906),
         ("Ende", 121.6626, -8.8432), ("Maumere", 122.2111, -8.6199),
         ("Larantuka", 122.9822, -8.3405)]


def read_coh(tag):
    d = f"{SNAP}/{tag}.data"
    hdr = sorted(glob.glob(f"{d}/coh_*.hdr"))[0]
    meta = {}
    for line in open(hdr, errors="ignore"):
        if "=" in line:
            k, _, v = line.partition("=")
            meta[k.strip().lower()] = v.strip()
    w, h = int(meta["samples"]), int(meta["lines"])
    endian = ">" if meta.get("byte order", "0").strip() == "1" else "<"
    a = np.fromfile(hdr[:-4] + ".img", dtype=endian + "f4").reshape(h, w)
    return a.astype("float32"), meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coevent", default="prepost_fullsea")
    ap.add_argument("--baseline", nargs="+", default=["prepre_fullsea"])
    ap.add_argument("--min-mean", type=float, default=0.35,
                    help="ignore pixels whose baseline coherence is too low to "
                         "have room to fall")
    ap.add_argument("--z", type=float, default=-3.0)
    ap.add_argument("--radius", type=float, default=3.0)
    a = ap.parse_args()

    co, meta = read_coh(a.coevent)
    stack = []
    for tag in a.baseline:
        b, _ = read_coh(tag)
        h = min(b.shape[0], co.shape[0]); w = min(b.shape[1], co.shape[1])
        co = co[:h, :w]
        stack = [s[:h, :w] for s in stack]
        stack.append(b[:h, :w])
    B = np.stack(stack)
    n = B.shape[0]
    print(f"co-event  {a.coevent}  {co.shape}")
    print(f"baseline  {n} pair(s): {', '.join(a.baseline)}")

    if n < 3:
        print(f"\n  WARNING: {n} baseline pair(s). A standard deviation from")
        print(f"  fewer than ~3 samples is not a standard deviation, and the")
        print(f"  z-scores below are indicative at best. Reported anyway so")
        print(f"  the pipeline is testable, but do NOT publish from n<3.")

    valid = (co > 0) & np.isfinite(co) & np.all((B > 0) & np.isfinite(B), 0)
    mean = np.where(valid, B.mean(0), np.nan)
    # ddof=1: with n samples the population formula understates the spread,
    # which inflates every z-score toward significance.
    sd = np.where(valid, B.std(0, ddof=1) if n > 1 else np.nan, np.nan)

    usable = valid & (mean >= a.min_mean) & np.isfinite(sd) & (sd > 0.01)
    print(f"\nobserved {int(valid.sum()):,} px; "
          f"usable (mean >= {a.min_mean}, sd > 0.01): {int(usable.sum()):,}")
    if usable.sum() < 1000:
        print("  too little stable ground to judge")
        return 1

    z = np.where(usable, (co - mean) / np.maximum(sd, 1e-6), np.nan)
    zz = z[np.isfinite(z)]
    print(f"  baseline mean coherence over usable: "
          f"{np.nanmedian(mean[usable]):.3f}")
    print(f"  baseline sd   over usable:           "
          f"{np.nanmedian(sd[usable]):.3f}")
    for q in (1, 5, 25, 50, 75):
        print(f"    z p{q:<3} {np.percentile(zz, q):+.2f}")
    flagged = int((zz <= a.z).sum())
    print(f"  pixels at z <= {a.z}: {flagged:,} "
          f"({100*flagged/zz.size:.2f}%)")

    m = meta["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    lon = west + (np.arange(z.shape[1])[None, :] + .5) * xr
    lat = north - (np.arange(z.shape[0])[:, None] + .5) * yr
    dist = np.hypot((lon - EPI_LON) * kx, (lat - EPI_LAT) * KM_LAT)

    print("\n=== z against distance from the rupture ===")
    print("  distance          n       median z    frac z<=-3")
    for lo in range(20, 175, 15):
        s = usable & (dist >= lo) & (dist < lo + 15)
        if s.sum() < 1500:
            continue
        v = z[s]
        print(f"   {lo:3d}-{lo+15:<3d} km  {int(s.sum()):>8,}   "
              f"{np.nanmedian(v):+.2f}      {100*np.nanmean(v <= a.z):5.2f}%")

    print(f"\n=== towns, within {a.radius:.0f} km ===")
    print("  town          dist_epi       n     median z   frac z<=-3")
    for name, tlon, tlat in TOWNS:
        d = np.hypot((lon - tlon) * kx, (lat - tlat) * KM_LAT)
        s = usable & (d <= a.radius)
        de = float(np.hypot((tlon - EPI_LON) * kx, (tlat - EPI_LAT) * KM_LAT))
        if s.sum() < 100:
            print(f"  {name:<12} {de:6.0f} km   {int(s.sum()):>6,}"
                  f"   -- too few stable pixels --")
            continue
        v = z[s]
        print(f"  {name:<12} {de:6.0f} km   {int(s.sum()):>6,}   "
              f"{np.nanmedian(v):+.2f}       {100*np.nanmean(v <= a.z):5.2f}%")

    out = f"{SNAP}/coherence_z_{a.coevent}.img"
    np.where(np.isfinite(z), z, 0).astype("float32").tofile(out)
    src = sorted(glob.glob(f"{SNAP}/{a.coevent}.data/coh_*.hdr"))[0]
    open(out[:-4] + ".hdr", "w").write(open(src).read())
    print(f"\nwrote {out}")
    print("\nDamage would show as z falling off WITH DISTANCE and towns near")
    print("the rupture sitting well below the rest. A flat profile means the")
    print("drop is weather, however large it is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
