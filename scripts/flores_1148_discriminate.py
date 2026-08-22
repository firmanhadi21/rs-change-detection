"""Is the north-coast LOS lobe deformation, an orbit ramp, or atmosphere?

Frame 1148 shows a negative line-of-sight lobe on the north Flores coast
reaching about -7 cm, with its median decaying outward from the epicentre:
-75.6 mm at 20-30 km, -27.3 at 30-50, +3.5 at 50-80. That is the shape of a
deformation field, and it is the first time in this campaign that a frame with
enough coherent land has been processed to see one.

It is also the shape of two things that are not deformation, so all three get
tested rather than the convenient one asserted:

  ORBIT RAMP. These are RESTITUTED orbits, ~10 cm against POEORB's few cm, and
  orbit error appears as a smooth ramp across the scene. A ramp also decays
  "outward" from any point you choose to measure from, which is exactly how it
  imitates a bullseye. Test: fit and remove a plane. A ramp IS the plane and
  vanishes; a source-centred field is not planar and survives.

  ATMOSPHERE. Tropospheric delay correlates with elevation. Test: regress the
  residual on the DEM. This is the test that overturned the Lombok result,
  where 81% of the phase variance turned out to be a function of height.

  DEFORMATION. Survives plane removal, is not explained by elevation, and its
  amplitude falls with distance from the SOURCE rather than with position in
  the scene. The discriminator is whether the residual is radially organised
  about the epicentre specifically -- so the same radial profile is also
  computed about two decoy centres, because a residual that looks equally
  "radial" around an arbitrary point is not evidence of anything.

    conda run -n base python scripts/flores_1148_discriminate.py
"""

import argparse
import os
import subprocess
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERGE = os.path.expanduser(
    _REPO_ROOT + "/data/flores_gmtsar_1148/merge")
DEM = os.path.expanduser(
    _REPO_ROOT + "/data/dem/flores/dem_1148.grd")
OUT = os.path.expanduser(
    _REPO_ROOT + "/output/coseismic/flores_1148_discriminate.png")
EPI = (121.3517, -8.3101)
KM_LAT = 110.57


def load(path):
    info = subprocess.run(["gmt", "grdinfo", "-C", path],
                          capture_output=True, text=True)
    if info.returncode != 0:
        return None, None, None
    f = info.stdout.split()
    x0, y0 = float(f[1]), float(f[3])
    dx, dy = float(f[7]), float(f[8])
    nx, ny = int(f[9]), int(f[10])
    raw = subprocess.run(["gmt", "grd2xyz", path, "-ZTLf"], capture_output=True)
    arr = np.frombuffer(raw.stdout, dtype="<f4").astype(float)
    if arr.size != nx * ny:
        raise ValueError(f"{path}: {arr.size} values, expected {nx*ny}")
    arr = arr.reshape(ny, nx)[::-1]
    lon = x0 + dx * np.arange(nx)
    lat = y0 + dy * np.arange(ny)
    if lon.max() < 0:
        lon = lon + 360.0
    return arr, lat, lon


def radial(v, R, edges):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = (R >= lo) & (R < hi)
        if s.sum() < 500:
            out.append((lo, hi, int(s.sum()), np.nan))
        else:
            out.append((lo, hi, int(s.sum()), float(np.median(v[s]))))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--merge", default=MERGE)
    ap.add_argument("--min-coh", type=float, default=0.2)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    los, lat, lon = load(os.path.join(a.merge, "los_ll.grd"))
    coh, clat, clon = load(os.path.join(a.merge, "corr_ll.grd"))
    if los is None:
        sys.exit(f"no los_ll.grd in {a.merge}")

    def match(arr, alat, alon):
        iy = np.clip(np.searchsorted(alat, lat), 1, len(alat) - 1) - 1
        ix = np.clip(np.searchsorted(alon, lon), 1, len(alon) - 1) - 1
        return arr[np.ix_(iy, ix)]

    C = match(coh, clat, clon)
    dem, dlat, dlon = load(DEM)
    Z = match(dem, dlat, dlon) if dem is not None else None

    good = np.isfinite(los) & (C >= a.min_coh)
    if Z is not None:
        good &= np.isfinite(Z)
    n = int(good.sum())
    print(f"{n:,} pixels at coherence >= {a.min_coh}")
    if n < 5000:
        sys.exit("too little coherent ground")

    kx = 111.32 * np.cos(np.deg2rad(EPI[1]))
    LON, LAT = np.meshgrid(lon, lat)
    R = np.hypot((LAT - EPI[1]) * KM_LAT, (LON - EPI[0]) * kx)
    v = los[good] / 10.0                       # cm
    edges = [20, 30, 40, 50, 65, 80, 100, 150]

    print(f"\n  RAW radial profile about the epicentre (cm, median)")
    for lo, hi, cnt, med in radial(v, R[good], edges):
        print(f"    {lo:>3}-{hi:<4} km {cnt:>8}   "
              + ("--" if not np.isfinite(med) else f"{med:+7.2f}"))

    # ---- 1. orbit ramp -------------------------------------------------
    # A plane in scene coordinates. Fit on coherent pixels only, then remove.
    x = (LON[good] - lon.mean()) * kx
    y = (LAT[good] - lat.mean()) * KM_LAT
    A = np.column_stack([x, y, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    plane = A @ coef
    resid = v - plane
    r2_plane = 1 - resid.var() / v.var()
    print(f"\n  plane fit: {coef[0]:+.4f} cm/km east, {coef[1]:+.4f} cm/km "
          f"north, R^2 = {r2_plane:.3f}")
    print(f"    scatter {v.std():.2f} -> {resid.std():.2f} cm after removal")

    # ---- 2. atmosphere --------------------------------------------------
    if Z is not None:
        z = Z[good]
        Az = np.column_stack([z, np.ones_like(z)])
        cz, *_ = np.linalg.lstsq(Az, resid, rcond=None)
        rz = resid - Az @ cz
        r2_z = 1 - rz.var() / resid.var()
        print(f"\n  elevation fit on the residual: "
              f"{cz[0]*1000:+.2f} cm per km of height, R^2 = {r2_z:.3f}")
        print(f"    (Lombok, where the answer was atmosphere, gave 0.81)")
    else:
        rz, r2_z = resid, 0.0

    # ---- 3. radial about the epicentre vs decoys ------------------------
    print(f"\n  radial profile AFTER removing the plane (cm, median)")
    print(f"    {'ring':<12}{'epicentre':>11}{'decoy W':>10}{'decoy E':>10}")
    # Decoys the same distance off, along strike, on coherent ground. If the
    # residual is radial about these too, it is not centred on the source.
    decoys = [(EPI[0] - 1.2, EPI[1]), (EPI[0] + 1.2, EPI[1])]
    Rd = [np.hypot((LAT - d[1]) * KM_LAT, (LON - d[0]) * kx)[good]
          for d in decoys]
    Rg = R[good]
    prof_e = radial(rz, Rg, edges)
    prof_d = [radial(rz, rd, edges) for rd in Rd]
    for i, (lo, hi, cnt, med) in enumerate(prof_e):
        row = f"    {lo:>3}-{hi:<7} km"
        for p in ([prof_e] + prof_d):
            m = p[i][3]
            row += f"{'   --   ' if not np.isfinite(m) else f'{m:+9.2f}'}"
        print(row)

    got = [m for *_, m in prof_e if np.isfinite(m)]
    swing_e = (max(got) - min(got)) if got else float("nan")
    swings_d = []
    for p in prof_d:
        g = [m for *_, m in p if np.isfinite(m)]
        swings_d.append((max(g) - min(g)) if g else float("nan"))
    print(f"\n  radial swing about the epicentre : {swing_e:.2f} cm")
    print(f"  radial swing about the decoys    : "
          + ", ".join(f"{s:.2f}" for s in swings_d) + " cm")

    print()
    if r2_plane > 0.6:
        print(f"  A PLANE explains {100*r2_plane:.0f}% of the field. On")
        print("  restituted orbits that is the expected signature of orbit")
        print("  error, and it is not evidence of ground motion.")
    if r2_z > 0.4:
        print(f"  ELEVATION explains {100*r2_z:.0f}% of what is left -- "
              "tropospheric\n  delay, the Lombok failure mode.")
    if np.isfinite(swing_e) and all(np.isfinite(s) for s in swings_d):
        if swing_e > 2 * max(swings_d):
            print(f"  The residual IS organised about the epicentre "
                  f"({swing_e:.2f} cm)\n  far more than about arbitrary "
                  f"centres ({max(swings_d):.2f} cm). That is what")
            print("  a source-centred deformation field looks like.")
        else:
            print(f"  The residual is NO more radial about the epicentre "
                  f"({swing_e:.2f} cm)\n  than about arbitrary centres "
                  f"({max(swings_d):.2f} cm), so its apparent")
            print("  decay with distance is not evidence of a source there.")

    # ---- figure ---------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    full_plane = np.full(los.shape, np.nan)
    full_resid = np.full(los.shape, np.nan)
    full_raw = np.full(los.shape, np.nan)
    full_raw[good] = v
    full_plane[good] = plane
    full_resid[good] = rz
    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    lim = np.nanpercentile(np.abs(full_raw), 98)
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.0))
    for axi, arr, ttl in (
        (ax[0], full_raw, "LOS as processed (cm)"),
        (ax[1], full_plane, f"best-fit plane — orbit ramp\n"
                            f"$R^2$ = {r2_plane:.2f}"),
        (ax[2], full_resid, "residual after plane and elevation\n"
                            "what is left for an earthquake to explain"),
    ):
        im = axi.imshow(arr, extent=ext, origin="lower", cmap="RdBu_r",
                        vmin=-lim, vmax=lim, interpolation="nearest")
        axi.plot(*EPI, "*", ms=16, mfc="#ffdd00", mec="black", mew=1.0,
                 zorder=5)
        for rk in (20, 30, 50):
            th = np.linspace(0, 2 * np.pi, 200)
            axi.plot(EPI[0] + rk / kx * np.cos(th),
                     EPI[1] + rk / KM_LAT * np.sin(th), "-", lw=.7,
                     color="#333", alpha=.6, zorder=4)
        axi.set_title(ttl, fontsize=10.5, loc="left")
        axi.set_xlabel("lon")
        fig.colorbar(im, ax=axi, shrink=.8, pad=.02, label="cm")
    ax[0].set_ylabel("lat")
    fig.suptitle("Flores frame 1148 — separating deformation from orbit ramp "
                 "and atmosphere", fontsize=12.5, y=.98)
    fig.tight_layout(rect=[0, 0, 1, .92])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=125)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
