"""Damage detection against each pixel's OWN coherence history, not the frame.

The three-scene analysis could only ask "is this pixel's drop large compared to
the island?". That question misranks: ground that swings 0.2-0.6 every cycle
looks alarming when it lands at 0.2, while a roof steady at 0.55 +/- 0.04
dropping to 0.45 looks fine -- when the second is the anomaly. With a history
of normal 12-day coherence the right question becomes available:

    z = (coh_coevent - mean(coh_baseline)) / std(coh_baseline)

Farmland that decorrelates every cycle has a large sd and needs a huge drop to
register. A building roof with a tiny sd registers on a small one.

READS HyP3 GeoTIFF, not SNAP BEAM-DIMAP. Three things that follow from that
and are not cosmetic:

  GRIDS DIFFER BETWEEN PAIRS. HyP3 sizes each product to its own granule
  footprint, so the 13 baseline rasters are not co-registered by array index.
  Differencing them positionally would offset the whole scene by the mismatch
  and smear the result along every edge -- the same failure that silently
  dropped 387 interferograms from the interseismic stack. Everything is
  reprojected onto the co-event grid first, NEAREST-neighbour, because
  interpolating coherence invents values that were never measured.

  FRAMES MUST NOT BE POOLED. 1148 and 1153 are different footprints covering
  different ground -- 1153 has the northern coast including Mbay and Riung,
  1148 the centre and south. They are processed separately and the towns are
  reported under whichever frame actually sees them. Frames are identified by
  the acquisition SECOND in the granule name (1148 ~10:16:45, 1153 ~10:17:10),
  not by the job variant tag, which distinguishes when a job was bought rather
  than where it points.

  ZERO IS NODATA, not zero coherence. HyP3 writes 0 outside the footprint and
  over masked water; treating those as measurements would drag every mean down.

MATCHED TEMPORAL BASELINE is assumed, not checked here: submit_coherence_
baseline.py buys only 12-day pairs, and the co-event pair is itself a 12-day
S1D->S1D pair, so it passes through the same filter and the same processor.

    conda run -n base python scripts/coherence_zscore.py --frame 1153
    conda run -n base python scripts/coherence_zscore.py --frame 1148 --season dry
"""

import argparse
import glob
import os
import re
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import Resampling, reproject
    from rasterio.warp import transform as warp_transform
except ImportError:                                    # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

BASE = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/baseline/hyp3")
EPI_LON, EPI_LAT = 121.3517, -8.3101
KM_LAT = 110.57
COEVENT = "20260806_20260818"

# Frames differ by ~25 s of along-track acquisition time.
FRAME_SECOND = {1148: "1016", 1153: "1017"}

TOWNS = [("Mbay", 121.3833, -8.4667), ("Riung", 121.0333, -8.4167),
         ("Boawae", 121.1333, -8.7667), ("Bajawa", 120.9856, -8.7906),
         ("Ende", 121.6626, -8.8432), ("Maumere", 122.2111, -8.6199),
         ("Larantuka", 122.9822, -8.3405)]

# Flores is wet roughly Nov-Apr. The co-event pair is August, so a wet-season
# baseline inflates each pixel's sd and shrinks every z -- hiding damage.
DRY_MONTHS = (5, 6, 7, 8, 9, 10)


def products(frame):
    """Every (dates, corr.tif) for one frame, keyed by pair date range."""
    want = FRAME_SECOND[frame]
    out = {}
    for d in sorted(glob.glob(f"{BASE}/earthchange-*")):
        if not os.path.isdir(d):
            continue
        tifs = glob.glob(f"{d}/*_corr.tif")
        if not tifs:
            continue
        base = os.path.basename(tifs[0])
        m = re.search(r"_(\d{8})T(\d{6})_", base)
        if not m or not m.group(2).startswith(want):
            continue
        dates = re.search(r"earthchange-(\d{8}_\d{8})", os.path.basename(d))
        if dates:
            out[dates.group(1)] = tifs[0]
    return out


def onto(path, ref):
    """Read a coherence raster resampled onto the reference grid."""
    dst = np.zeros((ref["height"], ref["width"]), dtype="float32")
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=dst,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=ref["transform"], dst_crs=ref["crs"],
                  # NEAREST: coherence is a measurement, and bilinear would
                  # blend footprint edges with the zeros beyond them.
                  resampling=Resampling.nearest)
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1153, choices=(1148, 1153))
    ap.add_argument("--season", default="all", choices=("all", "dry"))
    ap.add_argument("--min-mean", type=float, default=0.35)
    ap.add_argument("--z", type=float, default=-3.0)
    ap.add_argument("--radius", type=float, default=3.0)
    a = ap.parse_args()

    found = products(a.frame)
    if not found:
        sys.exit(f"no frame-{a.frame} products under {BASE}")
    co = found.pop(COEVENT, None)

    base_keys = sorted(found)
    if a.season == "dry":
        base_keys = [k for k in base_keys
                     if int(k[4:6]) in DRY_MONTHS and int(k[13:15]) in DRY_MONTHS]
    print(f"frame {a.frame}: {len(found)+bool(co)} products, "
          f"{len(base_keys)} baseline pairs ({a.season} season)")
    for k in base_keys:
        print(f"    {k[:8]} -> {k[9:]}")
    if co is None:
        print(f"\n  CO-EVENT pair {COEVENT} NOT on disk yet.")
        print("  Reporting baseline statistics only, so the reader can be")
        print("  verified now; re-run once the co-event product lands.")
    if len(base_keys) < 3:
        print(f"\n  WARNING: {len(base_keys)} baseline pairs. A standard "
              f"deviation from n<3 is not a standard deviation.")

    ref_path = co or found[base_keys[0]]
    with rasterio.open(ref_path) as src:
        ref = dict(transform=src.transform, crs=src.crs,
                   height=src.height, width=src.width)
        res = abs(src.transform.a)
    print(f"\nreference grid: {ref['height']}x{ref['width']} @ {res:.0f} m, "
          f"{ref['crs']}")

    stack = np.stack([onto(found[k], ref) for k in base_keys])
    # 0 is nodata in HyP3 coherence, not a measurement of zero coherence.
    stack = np.where(stack > 0, stack, np.nan)

    with np.errstate(invalid="ignore"):
        n_obs = np.sum(np.isfinite(stack), axis=0)
        mean = np.nanmean(stack, axis=0)
        # ddof=1: the population formula understates spread and would inflate
        # every z toward significance.
        sd = np.nanstd(stack, axis=0, ddof=1)

    complete = n_obs == len(base_keys)
    print(f"pixels observed in ALL {len(base_keys)} baseline pairs: "
          f"{int(complete.sum()):,} ({100*complete.mean():.1f}% of grid)")

    usable = complete & (mean >= a.min_mean) & (sd > 0.01)
    print(f"usable (mean >= {a.min_mean}, sd > 0.01): {int(usable.sum()):,}")
    if usable.sum() < 500:
        sys.exit("too little stable ground to judge")
    print(f"  baseline mean over usable: {np.nanmedian(mean[usable]):.3f}")
    print(f"  baseline sd   over usable: {np.nanmedian(sd[usable]):.3f}")

    rows, cols = np.mgrid[0:ref["height"], 0:ref["width"]]
    xs = ref["transform"].c + (cols + .5) * ref["transform"].a
    ys = ref["transform"].f + (rows + .5) * ref["transform"].e
    lon, lat = warp_transform(ref["crs"], "EPSG:4326",
                              xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(xs.shape)
    lat = np.array(lat).reshape(ys.shape)
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dist = np.hypot((lon - EPI_LON) * kx, (lat - EPI_LAT) * KM_LAT)

    if co is None:
        print("\n=== baseline variability by distance (no co-event yet) ===")
        print("  distance          n     median sd")
        for lo in range(10, 190, 20):
            s = usable & (dist >= lo) & (dist < lo + 20)
            if s.sum() < 300:
                continue
            print(f"   {lo:3d}-{lo+20:<3d} km  {int(s.sum()):>8,}   "
                  f"{np.nanmedian(sd[s]):.3f}")
        print("\nReader verified. Re-run when the co-event product lands.")
        return 0

    obs = onto(co, ref)
    obs = np.where(obs > 0, obs, np.nan)
    z = np.where(usable & np.isfinite(obs), (obs - mean) / sd, np.nan)
    zz = z[np.isfinite(z)]
    print(f"\n=== z-score, {len(base_keys)} baseline pairs ===")
    for q in (1, 5, 25, 50, 75):
        print(f"    p{q:<3} {np.percentile(zz, q):+.2f}")
    flagged = int((zz <= a.z).sum())
    print(f"  z <= {a.z}: {flagged:,} px ({100*flagged/zz.size:.2f}%)"
          f"   {flagged*res*res/1e4:,.0f} ha")

    print("\n=== z against distance from the rupture ===")
    print("  distance          n      median z   frac z<=-3")
    for lo in range(10, 190, 20):
        s = np.isfinite(z) & (dist >= lo) & (dist < lo + 20)
        if s.sum() < 300:
            continue
        v = z[s]
        print(f"   {lo:3d}-{lo+20:<3d} km  {int(s.sum()):>8,}   "
              f"{np.nanmedian(v):+.2f}      {100*np.nanmean(v <= a.z):5.2f}%")

    print(f"\n=== towns within {a.radius:.0f} km ===")
    print("  town          dist_epi       n    median z   frac z<=-3")
    for name, tlon, tlat in TOWNS:
        d = np.hypot((lon - tlon) * kx, (lat - tlat) * KM_LAT)
        s = np.isfinite(z) & (d <= a.radius)
        de = float(np.hypot((tlon - EPI_LON) * kx, (tlat - EPI_LAT) * KM_LAT))
        if s.sum() < 50:
            print(f"  {name:<12} {de:6.0f} km  {int(s.sum()):>6,}   "
                  f"-- not covered by frame {a.frame} --")
            continue
        v = z[s]
        print(f"  {name:<12} {de:6.0f} km  {int(s.sum()):>6,}   "
              f"{np.nanmedian(v):+.2f}      {100*np.nanmean(v <= a.z):5.2f}%")

    out = os.path.join(os.path.dirname(BASE),
                       f"coherence_z_frame{a.frame}_{a.season}.tif")
    with rasterio.open(out, "w", driver="GTiff", height=ref["height"],
                       width=ref["width"], count=1, dtype="float32",
                       crs=ref["crs"], transform=ref["transform"],
                       nodata=np.nan, compress="deflate") as dst:
        dst.write(z.astype("float32"), 1)
    print(f"\nwrote {out}")
    print("\nDamage shows as z falling off WITH DISTANCE and towns near the")
    print("rupture below the rest. A flat profile is weather, however large.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
