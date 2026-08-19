"""Is the PyGMTSAR LOS field the earthquake, or a ramp across one subswath?

PyGMTSAR unwrapped the 6->18 Aug pair and produced a smooth line-of-sight
field reaching ~0.08 m, strongest toward the epicentre. That is far above the
+/-1.4 cm bound the SNAP analysis established, so one of the two is wrong and
the difference has to be settled rather than argued.

The concern is specific, not general. The wrapped phase for this pair is
speckle with no visible fringes; the displacement looks smooth because a
Gaussian filter was applied before unwrapping. Unwrapping a noise field
returns a smooth surface -- smoothness is imposed by the filter and is not
evidence of signal. Worse, this covers ONE subswath ~90 km across, and across
a single subswath an orbital-baseline error, an ionospheric gradient and a
genuine far-field deformation gradient all look like the same tilted plane.

So, three tests, in increasing order of how hard they are to fake:

  1. HOW MUCH IS A PLANE? Fit a first-order surface. Deformation from a
     compact source is curved -- it decays roughly as 1/r^2 -- and a plane
     should explain only part of it. A ramp is a plane by definition, so a
     variance-explained near 1 is close to proof.

  2. DOES IT DECAY WITH DISTANCE? Bin by range from the epicentre. A source
     falls off monotonically; a ramp is linear in map coordinates and depends
     on which way the swath happens to point, not where the rupture was.

  3. WHAT SURVIVES DERAMPING? Remove the plane and look again near the
     rupture. Real near-field deformation leaves a localised residual; a ramp
     leaves noise.

    conda run -n base python scripts/check_pygmtsar_los.py \\
        "~/Downloads/los (2).tif"
"""

import argparse
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                   # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

EPI_LON, EPI_LAT = 121.3517, -8.3101
KM_LAT = 110.57
WAVELENGTH_CM = 5.5465


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?",
                    default=os.path.expanduser("~/Downloads/los (2).tif"))
    a = ap.parse_args()
    path = os.path.expanduser(a.path)

    with rasterio.open(path) as src:
        z = src.read(1).astype("float64")
        print(f"{os.path.basename(path)}  {src.shape}  {src.crs}  "
              f"{abs(src.transform.a):.0f} m")
        nod = src.nodata
        rows, cols = np.mgrid[0:src.height, 0:src.width]
        xs = src.transform.c + (cols + .5) * src.transform.a
        ys = src.transform.f + (rows + .5) * src.transform.e
        lon, lat = warp_transform(src.crs, "EPSG:4326",
                                  xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(z.shape)
    lat = np.array(lat).reshape(z.shape)

    ok = np.isfinite(z)
    if nod is not None:
        ok &= z != nod
    ok &= z != 0
    v = z[ok]
    print(f"valid {ok.sum():,} px ({100*ok.mean():.1f}%)")
    unit = "m" if np.nanpercentile(np.abs(v), 99) < 5 else "?"
    scale = 100.0 if unit == "m" else 1.0
    print(f"range {v.min()*scale:+.2f} .. {v.max()*scale:+.2f} cm  "
          f"(p1 {np.percentile(v,1)*scale:+.2f}, "
          f"p99 {np.percentile(v,99)*scale:+.2f})")
    print(f"peak-to-peak {(v.max()-v.min())*scale:.1f} cm = "
          f"{(v.max()-v.min())*scale/(WAVELENGTH_CM/2):.1f} fringes")

    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    X = (lon[ok] - EPI_LON) * kx
    Y = (lat[ok] - EPI_LAT) * KM_LAT
    d = np.hypot(X, Y)
    print(f"distance from epicentre: {d.min():.0f}-{d.max():.0f} km")

    # ---- 1. how much of it is simply a plane? ---------------------------
    A = np.column_stack([np.ones_like(X), X, Y])
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    fit = A @ coef
    res = v - fit
    r2 = 1 - res.var() / v.var()
    print(f"\n=== 1. planar fit ===")
    print(f"  gradient {coef[1]*scale:+.4f} cm/km east, "
          f"{coef[2]*scale:+.4f} cm/km north")
    print(f"  variance explained by a PLANE: {100*r2:.1f}%")
    print(f"  residual sd after deramping: {res.std()*scale:.2f} cm "
          f"(was {v.std()*scale:.2f} cm)")
    if r2 > 0.9:
        print("  -> a plane explains nearly all of it. Deformation from a")
        print("     compact source is curved; this is a ramp.")
    elif r2 > 0.6:
        print("  -> mostly planar, with something left over. Check test 3.")
    else:
        print("  -> not mainly a plane. Curvature is present.")

    # ---- 2. does it decay with distance? --------------------------------
    print(f"\n=== 2. profile against distance from the rupture ===")
    print("   distance          n      median raw   median deramped")
    prof = []
    for lo in range(int(d.min() // 10 * 10), int(d.max()) + 10, 10):
        s = (d >= lo) & (d < lo + 10)
        if s.sum() < 500:
            continue
        print(f"    {lo:3d}-{lo+10:<3d} km  {int(s.sum()):>8,}   "
              f"{np.median(v[s])*scale:+8.2f}    "
              f"{np.median(res[s])*scale:+8.2f}")
        prof.append((lo, float(np.median(v[s])), float(np.median(res[s]))))

    if len(prof) >= 3:
        raw = np.array([p[1] for p in prof]) * scale
        drp = np.array([p[2] for p in prof]) * scale
        print(f"\n  raw      near {raw[0]:+.2f} -> far {raw[-1]:+.2f} cm "
              f"(swing {raw.max()-raw.min():.2f})")
        print(f"  deramped near {drp[0]:+.2f} -> far {drp[-1]:+.2f} cm "
              f"(swing {drp.max()-drp.min():.2f})")

    # ---- 3. what survives deramping, near the rupture? -------------------
    print(f"\n=== 3. residual after removing the plane ===")
    near = d <= np.percentile(d, 20)
    far = d >= np.percentile(d, 80)
    print(f"  nearest 20% of pixels: median {np.median(res[near])*scale:+.2f} "
          f"cm, sd {res[near].std()*scale:.2f}")
    print(f"  farthest 20%:          median {np.median(res[far])*scale:+.2f} "
          f"cm, sd {res[far].std()*scale:.2f}")
    sep = abs(np.median(res[near]) - np.median(res[far])) * scale
    print(f"  separation {sep:.2f} cm against residual sd "
          f"{res.std()*scale:.2f} cm")
    if sep > 2 * res.std() * scale:
        print("  -> a localised signal survives deramping. Worth modelling.")
    else:
        print("  -> nothing localised survives. What looked like a source was")
        print("     the plane, and the plane is not attributable to the")
        print("     earthquake from one subswath alone.")

    print("\n=== the honest limit of this test ===")
    print("  A ramp and a FAR-FIELD deformation gradient are genuinely")
    print("  degenerate over ~90 km of a single subswath: both are close to")
    print("  linear. What breaks the degeneracy is a second look direction,")
    print("  or ground truth (GNSS). Descending path 163 is the cheap one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
