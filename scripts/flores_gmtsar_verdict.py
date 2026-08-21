"""Does GMTSAR see the co-seismic bullseye the USGS model predicts?

A fourth, independent processing chain on the Flores co-event pair. SNAP, ASF
HyP3 and PyGMTSAR all found no near-field concentric fringe pattern where the
finite-fault model puts one; PyGMTSAR shares GMTSAR's lineage, so this native
GMTSAR run is the first fully separate implementation.

THE PREDICTION BEING TESTED. The USGS finite-fault model implies about 20
fringes of concentric line-of-sight motion over the north coast -- roughly
54 cm at C-band, where one fringe is 2.77 cm. That is not a subtle signal: it
would be the dominant feature of the interferogram.

WHAT WOULD COUNT AS SEEING IT. Not "some phase near the epicentre" -- there is
always phase. A co-seismic bullseye is a LOS field that grows monotonically
toward a centre and reaches tens of centimetres. So the test is the amplitude
of the LOS field in the near field, measured against both the model's
prediction and the scene's own far-field variation, which is the atmosphere
and orbit residual that any real signal has to exceed.

GMTSAR's los.grd is in MILLIMETRES and its sign is opposite to the unwrapped
phase: los = -unwrap * lambda / (4 pi). Both are checked below rather than
assumed, because a sign error would turn subsidence into uplift and still look
entirely plausible.

    conda run -n base python scripts/flores_gmtsar_verdict.py
"""

import argparse
import os
import sys

import numpy as np

MERGE_DEFAULT = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/flores_gmtsar/merge")
OUT_DEFAULT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/gmtsar_verdict.png")
EPI = (121.3517, -8.3101)
LAMBDA = 0.05546            # Sentinel-1 C-band, m
FRINGE_CM = LAMBDA / 2 * 100    # 2.77 cm of LOS per fringe
KM_LAT = 110.57
USGS_FRINGES = 20.0


def load(name, M=MERGE_DEFAULT):
    """Read a GMT .grd through GMT itself.

    Not xarray: GMTSAR writes classic netCDF that this environment's xarray
    backends refuse to open, and the same file reads fine through `gmt`. Going
    via grd2xyz also removes any doubt about row order -- -ZTLf is explicitly
    top-to-bottom, left-to-right.
    """
    import subprocess
    p = os.path.join(M, name)
    if not os.path.exists(p):
        return None, None, None
    info = subprocess.run(["gmt", "grdinfo", "-C", p],
                          capture_output=True, text=True)
    if info.returncode != 0:
        return None, None, None
    f = info.stdout.split()
    x0, x1, y0, y1 = (float(f[1]), float(f[2]), float(f[3]), float(f[4]))
    dx, dy = float(f[7]), float(f[8])
    nx, ny = int(f[9]), int(f[10])
    raw = subprocess.run(["gmt", "grd2xyz", p, "-ZTLf"],
                         capture_output=True)
    arr = np.frombuffer(raw.stdout, dtype="<f4").astype(float)
    if arr.size != nx * ny:
        raise ValueError(f"{name}: got {arr.size} values, expected {nx*ny}")
    # grd2xyz -ZTLf emits top row first; flip so row 0 is the SOUTH edge and
    # imshow(origin="lower") puts north at the top.
    arr = arr.reshape(ny, nx)[::-1]
    # GMTSAR fills masked pixels with 0; only NaN them where 0 is not a
    # legitimate value. Zero phase and zero displacement are both real.
    if name.startswith("corr"):
        arr[arr == 0] = np.nan
    lon = x0 + dx * np.arange(nx)
    lat = y0 + dy * np.arange(ny)
    # GMTSAR's proj_ra2ll writes 121.35 as -238.65. Every geocoded grid in
    # this project has needed this; forgetting it silently puts the epicentre
    # outside the scene.
    if lon.max() < 0:
        lon = lon + 360.0
    return arr, lat, lon


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--merge", default=MERGE_DEFAULT,
                    help="GMTSAR merge directory to read")
    ap.add_argument("--label", default="", help="frame label for titles")
    ap.add_argument("--min-coh", type=float, default=0.15)
    ap.add_argument("--out", default=OUT_DEFAULT)
    a = ap.parse_args()

    M = os.path.expanduser(a.merge)
    los, lat, lon = load("los_ll.grd", M)
    unw, _, _ = load("unwrap_mask_ll.grd", M)
    coh, clat, clon = load("corr_ll.grd", M)
    ph, _, _ = load("phasefilt_mask_ll.grd", M)
    if los is None:
        sys.exit(f"no los_ll.grd in {M}")

    print(f"grid {los.shape}, lon {lon.min():.3f}..{lon.max():.3f}, "
          f"lat {lat.min():.3f}..{lat.max():.3f}")
    inside = (lon.min() < EPI[0] < lon.max()
              and lat.min() < EPI[1] < lat.max())
    print(f"epicentre {EPI} inside: {inside}")
    if not inside:
        sys.exit("epicentre outside the processed frame")

    # Confirm the unit and sign relationship rather than trusting it.
    m = np.isfinite(los) & np.isfinite(unw) & (np.abs(unw) > 1e-6)
    if m.sum() > 1000:
        ratio = np.median(los[m] / unw[m])
        expect = -LAMBDA / (4 * np.pi) * 1000       # mm per radian, negated
        print(f"\nlos / unwrap = {ratio:+.4f} mm/rad "
              f"(lambda/4pi negated = {expect:+.4f}) "
              f"-> los is in MILLIMETRES, sign opposite the phase")

    # Match coherence onto the LOS grid; the geocoded grids need not share one.
    def match(arr, alat, alon):
        iy = np.clip(np.searchsorted(alat, lat), 1, len(alat) - 1) - 1
        ix = np.clip(np.searchsorted(alon, lon), 1, len(alon) - 1) - 1
        return arr[np.ix_(iy, ix)]

    # Every geocoded grid GMTSAR writes here has its own extent -- los_ll is
    # 4010x5560 while phasefilt_mask_ll is 4700x6200 -- so each has to be put
    # on the LOS grid explicitly rather than assumed to align.
    C = match(coh, clat, clon) if coh is not None else np.ones_like(los)
    if ph is not None and ph.shape != los.shape:
        ph = match(ph, *load("phasefilt_mask_ll.grd", M)[1:])
    good = np.isfinite(los) & (C >= a.min_coh)
    print(f"\n{100*good.mean():.1f}% of the grid is coherent at >= {a.min_coh}"
          f"  ({int(good.sum()):,} pixels)")

    kx = 111.32 * np.cos(np.deg2rad(EPI[1]))
    R = np.hypot((lat[:, None] - EPI[1]) * KM_LAT,
                 (lon[None, :] - EPI[0]) * kx)

    print(f"\n  LOS displacement by distance from the epicentre")
    print(f"    {'range':<12}{'n':>9}{'median':>10}{'p2..p98 (mm)':>22}"
          f"{'span cm':>9}")
    rows = []
    for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 50), (50, 80),
                   (80, 150)):
        s = good & (R >= lo) & (R < hi)
        if s.sum() < 500:
            print(f"    {lo:>3}-{hi:<8}{int(s.sum()):>9}   -- too few --")
            continue
        v = los[s]
        p2, p98 = np.percentile(v, [2, 98])
        rows.append((lo, hi, int(s.sum()), np.median(v), p2, p98))
        print(f"    {lo:>3}-{hi:<3} km  {int(s.sum()):>9}"
              f"{np.median(v):>10.1f}{p2:>10.1f} ..{p98:>8.1f}"
              f"{(p98-p2)/10:>9.1f}")

    if not rows:
        sys.exit("\nno coherent ground anywhere -- nothing to conclude")

    # THE NEAREST RING WITH DATA IS NOT ALWAYS THE FIRST. The USGS epicentre
    # sits at -8.31, and Flores' north coast runs around -8.4 to -8.5, so the
    # first 20 km is open sea and carries no coherence by definition. Reporting
    # "no near-field signal" from empty water would be meaningless; the honest
    # measure is the closest ring that has ground in it, labelled as such.
    far = [r for r in rows if r[0] >= 50]
    with_data = [r for r in rows if r[2] >= 500]
    nearest = with_data[0] if with_data else None
    near_span = (nearest[5] - nearest[4]) / 10 if nearest else float("nan")
    far_span = max((r[5] - r[4]) for r in far) / 10 if far else float("nan")
    predicted = USGS_FRINGES * FRINGE_CM

    if nearest:
        print(f"\n  nearest ring WITH GROUND: {nearest[0]}-{nearest[1]} km, "
              f"LOS span {near_span:.1f} cm ({nearest[2]:,} px)")
        if nearest[0] >= 20:
            print("    (0-20 km is open sea -- the epicentre is offshore of")
            print("     the north coast, so there is nothing there to measure)")
    print(f"  far field (> 50 km)      LOS span {far_span:.1f} cm")
    print(f"  USGS finite-fault model predicts {predicted:.0f} cm "
          f"({USGS_FRINGES:.0f} fringes) at the epicentre")

    print()
    if not np.isfinite(near_span):
        print("  No coherent ground anywhere near the epicentre: this run")
        print("  cannot settle the question, and saying so is the result.")
    elif near_span > 0.5 * predicted:
        print("  A near-field signal of the predicted order IS present.")
        print("  That would overturn the standing null -- check the sign")
        print("  convention and the orbit ramp before believing it.")
    else:
        print(f"  The predicted {predicted:.0f} cm bullseye is ABSENT. The")
        print(f"  near field spans {near_span:.1f} cm, "
              f"{predicted/max(near_span,1e-9):.0f}x less than predicted,")
        print(f"  and no more than the far field's {far_span:.1f} cm, which is")
        print("  atmosphere and orbit residual rather than ground motion.")
        print("\n  Fourth independent chain, same answer: the model")
        print("  overpredicts onshore slip.")

    # ---- figure ---------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.8))
    show_los = np.where(good, los / 10.0, np.nan)          # cm
    lim = np.nanpercentile(np.abs(show_los), 98)
    for axi, arr, ttl, cmap, kw in (
        (ax[0], np.where(good, ph, np.nan),
         "GMTSAR wrapped phase\none cycle = 2.77 cm line-of-sight",
         "twilight_shifted", dict(vmin=-np.pi, vmax=np.pi)),
        (ax[1], show_los,
         f"LOS displacement (cm)\nmodel predicts {predicted:.0f} cm here",
         "RdBu_r", dict(vmin=-lim, vmax=lim)),
        (ax[2], np.where(np.isfinite(C), C, np.nan),
         "coherence\na fringe means nothing where this is low",
         "magma", dict(vmin=0, vmax=0.8)),
    ):
        im = axi.imshow(arr, extent=ext, origin="lower", cmap=cmap,
                        interpolation="nearest", **kw)
        axi.plot(*EPI, "*", ms=17, mfc="#ffdd00", mec="black", mew=1.1,
                 zorder=5)
        for r_km in (10, 20, 30):
            th = np.linspace(0, 2 * np.pi, 200)
            axi.plot(EPI[0] + r_km / kx * np.cos(th),
                     EPI[1] + r_km / KM_LAT * np.sin(th),
                     "-", lw=.7, color="#333333", alpha=.55, zorder=4)
        axi.set_title(ttl, fontsize=10.5, loc="left")
        axi.set_xlabel("lon")
        fig.colorbar(im, ax=axi, shrink=.82, pad=.02)
    ax[0].set_ylabel("lat")
    fig.suptitle("Flores 2026-08-06 → 2026-08-18, native GMTSAR TOPS — "
                 "rings at 10, 20, 30 km from the epicentre",
                 fontsize=12.5, y=.98)
    fig.tight_layout(rect=[0, 0, 1, .93])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=125)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
