"""Test whether the two tracks agree, then decompose them into vertical + east-west.

Ascending and descending see the same ground through different look geometries.
Two line-of-sight velocity fields can be solved for the vertical and east-west
components -- but only if they measure the same thing to begin with. Before
correction these two tracks disagreed spatially over identical ground and
period, which is what identified the fields as atmosphere rather than motion.

So the agreement test runs FIRST and is reported on its own terms. A
decomposition of two fields that disagree is arithmetic, not measurement: it
will return a smooth, plausible map either way, which is exactly what makes
skipping the test dangerous.

North-south is not recoverable. Both orbits are near-polar, so the look
directions are nearly parallel to it and the inversion is singular in that
component -- a standard limitation, not a shortcoming of this data.

    python3 scripts/decompose.py output/insar_geom_asc output/insar_geom_desc
"""

import argparse
import os
import sys

for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

import h5py  # noqa: E402
import numpy as np  # noqa: E402


SANE_MM_YR = 500.0   # 0.5 m/yr; no tectonic rate here is remotely this large


def read_velocity(path, mask_path=None):
    """Velocity in mm/yr with its grid, masked to pixels worth comparing.

    timeseries2velocity writes no mask dataset, so falling back to isfinite
    admits every pixel -- including ill-conditioned ones carrying 1e22 mm/yr,
    which alone are enough to drive the correlation to zero and make two
    agreeing fields look unrelated. Use MintPy's own temporal-coherence mask,
    and additionally drop physically impossible rates.
    """
    with h5py.File(path, "r") as f:
        v = f["velocity"][:] * 1000.0        # MintPy writes m/yr
        a = dict(f.attrs)
        mask = f["mask"][:].astype(bool) if "mask" in f else None

    if mask is None and mask_path and os.path.exists(mask_path):
        with h5py.File(mask_path, "r") as f:
            m = f["mask"][:].astype(bool)
        mask = m if m.shape == v.shape else None
    if mask is None:
        mask = np.isfinite(v) & (v != 0)

    finite = np.isfinite(v)
    wild = finite & (np.abs(v) > SANE_MM_YR)
    mask = mask & finite & (np.abs(v) <= SANE_MM_YR) & (v != 0)
    print(f"  {os.path.basename(os.path.dirname(os.path.dirname(path)))}: "
          f"{mask.sum():,} px kept, {int(wild.sum()):,} dropped as "
          f"|v| > {SANE_MM_YR:.0f} mm/yr, {int((~finite).sum()):,} non-finite")

    return v, mask, {k: float(a[k]) for k in
                     ("X_FIRST", "X_STEP", "Y_FIRST", "Y_STEP")}


def common_grid(ga, gd, sa, sd):
    """Overlapping lat/lon window, expressed as slices into each array.

    The tracks are geocoded to the same posting but different origins, so the
    overlap is an integer pixel offset rather than a resample.
    """
    step = ga["X_STEP"]
    if not np.isclose(step, gd["X_STEP"], rtol=1e-6):
        raise SystemExit(f"posting differs: {step} vs {gd['X_STEP']}")

    west = max(ga["X_FIRST"], gd["X_FIRST"])
    north = min(ga["Y_FIRST"], gd["Y_FIRST"])
    east = min(ga["X_FIRST"] + sa[1] * step, gd["X_FIRST"] + sd[1] * step)
    south = max(ga["Y_FIRST"] + sa[0] * ga["Y_STEP"],
                gd["Y_FIRST"] + sd[0] * gd["Y_STEP"])

    def window(g, shape):
        x0 = int(round((west - g["X_FIRST"]) / g["X_STEP"]))
        y0 = int(round((north - g["Y_FIRST"]) / g["Y_STEP"]))
        nx = int(round((east - west) / g["X_STEP"]))
        ny = int(round((south - north) / g["Y_STEP"]))
        x0, y0 = max(x0, 0), max(y0, 0)
        nx = min(nx, shape[1] - x0)
        ny = min(ny, shape[0] - y0)
        return slice(y0, y0 + ny), slice(x0, x0 + nx)

    return window(ga, sa), window(gd, sd), (west, south, east, north)


def agreement(va, vd, both):
    """Do the tracks measure the same ground motion?"""
    a, d = va[both], vd[both]
    print(f"  overlapping valid pixels: {a.size:,}")
    if a.size < 100:
        print("  too few pixels to judge")
        return None

    r = float(np.corrcoef(a, d)[0, 1])
    diff = a - d
    print(f"  asc  mean {a.mean():+7.1f}  std {a.std():6.1f} mm/yr")
    print(f"  desc mean {d.mean():+7.1f}  std {d.std():6.1f} mm/yr")
    print(f"  correlation           r = {r:+.3f}")
    print(f"  difference  RMS {np.sqrt((diff**2).mean()):6.1f}  "
          f"p95 |diff| {np.percentile(np.abs(diff), 95):6.1f} mm/yr")

    # Vertical motion appears with the SAME sign on both tracks; east-west
    # flips. A strong positive r means a shared, mostly vertical signal.
    # Near-zero r means the two fields are unrelated -- i.e. still atmosphere.
    verdict = ("tracks agree — shared signal present" if r > 0.5 else
               "weak agreement — signal may be marginal" if r > 0.2 else
               "tracks DISAGREE — fields are not measuring common ground motion")
    print(f"  verdict: {verdict}")
    return r


def decompose(va, vd, inc_a, inc_d, both):
    """Solve LOS_asc, LOS_desc for vertical and east-west.

        d_los = d_up * cos(inc) - d_east * sin(inc) * cos(alpha_h)
    with the heading term opposite in sign between ascending and descending,
    which is exactly what makes the 2x2 solvable.
    """
    ca, sa_ = np.cos(np.radians(inc_a)), np.sin(np.radians(inc_a))
    cd, sd_ = np.cos(np.radians(inc_d)), np.sin(np.radians(inc_d))

    # [va]   [ca  -sa][up  ]      ascending looks east, descending looks west,
    # [vd] = [cd  +sd][east]      hence the opposite sign on the east column.
    det = ca * sd_ + cd * sa_
    up = np.where(both, (va * sd_ + vd * sa_) / det, np.nan)
    east = np.where(both, (vd * ca - va * cd) / det, np.nan)
    return up, east


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("asc_dir")
    ap.add_argument("desc_dir")
    ap.add_argument("-o", "--out", default="output/decomposition")
    ap.add_argument("--velocity", default="velocityERA5.h5",
                    help="velocity file inside each mintpy dir; must be the "
                         "SAME name on both tracks or the comparison is unfair")
    a = ap.parse_args()

    paths = {}
    for role, d in (("asc", a.asc_dir), ("desc", a.desc_dir)):
        # Prefer the ERA5-corrected velocity. Falling back to the uncorrected
        # one silently would compare an atmosphere-dominated field against a
        # corrected one and call the disagreement a result.
        p = f"{d}/mintpy/{a.velocity}"
        if not os.path.exists(p):
            raise SystemExit(f"{p} not found — has smallbaselineApp finished?")
        paths[role] = p
    print(f"using {a.velocity} on both tracks")

    print("=== masking ===")
    va, ma, ga = read_velocity(paths["asc"],
                               f"{a.asc_dir}/mintpy/maskTempCoh.h5")
    vd, md, gd = read_velocity(paths["desc"],
                               f"{a.desc_dir}/mintpy/maskTempCoh.h5")
    print(f"asc  {va.shape}  desc {vd.shape}")

    wa, wd, bbox = common_grid(ga, gd, va.shape, vd.shape)
    va, ma = va[wa], ma[wa]
    vd, md = vd[wd], md[wd]
    h = min(va.shape[0], vd.shape[0])
    w = min(va.shape[1], vd.shape[1])
    va, ma, vd, md = va[:h, :w], ma[:h, :w], vd[:h, :w], md[:h, :w]
    print(f"common window {va.shape}  bbox W{bbox[0]:.3f} S{bbox[1]:.3f} "
          f"E{bbox[2]:.3f} N{bbox[3]:.3f}")

    both = ma & md & np.isfinite(va) & np.isfinite(vd)
    print(f"\n=== agreement test ===")
    r = agreement(va, vd, both)

    inc = {}
    for role, d in (("asc", a.asc_dir), ("desc", a.desc_dir)):
        with h5py.File(f"{d}/mintpy/inputs/geometryGeo.h5", "r") as f:
            g = f["incidenceAngle"][:]
        v = g[np.isfinite(g) & (g > 0)]
        inc[role] = float(np.median(v))
        # Guard the units bug: HyP3 ships radians, MintPy expects degrees.
        if inc[role] < np.pi / 2:
            raise SystemExit(
                f"{role} incidenceAngle median {inc[role]:.3f} looks like "
                f"RADIANS; MintPy expects degrees. Refusing to decompose.")
    print(f"\nincidence: asc {inc['asc']:.1f} deg, desc {inc['desc']:.1f} deg")

    up, east = decompose(va, vd, inc["asc"], inc["desc"], both)
    print("\n=== decomposition ===")
    for name, arr in (("vertical", up), ("east-west", east)):
        v = arr[np.isfinite(arr)]
        print(f"  {name:10} mean {v.mean():+7.1f}  std {v.std():6.1f}  "
              f"p5 {np.percentile(v,5):+7.1f}  p95 {np.percentile(v,95):+7.1f} mm/yr")

    os.makedirs(a.out, exist_ok=True)
    outp = f"{a.out}/horz_vert.h5"
    with h5py.File(outp, "w") as f:
        f.create_dataset("vertical", data=up.astype("float32"))
        f.create_dataset("eastWest", data=east.astype("float32"))
        f.attrs.update(X_FIRST=bbox[0], Y_FIRST=bbox[3],
                       X_STEP=ga["X_STEP"], Y_STEP=ga["Y_STEP"],
                       UNIT="mm/yr", INC_ASC=inc["asc"], INC_DESC=inc["desc"],
                       AGREEMENT_R=r if r is not None else np.nan)
    print(f"\nwrote {outp}")
    if r is not None and r < 0.2:
        print("NOTE: tracks disagree, so the components above are arithmetic, "
              "not a measurement of ground motion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
