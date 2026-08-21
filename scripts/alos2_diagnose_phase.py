"""Why does our ALOS-2 interferogram not match GMTSAR's?

The state to explain: our geocoded pair is internally COHERENT -- 20.6% of
48 m looks above 0.3, against GMTSAR's 22.5% -- but its phase is unrelated to
GMTSAR's, agreement 0.001 against a chance floor of 0.001.

Coherent but different is a narrow diagnosis. It rules out the geocoding being
broken (broken geocoding decorrelates) and points at a phase TERM that one
pipeline applied and the other did not, or applied differently. The candidates,
in the order this script tests them:

  1. Sign. If one of us forms ref*conj(rep) and the other rep*conj(ref), the
     phases are negatives and any correlation test on the difference returns
     zero. Cheapest possible check, so first.
  2. A residual ramp or topographic term. This is the one the picture
     diagnoses: dense fringes at a scale finer than the eye expects still give
     good coherence at 48 m looks while looking like noise on a map, and would
     share nothing with GMTSAR's smooth pattern.
  3. Scale. GMTSAR's phasefilt is Goldstein-filtered and ours is not, so ours
     is noisier -- but filtering changes amplitude, not the underlying
     pattern, and cannot take agreement to zero.

    conda run -n insardev-test python scripts/alos2_diagnose_phase.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1")
INTF = os.path.join(BASE, "intf", "2018132_2018216")
STACK = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/alos2_lombok_stack.zarr")
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/alos2_phase_diagnosis.png")


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

    def load(path):
        ds = xr.open_zarr(path, consolidated=False)
        fill = ds["re"].attrs.get("_FillValue", 32767)
        sc = ds["re"].attrs.get("scale_factor", 1.0)
        r, m = ds["re"].values, ds["im"].values
        return ds, (np.where(r == fill, np.nan, r * sc).astype(np.float32)
                    + 1j * np.where(m == fill, np.nan,
                                    m * sc).astype(np.float32))

    ds0, z0 = load(scenes[0])
    _, z1 = load(scenes[1])
    yv, xv = ds0["y"].values, ds0["x"].values
    dy, dx = abs(float(yv[1] - yv[0])), abs(float(xv[1] - xv[0]))
    Ly, Lx = max(1, round(a.target_m / dy)), max(1, round(a.target_m / dx))

    ifg = z0 * np.conj(z1)
    ny, nx = (ifg.shape[0] // Ly) * Ly, (ifg.shape[1] // Lx) * Lx
    with np.errstate(invalid="ignore"):
        num = np.nanmean(
            ifg[:ny, :nx].reshape(ny // Ly, Ly, nx // Lx, Lx), axis=(1, 3))
        d0 = np.nanmean(
            (np.abs(z0) ** 2)[:ny, :nx].reshape(ny // Ly, Ly, nx // Lx, Lx),
            axis=(1, 3))
        d1 = np.nanmean(
            (np.abs(z1) ** 2)[:ny, :nx].reshape(ny // Ly, Ly, nx // Lx, Lx),
            axis=(1, 3))
        coh = np.abs(num) / np.sqrt(d0 * d1)
    ph = np.angle(num)
    ys = yv[:ny].reshape(ny // Ly, Ly).mean(axis=1)
    xs = xv[:nx].reshape(nx // Lx, Lx).mean(axis=1)

    # GMTSAR on the same grid
    g_ph = xr.open_dataarray(os.path.join(INTF, "phasefilt_ll.grd"))
    g_co = xr.open_dataarray(os.path.join(INTF, "corr_ll.grd"))
    glat = g_ph[g_ph.dims[0]].values
    glon = g_ph[g_ph.dims[1]].values
    tr = Transformer.from_crs("EPSG:32750", "EPSG:4326", always_xy=True)
    X, Y = np.meshgrid(xs, ys)
    lon, lat = tr.transform(X, Y)
    iy = np.clip(np.searchsorted(glat, lat) - 1, 0, len(glat) - 1)
    ix = np.clip(np.searchsorted(glon, lon) - 1, 0, len(glon) - 1)
    inside = ((lat > glat.min()) & (lat < glat.max())
              & (lon > glon.min()) & (lon < glon.max()))
    gp = np.where(inside, g_ph.values[iy, ix], np.nan)
    gc = np.where(inside, g_co.values[iy, ix], np.nan)

    sel = np.isfinite(ph) & np.isfinite(gp) & (gc >= 0.3) & (coh >= 0.3)
    n = int(sel.sum())
    print(f"grid {ph.shape}, {Ly}x{Lx} looks = {Ly*dy:.0f}x{Lx*dx:.0f} m")
    print(f"{n} looks coherent in BOTH\n")

    # --- 1. sign ----------------------------------------------------------
    for label, d in (("ours - theirs", ph[sel] - gp[sel]),
                     ("ours + theirs", ph[sel] + gp[sel])):
        R = float(np.abs(np.mean(np.exp(1j * d))))
        print(f"  agreement, {label:<16} {R:.4f}")
    print(f"  chance floor {1/np.sqrt(max(n,1)):.4f}\n")

    # --- 2. how fast does our phase vary? --------------------------------
    # A residual ramp or an unremoved topographic term shows up as a phase
    # gradient far steeper than GMTSAR's. Measure it wrap-safely, as the
    # angle between neighbouring phasors -- never by differencing angles.
    def gradient(arr, mask):
        u = np.exp(1j * arr)
        gx = np.angle(u[:, 1:] * np.conj(u[:, :-1]))
        gy = np.angle(u[1:, :] * np.conj(u[:-1, :]))
        mx = mask[:, 1:] & mask[:, :-1]
        my = mask[1:, :] & mask[:-1, :]
        return (np.median(np.abs(gx[mx])) if mx.any() else np.nan,
                np.median(np.abs(gy[my])) if my.any() else np.nan)

    ox, oy = gradient(ph, sel)
    gx_, gy_ = gradient(gp, sel)
    px = Lx * dx
    print(f"  median |phase step| between adjacent {px:.0f} m looks")
    print(f"    ours    x {ox:.3f} rad   y {oy:.3f} rad")
    print(f"    GMTSAR  x {gx_:.3f} rad   y {gy_:.3f} rad")
    if np.isfinite(ox) and np.isfinite(gx_) and gx_ > 0:
        print(f"    ratio   x {ox/gx_:.2f}   y {oy/gy_:.2f}")
        print(f"    one fringe per {2*np.pi/max(ox,1e-9)*px/1000:.2f} km "
              f"(ours) vs {2*np.pi/max(gx_,1e-9)*px/1000:.2f} km (GMTSAR), "
              f"in x")

    # --- 3. picture -------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    show = np.where(sel | (coh >= 0.3), ph, np.nan)
    gshow = np.where(np.isfinite(gp) & (gc >= 0.3), gp, np.nan)

    fig, ax = plt.subplots(1, 3, figsize=(17, 6))
    for axi, arr, ttl, cmap, kw in (
        (ax[0], show, "insardev, ours\nwrapped phase where coherent",
         "twilight_shifted", dict(vmin=-np.pi, vmax=np.pi)),
        (ax[1], gshow, "GMTSAR phasefilt\nsame grid, same coherence cut",
         "twilight_shifted", dict(vmin=-np.pi, vmax=np.pi)),
        (ax[2], np.where(np.isfinite(coh), coh, np.nan),
         "our coherence\n20.6% above 0.3 vs GMTSAR's 22.5%",
         "magma", dict(vmin=0, vmax=0.8)),
    ):
        im = axi.imshow(arr, extent=ext, origin="upper", cmap=cmap,
                        interpolation="nearest", **kw)
        axi.set_title(ttl, fontsize=10.5, loc="left")
        axi.set_xlabel("lon")
        fig.colorbar(im, ax=axi, shrink=.8, pad=.02)
    ax[0].set_ylabel("lat")
    fig.suptitle("ALOS-2 Lombok 2018-05-12 -> 2018-08-04: two pipelines, "
                 "same pair", fontsize=13, y=.98)
    fig.tight_layout(rect=[0, 0, 1, .94])
    fig.savefig(a.out, dpi=125)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
