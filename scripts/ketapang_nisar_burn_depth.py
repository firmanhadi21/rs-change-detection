#!/usr/bin/env python3
"""Can NISAR L-band 12-day interferograms see peat burning down?

A peat fire removes the top of the peat, so the surface drops. If the
L-band signal stays coherent through the burn, an interferogram spanning the
burn date should show burned pixels moving away from the satellite relative
to unburned land next to them; one with no fire in between should not.

Pairs (track 90 descending, frame 89, 40 MHz HH, NISAR L2 GUNW provisional):
  control  2026-06-20 -> 07-02   almost no fire
  fire     2026-08-19 -> 08-31   peak fire in SKM / MKK
  fire     2026-08-31 -> 09-12

Classes on the GUNW 80 m grid, from the 25 m S2 burn mask
(landcover_burned.tif band 2) and VIIRS detections:
  burned_in_window   S2-burned and a VIIRS detection within 400 m between
                     the two dates
  burned_elsewhere   S2-burned but no detection in the window (burned before
                     or after the pair)
  unburned           land not S2-burned
Displacement is made relative to the local median of unburned pixels in
the same connected component within 1.5 km, so ramps, the ionosphere
residual and unwrapping offsets between components cancel.
Phase -> LOS metres: d = -phase * lambda / (4 pi) (phase minus ionosphere
screen); positive d = towards the satellite. Sign checked against the
convention printed by the file's attributes.

    conda run -n insardev python scripts/ketapang_nisar_burn_depth.py
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
G = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/"
LOCAL_M, VIIRS_M = 1500, 400


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

    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(NIS, "*.h5")))
    viirs = pd.read_csv(glob.glob(os.path.join(ORIGIN, "viirs_*.csv"))[0])
    viirs["t"] = pd.to_datetime(viirs.acq_epoch, unit="s", utc=True)
    peat_g = gpd.read_file(PEAT).to_crs(32749)
    conc = gpd.read_file(CONC).to_crs(32749)
    four = {a: conc[conc.company.str.contains(n, case=False, na=False)].geometry for a, n in FOUR.items()}
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])

    res, panels = {}, []
    for f in files:
        h = h5py.File(f, "r")
        name = os.path.basename(f)
        parts = name.split("_")
        t0, t1 = pd.Timestamp(parts[11][:8], tz="UTC"), pd.Timestamp(parts[13][:8], tz="UTC")
        lam = C / float(h["science/LSAR/GUNW/grids/frequencyA/centerFrequency"][()])
        xs, ys = h[G + "xCoordinates"][()], h[G + "yCoordinates"][()]
        ci = np.flatnonzero((xs >= x0) & (xs <= x1))
        ri = np.flatnonzero((ys >= y0) & (ys <= y1))
        sl = (slice(ri[0], ri[-1] + 1), slice(ci[0], ci[-1] + 1))
        ph = h[G + "HH/unwrappedPhase"][sl].astype(np.float64)
        ion = h[G + "HH/ionospherePhaseScreen"][sl].astype(np.float64)
        coh = h[G + "HH/coherenceMagnitude"][sl].astype(np.float64)
        cc = h[G + "HH/connectedComponents"][sl]
        if not res:
            for k in ("unwrappedPhase", "connectedComponents"):
                print(k, {a: (v.decode() if isinstance(v, bytes) else v)
                          for a, v in h[G + "HH/" + k].attrs.items()
                          if a in ("description", "units", "_FillValue")})
        dx = float(xs[1] - xs[0])
        dy = float(ys[1] - ys[0])
        tr = Affine(dx, 0, xs[ci[0]] - dx / 2, 0, dy, ys[ri[0]] - dy / 2)
        sh = ph.shape
        good = np.isfinite(ph) & (cc > 0) & (cc != 65535) & np.isfinite(coh)
        disp = -(ph - np.nan_to_num(ion)) * lam / (4 * np.pi)       # m, + towards satellite

        if not panels:   # rasters on this grid, once (same grid for all pairs on the frame)
            with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as src:
                bf = np.zeros(sh, np.float32)
                land = np.zeros(sh, np.float32)
                reproject(src.read(2).astype(np.float32), bf, src_transform=src.transform,
                          src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:32749",
                          resampling=Resampling.average)
                reproject((src.read(1) != 255).astype(np.float32), land, src_transform=src.transform,
                          src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:32749",
                          resampling=Resampling.average)
            burned, landm = bf >= 0.5, land >= 0.5
            unburned = (bf == 0) & landm
            peat = features.rasterize([(g, 1) for g in peat_g.geometry if g is not None],
                                      out_shape=sh, transform=tr, dtype="uint8") > 0
            cmask = {a: features.rasterize([(g, 1) for g in gs], out_shape=sh, transform=tr,
                                           dtype="uint8") > 0 for a, gs in four.items()}

        w = viirs[(viirs.t > t0) & (viirs.t <= t1)]
        vx, vy = to_utm.transform(w.lon.to_numpy(), w.lat.to_numpy())
        hit = np.zeros(sh, bool)
        rr, cc_ = rasterio.transform.rowcol(tr, vx, vy)
        rr, cc_ = np.asarray(rr), np.asarray(cc_)
        ok = (rr >= 0) & (rr < sh[0]) & (cc_ >= 0) & (cc_ < sh[1])
        hit[rr[ok], cc_[ok]] = True
        hit = ndimage.binary_dilation(hit, iterations=int(round(VIIRS_M / abs(dx))))
        cls = {"burned_in_window": burned & hit, "burned_elsewhere": burned & ~hit,
               "unburned": unburned}

        # local reference: median-like (mean) of unburned pixels, same component, within LOCAL_M
        k = int(round(LOCAL_M / abs(dx)))
        ref = np.full(sh, np.nan)
        refmask = unburned & good
        for comp in np.unique(cc[good]):
            m = refmask & (cc == comp)
            if m.sum() < 200:
                continue
            num = ndimage.uniform_filter(np.where(m, disp, 0.0), 2 * k + 1)
            den = ndimage.uniform_filter(m.astype(float), 2 * k + 1)
            inc = (cc == comp) & good & (den > 0.05)
            ref[inc] = num[inc] / den[inc]
        rel = (disp - ref) * 100                                 # cm, + towards satellite

        key = f"{t0.date()}_{t1.date()}"
        r = {"n_viirs_in_window": int(len(w)), "wavelength_m": lam}
        for zone, zm in [("all", np.ones(sh, bool)), ("peat", peat)] + list(cmask.items()):
            for cn, m in cls.items():
                mm = m & zm & landm
                v = mm & good & np.isfinite(rel)
                cvals = coh[mm & np.isfinite(coh)]
                r[f"{zone}|{cn}"] = {
                    "pixels": int(mm.sum()),
                    "coh_median": float(np.median(cvals)) if cvals.size else None,
                    "share_coh_ge_0.3": float((cvals >= 0.3).mean()) if cvals.size else None,
                    "share_unwrapped": float(v.sum() / max(mm.sum(), 1)),
                    "rel_cm_median": float(np.median(rel[v])) if v.sum() > 30 else None,
                    "rel_cm_p25": float(np.percentile(rel[v], 25)) if v.sum() > 30 else None,
                    "rel_cm_p75": float(np.percentile(rel[v], 75)) if v.sum() > 30 else None,
                    "rel_cm_median_coh_ge_0.3": float(np.median(rel[v & (coh >= 0.3)]))
                    if (v & (coh >= 0.3)).sum() > 30 else None}
        res[key] = r
        print(f"\n== {key}  ({len(w)} VIIRS detections in window)")
        print(f"   {'zone|class':34}{'pixels':>8}{'coh med':>8}{'coh>=.3':>8}{'unwr':>6}"
              f"{'rel cm':>8}{'p25':>7}{'p75':>7}{'rel@coh.3':>10}")
        for zk, v in r.items():
            if not isinstance(v, dict) or v["pixels"] < 50:
                continue
            fmt = lambda x, p=1: "   -" if x is None else f"{x:.{p}f}"  # noqa: E731
            print(f"   {zk:34}{v['pixels']:>8}{fmt(v['coh_median'], 2):>8}{fmt(v['share_coh_ge_0.3'], 2):>8}"
                  f"{fmt(v['share_unwrapped'], 2):>6}{fmt(v['rel_cm_median']):>8}{fmt(v['rel_cm_p25']):>7}"
                  f"{fmt(v['rel_cm_p75']):>7}{fmt(v['rel_cm_median_coh_ge_0.3']):>10}")
        panels.append((key, coh, np.where(good, rel, np.nan), tr))

    json.dump(res, open(os.path.join(OUT, "burn_depth_test.json"), "w"), indent=2)
    # quicklook: coherence and relative LOS (cm) per pair, burn outline and concessions
    fig, ax = plt.subplots(2, len(panels), figsize=(6 * len(panels), 11))
    for j, (key, coh, rel, tr) in enumerate(panels):
        ext = (tr.c, tr.c + tr.a * coh.shape[1], tr.f + tr.e * coh.shape[0], tr.f)
        ax[0, j].imshow(coh, cmap="gray", vmin=0, vmax=0.8, extent=ext)
        ax[1, j].imshow(rel, cmap="RdBu", vmin=-10, vmax=10, extent=ext)
        for i in (0, 1):
            ax[i, j].contour(np.flipud(burned) if tr.e > 0 else burned, levels=[0.5], colors="orange",
                             linewidths=0.4, extent=ext, origin="upper")
            conc.cx[ext[0]:ext[1], ext[2]:ext[3]].boundary.plot(ax=ax[i, j], color="k", lw=0.6)
            ax[i, j].set_xlim(ext[:2]); ax[i, j].set_ylim(ext[2:])
            ax[i, j].set_xticks([]); ax[i, j].set_yticks([])
        ax[0, j].set_title(f"{key}\ncoherence (L-band, 12 d)")
        ax[1, j].set_title("LOS rel. to local unburned, cm (blue = towards sat.)")
    plt.tight_layout()
    p = os.path.join(OUT, "burn_depth_quicklook.png")
    plt.savefig(p, dpi=70)
    print(f"\nSaved: {p}\nSaved: {os.path.join(OUT, 'burn_depth_test.json')}")


if __name__ == "__main__":
    main()
