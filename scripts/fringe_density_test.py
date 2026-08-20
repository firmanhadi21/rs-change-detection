"""Could this interferogram have recovered the deformation the USGS model predicts?

Unwrapping has a hard limit. It assumes the true phase changes by less than pi
between neighbouring pixels; where it changes by more, the algorithm cannot
tell a real jump from a wrap and silently guesses. It does not fail loudly --
it returns a smooth, plausible surface that can be locally inverted, and it
goes wrong hardest where fringes are densest, which for an earthquake is the
near field. That is the one mechanism that would explain all three oddities in
this dataset at once: an anomaly co-located with the modelled lobe, opposite in
sign, and smaller in amplitude than the model.

So this asks the observability question directly, in two halves.

  OBSERVED   From the wrapped phase, measure the local phase gradient
             (wrap-safe, via the complex product of neighbours) and convert to
             fringe spacing in pixels. Below ~2 px the signal is aliased and no
             unwrapper can recover it; 2-4 px is marginal.

  PREDICTED  Take the USGS finite-fault LOS field, compute ITS gradient on the
             same ground, and ask what fringe spacing the real earthquake would
             have produced. If the model implies spacing below the pixel limit
             in the near field, then this interferogram could not have measured
             that deformation whatever it shows -- and the unwrapped product
             there is not evidence about the earthquake either way.

Coherence gates both: fringes wider than the pixel limit still cannot be
unwrapped where the phase is noise, so the test is run over coherent ground.

    conda run -n base python scripts/fringe_density_test.py
"""

import argparse
import glob
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                   # pragma: no cover
    sys.exit("needs rasterio + okada-wrapper under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usgs_finite_fault_los import (displacement, patches,      # noqa: E402
                                   los_away, EPI_LON, EPI_LAT, KM_LAT)

FRINGE_CM = 5.5465 / 2
ROOT = os.path.expanduser("~/GitHub/rs-change-detection/output/coseismic")
FFM = ("/private/tmp/claude-501/-Users-firmanhadi-GitHub-rs-change-detection/"
       "002f025e-d8ee-4126-aa65-97d981ababcf/scratchpad/FFM.geojson")

ALIASED_PX = 2.0        # below this, unrecoverable
MARGINAL_PX = 4.0       # below this, unreliable


def wrapped_gradient(phase, valid):
    """Local |phase gradient| in rad/pixel, correct through wraps."""
    z = np.where(valid, np.exp(1j * phase), 0)
    gx = np.zeros_like(phase, dtype=float)
    gy = np.zeros_like(phase, dtype=float)
    px = z[:, 1:] * np.conj(z[:, :-1])
    py = z[1:, :] * np.conj(z[:-1, :])
    gx[:, :-1] = np.abs(np.angle(px))
    gy[:-1, :] = np.abs(np.angle(py))
    ok = np.zeros_like(valid)
    ok[:, :-1] = valid[:, 1:] & valid[:, :-1]
    ok[:-1, :] &= valid[1:, :] & valid[:-1, :]
    return np.hypot(gx, gy), ok


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product", default="*prepost-d2*")
    ap.add_argument("--min-coh", type=float, default=0.3)
    ap.add_argument("--near-km", type=float, default=60.0)
    ap.add_argument("--stride", type=int, default=20,
                    help="decimation for the model forward-calculation only")
    a = ap.parse_args()

    wrp = sorted(glob.glob(f"{ROOT}/{a.product}/*_wrapped_phase.tif"))
    if not wrp:
        sys.exit(f"no wrapped_phase.tif under {ROOT}/{a.product}")
    wrp = wrp[0]
    corr_p = wrp.replace("_wrapped_phase.tif", "_corr.tif")
    print(f"product: {os.path.basename(wrp)[:56]}")

    with rasterio.open(wrp) as src:
        phase = src.read(1).astype("float64")
        tr, crs, H, W = src.transform, src.crs, src.height, src.width
        res_m = abs(src.transform.a)
    with rasterio.open(corr_p) as src:
        coh = src.read(1)

    valid = np.isfinite(phase) & (phase != 0) & (coh >= a.min_coh)
    print(f"grid {H}x{W} at {res_m:.0f} m, {int(valid.sum()):,} coherent px")

    grad, gok = wrapped_gradient(phase, valid)
    use = gok & valid & (grad > 0)
    spacing = np.where(use, 2 * np.pi / np.maximum(grad, 1e-9), np.nan)

    rows, cols = np.mgrid[0:H, 0:W]
    xs = tr.c + (cols + .5) * tr.a
    ys = tr.f + (rows + .5) * tr.e
    lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(phase.shape)
    lat = np.array(lat).reshape(phase.shape)
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dist = np.hypot((lon - EPI_LON) * kx, (lat - EPI_LAT) * KM_LAT)

    print(f"\n=== OBSERVED fringe spacing (pixels of {res_m:.0f} m) ===")
    print("  region            n        median   %<2px   %<4px")
    for name, sel in (("near (<%.0f km)" % a.near_km, use & (dist < a.near_km)),
                      ("far  (>=%.0f km)" % a.near_km, use & (dist >= a.near_km)),
                      ("all", use)):
        if sel.sum() < 100:
            continue
        v = spacing[sel]
        print(f"  {name:<16}{int(sel.sum()):>9,}  {np.nanmedian(v):>8.2f}"
              f"{100*np.nanmean(v < ALIASED_PX):>8.1f}"
              f"{100*np.nanmean(v < MARGINAL_PX):>8.1f}")

    # ---- what the earthquake would have produced ------------------------
    print(f"\n=== PREDICTED by the USGS finite fault ===")
    subs = patches(FFM)
    sl = (slice(None, None, a.stride), slice(None, None, a.stride))
    mlon, mlat = lon[sl], lat[sl]
    E, N, U = displacement(mlon, mlat, subs)
    mod = los_away(E, N, U, 39.0, -13.0) * 100.0        # cm, away positive

    # Gradient of the model field, in cm per model-cell, then per 40 m pixel.
    cell_m = res_m * a.stride
    gx = np.abs(np.gradient(mod, axis=1)) / cell_m
    gy = np.abs(np.gradient(mod, axis=0)) / cell_m
    gmag_cm_per_m = np.hypot(gx, gy)
    cm_per_pixel = gmag_cm_per_m * res_m
    model_spacing = np.where(cm_per_pixel > 0,
                             FRINGE_CM / np.maximum(cm_per_pixel, 1e-12),
                             np.inf)

    mdist = dist[sl]
    mvalid = valid[sl]
    print("  region            n        median   %<2px   %<4px")
    for name, sel in (("near (<%.0f km)" % a.near_km,
                       mvalid & (mdist < a.near_km)),
                      ("far  (>=%.0f km)" % a.near_km,
                       mvalid & (mdist >= a.near_km))):
        if sel.sum() < 20:
            continue
        v = model_spacing[sel]
        print(f"  {name:<16}{int(sel.sum()):>9,}  {np.nanmedian(v):>8.2f}"
              f"{100*np.nanmean(v < ALIASED_PX):>8.1f}"
              f"{100*np.nanmean(v < MARGINAL_PX):>8.1f}")

    near_model = model_spacing[mvalid & (mdist < a.near_km)]
    print("\n=== verdict ===")
    if near_model.size:
        frac_bad = float(np.nanmean(near_model < ALIASED_PX))
        print(f"  Model implies fringes closer than {ALIASED_PX:.0f} px over "
              f"{100*frac_bad:.1f}% of coherent near-field ground.")
        if frac_bad > 0.2:
            print("  -> The real deformation would have been ALIASED here.")
            print("     The unwrapped product cannot be read as a measurement")
            print("     of it, and its sign in the near field carries no")
            print("     information about the earthquake.")
        elif frac_bad > 0.02:
            print("  -> Aliasing affects a minority of the near field. The")
            print("     unwrapped product is usable away from those patches.")
        else:
            print("  -> The modelled deformation is comfortably resolvable at")
            print("     this pixel size. Unwrapping failure does NOT explain")
            print("     the disagreement, and another cause must be found.")
    print("\n  Observed spacing below the limit means the DATA is aliased")
    print("  whatever caused it; predicted spacing below the limit means the")
    print("  earthquake was unmeasurable here even in principle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
