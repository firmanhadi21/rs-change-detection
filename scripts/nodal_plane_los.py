"""Project both nodal planes into ascending LOS and compare with the observed.

A thrust focal mechanism has two nodal planes that fit the seismic data
equally well. They are NOT equivalent at the surface: for a rupture just north
of Flores, the shallow south-dipping plane puts the island on the HANGING WALL
and the steep north-dipping plane puts it on the FOOTWALL, and those predict
opposite vertical motion on the north coast. Resolving that ambiguity is the
classic thing geodesy contributes and seismology alone cannot.

But the naive version of that argument is wrong, and worth stating so nobody
stops there. A dipping thrust does not uplift its whole hanging wall. Uplift
concentrates above the UP-DIP part of the slip patch and reverses to
subsidence farther landward, above the DOWN-DIP end. So a south-dipping plane
can also produce subsidence on the north coast, if the coast sits landward of
the slip. Sign alone does not identify the plane -- the spatial PATTERN does,
which is why this compares maps and not points.

MODEL. Okada (1985) rectangular dislocation in an elastic half-space, via
okada_wrapper, which calls Okada's own DC3D. Uniform slip, because the USGS
finite-fault distribution is not in hand; every parameter is a flag so real
values drop straight in. Fault size and slip come from M7.7 scaling
(L ~ 104 km, W ~ 48 km, slip ~ 3.0 m at mu = 30 GPa), not from fitting
anything to the interferogram.

GEOMETRY. Sentinel-1 ascending, right-looking. Ground-to-satellite unit vector
in (E, N, U) is [-sin(theta)sin(a), -sin(theta)cos(a), cos(theta)] with look
azimuth a = heading + 90. Sign convention throughout matches the published
maps: POSITIVE = AWAY from the satellite.

COMPARISON is re-referenced. Both model and observation are differenced
against the same HyP3 reference pixel before anything is compared, because an
InSAR product measures differences and an unreferenced model comparison is
meaningless.

    conda run -n base python scripts/nodal_plane_los.py
    conda run -n base python scripts/nodal_plane_los.py --strike-a 100 --dip-a 15
"""

import argparse
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
    from okada_wrapper import dc3dwrapper
except ImportError as e:                               # pragma: no cover
    sys.exit(f"needs rasterio + okada-wrapper under `conda run -n base`: {e}")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradient_zscore import COEVENT, products          # noqa: E402

FRINGE_CM = 5.5465 / 2
EPI_LON, EPI_LAT = 121.3517, -8.3101
HYP3_REF = (122.7795, -8.5493)
KM_LAT = 110.57
ALPHA = 2.0 / 3.0                 # (lambda+mu)/(lambda+2mu), Poisson solid

TARGET = dict(lon0=120.70, lon1=121.45, lat0=-8.62, lat1=-8.35)


def okada_surface(lon, lat, clon, clat, depth_km, strike, dip, rake,
                  length_km, width_km, slip_m):
    """Surface E,N,U displacement in metres for a uniform-slip rectangle."""
    kx = 111.32 * np.cos(np.deg2rad(clat))
    dE = (lon - clon) * kx
    dN = (lat - clat) * KM_LAT

    s = np.deg2rad(strike)
    # Along-strike unit vector is (sin s, cos s); the horizontal dip direction
    # is 90 deg clockwise from it. This rotation is its own inverse.
    x = dE * np.sin(s) + dN * np.cos(s)
    y = dE * np.cos(s) - dN * np.sin(s)

    r = np.deg2rad(rake)
    ss = slip_m * np.cos(r)        # strike-slip
    ds = slip_m * np.sin(r)        # dip-slip, positive = thrust

    al = [-length_km / 2.0, length_km / 2.0]
    aw = [-width_km / 2.0, width_km / 2.0]

    ux = np.zeros_like(x, dtype=float)
    uy = np.zeros_like(x, dtype=float)
    uz = np.zeros_like(x, dtype=float)
    flat_x, flat_y = x.ravel(), y.ravel()
    ox, oy, oz = ux.ravel(), uy.ravel(), uz.ravel()
    for i in range(flat_x.size):
        ok, u, _ = dc3dwrapper(ALPHA, [flat_x[i], flat_y[i], 0.0],
                               depth_km, dip, al, aw, [ss, ds, 0.0])
        if ok == 0:
            ox[i], oy[i], oz[i] = u[0], u[1], u[2]
    ux = ox.reshape(x.shape); uy = oy.reshape(x.shape); uz = oz.reshape(x.shape)

    E = ux * np.sin(s) + uy * np.cos(s)
    N = ux * np.cos(s) - uy * np.sin(s)
    return E, N, uz


def los_away(E, N, U, incidence, heading):
    """Positive = AWAY from the satellite, matching the published maps."""
    th = np.deg2rad(incidence)
    a = np.deg2rad(heading + 90.0)          # look azimuth, right-looking
    # ground -> satellite
    nE, nN, nU = -np.sin(th) * np.sin(a), -np.sin(th) * np.cos(a), np.cos(th)
    toward = nE * E + nN * N + nU * U
    return -toward


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", type=int, default=1148)
    ap.add_argument("--min-coh", type=float, default=0.3)
    ap.add_argument("--stride", type=int, default=12, help="grid decimation")
    # Plane A: shallow, south-dipping — Flores on the hanging wall
    ap.add_argument("--strike-a", type=float, default=90.0)
    ap.add_argument("--dip-a", type=float, default=20.0)
    ap.add_argument("--rake-a", type=float, default=90.0)
    # Plane B: the conjugate — steep, north-dipping — Flores on the footwall
    ap.add_argument("--strike-b", type=float, default=270.0)
    ap.add_argument("--dip-b", type=float, default=70.0)
    ap.add_argument("--rake-b", type=float, default=90.0)
    ap.add_argument("--depth", type=float, default=20.0, help="centroid km")
    ap.add_argument("--length", type=float, default=104.0)
    ap.add_argument("--width", type=float, default=48.0)
    ap.add_argument("--slip", type=float, default=3.0)
    ap.add_argument("--clon", type=float, default=EPI_LON)
    ap.add_argument("--clat", type=float, default=EPI_LAT)
    ap.add_argument("--incidence", type=float, default=39.0)
    ap.add_argument("--heading", type=float, default=-13.0)
    a = ap.parse_args()

    unw = products(a.frame, "unw_phase")
    corr = products(a.frame, "corr")
    if COEVENT not in unw:
        sys.exit("co-event product not on disk")

    with rasterio.open(unw[COEVENT]) as src:
        phi = src.read(1).astype("float64")[::a.stride, ::a.stride]
        tr, crs = src.transform, src.crs
    with rasterio.open(corr[COEVENT]) as src:
        coh = src.read(1)[::a.stride, ::a.stride]

    rows, cols = np.mgrid[0:phi.shape[0], 0:phi.shape[1]]
    xs = tr.c + (cols * a.stride + .5) * tr.a
    ys = tr.f + (rows * a.stride + .5) * tr.e
    lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
    lon = np.array(lon).reshape(phi.shape)
    lat = np.array(lat).reshape(phi.shape)

    ok = np.isfinite(phi) & (phi != 0) & (coh >= a.min_coh)
    obs = phi * FRINGE_CM / (2 * np.pi)     # positive = away from satellite
    print(f"observed grid {phi.shape}, {int(ok.sum()):,} usable px "
          f"(stride {a.stride})")

    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dref = np.hypot((lon - HYP3_REF[0]) * kx, (lat - HYP3_REF[1]) * KM_LAT)
    refsel = ok & (dref <= 5.0)
    if refsel.sum() < 20:
        sys.exit("no coherent ground at the HyP3 reference point")
    obs = obs - np.median(obs[refsel])

    tgt = (ok & (lon >= TARGET["lon0"]) & (lon <= TARGET["lon1"])
           & (lat >= TARGET["lat0"]) & (lat <= TARGET["lat1"]))
    print(f"observed north coast: median {np.median(obs[tgt]):+.2f} cm "
          f"(positive = away from satellite)\n")

    print(f"model: L={a.length:.0f} km  W={a.width:.0f} km  "
          f"slip={a.slip:.1f} m  centroid depth={a.depth:.0f} km")
    print(f"       centroid {a.clon:.4f}, {a.clat:.4f}   "
          f"LOS: inc {a.incidence:.0f} deg, heading {a.heading:.0f} deg\n")

    print("  plane                          north coast   corr w/ obs   "
          "RMS diff")
    results = {}
    for tag, st, dp, rk, desc in (
            ("A", a.strike_a, a.dip_a, a.rake_a,
             "shallow S-dip, Flores = hanging wall"),
            ("B", a.strike_b, a.dip_b, a.rake_b,
             "steep N-dip, Flores = footwall")):
        E, N, U = okada_surface(lon, lat, a.clon, a.clat, a.depth,
                                st, dp, rk, a.length, a.width, a.slip)
        mod = los_away(E, N, U, a.incidence, a.heading) * 100.0   # cm
        mod = mod - np.median(mod[refsel])            # SAME reference
        r = np.corrcoef(obs[ok], mod[ok])[0, 1]
        rms = float(np.sqrt(np.mean((obs[ok] - mod[ok]) ** 2)))
        med = float(np.median(mod[tgt]))
        print(f"  {tag}: strike {st:5.0f} dip {dp:4.0f}   "
              f"{med:+8.2f} cm   {r:+8.3f}   {rms:8.2f}")
        print(f"     {desc}")
        results[tag] = dict(med=med, r=r, rms=rms, mod=mod)

    obs_med = float(np.median(obs[tgt]))
    print("\n=== reading ===")
    print(f"  observed north coast {obs_med:+.2f} cm")
    for tag in ("A", "B"):
        m = results[tag]["med"]
        agree = "SAME sign" if np.sign(m) == np.sign(obs_med) else "OPPOSITE"
        print(f"  plane {tag}: {m:+.2f} cm  -> {agree} as observed")
    best = max(results, key=lambda t: abs(results[t]["r"]))
    print(f"\n  higher |correlation|: plane {best} "
          f"({results[best]['r']:+.3f})")
    print("\n  Correlation is the discriminator, not sign: sign at one place")
    print("  can be matched by moving the slip patch, whereas the spatial")
    print("  pattern across 250 km cannot. Both are weak evidence while slip")
    print("  is uniform and the centroid is assumed -- replace them with the")
    print("  USGS finite-fault and this becomes a real test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
