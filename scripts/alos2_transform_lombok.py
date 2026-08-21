"""Geocode the Lombok pair through insardev's transform, and check the result.

This is the first end-to-end run: scan, align, project both dates onto a
common geographic grid, remove topographic and tidal phase, write a Zarr
stack. If it works, an interferogram is one multiplication away.

WHAT IS CHECKED, and why each one is not redundant:

  * The stack exists and both dates are in it. A transform that silently wrote
    an empty grid still produces a valid Zarr.
  * Coverage is non-trivial. cv2.remap fills out-of-range pixels with NaN, so
    a wrong offset model geocodes to a mostly-empty grid rather than failing.
  * The two dates overlap. They are aligned to the same reference geometry, so
    disagreeing footprints means the alignment did not transfer.
  * The interferometric phase is not noise. This is the only check that
    exercises the whole chain at once: form ref * conj(rep) and measure the
    resultant length of the phasor over a window. Uniform noise gives R near
    0; correlated ground gives R well above it. Geocoding that is subtly wrong
    -- half a pixel of misregistration, a phase ramp applied twice -- shows up
    here and nowhere earlier.

    conda run -n insardev-test python scripts/alos2_transform_lombok.py
"""

import argparse
import os
import shutil
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1")
RAW = os.path.join(BASE, "raw")
DEM = os.path.join(BASE, "topo", "dem.grd")
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/alos2_lombok_stack.zarr")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--resolution", type=int, nargs=2, default=(8, 16),
                    help="metres per pixel. Must stay near the native ~4x3 m. "
                         "cv2.remap SAMPLES rather than averages, so a coarse "
                         "output grid aliases the speckle and the two dates "
                         "decorrelate -- 30 m put 0.6%% of looks above 0.3 "
                         "coherence where GMTSAR gets 22.5%%, while leaving "
                         "the MEDIAN coherence looking correct.")
    ap.add_argument("--chunk", type=int, default=4096)
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--bbox", type=float, nargs=4, default=None,
                    help="lon_min lat_min lon_max lat_max, to cut the run down")
    ap.add_argument("--keep", action="store_true",
                    help="reuse an existing stack instead of rebuilding")
    ap.add_argument("--no-topo", action="store_true",
                    help="skip topographic phase removal. It is applied to "
                         "the SECONDARY only (the reference is passed "
                         "baseline_params=None), so a wrong baseline injects "
                         "spurious fringes into one date and decorrelates the "
                         "pair -- turning it off isolates that.")
    ap.add_argument("--no-tidal", action="store_true")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    from earthchange.alos2_transform import ALOS2

    if not os.path.exists(DEM):
        sys.exit(f"missing DEM {DEM}")

    stack = ALOS2(RAW, DEM=DEM)
    dates = sorted(stack.df.startTime.dt.date.astype(str).unique())
    ref = dates[0]
    print(f"\ndates {dates}, reference {ref}")
    print(f"output {a.out}")

    if os.path.exists(a.out) and not a.keep:
        shutil.rmtree(a.out)

    if not os.path.exists(a.out):
        t0 = time.perf_counter()
        stack.transform(
            a.out, ref=ref,
            resolution=tuple(a.resolution),
            chunk=(a.chunk, a.chunk),
            bbox=a.bbox,
            n_jobs=a.n_jobs,
            remove_topo_phase=not a.no_topo,
            remove_tidal_phase=not a.no_tidal,
            debug=a.debug)
        print(f"\ntransform took {time.perf_counter() - t0:.1f} s")

    # --- inspect what came out -------------------------------------------
    # The stack is a Zarr HIERARCHY, not one flat dataset: a group per pairing
    # group, then a subgroup per scene holding re/im/x/y, alongside the shared
    # `transform` and `conversion` groups. Opening the root with open_zarr
    # yields an empty dataset, which reads as "nothing was written" when in
    # fact everything was.
    import xarray as xr

    ok = []

    def check(label, cond, detail=""):
        ok.append(bool(cond))
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}" +
              (f"   {detail}" if detail else ""))

    groups = [d for d in sorted(os.listdir(a.out))
              if os.path.isdir(os.path.join(a.out, d))]
    scene_dirs = []
    for gname in groups:
        gpath = os.path.join(a.out, gname)
        for s in sorted(os.listdir(gpath)):
            if s in ("transform", "conversion") or \
               not os.path.isdir(os.path.join(gpath, s)):
                continue
            if os.path.exists(os.path.join(gpath, s, "re")):
                scene_dirs.append(os.path.join(gpath, s))
    print(f"\nstack groups {groups}")
    for s in scene_dirs:
        print(f"  scene {os.path.basename(s)}")

    check("both dates are in the stack", len(scene_dirs) == 2,
          f"{len(scene_dirs)} scenes with re/im")
    if not scene_dirs:
        print(f"\n{sum(ok)}/{len(ok)} checks passed")
        return 1

    dsets = [xr.open_zarr(s, consolidated=False) for s in scene_dirs]
    d0 = dsets[0]
    print(f"  grid {dict(d0.sizes)}, variables {list(d0.data_vars)}")
    check("stack holds re/im", {"re", "im"} <= set(d0.data_vars))

    # Decimate so this stays cheap.
    step = max(1, min(d0.sizes["y"], d0.sizes["x"]) // 1200)

    def as_complex(ds):
        sub = ds.isel(y=slice(None, None, step), x=slice(None, None, step))
        fill = ds["re"].attrs.get("_FillValue", 32767)
        scale = ds["re"].attrs.get("scale_factor", 1.0)
        r = sub["re"].values
        m = sub["im"].values
        return (np.where(r == fill, np.nan, r * scale).astype(np.float32)
                + 1j * np.where(m == fill, np.nan,
                                m * scale).astype(np.float32))

    z0 = as_complex(dsets[0])
    z1 = as_complex(dsets[1]) if len(dsets) > 1 else None
    cov0 = np.isfinite(z0.real).mean()
    print(f"\n  decimated to {z0.shape} (every {step}th pixel)")
    check("date 0 covers a real area", cov0 > 0.05,
          f"{100*cov0:.1f}% of the grid is valid")
    if z1 is not None:
        cov1 = np.isfinite(z1.real).mean()
        both = (np.isfinite(z0.real) & np.isfinite(z1.real)).mean()
        check("date 1 covers a real area", cov1 > 0.05,
              f"{100*cov1:.1f}%")
        check("the two dates overlap", both > 0.8 * min(cov0, cov1),
              f"{100*both:.1f}% valid in both")

        # --- the interferogram ------------------------------------------
        # Resultant length of the phasor over local windows. Never average
        # angles: the mean of +3.0 and -3.0 rad is 0 when they are 0.28 apart.
        ifg = z0 * np.conj(z1)
        good = np.isfinite(ifg.real) & (np.abs(ifg) > 0)
        u = np.where(good, ifg / np.abs(np.where(good, ifg, 1)), np.nan)

        w = 8
        ny, nx = (u.shape[0] // w) * w, (u.shape[1] // w) * w
        blocks = u[:ny, :nx].reshape(ny // w, w, nx // w, w)
        with np.errstate(invalid="ignore"):
            R = np.abs(np.nanmean(blocks, axis=(1, 3)))
        R = R[np.isfinite(R)]
        med = float(np.median(R)) if R.size else 0.0
        # Pure noise in an 8x8 window averages to about 1/sqrt(64) = 0.125.
        check("interferometric phase is correlated, not noise", med > 0.25,
              f"median resultant length {med:.3f} over {w}x{w} windows "
              f"(noise would give ~{1/w:.3f})")
        print(f"      p25 {np.percentile(R, 25):.3f}   "
              f"p75 {np.percentile(R, 75):.3f}   "
              f"fraction above 0.5: {100*(R > 0.5).mean():.1f}%")

    print(f"\n{sum(ok)}/{len(ok)} checks passed")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
