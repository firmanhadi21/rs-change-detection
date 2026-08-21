"""Does insardev's ALOS-2 interferogram agree with GMTSAR's on the same pair?

The geocoded stack gives a resultant length of 0.106 over 8x8 windows, which
is barely above the 0.125 that pure noise would give -- so the obvious reading
is that the pipeline is broken. Before accepting that, check the reference:
GMTSAR's own coherence on this pair has median 0.094 with 22.5% above 0.3.
The pair is genuinely decorrelated over most of the island, and a correct
pipeline is supposed to reproduce that, not beat it.

So "is the phase noise?" is the wrong question. The right ones are:

  1. Does the coherence DISTRIBUTION match GMTSAR's? Too high is as wrong as
     too low -- it would mean something is smoothing, or that the two dates
     are not independent.
  2. Where GMTSAR is coherent, does our phase agree with GMTSAR's? This is the
     test that cannot be passed by accident. Two independent pipelines landing
     on the same fringe pattern over the same pixels is the whole claim.

Compared in the complex domain throughout, never on angles: the mean of +3.0
and -3.0 rad is 0 when the two are 0.28 rad apart, and a correlation computed
on wrapped angles is meaningless for the same reason. Agreement is measured as
the resultant length of exp(i * (ours - theirs)), which is 1 when the two
differ by a constant and 0 when they are unrelated. A CONSTANT offset is
expected and must not count against agreement -- neither pipeline has an
absolute phase reference.

    conda run -n insardev-test python scripts/alos2_compare_gmtsar_ifg.py
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
    "~/GitHub/rs-change-detection/output/alos2_insardev_vs_gmtsar.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=STACK)
    ap.add_argument("--target-m", type=float, default=50.0,
                    help="ground size of one look, metres. Looks are derived "
                         "per axis from the grid's own spacing rather than "
                         "given as a factor, because the output is anisotropic "
                         "(8 m range, 16 m azimuth) and one factor would "
                         "average unequal ground distances on the two axes.")
    ap.add_argument("--min-coh", type=float, default=0.3)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import xarray as xr
    from pyproj import Transformer

    # --- ours -------------------------------------------------------------
    scenes = []
    for g in sorted(os.listdir(a.stack)):
        gp = os.path.join(a.stack, g)
        if not os.path.isdir(gp):
            continue
        for s in sorted(os.listdir(gp)):
            if os.path.exists(os.path.join(gp, s, "re")):
                scenes.append(os.path.join(gp, s))
    if len(scenes) != 2:
        sys.exit(f"expected 2 scenes in {a.stack}, found {len(scenes)}")

    def load(path):
        ds = xr.open_zarr(path, consolidated=False)
        fill = ds["re"].attrs.get("_FillValue", 32767)
        sc = ds["re"].attrs.get("scale_factor", 1.0)
        r, m = ds["re"].values, ds["im"].values
        z = (np.where(r == fill, np.nan, r * sc).astype(np.float32)
             + 1j * np.where(m == fill, np.nan, m * sc).astype(np.float32))
        return ds, z

    ds0, z0 = load(scenes[0])
    _, z1 = load(scenes[1])

    yv, xv = ds0["y"].values, ds0["x"].values
    dy = abs(float(yv[1] - yv[0]))
    dx = abs(float(xv[1] - xv[0]))
    Ly = max(1, int(round(a.target_m / dy)))
    Lx = max(1, int(round(a.target_m / dx)))
    print(f"ours: {z0.shape} on EPSG:32750, pixel {dx:.1f} x {dy:.1f} m "
          f"-> {Ly}x{Lx} looks = {Ly*dy:.0f} x {Lx*dx:.0f} m")

    # Multilook in the COMPLEX domain. This is what turns single-look speckle
    # into a coherence estimate; without it every pixel has |gamma| = 1 by
    # construction and the number means nothing.
    ifg = z0 * np.conj(z1)
    p0 = np.abs(z0) ** 2
    p1 = np.abs(z1) ** 2
    ny, nx = (ifg.shape[0] // Ly) * Ly, (ifg.shape[1] // Lx) * Lx

    def block(arr):
        return arr[:ny, :nx].reshape(ny // Ly, Ly, nx // Lx, Lx)

    with np.errstate(invalid="ignore"):
        num = np.nanmean(block(ifg), axis=(1, 3))
        d0 = np.nanmean(block(p0), axis=(1, 3))
        d1 = np.nanmean(block(p1), axis=(1, 3))
        coh_ours = np.abs(num) / np.sqrt(d0 * d1)
    phase_ours = np.angle(num)

    ys = yv[:ny].reshape(ny // Ly, Ly).mean(axis=1)
    xs = xv[:nx].reshape(nx // Lx, Lx).mean(axis=1)

    good = np.isfinite(coh_ours)
    print(f"  ours   coherence median {np.nanmedian(coh_ours[good]):.3f}, "
          f"{100*np.nanmean(coh_ours[good] >= 0.3):.1f}% above 0.3 "
          f"({good.sum()} looks)")

    # --- GMTSAR ------------------------------------------------------------
    g_ph = xr.open_dataarray(os.path.join(INTF, "phasefilt_ll.grd"))
    g_co = xr.open_dataarray(os.path.join(INTF, "corr_ll.grd"))
    glat = g_ph[g_ph.dims[0]].values
    glon = g_ph[g_ph.dims[1]].values
    gc = g_co.values
    fin = np.isfinite(gc)
    print(f"  GMTSAR coherence median {np.nanmedian(gc[fin]):.3f}, "
          f"{100*np.nanmean(gc[fin] >= 0.3):.1f}% above 0.3")

    # --- put ours on GMTSAR's grid ----------------------------------------
    tr = Transformer.from_crs("EPSG:32750", "EPSG:4326", always_xy=True)
    X, Y = np.meshgrid(xs, ys)
    lon, lat = tr.transform(X, Y)

    iy = np.searchsorted(glat, lat)
    ix = np.searchsorted(glon, lon)
    inside = (iy > 0) & (iy < len(glat)) & (ix > 0) & (ix < len(glon))
    iy = np.clip(iy - 1, 0, len(glat) - 1)
    ix = np.clip(ix - 1, 0, len(glon) - 1)
    g_phase = np.where(inside, g_ph.values[iy, ix], np.nan)
    g_coh = np.where(inside, gc[iy, ix], np.nan)

    m = (inside & np.isfinite(phase_ours) & np.isfinite(g_phase)
         & np.isfinite(coh_ours) & np.isfinite(g_coh))
    print(f"\n  {m.sum()} looks land inside GMTSAR's grid")

    ok = []

    def check(label, cond, detail=""):
        ok.append(bool(cond))
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}" +
              (f"   {detail}" if detail else ""))

    med_o = float(np.nanmedian(coh_ours[m]))
    med_g = float(np.nanmedian(g_coh[m]))
    check("coherence distribution matches GMTSAR's",
          abs(med_o - med_g) < 0.10,
          f"ours {med_o:.3f} vs GMTSAR {med_g:.3f}")

    # The real test, on ground GMTSAR calls coherent.
    sel = m & (g_coh >= a.min_coh)
    n = int(sel.sum())
    if n < 500:
        check("enough coherent ground to compare", False, f"{n} looks")
    else:
        check("enough coherent ground to compare", True, f"{n} looks")
        d = np.exp(1j * (phase_ours[sel] - g_phase[sel]))
        R = float(np.abs(np.mean(d)))
        # Random phase over n samples gives R ~ 1/sqrt(n).
        floor = 1.0 / np.sqrt(n)
        check("our phase agrees with GMTSAR's where GMTSAR is coherent",
              R > 10 * floor,
              f"resultant length {R:.3f} (chance would give ~{floor:.3f})")
        print(f"      constant offset between the two: "
              f"{np.angle(np.mean(d)):+.3f} rad "
              f"(expected, neither has an absolute reference)")
        # Weight by GMTSAR's coherence: agreement should improve on better
        # ground, which chance alignment would not do.
        for lo, hi in ((0.3, 0.4), (0.4, 0.6), (0.6, 1.01)):
            s = m & (g_coh >= lo) & (g_coh < hi)
            if s.sum() < 200:
                continue
            Rb = float(np.abs(np.mean(
                np.exp(1j * (phase_ours[s] - g_phase[s])))))
            print(f"      GMTSAR coherence {lo:.1f}-{hi:.1f}: "
                  f"{int(s.sum()):>6} looks, agreement {Rb:.3f}")

    print(f"\n{sum(ok)}/{len(ok)} checks passed")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
