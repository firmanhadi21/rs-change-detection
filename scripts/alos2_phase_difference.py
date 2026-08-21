"""What is left between our ALOS-2 interferogram and GMTSAR's, and is it structured?

Agreement between the two is 0.527, rising only to 0.593 when our phase is
smoothed to match GMTSAR's Goldstein filtering. So filtering explains a small
part of the difference and something else explains the rest. R = 0.593 is a
per-look scatter of sqrt(-2 ln R) = 1.02 rad, about a sixth of a fringe, or
2 cm of line-of-sight.

The question this answers is whether that residual is NOISE or a FIELD.

  * White -> the two pipelines average different sets of scatterers. GMTSAR
    multilooks 4x8 in RADAR coordinates, where a look is a parallelogram whose
    ground shape depends on terrain slope; we multilook 6x3 in MAP coordinates,
    where it is a square. On Rinjani's flanks those are genuinely different
    scatterers, so the speckle realisations differ even with identical input.
    Nothing to fix; it is what "same pair, different processing" means.
  * Smooth -> a systematic model difference, most likely in the topographic
    and flat-earth phase. GMTSAR removes it via topo_ra computed in radar
    coordinates; we compute flat_earth_topo_phase per chunk from the baseline.
    Both approximately right, differing slowly across the scene. That WOULD be
    worth chasing, because it biases any deformation estimate.

Reported as the resultant length of the difference phasor within moving
windows: high within a window and low across the scene means a smooth field,
low everywhere means noise.

    conda run -n insardev-test python scripts/alos2_phase_difference.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1")
INTF = os.path.join(BASE, "intf", "2018132_2018216")
STACK = "/tmp/alos2_lombok_stack.zarr"
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/alos2_phase_difference.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=STACK)
    ap.add_argument("--target-m", type=float, default=50.0)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import xarray as xr
    from pyproj import Transformer

    scenes = []
    for g in sorted(os.listdir(a.stack)):
        gp = os.path.join(a.stack, g)
        if not os.path.isdir(gp):
            continue
        for s in sorted(os.listdir(gp)):
            if os.path.exists(os.path.join(gp, s, "re")):
                scenes.append(os.path.join(gp, s))

    def load(p):
        ds = xr.open_zarr(p, consolidated=False)
        return ds, (ds["re"].values.astype(np.float32)
                    + 1j * ds["im"].values.astype(np.float32))

    ds0, z0 = load(scenes[0])
    _, z1 = load(scenes[1])
    yv, xv = ds0["y"].values, ds0["x"].values
    dy, dx = abs(float(yv[1] - yv[0])), abs(float(xv[1] - xv[0]))
    Ly, Lx = max(1, round(a.target_m / dy)), max(1, round(a.target_m / dx))

    ifg = z0 * np.conj(z1)
    ny, nx = (ifg.shape[0] // Ly) * Ly, (ifg.shape[1] // Lx) * Lx

    def blk(arr):
        return arr[:ny, :nx].reshape(ny // Ly, Ly, nx // Lx, Lx)

    with np.errstate(invalid="ignore"):
        num = np.nanmean(blk(ifg), axis=(1, 3))
        d0 = np.nanmean(blk(np.abs(z0) ** 2), axis=(1, 3))
        d1 = np.nanmean(blk(np.abs(z1) ** 2), axis=(1, 3))
        coh = np.abs(num) / np.sqrt(d0 * d1)
    ph = np.angle(num)
    ys = yv[:ny].reshape(ny // Ly, Ly).mean(axis=1)
    xs = xv[:nx].reshape(nx // Lx, Lx).mean(axis=1)

    g_ph = xr.open_dataarray(os.path.join(INTF, "phasefilt_ll.grd"))
    g_co = xr.open_dataarray(os.path.join(INTF, "corr_ll.grd"))
    glat = g_ph[g_ph.dims[0]].values
    glon = g_ph[g_ph.dims[1]].values
    tr = Transformer.from_crs("EPSG:32750", "EPSG:4326", always_xy=True)
    X, Y = np.meshgrid(xs, ys)
    lon, lat = tr.transform(X, Y)
    inside = ((lat > glat.min()) & (lat < glat.max())
              & (lon > glon.min()) & (lon < glon.max()))
    iy = np.clip(np.searchsorted(glat, lat) - 1, 0, len(glat) - 1)
    ix = np.clip(np.searchsorted(glon, lon) - 1, 0, len(glon) - 1)
    gp = np.where(inside, g_ph.values[iy, ix], np.nan)
    gc = np.where(inside, g_co.values[iy, ix], np.nan)

    m = np.isfinite(ph) & np.isfinite(gp) & (gc >= 0.3) & (coh >= 0.3)
    diff = np.where(m, np.angle(np.exp(1j * (ph - gp))), np.nan)
    n = int(m.sum())
    R = float(np.abs(np.mean(np.exp(1j * diff[m]))))
    print(f"{n} looks compared, global agreement {R:.4f}, "
          f"scatter {np.sqrt(-2*np.log(max(R,1e-9))):.2f} rad")

    # Local coherence OF THE DIFFERENCE. If the residual is a smooth field,
    # neighbouring looks share it and this is high. If it is independent
    # speckle, it sits near the 1/sqrt(N) floor for the window.
    print("\n  window   local resultant of (ours - theirs)   noise floor")
    z = np.where(m, np.exp(1j * diff), np.nan)
    for w in (3, 5, 9, 17, 33):
        ny2, nx2 = (z.shape[0] // w) * w, (z.shape[1] // w) * w
        b = z[:ny2, :nx2].reshape(ny2 // w, w, nx2 // w, w)
        with np.errstate(invalid="ignore"):
            local = np.abs(np.nanmean(b, axis=(1, 3)))
        cnt = np.sum(np.isfinite(b), axis=(1, 3))
        good = np.isfinite(local) & (cnt > 0.5 * w * w)
        if good.sum() < 20:
            continue
        med = float(np.median(local[good]))
        floor = 1.0 / np.sqrt(w * w)
        print(f"  {w:>3}x{w:<3} ({w*Lx*dx:>4.0f} m)      {med:.3f}"
              f"                       {floor:.3f}")

    print("\n  A local resultant far above the floor at every window size")
    print("  means the residual is a FIELD, not noise -- neighbouring looks")
    print("  disagree with GMTSAR in the same direction.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    fig, ax = plt.subplots(1, 2, figsize=(13, 6))
    im = ax[0].imshow(diff, extent=ext, origin="upper", cmap="twilight_shifted",
                      vmin=-np.pi, vmax=np.pi, interpolation="nearest")
    ax[0].set_title("ours - GMTSAR, wrapped\nstructure here is a model "
                    "difference; speckle is not", fontsize=10, loc="left")
    fig.colorbar(im, ax=ax[0], shrink=.8, pad=.02, label="rad")

    # Smoothed, to make any field visible through the speckle.
    from scipy.signal import fftconvolve
    k = np.ones((9, 9))
    zz = np.where(np.isfinite(diff), np.exp(1j * diff), 0)
    ww = np.isfinite(diff).astype(float)
    with np.errstate(invalid="ignore"):
        sm = (fftconvolve(zz.real, k, "same") + 1j * fftconvolve(zz.imag, k,
                                                                 "same"))
        den = fftconvolve(ww, k, "same")
        smooth = np.where(den > 20, np.angle(sm), np.nan)
    im = ax[1].imshow(smooth, extent=ext, origin="upper",
                      cmap="twilight_shifted", vmin=-np.pi, vmax=np.pi,
                      interpolation="nearest")
    ax[1].set_title("same, 9x9 complex boxcar\nwhat survives averaging is "
                    "systematic", fontsize=10, loc="left")
    fig.colorbar(im, ax=ax[1], shrink=.8, pad=.02, label="rad")
    for axi in ax:
        axi.set_xlabel("lon")
    ax[0].set_ylabel("lat")
    fig.suptitle("Where our ALOS-2 interferogram differs from GMTSAR's",
                 fontsize=12.5, y=.97)
    fig.tight_layout(rect=[0, 0, 1, .93])
    fig.savefig(a.out, dpi=125)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
