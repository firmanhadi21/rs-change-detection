"""Does the north-coast LOS sign survive a change of reference point?

A finite-fault model predicts UPLIFT on the north coast of Flores; the HyP3
vertical projection reports apparent SUBSIDENCE of ~19-22 cm. Before treating
that as a contradiction between seismology and geodesy, one mundane
explanation has to be excluded.

InSAR measures DIFFERENCES. Every value in a HyP3 product is relative to an
automatically chosen reference pixel -- here 122.7795 E, 8.5493 S, about
155 km east of the epicentre. For an M7.7 that is not obviously far field. If
the reference pixel ITSELF moved toward the satellite, then ground that also
moved toward the satellite, but less, is reported as moving AWAY. The sign of
the anomaly would then be an artefact of where the reference landed, not a
statement about the ground.

This re-references the same unwrapped phase to a series of points at
increasing distance from the rupture and reports the north-coast anomaly under
each. If the sign is robust, the number changes but never flips. If it flips,
the uplift/subsidence disagreement is resolved without invoking either a wrong
fault model or a wrong interferogram.

SIGN CONVENTION here: positive = AWAY from the satellite, matching the
published maps. HyP3 unwrapped phase increases as range increases.

    conda run -n base python scripts/reference_sensitivity.py
"""

import argparse
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                    # pragma: no cover
    sys.exit("needs rasterio: run under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradient_zscore import COEVENT, products          # noqa: E402

FRINGE_CM = 5.5465 / 2
EPI_LON, EPI_LAT = 121.3517, -8.3101
KM_LAT = 110.57

HYP3_REF = (122.7795, -8.5493)

# Candidate reference points, ordered by distance from the epicentre. All are
# on Flores; the last are as far from the rupture as this frame allows.
REFS = [
    ("HyP3 automatic",   122.7795, -8.5493),
    ("Bajawa   (67 km)", 120.9856, -8.7906),
    ("Ende     (68 km)", 121.6626, -8.8432),
    ("Maumere (101 km)", 122.2111, -8.6199),
    ("far east(155 km)", 122.9000, -8.4500),
]

# The north-coast anomaly the maps highlight: northwest Flores.
TARGET = dict(name="north coast NW", lon0=120.70, lon1=121.45,
              lat0=-8.62, lat1=-8.35)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1148, choices=(1148, 1153))
    ap.add_argument("--min-coh", type=float, default=0.3)
    ap.add_argument("--radius", type=float, default=5.0,
                    help="km averaged around each reference point")
    a = ap.parse_args()

    unw = products(a.frame, "unw_phase")
    corr = products(a.frame, "corr")
    if COEVENT not in unw:
        sys.exit("co-event product not on disk")

    with rasterio.open(unw[COEVENT]) as src:
        phi = src.read(1).astype("float64")
        tr, crs = src.transform, src.crs
        H, W = src.height, src.width
    with rasterio.open(corr[COEVENT]) as src:
        coh = src.read(1)

    ok = np.isfinite(phi) & (phi != 0) & (coh >= a.min_coh)
    rows, cols = np.mgrid[0:H, 0:W]
    xs = tr.c + (cols + .5) * tr.a
    ys = tr.f + (rows + .5) * tr.e
    lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(phi.shape)
    lat = np.array(lat).reshape(phi.shape)

    los = phi * FRINGE_CM / (2 * np.pi)      # positive = away from satellite
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))

    tgt = (ok & (lon >= TARGET["lon0"]) & (lon <= TARGET["lon1"])
           & (lat >= TARGET["lat0"]) & (lat <= TARGET["lat1"]))
    print(f"frame {a.frame}, co-event 6->18 Aug")
    print(f"target: {TARGET['name']}, {int(tgt.sum()):,} px")
    print("positive = AWAY from satellite (matches the published maps)\n")

    print("  reference point        dist_epi   ref value   target median   p90")
    out = []
    for name, rlon, rlat in REFS:
        d = np.hypot((lon - rlon) * kx, (lat - rlat) * KM_LAT)
        sel = ok & (d <= a.radius)
        if sel.sum() < 200:
            print(f"  {name:<22} -- no coherent ground within "
                  f"{a.radius:.0f} km --")
            continue
        ref_val = float(np.median(los[sel]))
        rel = los - ref_val
        de = float(np.hypot((rlon - EPI_LON) * kx, (rlat - EPI_LAT) * KM_LAT))
        med = float(np.median(rel[tgt]))
        p90 = float(np.percentile(rel[tgt], 90))
        print(f"  {name:<22} {de:6.0f} km  {ref_val:+8.2f}    "
              f"{med:+8.2f} cm   {p90:+7.2f}")
        out.append((name, de, med, p90))

    if len(out) >= 3:
        meds = np.array([o[2] for o in out])
        print(f"\n  target median across references: "
              f"{meds.min():+.2f} .. {meds.max():+.2f} cm "
              f"(spread {meds.max()-meds.min():.2f})")
        if (meds > 0).all() or (meds < 0).all():
            print("  -> the SIGN is stable under every reference tried.")
            print("     The direction of motion is not an artefact of the")
            print("     reference pixel; only its magnitude is relative.")
        else:
            print("  -> the SIGN FLIPS with the reference point. The")
            print("     uplift/subsidence disagreement is then a referencing")
            print("     question, not a disagreement between the fault model")
            print("     and the interferogram.")

    print("\nNote: a stable sign still does not make this VERTICAL. Ascending")
    print("LOS mixes up and east; for theta ~ 39 deg, d_los is roughly")
    print("0.78*U - 0.63*E, so 16 cm away from the satellite is 21 cm of")
    print("subsidence, or 25 cm of eastward motion, or any combination.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
