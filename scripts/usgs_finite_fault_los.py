"""The USGS finite-fault model, projected into Sentinel-1 ascending LOS.

This replaces the uniform-slip rectangles that came before. Those were my own
invention and they failed badly -- a centroid placed at the epicentre predicted
40-90 cm of uplift on the north coast against an observed ~5 cm in the other
direction. The real model resolves that: peak slip of 3.87 m sits at latitude
-8.230, NORTH of the hypocentre at -8.3101, and only 4.4 km deep. Slip is
concentrated up-dip and offshore, so the north coast is not sitting on the
uplift maximum at all.

    us6000tkt2, 375 subfault patches, 4.86e20 N.m (Mw 7.72)
    https://earthquake.usgs.gov/earthquakes/eventpage/us6000tkt2/finite-fault

METHOD. Each patch is one Okada (1985) rectangular dislocation in an elastic
half-space, summed. Geometry is read from each patch's own polygon rather than
assumed globally: the constant-depth edge gives strike and along-strike length,
the shallow-to-deep offset gives dip and down-dip width. Strike is oriented so
that the down-dip direction is 90 degrees clockwise from it, which is the
convention DC3D expects; getting that backwards mirrors the whole deformation
field about the fault trace and is invisible in a single map.

COMPARISON is re-referenced. The model is differenced against the HyP3
reference pixel before any comparison, because an InSAR product measures
differences and comparing an absolute model to a relative observation is
meaningless. Sign convention follows the published maps: POSITIVE = AWAY from
the satellite.

    conda run -n base python scripts/usgs_finite_fault_los.py
"""

import argparse
import json
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
ALPHA = 2.0 / 3.0
TARGET = dict(lon0=120.70, lon1=121.45, lat0=-8.62, lat1=-8.35)


def patches(path):
    """One dict per subfault: centre, strike, dip, size, slip, rake."""
    d = json.load(open(path))
    out = []
    for f in d["features"]:
        p = f["properties"]
        if p.get("slip", 0.0) <= 0.0:
            continue
        c = np.array(f["geometry"]["coordinates"][0])[:4]
        dep = c[:, 2] / 1000.0
        shallow = dep < dep.mean()
        if shallow.sum() != 2:
            continue
        sh, dp_ = c[shallow], c[~shallow]
        clat = c[:, 1].mean()
        kx = 111.32 * np.cos(np.deg2rad(clat))

        # along-strike edge, at constant depth
        vx = (sh[1, 0] - sh[0, 0]) * kx
        vy = (sh[1, 1] - sh[0, 1]) * KM_LAT
        length = float(np.hypot(vx, vy))
        strike = float(np.degrees(np.arctan2(vx, vy)) % 360.0)

        # shallow edge -> deep edge: horizontal offset and depth drop
        hx = (dp_[:, 0].mean() - sh[:, 0].mean()) * kx
        hy = (dp_[:, 1].mean() - sh[:, 1].mean()) * KM_LAT
        horiz = float(np.hypot(hx, hy))
        drop = float(dp_[:, 2].mean() - sh[:, 2].mean()) / 1000.0
        if horiz <= 0 or length <= 0:
            continue
        dip = float(np.degrees(np.arctan2(drop, horiz)))
        width = float(np.hypot(horiz, drop))

        # DC3D expects the down-dip direction 90 deg CLOCKWISE from strike.
        # If it is anticlockwise, the plane is described by the reversed
        # strike; flipping it here rather than negating the dip keeps the
        # dislocation signs meaningful.
        want = np.deg2rad(strike + 90.0)
        if (np.sin(want) * hx + np.cos(want) * hy) < 0:
            strike = (strike + 180.0) % 360.0

        out.append(dict(lon=float(c[:, 0].mean()), lat=clat,
                        depth=float(dep.mean()), strike=strike, dip=dip,
                        length=length, width=width,
                        slip=float(p["slip"]), rake=float(p["rake"])))
    return out


def displacement(lon, lat, subs):
    """Sum the Okada contribution of every patch. Metres, (E, N, U)."""
    E = np.zeros(lon.size); N = np.zeros(lon.size); U = np.zeros(lon.size)
    flon, flat = lon.ravel(), lat.ravel()
    for k, s in enumerate(subs):
        kx = 111.32 * np.cos(np.deg2rad(s["lat"]))
        dE = (flon - s["lon"]) * kx
        dN = (flat - s["lat"]) * KM_LAT
        a = np.deg2rad(s["strike"])
        x = dE * np.sin(a) + dN * np.cos(a)
        y = dE * np.cos(a) - dN * np.sin(a)
        r = np.deg2rad(s["rake"])
        ss, ds = s["slip"] * np.cos(r), s["slip"] * np.sin(r)
        al = [-s["length"] / 2, s["length"] / 2]
        aw = [-s["width"] / 2, s["width"] / 2]
        for i in range(x.size):
            ok, u, _ = dc3dwrapper(ALPHA, [x[i], y[i], 0.0], s["depth"],
                                   s["dip"], al, aw, [ss, ds, 0.0])
            if ok == 0:
                E[i] += u[0] * np.sin(a) + u[1] * np.cos(a)
                N[i] += u[0] * np.cos(a) - u[1] * np.sin(a)
                U[i] += u[2]
        if (k + 1) % 75 == 0:
            print(f"    ...{k+1}/{len(subs)} patches", flush=True)
    return E.reshape(lon.shape), N.reshape(lon.shape), U.reshape(lon.shape)


def los_away(E, N, U, inc, heading):
    th, a = np.deg2rad(inc), np.deg2rad(heading + 90.0)
    nE, nN, nU = -np.sin(th) * np.sin(a), -np.sin(th) * np.cos(a), np.cos(th)
    return -(nE * E + nN * N + nU * U)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ffm", default=os.path.expanduser(
        "/private/tmp/claude-501/-Users-firmanhadi-GitHub-rs-change-detection/"
        "002f025e-d8ee-4126-aa65-97d981ababcf/scratchpad/FFM.geojson"))
    ap.add_argument("--frame", type=int, default=1148)
    ap.add_argument("--stride", type=int, default=25)
    ap.add_argument("--incidence", type=float, default=39.0)
    ap.add_argument("--heading", type=float, default=-13.0)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/GitHub/rs-change-detection/output/coseismic/usgs_ffm_los.png"))
    a = ap.parse_args()

    subs = patches(a.ffm)
    tot = sum(s["slip"] for s in subs)
    print(f"{len(subs)} patches with slip > 0")
    print(f"  strike {np.mean([s['strike'] for s in subs]):.1f} deg, "
          f"dip {np.mean([s['dip'] for s in subs]):.1f} deg, "
          f"patch {np.mean([s['length'] for s in subs]):.1f} x "
          f"{np.mean([s['width'] for s in subs]):.1f} km")
    print(f"  mean slip {tot/len(subs):.2f} m, "
          f"max {max(s['slip'] for s in subs):.2f} m")

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

    ok = np.isfinite(phi) & (phi != 0) & (coh >= 0.3)
    obs = phi * FRINGE_CM / (2 * np.pi)
    print(f"\nobservation grid {phi.shape}, {int(ok.sum()):,} usable px")

    print(f"forward-modelling {len(subs)} patches over {lon.size:,} points:")
    E, N, U = displacement(lon, lat, subs)
    mod = los_away(E, N, U, a.incidence, a.heading) * 100.0

    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dref = np.hypot((lon - HYP3_REF[0]) * kx, (lat - HYP3_REF[1]) * KM_LAT)
    refsel = ok & (dref <= 8.0)
    obs = obs - np.median(obs[refsel])
    mod = mod - np.median(mod[refsel])

    tgt = (ok & (lon >= TARGET["lon0"]) & (lon <= TARGET["lon1"])
           & (lat >= TARGET["lat0"]) & (lat <= TARGET["lat1"]))
    r = float(np.corrcoef(obs[ok], mod[ok])[0, 1])
    rms = float(np.sqrt(np.mean((obs[ok] - mod[ok]) ** 2)))
    print(f"\n=== USGS finite fault vs observation, both re-referenced ===")
    print(f"  north coast  observed {np.median(obs[tgt]):+7.2f} cm   "
          f"model {np.median(mod[tgt]):+7.2f} cm")
    print(f"  whole scene  obs sd {obs[ok].std():.2f}   "
          f"model sd {mod[ok].std():.2f} cm")
    print(f"  correlation {r:+.3f}   RMS difference {rms:.2f} cm")
    print(f"  model range over land: {mod[ok].min():+.1f} .. "
          f"{mod[ok].max():+.1f} cm")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    lim = max(abs(np.percentile(obs[ok], [2, 98])).max(),
              abs(np.percentile(mod[ok], [2, 98])).max())
    fig, ax = plt.subplots(3, 1, figsize=(13, 11))
    for axi, arr, ttl in (
            (ax[0], np.where(ok, obs, np.nan), "Observed  (HyP3 6→18 Aug)"),
            (ax[1], np.where(ok, mod, np.nan), "USGS finite fault → LOS"),
            (ax[2], np.where(ok, obs - mod, np.nan), "Observed − model")):
        im = axi.imshow(arr, cmap="RdYlBu_r", extent=ext, origin="upper",
                        vmin=-lim, vmax=lim, interpolation="nearest")
        axi.plot(EPI_LON, EPI_LAT, "*", color="#00ff88", ms=17, mec="k")
        axi.set_title(f"{ttl}   (positive = away from satellite)",
                      fontsize=10, loc="left")
        axi.set_ylabel("lat")
        fig.colorbar(im, ax=axi, shrink=.9, pad=.02, label="cm")
    ax[2].set_xlabel("lon")
    fig.suptitle(f"Flores M7.7 us6000tkt2 — finite fault vs InSAR   "
                 f"r = {r:+.3f}, RMS {rms:.1f} cm", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, .97])
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
