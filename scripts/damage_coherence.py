"""Coherence-change damage detection, aimed at where damage would actually be.

The whole-island median was too blunt to answer this. Damage from shaking is
concentrated in SETTLEMENTS, which are a tiny fraction of pixels; a median over
every land pixel on Flores dilutes a real town-scale signal into nothing. Three
refinements, each addressing a specific way the blunt test fails:

BUILT-UP PROXY. Vegetation decorrelates over 12 days regardless, so its
coherence change is dominated by growth and wind. Buildings and bare ground
hold coherence, which is exactly why damage shows up as a DROP there. Restrict
to pixels whose baseline coherence is high; without a land-cover layer, high
baseline coherence is itself the best available proxy for built-up ground.

FRAME-WIDE OFFSET REMOVED. Coherence fell ~0.072 everywhere between these
pairs -- weather, not the earthquake. Damage is what remains AFTER subtracting
that. Leaving it in makes every town look damaged; subtracting it means each
town is judged against the island that day, which is the correct comparison.

TOWNS BY NAME. A per-town number is checkable by someone who was there, which
a percentile of a distribution is not. The nearest town to this rupture is what
the analysis lives or dies on.

WHAT THIS CANNOT DO, stated plainly: with only three scenes there is no CONTROL
coherence-change field. 25 Jul->6 Aug and 6 Aug->18 Aug are the only two
12-day pairs available, and the first is the baseline of the second. So the
normal variability of a 12-day coherence CHANGE over Flores is unmeasured here,
and "anomalous" below means anomalous against the frame, not against history.
A fourth scene (13 Jul 2026) would fix this and is the single highest-value
addition to this analysis.

    python3 scripts/damage_coherence.py
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

# Approximate town centres, Flores and adjacent islands. Coordinates are
# nominal town centres, good to ~1 km, which is well inside the radius used.
TOWNS = [
    ("Mbay",        121.3833, -8.4667),
    ("Riung",       121.0333, -8.4167),
    ("Boawae",      121.1333, -8.7667),
    ("Bajawa",      120.9856, -8.7906),
    ("Aimere",      120.9167, -8.8333),
    ("Ende",        121.6626, -8.8432),
    ("Nangapanda",  121.5167, -8.8167),
    ("Maumere",     122.2111, -8.6199),
    ("Larantuka",   122.9822, -8.3405),
    ("Wolowaru",    121.9000, -8.7833),
]


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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suffix", default="full")
    ap.add_argument("--builtup", type=float, default=0.5,
                    help="baseline coherence marking stable/built-up ground")
    ap.add_argument("--radius", type=float, default=3.0,
                    help="km around each town centre")
    ap.add_argument("--cell-km", type=float, default=0.4)
    a = ap.parse_args()

    pre, meta = read_img(f"{SNAP}/prepre_{a.suffix}.data", "coh_")
    post, meta2 = read_img(f"{SNAP}/prepost_{a.suffix}.data", "coh_")
    h = min(pre.shape[0], post.shape[0]); w = min(pre.shape[1], post.shape[1])
    pre, post = pre[:h, :w], post[:h, :w]

    m = meta2["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))

    obs = (pre > 0) & (post > 0) & np.isfinite(pre) & np.isfinite(post)
    chg = np.where(obs, post - pre, np.nan)

    # The weather offset, measured on ordinary coherent land. Using the median
    # makes it robust to whatever localised change may exist.
    land = obs & (pre >= 0.3)
    offset = float(np.nanmedian(chg[land]))
    print(f"observed {obs.sum():,} px; frame-wide median change "
          f"{offset:+.3f} (removed as weather)")

    built = obs & (pre >= a.builtup)
    print(f"built-up proxy (baseline >= {a.builtup}): {built.sum():,} px "
          f"({100*built.sum()/obs.sum():.1f}% of observed)")
    res = chg - offset          # residual after removing the frame-wide shift

    rb = np.nanmedian(res[built])
    sb = 1.4826 * np.nanmedian(np.abs(res[built] - rb))
    print(f"residual over built-up: median {rb:+.3f}, robust sigma {sb:.3f}")

    rows = np.arange(h)[:, None]; cols = np.arange(w)[None, :]
    lon = west + (cols + .5) * xr
    lat = north - (rows + .5) * yr

    # ---- does the residual depend on distance, within built-up ground? ----
    dist = np.hypot((lon - EPI_LON) * kx, (lat - EPI_LAT) * KM_LAT)
    print("\n=== built-up residual vs distance (weather removed) ===")
    print("  distance         n        median    p10")
    prof = []
    for lo in range(20, 175, 15):
        s = built & (dist >= lo) & (dist < lo + 15)
        n = int(s.sum())
        if n < 1500:
            continue
        v = res[s]
        print(f"   {lo:3d}-{lo+15:<3d} km  {n:>8,}   {np.median(v):+.3f}   "
              f"{np.percentile(v,10):+.3f}")
        prof.append((lo, float(np.median(v))))
    if len(prof) >= 4:
        near = np.mean([p[1] for p in prof[:2]])
        far = np.mean([p[1] for p in prof[-2:]])
        print(f"  nearest {near:+.3f}   farthest {far:+.3f}   "
              f"difference {near-far:+.3f}")

    # ---------------------------------- per town ---------------------------
    print(f"\n=== towns, built-up pixels within {a.radius:.0f} km ===")
    print("  town          dist_epi     n    median res   p10    frac<-0.2")
    trows = []
    for name, tlon, tlat in TOWNS:
        d = np.hypot((lon - tlon) * kx, (lat - tlat) * KM_LAT)
        s = built & (d <= a.radius)
        n = int(s.sum())
        de = float(np.hypot((tlon - EPI_LON) * kx, (tlat - EPI_LAT) * KM_LAT))
        if n < 200:
            print(f"  {name:<12} {de:6.0f} km  {n:>6,}   "
                  f"-- too few built-up pixels to judge --")
            trows.append((name, de, n, np.nan, np.nan))
            continue
        v = res[s]
        med = float(np.median(v))
        frac = float((v <= -0.2).mean())
        print(f"  {name:<12} {de:6.0f} km  {n:>6,}   {med:+.3f}     "
              f"{np.percentile(v,10):+.3f}   {100*frac:5.1f}%")
        trows.append((name, de, n, med, frac))

    ok = [t for t in trows if np.isfinite(t[3])]
    if len(ok) >= 4:
        dd = np.array([t[1] for t in ok]); mm = np.array([t[3] for t in ok])
        r = float(np.corrcoef(dd, mm)[0, 1])
        worst = min(ok, key=lambda t: t[3])
        print(f"\n  correlation(distance, median residual) = {r:+.3f}")
        print(f"  most negative town: {worst[0]} at {worst[3]:+.3f}, "
              f"{worst[3]/sb:+.1f} robust sigma")
        print("  Damage would make this correlation clearly POSITIVE (more")
        print("  negative residual near the rupture) and put the nearest towns")
        print("  at the bottom of the list.")

    # ------------------------- clustering on a 400 m grid ------------------
    cy = max(1, int(round(a.cell_km / (yr * KM_LAT))))
    cx = max(1, int(round(a.cell_km / (xr * kx))))
    nh, nw = h // cy, w // cx
    drop = (built & (res <= -0.2))[:nh * cy, :nw * cx]
    cnt = built[:nh * cy, :nw * cx]
    dsum = drop.reshape(nh, cy, nw, cx).sum(axis=(1, 3))
    csum = cnt.reshape(nh, cy, nw, cx).sum(axis=(1, 3))
    frac = np.where(csum >= 20, dsum / np.maximum(csum, 1), np.nan)
    good = np.isfinite(frac)
    print(f"\n=== spatial clustering, {a.cell_km*1000:.0f} m cells ===")
    print(f"  cells with >=20 built-up pixels: {good.sum():,}")

    # Moran's I: is the drop fraction clustered, or scattered? Damage clusters.
    f = np.where(good, frac, np.nan)
    fm = np.nanmean(f)
    z = np.where(good, f - fm, 0.0)
    num = 0.0; wsum = 0.0
    for dr, dc in ((0, 1), (1, 0)):
        A = z[:nh - dr, :nw - dc]; B = z[dr:, dc:]
        M = good[:nh - dr, :nw - dc] & good[dr:, dc:]
        num += float((A[M] * B[M]).sum()) * 2
        wsum += float(M.sum()) * 2
    den = float((z[good] ** 2).sum())
    I = (good.sum() / wsum) * (num / den) if den > 0 and wsum > 0 else np.nan
    print(f"  mean drop fraction {fm:.3f}")
    print(f"  Moran's I = {I:+.3f}   (0 = scattered, ->1 = strongly clustered)")
    print("  Note: atmosphere clusters too, so a high I alone is NOT damage;")
    print("  it must ALSO concentrate near the rupture, which the distance")
    print("  table above tests.")

    hi = np.nanpercentile(f[good], 99.5)
    yy, xx = np.nonzero(good & (f >= hi))
    print(f"\n  worst 0.5% of cells (drop fraction >= {hi:.2f}): {len(yy):,}")
    if len(yy):
        clon = west + (xx + .5) * cx * xr
        clat = north - (yy + .5) * cy * yr
        cd = np.hypot((clon - EPI_LON) * kx, (clat - EPI_LAT) * KM_LAT)
        print(f"    their distance from epicentre: median {np.median(cd):.0f} "
              f"km, range {cd.min():.0f}-{cd.max():.0f}")
        print(f"    all built-up ground for comparison: median "
              f"{np.median(dist[built]):.0f} km")
        print("    If these matched damage they would sit much closer to the")
        print("    rupture than built-up ground in general does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
