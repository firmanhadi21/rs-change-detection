"""Is the structured phase in western Flores deformation, or atmosphere?

The whole-scene interferogram has smooth phase blobs over the western
highlands. Three things produce that, and they are separable:

  DEFORMATION   phase varies with DISTANCE FROM THE RUPTURE, monotonically,
                strongest nearest and decaying away.
  ATMOSPHERE    phase varies with ELEVATION (stratified water vapour), or
                wanders with no relation to either.
  DEM ERROR     also varies with elevation, and is indistinguishable from
                stratified atmosphere in a single pair. Both are nuisance.

Wrapped phase cannot be averaged directly -- the mean of +3.0 and -3.0 rad is
0, when the two are 0.28 rad apart. So every statistic here is computed on the
COMPLEX PHASOR exp(i*phi) and converted back with arctan2. The resultant length
R is the payoff: R near 1 means the phase in that bin is consistent, R near 0
means it is uniformly distributed, i.e. noise. Reporting a bin angle without R
would let pure noise masquerade as a trend.

    python3 scripts/phase_diagnose.py --pair prepost --suffix full
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
FRINGE_CM = 5.5465 / 2


def read_img(data_dir, prefix):
    hdr = sorted(glob.glob(f"{data_dir}/{prefix}*.hdr"))[0]
    meta = {}
    for line in open(hdr, errors="ignore"):
        if "=" in line:
            k, _, v = line.partition("=")
            meta[k.strip().lower()] = v.strip()
    w, h = int(meta["samples"]), int(meta["lines"])
    endian = ">" if meta.get("byte order", "0").strip() == "1" else "<"
    kind = {"4": "f4", "5": "f8", "12": "u2", "2": "i2"}.get(
        meta.get("data type", "4").strip(), "f4")
    a = np.fromfile(hdr[:-4] + ".img", dtype=endian + kind)
    return a.reshape(h, w).astype("float32"), meta


def grid(meta, shape):
    m = meta["map info"].strip("{}").split(",")
    rx, ry = float(m[1]), float(m[2])
    ulx, uly = float(m[3]), float(m[4])
    xr, yr = float(m[5]), float(m[6])
    west = ulx - (rx - 1) * xr
    north = uly + (ry - 1) * yr
    lon = west + (np.arange(shape[1]) + 0.5) * xr
    lat = north - (np.arange(shape[0]) + 0.5) * yr
    return np.meshgrid(lon, lat)


def binned(phi, x, edges, label, unit):
    """Circular mean and resultant length of phi within bins of x."""
    print(f"\n  {label:<22} n        mean phase   R      as cm LOS")
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (x >= lo) & (x < hi)
        n = int(sel.sum())
        if n < 500:
            continue
        z = np.exp(1j * phi[sel]).mean()
        ang, R = np.angle(z), abs(z)
        cm = ang / (2 * np.pi) * FRINGE_CM
        print(f"    {lo:7.0f}-{hi:<7.0f}{unit:<5} {n:>9,}  "
              f"{ang:+7.3f} rad  {R:5.3f}  {cm:+6.2f}")
        rows.append((0.5 * (lo + hi), ang, R, n))
    return rows


# A bin's mean angle is only meaningful if the phase in that bin is actually
# consistent. Below this R the angle is the direction of a random walk: it has
# a value, but that value carries no information, and unwrapping a sequence of
# such angles manufactures an impressive-looking trend out of nothing.
R_INTERPRETABLE = 0.15


def verdict(rows, what):
    if len(rows) < 4:
        print(f"    too few populated bins to judge {what}")
        return
    R = np.array([r[2] for r in rows])
    print(f"\n    resultant length R: median {np.median(R):.3f}, "
          f"max {R.max():.3f}")

    # Gate on R BEFORE looking at the angles. Note that comparing R against
    # 0.886/sqrt(n_pixels) would be far too lenient: 40 m pixels are strongly
    # spatially correlated, so a bin holding 300,000 pixels holds only a few
    # hundred INDEPENDENT samples of the atmosphere. The effective noise floor
    # is therefore of order 0.04, not 0.002.
    if np.median(R) < R_INTERPRETABLE:
        print(f"    -> phase within each bin is {100*(1-np.median(R)):.0f}% "
              f"uniformly distributed.")
        print(f"       The bin angles are not interpretable, so no statement")
        print(f"       about {what} can be made from them -- in either")
        print(f"       direction. This is an absence of signal, not evidence")
        print(f"       of a flat relationship.")
        return

    ang = np.unwrap(np.array([r[1] for r in rows]))
    swing = ang.max() - ang.min()
    steps = np.diff(ang)
    monotone = abs(np.sign(steps).sum()) / len(steps)
    print(f"    swing across bins: {swing:.2f} rad "
          f"({swing/(2*np.pi)*FRINGE_CM:+.2f} cm equivalent)")
    print(f"    monotonicity: {monotone:.2f}  (1 = every step same direction)")
    if swing < 0.5:
        print(f"    -> phase is consistent but FLAT across {what}. No trend.")
    elif monotone < 0.5:
        print(f"    -> phase is consistent but wanders non-monotonically with")
        print(f"       {what}. Structured, but not a {what} relationship.")
    else:
        print(f"    -> phase varies systematically and monotonically with "
              f"{what}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair", default="prepost")
    ap.add_argument("--suffix", default="full")
    ap.add_argument("--min-coh", type=float, default=0.3)
    a = ap.parse_args()

    d = f"{SNAP}/{a.pair}_{a.suffix}.data"
    i, meta = read_img(d, "i_ifg")
    q, _ = read_img(d, "q_ifg")
    coh, _ = read_img(d, "coh_")
    dem, _ = read_img(d, "elevation")

    phase = np.arctan2(q, i)
    lon, lat = grid(meta, i.shape)

    # Only pixels with enough coherence to carry phase at all. Below this the
    # phase is uniformly distributed and adds nothing but dilution.
    ok = (coh >= a.min_coh) & np.isfinite(coh) & ((i != 0) | (q != 0)) \
        & np.isfinite(dem) & (dem > -100)
    print(f"{a.pair}/{a.suffix}: {i.shape}, "
          f"{ok.sum():,} px at coh >= {a.min_coh}")

    phi = phase[ok]
    z_all = np.exp(1j * phi).mean()
    print(f"scene-wide resultant length: {abs(z_all):.4f}  "
          f"(1 = one phase everywhere, 0 = uniform noise)")

    # Degrees to km at this latitude; good enough for binning.
    dx = (lon[ok] - EPI_LON) * 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dy = (lat[ok] - EPI_LAT) * 110.57
    dist = np.hypot(dx, dy)
    elev = dem[ok]

    print(f"\ndistance to epicentre: {dist.min():.0f}-{dist.max():.0f} km")
    print(f"elevation:             {elev.min():.0f}-{elev.max():.0f} m")

    print("\n=== TEST 1: does phase vary with DISTANCE FROM THE RUPTURE? ===")
    print("    (deformation must; nothing else has any reason to)")
    rows = binned(phi, dist, np.arange(0, 161, 10), "distance", "km")
    verdict(rows, "distance from the epicentre")

    print("\n=== TEST 2: does phase vary with ELEVATION? ===")
    print("    (stratified atmosphere and DEM error both do)")
    rows = binned(phi, elev, np.array([0, 100, 250, 500, 750, 1000, 1250,
                                       1500, 2000, 3000]), "elevation", "m")
    verdict(rows, "elevation")

    print("\n=== how to conclude ===")
    print("  Test 1 trend, Test 2 flat   -> co-seismic deformation")
    print("  Test 2 trend, Test 1 flat   -> atmosphere or DEM error")
    print("  Both flat, R tiny           -> no resolvable signal at all")
    print("  Both trend                  -> confounded; the two are collinear")
    print("     here because the mountains sit away from the epicentre, so")
    print("     this pair alone cannot separate them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
