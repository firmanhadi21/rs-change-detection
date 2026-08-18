"""Coherence change across the Flores rupture: the damage proxy.

    change = coherence(pre-post) - coherence(pre-pre)

Both pairs span 12 days on the same track and subswath, so the comparison is
not confounded by temporal baseline -- the only difference between them is the
earthquake.

Two masks, and neither is optional:

  BASELINE >= 0.3   A pixel that was already incoherent has no room to drop, so
                    its difference carries no information. Without this, every
                    steep slope and water body reads as damage.
  BOTH FINITE       SNAP writes zeros outside the geocoded footprint.

Low co-event coherence on its own means nothing here: much of this terrain
decorrelates over 12 days regardless, which four years of interseismic work on
this frame established. What indicates damage is coherence that was high before
and collapsed across the event.

    python3 scripts/coherence_change.py
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


def read_img(data_dir, prefix):
    """Read a BEAM-DIMAP band. ENVI .hdr beside a flat .img."""
    hdrs = glob.glob(f"{data_dir}/{prefix}*.hdr")
    if not hdrs:
        raise SystemExit(f"no {prefix}* in {data_dir}")
    hdr = hdrs[0]
    meta = {}
    for line in open(hdr, errors="ignore"):
        if "=" in line:
            k, _, v = line.partition("=")
            meta[k.strip().lower()] = v.strip()
    w, h = int(meta["samples"]), int(meta["lines"])
    # SNAP writes BIG-endian (byte order = 1), not little. Reading it as
    # little-endian silently produced coherence values around 1e38 instead of
    # 0-1 -- plausible-looking arrays, entirely wrong numbers.
    endian = ">" if meta.get("byte order", "0").strip() == "1" else "<"
    kind = {"4": "f4", "5": "f8", "12": "u2", "2": "i2"}.get(
        meta.get("data type", "4").strip(), "f4")
    dtype = endian + kind
    img = hdr[:-4] + ".img"
    a = np.fromfile(img, dtype=dtype)
    if a.size != w * h:
        raise SystemExit(f"{img}: {a.size} values, expected {w*h}")
    return a.reshape(h, w), meta, os.path.basename(hdr)[:-4]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-baseline", type=float, default=0.3)
    ap.add_argument("--drop", type=float, default=0.3,
                    help="coherence loss counted as candidate damage")
    ap.add_argument("--suffix", default="coh",
                    help="'coh' for the IW2-only run, 'full' for all three "
                         "subswaths merged")
    a = ap.parse_args()

    pre, meta, npre = read_img(f"{SNAP}/prepre_{a.suffix}.data", "coh_")
    post, _, npost = read_img(f"{SNAP}/prepost_{a.suffix}.data", "coh_")
    print(f"baseline : {npre}   {pre.shape}")
    print(f"co-event : {npost}  {post.shape}")

    # Terrain-Correction sizes each product to its own data footprint, so the
    # two differ by a few pixels even from identical settings. Align on the
    # GEOCODING rather than assuming equal shapes -- comparing them by array
    # index would offset the whole scene by the difference and smear the
    # result across every edge in the image.
    def geo(meta):
        m = meta["map info"].strip("{}").split(",")
        # {proj, ref_x, ref_y, ulx, uly, xres, yres, datum, units}
        return (float(m[3]), float(m[4]), float(m[5]), float(m[6]),
                float(m[1]), float(m[2]))

    if pre.shape != post.shape:
        ulx1, uly1, xr1, yr1, rx1, ry1 = geo(meta)
        _, meta2, _ = read_img(f"{SNAP}/prepost_{a.suffix}.data", "coh_")
        ulx2, uly2, xr2, yr2, rx2, ry2 = geo(meta2)
        if abs(xr1 - xr2) > 1e-9:
            raise SystemExit(f"pixel sizes differ: {xr1} vs {xr2}")

        # ENVI reference pixel is 1-based and may be fractional; convert each
        # corner to the true upper-left before differencing.
        west1, north1 = ulx1 - (rx1 - 1) * xr1, uly1 + (ry1 - 1) * yr1
        west2, north2 = ulx2 - (rx2 - 1) * xr2, uly2 + (ry2 - 1) * yr2

        west, north = max(west1, west2), min(north1, north2)
        c1, r1 = int(round((west - west1) / xr1)), int(round((north1 - north) / yr1))
        c2, r2 = int(round((west - west2) / xr2)), int(round((north2 - north) / yr2))
        h = min(pre.shape[0] - r1, post.shape[0] - r2)
        w = min(pre.shape[1] - c1, post.shape[1] - c2)
        print(f"\ngrids differ ({pre.shape} vs {post.shape}); aligned on "
              f"geocoding, offsets pre({r1},{c1}) post({r2},{c2}) -> {h}x{w}")
        pre = pre[r1:r1 + h, c1:c1 + w]
        post = post[r2:r2 + h, c2:c2 + w]

    observed = (pre > 0) & (post > 0) & np.isfinite(pre) & np.isfinite(post)
    print(f"\nobserved on both: {observed.sum():,} px "
          f"({100*observed.mean():.1f}% of frame)")

    for name, arr in (("baseline", pre), ("co-event", post)):
        v = arr[observed]
        print(f"  {name:9} median {np.median(v):.3f}  "
              f"p25 {np.percentile(v,25):.3f}  p75 {np.percentile(v,75):.3f}")

    usable = observed & (pre >= a.min_baseline)
    print(f"\nusable (baseline >= {a.min_baseline}): {usable.sum():,} px "
          f"({100*usable.sum()/max(observed.sum(),1):.1f}% of observed)")
    if usable.sum() < 1000:
        print("  too little coherent ground to judge damage")
        return 1

    change = np.where(usable, post - pre, np.nan)
    d = change[np.isfinite(change)]
    print(f"\n=== coherence change (co-event minus baseline) ===")
    for q in (1, 5, 25, 50, 75, 95):
        print(f"    p{q:<3} {np.percentile(d, q):+.3f}")
    print(f"    mean {d.mean():+.3f}   std {d.std():.3f}")

    dropped = int((d <= -a.drop).sum())
    print(f"\n  pixels losing >= {a.drop}: {dropped:,} "
          f"({100*dropped/d.size:.2f}% of usable)")
    px_ha = (40 * 40) / 1e4
    print(f"  area: {dropped * px_ha:,.0f} ha at 40 m")

    # The decisive test. Shaking damage falls off with distance from the
    # rupture; weather does not know where the rupture was. A frame-wide median
    # tells you the size of the drop but nothing about its cause, so bin it.
    m = meta["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr
    rows, cols = np.nonzero(usable)
    lon = west + (cols + 0.5) * xr
    lat = north - (rows + 0.5) * yr
    dist = np.hypot((lon - 121.3517) * 111.32 * np.cos(np.deg2rad(-8.31)),
                    (lat + 8.3101) * 110.57)
    vals = (post - pre)[usable]

    print("\n=== coherence change vs DISTANCE FROM THE RUPTURE ===")
    print("  distance        n         median    frac losing >= "
          f"{a.drop}")
    prof = []
    for lo in range(20, 170, 15):
        sel = (dist >= lo) & (dist < lo + 15)
        if sel.sum() < 2000:
            continue
        v = vals[sel]
        frac = (v <= -a.drop).mean()
        print(f"    {lo:3d}-{lo+15:<3d} km  {sel.sum():>9,}   "
              f"{np.median(v):+.3f}     {100*frac:5.2f}%")
        prof.append((lo, np.median(v), frac))

    if len(prof) >= 4:
        near = np.mean([p[1] for p in prof[:2]])
        far = np.mean([p[1] for p in prof[-2:]])
        print(f"\n  nearest bins {near:+.3f}   farthest bins {far:+.3f}"
              f"   difference {near-far:+.3f}")
        if near < far - 0.05:
            print("  -> loss concentrates near the rupture. Consistent with")
            print("     shaking damage; map the clusters.")
        else:
            print("  -> no gradient with distance. The drop is frame-wide,")
            print("     which damage cannot produce and weather can. Do not")
            print("     report this as damage.")

    out = f"{SNAP}/coherence_change_{a.suffix}.img"
    change.astype("float32").tofile(out)
    hdr = out[:-4] + ".hdr"
    src_hdr = glob.glob(f"{SNAP}/prepre_{a.suffix}.data/coh_*.hdr")[0]
    open(hdr, "w").write(open(src_hdr).read())
    print(f"\nwrote {out}")

    print("\n=== reading ===")
    # A real earthquake signal is spatially clustered. Scattered single pixels
    # at this rate are what an undisturbed scene looks like.
    if d.mean() < -0.05:
        print("  Coherence fell broadly across the frame. Check whether this")
        print("  is the event or a seasonal/weather difference between the")
        print("  two pairs before attributing it to damage.")
    elif dropped / d.size > 0.02:
        print("  A minority of pixels lost coherence sharply. Map them and")
        print("  check whether they CLUSTER -- clustered loss near the coast")
        print("  facing the epicentre is the signature worth reporting;")
        print("  scattered singletons are noise.")
    else:
        print("  Little coherence loss beyond the noise level. Either damage")
        print("  is below what 40 m C-band resolves, or the shaking onshore")
        print("  was not destructive at this scale.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
