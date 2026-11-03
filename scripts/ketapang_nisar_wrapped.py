#!/usr/bin/env python3
"""Burn depth from NISAR 20 m WRAPPED phase: fringe maps and phase steps.

The 80 m unwrapped GUNW layer showed no burn signal, but a drop larger
than ~lambda/4 at a sharp scar edge is ambiguous to an unwrapper. The 20 m
wrapped interferogram keeps it, modulo one fringe = lambda/2 (~12.1 cm LOS).

For large scars that VIIRS dates to the 19-31 Aug pair window, per pair:
  1. remove a smooth background: coherence-free complex average of UNBURNED
     pixels (Gaussian, sigma 1 km), so the residual phase is ~0 off-scar
  2. phase step = circular mean of the residual inside the scar, and its
     consistency R (|mean unit phasor|; 0 = random, 1 = one uniform step)
  3. profile with distance from the scar edge (0-60, 60-200, 200-500, >500 m):
     a depth that tapers into the scar rotates the phase with distance
  4. fringe rate: mean |phase difference| between neighbouring pixels,
     inside vs the 1 km ring (coherence >= 0.3 only)
The control pair (20 Jun-2 Jul, before the fires) and a pair that spans
other burns (31 Aug-12 Sep) must show nothing for these same scars.

    conda run -n insardev python scripts/ketapang_nisar_wrapped.py
"""

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import CONC, FOUR, PEAT, _DATA_ROOT  # noqa: E402

NIS = os.path.join(_DATA_ROOT, "data", "nisar_ketapang")
ORIGIN = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin")
OUT = os.path.join(ORIGIN, "nisar")
AOI = (110.00, -2.10, 110.58, -1.45)
C = 299792458.0
W = "science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/"
FIRE_WIN = ("2026-08-19", "2026-08-31")
N_SCARS = 10
MIN_HA = 40


def main():
    import geopandas as gpd
    import h5py
    import numpy as np
    import pandas as pd
    import rasterio
    from affine import Affine
    from pyproj import Transformer
    from rasterio import features
    from rasterio.warp import reproject, Resampling
    from scipy import ndimage
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = sorted(glob.glob(os.path.join(NIS, "*.h5")))
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])

    # grid from the first file (all three share frame 89 posting)
    with h5py.File(files[0], "r") as h:
        xs, ys = h[W + "xCoordinates"][()], h[W + "yCoordinates"][()]
        freq = float(h["science/LSAR/GUNW/grids/frequencyA/centerFrequency"][()])
    lam = C / freq
    ci = np.flatnonzero((xs >= x0) & (xs <= x1))
    ri = np.flatnonzero((ys >= y0) & (ys <= y1))
    sl = (slice(ri[0], ri[-1] + 1), slice(ci[0], ci[-1] + 1))
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    tr = Affine(dx, 0, xs[ci[0]] - dx / 2, 0, dy, ys[ri[0]] - dy / 2)
    sh = (len(ri), len(ci))
    px = abs(dx)
    print(f"20 m crop {sh}, wavelength {lam * 100:.2f} cm, one fringe = {lam / 2 * 100:.2f} cm LOS")

    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as src:
        b = np.zeros(sh, np.uint8)
        lnd = np.zeros(sh, np.uint8)
        reproject(src.read(2), b, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.nearest)
        reproject((src.read(1) != 255).astype(np.uint8), lnd, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:32749",
                  resampling=Resampling.nearest)
    land = lnd > 0
    burned = ndimage.binary_opening(b > 0, iterations=1) & land
    unburned = land & ~ndimage.binary_dilation(b > 0, iterations=3)      # 60 m clear of any burn
    # per-pixel first-burn date: earliest VIIRS detection within ~400 m
    v = pd.read_csv(glob.glob(os.path.join(ORIGIN, "viirs_*.csv"))[0])
    v["t"] = pd.to_datetime(v.acq_epoch, unit="s", utc=True)
    v = v[v.t >= pd.Timestamp("2026-06-01", tz="UTC")]
    vx, vy = to_utm.transform(v.lon.to_numpy(), v.lat.to_numpy())
    rr, cc = rasterio.transform.rowcol(tr, vx, vy)
    rr, cc = np.asarray(rr), np.asarray(cc)
    ok = (rr >= 0) & (rr < sh[0]) & (cc >= 0) & (cc < sh[1])
    doy = v.t.dt.dayofyear.to_numpy()
    first = np.full(sh, 999, np.int16)
    np.minimum.at(first, (rr[ok], cc[ok]), doy[ok].astype(np.int16))
    first = ndimage.minimum_filter(first, size=int(2 * 400 / px) + 1)
    w0 = pd.Timestamp(FIRE_WIN[0]).dayofyear
    w1 = pd.Timestamp(FIRE_WIN[1]).dayofyear
    in_win = burned & (first >= w0) & (first < w1)          # first burned inside the fire pair
    print(f"burned pixels first dated to {FIRE_WIN}: {in_win.sum() * px * px / 1e4:,.0f} ha")
    lab, nlab = ndimage.label(ndimage.binary_opening(in_win, iterations=2))
    area_ha = np.bincount(lab.ravel(), minlength=nlab + 1) * px * px / 1e4
    idx = np.flatnonzero(area_ha >= MIN_HA)
    idx = idx[idx > 0]
    stats = pd.DataFrame({"ha": area_ha[idx]}, index=idx)
    stats["share_win"] = 1.0
    stats["n_win"] = 99

    conc = gpd.read_file(CONC).to_crs(32749)
    cm = np.zeros(sh, np.uint8)
    for k, (acr, n) in enumerate(FOUR.items(), 1):
        g = conc[conc.company.str.contains(n, case=False, na=False)].geometry
        cm[features.rasterize([(gg, 1) for gg in g], out_shape=sh, transform=tr, dtype="uint8") > 0] = k
    names = {k: a for k, a in enumerate(FOUR, 1)}
    stats["conc"] = [names.get(int(np.bincount(cm[lab == s]).argmax()), "outside") for s in stats.index]
    peat_g = gpd.read_file(PEAT).to_crs(32749)
    peat = features.rasterize([(g, 1) for g in peat_g.geometry if g is not None],
                              out_shape=sh, transform=tr, dtype="uint8") > 0
    stats["peat_share"] = [peat[lab == s].mean() for s in stats.index]
    # peat scars first, then the rest, largest first
    stats["is_peat"] = stats.peat_share >= 0.5
    pick = stats.sort_values(["is_peat", "ha"], ascending=False).head(N_SCARS)
    print(f"{len(stats)} patches >= {MIN_HA} ha first burned in {FIRE_WIN}; chosen:")
    print(pick[["ha", "conc", "peat_share"]].round(2).to_string())

    dist_in = ndimage.distance_transform_edt(burned) * px           # m inside scar from its edge
    ring = unburned
    BINS = [(0, 60), (60, 200), (200, 500), (500, 1e9)]
    masks = {}
    for s in pick.index:                    # scar, its own 1 km unburned ring, bbox
        sc = lab == s
        masks[s] = (sc, ring & (ndimage.distance_transform_edt(~sc) * px <= 1500),
                    ndimage.find_objects(sc.astype(int))[0])

    res, crops = {}, {}
    for f in files:
        name = os.path.basename(f).split("_")
        key = f"{name[11][:8]}_{name[13][:8]}"
        with h5py.File(f, "r") as h:
            z = h[W + "HH/wrappedInterferogram"][sl]
            coh = h[W + "HH/coherenceMagnitude"][sl]
        good = np.isfinite(z) & (np.abs(z) > 0) & np.isfinite(coh)
        u = np.where(good, z / np.where(np.abs(z) > 0, np.abs(z), 1), 0)
        # smooth background from unburned pixels only (normalised complex convolution)
        m = (unburned & good).astype(np.float32)
        sig = 1000 / px
        bre = ndimage.gaussian_filter(u.real * m, sig)
        bim = ndimage.gaussian_filter(u.imag * m, sig)
        bg = bre + 1j * bim
        r = u * np.conj(bg) / np.where(np.abs(bg) > 0, np.abs(bg), 1)
        r[~good] = 0
        ph = np.angle(r)
        # fringe rate (neighbour phase difference), coherent pixels only
        dxph = np.abs(np.angle(r[:, 1:] * np.conj(r[:, :-1])))
        dyph = np.abs(np.angle(r[1:, :] * np.conj(r[:-1, :])))
        fr = np.full(sh, np.nan)
        fr[:-1, :-1] = 0.5 * (dxph[:-1, :] + dyph[:, :-1])
        cg = good & (coh >= 0.3)

        out = {}
        for s, row in pick.iterrows():
            sc, rg, box = masks[s]

            def circ(mask):
                w_ = r[mask & good]
                if w_.size < 30:
                    return None, None, int(w_.size)
                mu = w_.mean()
                return float(np.angle(mu)), float(np.abs(mu)), int(w_.size)

            a_in, R_in, n_in = circ(sc)
            a_rg, R_rg, n_rg = circ(rg)
            prof = []
            for lo, hi in BINS:
                a_, R_, n_ = circ(sc & (dist_in > lo) & (dist_in <= hi))
                prof.append({"bin_m": f"{lo}-{hi if hi < 1e8 else 'inf'}", "phase": a_, "R": R_, "n": n_})
            out[int(s)] = {
                "conc": row.conc, "ha": float(row.ha), "peat_share": float(row.peat_share),
                "coh_in_median": float(np.nanmedian(coh[sc & good])),
                "coh_ring_median": float(np.nanmedian(coh[rg & good])),
                "step_phase_rad": a_in, "step_R": R_in,
                "step_cm_mod_fringe": None if a_in is None else float(-a_in * lam / (4 * np.pi) * 100),
                "ring_phase_rad": a_rg, "ring_R": R_rg,
                "fringe_rate_in": float(np.nanmean(fr[sc & cg])) if (sc & cg).sum() > 30 else None,
                "fringe_rate_ring": float(np.nanmean(fr[rg & cg])) if (rg & cg).sum() > 30 else None,
                "profile": prof}
            if s in pick.index[:6]:
                b0 = (max(box[0].start - 60, 0), min(box[0].stop + 60, sh[0]),
                      max(box[1].start - 60, 0), min(box[1].stop + 60, sh[1]))
                crops.setdefault(int(s), {})[key] = (ph[b0[0]:b0[1], b0[2]:b0[3]],
                                                     coh[b0[0]:b0[1], b0[2]:b0[3]],
                                                     sc[b0[0]:b0[1], b0[2]:b0[3]])
        res[key] = out
        print(f"\n== {key}")
        print(f"   {'scar':>6} {'conc':7}{'ha':>6}{'peat':>5}{'coh in':>7}{'ring':>6}"
              f"{'step rad':>9}{'R':>6}{'mod cm':>7}{'ring R':>7}{'frate in':>9}{'ring':>6}   profile phase(R)")
        for s, o in out.items():
            f_ = lambda x, p=2: "  -" if x is None else f"{x:.{p}f}"  # noqa: E731
            pr = " ".join(f"{f_(q['phase'], 1)}({f_(q['R'], 2)})" for q in o["profile"])
            print(f"   {s:>6} {o['conc']:7}{o['ha']:>6.0f}{o['peat_share']:>5.1f}{o['coh_in_median']:>7.2f}"
                  f"{o['coh_ring_median']:>6.2f}{f_(o['step_phase_rad']):>9}{f_(o['step_R']):>6}"
                  f"{f_(o['step_cm_mod_fringe'], 1):>7}{f_(o['ring_R']):>7}{f_(o['fringe_rate_in']):>9}"
                  f"{f_(o['fringe_rate_ring']):>6}   {pr}")

    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "wrapped_phase_test.json"), "w"), indent=2)
    keys = sorted(res)
    fig, ax = plt.subplots(len(crops), len(keys), figsize=(4.2 * len(keys), 3.8 * len(crops)),
                           squeeze=False)
    for i, (s, d) in enumerate(crops.items()):
        for j, k in enumerate(keys):
            p_, c_, sc_ = d[k]
            rgba = plt.cm.hsv((p_ + np.pi) / (2 * np.pi))
            rgba[..., 3] = np.clip(c_ / 0.5, 0, 1)
            ax[i, j].set_facecolor("black")
            ax[i, j].imshow(rgba, interpolation="nearest")
            ax[i, j].contour(sc_, levels=[0.5], colors="white", linewidths=0.7)
            ax[i, j].set_xticks([]); ax[i, j].set_yticks([])
            o = res[k][s]
            ax[i, j].set_title(f"scar {s} {o['conc']} {o['ha']:.0f} ha\n{k}  step R={o['step_R'] or 0:.2f}",
                               fontsize=9)
    plt.suptitle("NISAR 20 m wrapped residual phase (hue; one cycle = 12.1 cm LOS), "
                 "faded by coherence; white = scar", fontsize=11)
    plt.tight_layout()
    p = os.path.join(OUT, "wrapped_phase_scars.png")
    plt.savefig(p, dpi=70)
    print(f"\nSaved: {p}\nSaved: {os.path.join(OUT, 'wrapped_phase_test.json')}")


if __name__ == "__main__":
    main()
