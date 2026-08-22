"""Is the descending gradient a source, or a ramp across one-sided ground?

desc61_analyse.py reported "source-shaped" on two tests: the profile decays
monotonically outward, and its swing is 3.5x the quiet control's. Looking at
the map makes both suspect. The coherent ground is a single patch southwest of
the epicentre, not ground surrounding it. On one-sided ground, distance from
the epicentre is almost collinear with position across the patch, so a plain
linear ramp -- orbit error, a broad atmospheric gradient -- reproduces a
monotonic radial decay exactly. The test cannot distinguish them, and reporting
its verdict would be reporting an artefact of the geometry.

This is the same degeneracy that limited the ascending result, where a plane
took R^2 = 0.32. Here it is worse, because there is no ground on the far side
of the source to break it.

Three things settle how much can be claimed:

  AZIMUTHAL COVERAGE. What angular sector around the epicentre actually has
  coherent pixels. Below roughly a quadrant, a radial profile is not measuring
  a radial quantity.

  PLANE FIT. How much of the field a single tilted plane explains. If a plane
  takes nearly all of it, "decays with distance" is not evidence of a source.
  The control gets the same fit, so the comparison is like for like.

  RESIDUAL SHAPE. After removing the best plane, does anything centred on the
  source survive -- and does it survive in the co-event pair more than in the
  quiet control?

    conda run -n insardev-test python scripts/desc61_discriminate.py
"""

import argparse
import glob
import os
import sys

import numpy as np

REPO = os.path.expanduser("~/GitHub/rs-change-detection")
CO = os.path.join(REPO, "output/coseismic",
                  "flores-coseismic-2026-desc61-f621-prepost-d2")
CTRL = os.path.join(REPO, "output/coseismic",
                    "flores-coseismic-2026-desc61-f621-prepre-d2")
EPI = (121.3517, -8.3101)


def load(d, name):
    import rioxarray  # noqa: F401
    import xarray as xr
    hits = glob.glob(os.path.join(d, f"*_{name}.tif"))
    if not hits:
        sys.exit(f"no {name} in {os.path.basename(d)}")
    da = xr.open_dataarray(hits[0], engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def prep(d, min_coh):
    from pyproj import Transformer
    los = load(d, "los_disp")
    coh = load(d, "corr").values
    water = load(d, "water_mask").values
    v = los.values.astype("float64") * 100.0
    xs = los[los.dims[-1]].values
    ys = los[los.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", los.rio.crs, always_xy=True)
    ex, ey = fwd.transform(*EPI)
    X = (xs[None, :] - ex) / 1000.0
    Y = (ys[:, None] - ey) / 1000.0
    X = np.broadcast_to(X, v.shape)
    Y = np.broadcast_to(Y, v.shape)
    good = np.isfinite(v) & (coh >= min_coh) & (water > 0)
    return v, X, Y, good


def report(tag, v, X, Y, good, max_km):
    R = np.hypot(X, Y)
    m = good & (R <= max_km)
    n = int(m.sum())
    print(f"\n=== {tag}: {n:,} coherent pixels within {max_km:.0f} km")
    if n < 1000:
        print("   too few to judge")
        return None

    az = np.degrees(np.arctan2(Y[m], X[m])) % 360.0
    hist, _ = np.histogram(az, bins=36, range=(0, 360))
    occupied = int((hist > n * 0.002).sum())
    print(f"   azimuthal coverage: {occupied} of 36 ten-degree sectors "
          f"({occupied*10}deg)")

    d = v[m]
    A = np.column_stack([np.ones(n), X[m], Y[m]])
    coef, *_ = np.linalg.lstsq(A, d, rcond=None)
    fit = A @ coef
    res = d - fit
    ss = np.sum((d - d.mean()) ** 2)
    r2 = 1.0 - np.sum(res ** 2) / ss if ss > 0 else np.nan
    grad = np.hypot(coef[1], coef[2])
    print(f"   plane fit R^2 = {r2:.3f}   gradient {grad:.3f} cm/km "
          f"({grad*100:.1f} cm per 100 km)")
    print(f"   field sd {d.std():.2f} cm -> residual sd {res.std():.2f} cm")

    rr = R[m]
    print(f"   {'ring km':>10}{'raw':>9}{'de-planed':>11}")
    rows = []
    for r0, r1 in [(20, 30), (30, 40), (40, 50), (50, 65)]:
        k = (rr >= r0) & (rr < r1)
        if k.sum() < 200:
            print(f"   {f'{r0}-{r1}':>10}     --         --")
            rows.append(np.nan)
            continue
        print(f"   {f'{r0}-{r1}':>10}{np.median(d[k]):>9.2f}"
              f"{np.median(res[k]):>11.2f}")
        rows.append(float(np.median(res[k])))
    return {"r2": r2, "grad": grad, "res_sd": float(res.std()),
            "rings": rows, "az": occupied}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.3)
    ap.add_argument("--max-km", type=float, default=80.0)
    a = ap.parse_args()

    co = report("co-event 2->20 Aug", *prep(CO, a.min_coh), a.max_km)
    ct = report("control 21 Jul->2 Aug", *prep(CTRL, a.min_coh), a.max_km)
    if co is None or ct is None:
        return 1

    print("\n" + "=" * 62)
    if co["az"] < 9:
        print(f"Coherent ground spans only {co['az']*10} degrees of azimuth "
              f"around the\nepicentre. A radial profile over less than a "
              f"quadrant cannot separate\nradial decay from a linear "
              f"gradient -- they are the same function of\nposition over that "
              f"sector.")

    cr = np.array(co["rings"], dtype=float)
    qr = np.array(ct["rings"], dtype=float)
    ok = np.isfinite(cr) & np.isfinite(qr)
    swing_c = np.nanmax(cr[ok]) - np.nanmin(cr[ok]) if ok.sum() >= 2 else 0
    swing_q = np.nanmax(qr[ok]) - np.nanmin(qr[ok]) if ok.sum() >= 2 else 0
    print(f"\nAfter removing the best plane from each:")
    print(f"  co-event residual ring swing {swing_c:.2f} cm")
    print(f"  control  residual ring swing {swing_q:.2f} cm")
    print(f"  plane explains {100*co['r2']:.0f}% of the co-event field, "
          f"{100*ct['r2']:.0f}% of the control")

    print()
    if co["r2"] > 0.85:
        print("A single plane explains almost the whole co-event field. On")
        print("this track the descending data CANNOT independently confirm")
        print("the ascending result -- not because the signal is absent, but")
        print("because the coherent ground is one-sided and a ramp and a")
        print("source are indistinguishable over it.")
    elif swing_c > 2 * max(swing_q, 0.3):
        print("Structure centred on the source survives the plane removal in")
        print("the co-event pair and not in the control. That is evidence a")
        print("plane alone does not explain, from an independent geometry.")
    else:
        print("Nothing survives plane removal that the control does not also")
        print("show. Descending path 61 is not decisive either way.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
