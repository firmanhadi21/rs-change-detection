#!/usr/bin/env python3
"""Fire spread on the Ketapang coast from NISAR L-band coherence loss.

L-band 12-day coherence over peat is ~0.4-0.5 and stays there unless the
surface changes. Burning breaks it for the one pair that spans the burn
(the scar then becomes a stable, MORE coherent bare surface), so each pixel's
burn is dated to the pair where its coherence dips below both neighbours in
time. Smoke and cloud do not matter to radar, so this is an independent
check on VIIRS timing and on the ignition lineage.

Data: NISAR L2 GUNW (provisional), 20 m coherence of the wrapped
interferogram, only the HDF5 chunks over the AOI are range-read from ASF
(Earthdata login from ~/.netrc), cached as .npz.
  track 90 descending, frame 89: all four concessions, 9 consecutive pairs
  track 155 ascending: SKM, SPAS and most of MKK, pairs offset ~4 days
On a common 40 m UTM grid; 3x3 median (~120 m effective).

Dip of pair k: d_k = mean(g_{k-1}, g_{k+1}) - g_k (one neighbour at the ends),
minus the AOI-wide median dip of that pair (scene-wide moisture changes).
Burned in pair k* = argmax d_k if d_k* >= T; T set by Youden's J against the
S2 burn mask on even-numbered 5 km blocks and SCORED on odd blocks.

STAGES  fetch | map
    conda run -n insardev python scripts/ketapang_nisar_spread.py --stage fetch
"""

import argparse
import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import CONC, FOUR, PEAT, _DATA_ROOT  # noqa: E402

ORIGIN = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin")
OUT = os.path.join(ORIGIN, "nisar")
CACHE = os.path.join(_DATA_ROOT, "data", "nisar_ketapang", "coh20")
AOI = (110.00, -2.10, 110.58, -1.45)
W = "science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/"
TRACKS = {90: "D", 155: "A"}
RES = 40.0
BLOCK_M = 5000
SEARCH = "https://api.daac.asf.alaska.edu/services/search/param"


class RangeFile(io.RawIOBase):
    """Read-only file object over HTTP range requests with a block cache, so
    h5py fetches only the chunks it needs."""
    BS = 4 << 20

    def __init__(self, url, session):
        r = session.get(url, headers={"Range": "bytes=0-0"}, allow_redirects=True, timeout=120)
        r.raise_for_status()
        self.url, self.s = r.url, session                 # presigned final URL
        self.size = int(r.headers["Content-Range"].split("/")[-1])
        self.pos, self.cache, self.fetched = 0, {}, 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _block(self, i):
        if i not in self.cache:
            a, b = i * self.BS, min((i + 1) * self.BS, self.size) - 1
            for k in range(4):
                try:
                    r = self.s.get(self.url, headers={"Range": f"bytes={a}-{b}"}, timeout=300)
                    r.raise_for_status()
                    break
                except Exception:                          # noqa: BLE001
                    if k == 3:
                        raise
            self.cache[i] = r.content
            self.fetched += len(r.content)
        return self.cache[i]

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        out, p, end = memoryview(buf), self.pos, self.pos + n
        while p < end:
            i = p // self.BS
            blk = self._block(i)
            o = p - i * self.BS
            m = min(len(blk) - o, end - p)
            out[p - self.pos:p - self.pos + m] = blk[o:o + m]
            p += m
        self.pos = end
        return n


def scenes():
    import geopandas as gpd
    import pandas as pd
    import requests
    import shapely
    box = shapely.geometry.box(*AOI)
    r = requests.get(SEARCH, params={"dataset": "NISAR", "intersectsWith": box.wkt, "output": "geojson",
                                     "maxResults": 2000, "processingLevel": "GUNW"}, timeout=300)
    g = gpd.GeoDataFrame.from_features(r.json()["features"], crs=4326)
    g["ref"] = g.sceneName.str.split("_").str[11].str[:8]
    g["rep"] = g.sceneName.str.split("_").str[13].str[:8]
    g["cov"] = g.geometry.intersection(box).area / box.area
    g["days"] = (pd.to_datetime(g.rep) - pd.to_datetime(g.ref)).dt.days
    out = []
    for t in TRACKS:
        # the consecutive chain: from each ref date the shortest pair with the best coverage
        s = g[(g.pathNumber == t) & (g["cov"] > 0.3)]
        s = s.sort_values(["ref", "days", "cov"], ascending=[True, True, False]).drop_duplicates("ref")
        chain, last = [], None
        for row in s.itertuples():
            if last is None or row.ref == last:
                chain.append(row)
                last = row.rep
        out += chain
    return out


def stage_fetch(a):
    import h5py
    import numpy as np
    import requests
    from pyproj import Transformer
    os.makedirs(CACHE, exist_ok=True)
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])
    s = requests.Session()
    for row in scenes():
        p = os.path.join(CACHE, f"t{row.pathNumber}_{row.ref}_{row.rep}.npz")
        if os.path.exists(p):
            print("have", os.path.basename(p))
            continue
        local = os.path.join(_DATA_ROOT, "data", "nisar_ketapang", os.path.basename(row.url))
        fo = open(local, "rb") if os.path.exists(local) else RangeFile(row.url, s)
        with h5py.File(fo, "r") as h:
            xs, ys = h[W + "xCoordinates"][()], h[W + "yCoordinates"][()]
            ci = np.flatnonzero((xs >= x0) & (xs <= x1))
            ri = np.flatnonzero((ys >= y0) & (ys <= y1))
            if len(ci) < 10 or len(ri) < 10:
                print("no overlap", row.sceneName)
                continue
            coh = h[W + "HH/coherenceMagnitude"][ri[0]:ri[-1] + 1, ci[0]:ci[-1] + 1]
            epsg = int(h[W + "HH/projection"][()])
        np.savez_compressed(p, coh=coh.astype(np.float16), x=xs[ci], y=ys[ri], epsg=epsg)
        mb = getattr(fo, "fetched", 0) / 1e6
        print(f"saved {os.path.basename(p)} {coh.shape} epsg {epsg} ({mb:.0f} MB read)", flush=True)


def stage_map(a):
    import glob
    import geopandas as gpd
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
    from matplotlib.colors import ListedColormap, BoundaryNorm

    os.makedirs(OUT, exist_ok=True)
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])
    tr = Affine(RES, 0, x0, 0, -RES, y1)
    sh = (int((y1 - y0) // RES), int((x1 - x0) // RES))

    def on_grid(p):
        z = np.load(p)
        c = z["coh"].astype(np.float32)
        c[~np.isfinite(c) | (c <= 0)] = np.nan
        x, y = z["x"], z["y"]
        dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
        st = Affine(dx, 0, x[0] - dx / 2, 0, dy, y[0] - dy / 2)
        dst = np.full(sh, np.nan, np.float32)
        reproject(c, dst, src_transform=st, src_crs=f"EPSG:{int(z['epsg'])}", dst_transform=tr,
                  dst_crs="EPSG:32749", resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
        st_ = np.stack([np.roll(np.roll(dst, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)])
        return np.nanmedian(st_, axis=0)                          # 3x3 median, ~120 m

    # reference rasters on the grid
    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as src:
        bf = np.zeros(sh, np.float32)
        lf = np.zeros(sh, np.float32)
        reproject(src.read(2).astype(np.float32), bf, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.average)
        reproject((src.read(1) != 255).astype(np.float32), lf, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.average)
    land = lf >= 0.5
    s2b, s2u = (bf >= 0.5) & land, (bf == 0) & land
    v = pd.read_csv(glob.glob(os.path.join(ORIGIN, "viirs_*.csv"))[0])
    v["t"] = pd.to_datetime(v.acq_epoch, unit="s", utc=True).dt.tz_localize(None)
    v = v[v.t >= "2026-06-01"]
    vx, vy = to_utm.transform(v.lon.to_numpy(), v.lat.to_numpy())
    rr, cc = rasterio.transform.rowcol(tr, vx, vy)
    rr, cc = np.asarray(rr), np.asarray(cc)
    ok = (rr >= 0) & (rr < sh[0]) & (cc >= 0) & (cc < sh[1])
    vday = np.full(sh, 9999, np.int32)
    days0 = (v.t - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    np.minimum.at(vday, (rr[ok], cc[ok]), days0[ok].astype(np.int32))
    vday = ndimage.minimum_filter(vday, size=int(2 * 400 / RES) + 1)       # first VIIRS within 400 m
    yy, xx = np.indices(sh)
    blk = ((yy * RES // BLOCK_M) + (xx * RES // BLOCK_M)) % 2               # checkerboard 5 km blocks

    conc = gpd.read_file(CONC).to_crs(32749)
    cmask = {acr: features.rasterize(
        [(g, 1) for g in conc[conc.company.str.contains(n, case=False, na=False)].geometry],
        out_shape=sh, transform=tr, dtype="uint8") > 0 for acr, n in FOUR.items()}
    anyc = features.rasterize([(g, 1) for g in conc.geometry if g is not None], out_shape=sh,
                              transform=tr, dtype="uint8") > 0
    peat = features.rasterize([(g, 1) for g in gpd.read_file(PEAT).to_crs(32749).geometry
                               if g is not None], out_shape=sh, transform=tr, dtype="uint8") > 0

    day = lambda s: (pd.Timestamp(s) - pd.Timestamp("2026-01-01")).days   # noqa: E731
    report, per_track = {}, {}
    for t in TRACKS:
        files = sorted(glob.glob(os.path.join(CACHE, f"t{t}_*.npz")))
        if len(files) < 3:
            continue
        pairs = [tuple(os.path.basename(f)[:-4].split("_")[1:]) for f in files]
        G = np.stack([on_grid(f) for f in files])                       # k, y, x
        K = len(files)
        D = np.full_like(G, np.nan)
        for k in range(K):
            nb = [G[j] for j in (k - 1, k + 1) if 0 <= j < K]
            D[k] = np.nanmean(np.stack(nb), axis=0) - G[k]
            D[k] -= np.nanmedian(D[k][land & np.isfinite(D[k])])
        # the end pairs have one neighbour only: a one-sided difference flags any
        # trend as a burn (35k ha "burned" in June on the first run), so a burn
        # can only be dated to an interior pair
        D[0] = np.nan
        D[-1] = np.nan
        valid = np.isfinite(D).sum(0) >= max(3, K - 4)
        Dz = np.where(np.isfinite(D), D, -9)
        kstar = Dz.argmax(0)
        dmax = Dz.max(0)
        cal = valid & (blk == 0)
        thr = np.round(np.arange(0.03, 0.40, 0.01), 2)
        J = [((dmax >= x) & s2b & cal).sum() / max((s2b & cal).sum(), 1)
             - ((dmax >= x) & s2u & cal).sum() / max((s2u & cal).sum(), 1) for x in thr]
        T = float(thr[int(np.argmax(J))])
        burn = valid & (dmax >= T) & land
        te = valid & (blk == 1)
        tp, fp = (burn & s2b & te).sum(), (burn & s2u & te).sum()
        fn = (~burn & s2b & te).sum()
        prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        # timing vs VIIRS first detection (pixels detected by both)
        t0 = np.array([day(p[0]) for p in pairs])
        t1 = np.array([day(p[1]) for p in pairs])
        both = burn & (vday < 9999)
        vd = vday[both]
        ks = kstar[both]
        exact = (vd >= t0[ks]) & (vd < t1[ks])
        within1 = (vd >= t0[np.maximum(ks - 1, 0)]) & (vd < t1[np.minimum(ks + 1, K - 1)])
        later = vd >= t1[ks]                    # radar sees the loss BEFORE VIIRS
        earlier = vd < t0[ks]                   # VIIRS first, radar later (smouldering)
        no_viirs = burn & s2b & (vday == 9999)
        # mode 2: WHERE from Sentinel-2, WHEN from radar (no threshold): every
        # S2-burned pixel dated to its deepest coherence dip
        sd = s2b & valid & (vday < 9999)
        ks2, vd2 = kstar[sd], vday[sd]
        r_s2 = {"n_px": int(sd.sum()),
                "same_pair": float(((vd2 >= t0[ks2]) & (vd2 < t1[ks2])).mean()),
                "within_1_pair": float(((vd2 >= t0[np.maximum(ks2 - 1, 0)])
                                        & (vd2 < t1[np.minimum(ks2 + 1, K - 1)])).mean()),
                "radar_lag_days_median": float(np.median(0.5 * (t0[ks2] + t1[ks2]) - vd2))}
        px_ha = RES * RES / 1e4
        r = {"pairs": [f"{p[0]}-{p[1]}" for p in pairs], "threshold_dip": T,
             "val_precision_vs_S2": float(prec), "val_recall_vs_S2": float(rec),
             "val_f1": float(2 * prec * rec / max(prec + rec, 1e-9)),
             "n_px_both": int(both.sum()),
             "timing_exact_pair": float(exact.mean()), "timing_within_1_pair": float(within1.mean()),
             "viirs_after_radar_pair": float(later.mean()), "viirs_before_radar_pair": float(earlier.mean()),
             "burned_s2_and_radar_no_viirs_ha": float(no_viirs.sum() * px_ha),
             "radar_burned_ha": float(burn.sum() * px_ha), "s2_where_radar_when": r_s2}
        per_pair = []
        for k, p in enumerate(pairs):
            bk = burn & (kstar == k)
            row = {"pair": f"{p[0]}-{p[1]}", "aoi_ha": float(bk.sum() * px_ha),
                   "outside_conc_ha": float((bk & ~anyc).sum() * px_ha),
                   "peat_ha": float((bk & peat).sum() * px_ha)}
            for acr, m in cmask.items():
                row[acr] = float((bk & m).sum() * px_ha)
                row[acr + "_valid_frac"] = float(valid[m].mean())
            per_pair.append(row)
        r["per_pair"] = per_pair
        report[f"track_{t}"] = r
        per_track[t] = (pairs, burn, kstar, valid)
        print(f"\n== track {t}{TRACKS[t]}: {K} pairs, dip threshold {T:.2f}")
        print(f"   held-out blocks vs S2 burn: precision {prec:.2f} recall {rec:.2f}")
        print(f"   timing vs first VIIRS (n={both.sum():,}): same pair {exact.mean():.0%}, "
              f"within +-1 pair {within1.mean():.0%}; VIIRS later {later.mean():.0%}, earlier {earlier.mean():.0%}")
        print(f"   S2-burned + radar-burned but no VIIRS within 400 m: {no_viirs.sum() * px_ha:,.0f} ha")
        print(f"   S2 where / radar when (n={r_s2['n_px']:,}): same pair as first VIIRS {r_s2['same_pair']:.0%}, "
              f"within +-1 {r_s2['within_1_pair']:.0%}, radar minus VIIRS median {r_s2['radar_lag_days_median']:+.0f} d")
        print(pd.DataFrame(per_pair).drop(columns=[c for c in per_pair[0] if c.endswith("valid_frac")])
              .round(0).to_string(index=False))

        # map: burn pair
        cols = plt.cm.inferno(np.linspace(0.15, 0.95, K))
        img = np.where(burn, kstar, np.nan)
        fig, ax = plt.subplots(figsize=(10, 11))
        ax.set_facecolor("#dddddd")
        ext = (x0, x0 + sh[1] * RES, y1 - sh[0] * RES, y1)
        ax.imshow(np.where(land, 1, np.nan), cmap=ListedColormap(["#f4f4f4"]), extent=ext)
        im = ax.imshow(img, cmap=ListedColormap(cols), norm=BoundaryNorm(np.arange(-0.5, K), K),
                       extent=ext, interpolation="nearest")
        conc.cx[ext[0]:ext[1], ext[2]:ext[3]].boundary.plot(ax=ax, color="#555", lw=0.4)
        for acr, n in FOUR.items():
            g = conc[conc.company.str.contains(n, case=False, na=False)]
            g.boundary.plot(ax=ax, color="k", lw=1.4)
            c = g.geometry.iloc[0].representative_point()
            ax.annotate(acr, (c.x, c.y), fontsize=11, weight="bold", ha="center",
                        bbox=dict(fc="white", alpha=0.7, lw=0))
        cb = plt.colorbar(im, ax=ax, ticks=range(K), shrink=0.7)
        cb.ax.set_yticklabels([f"{p[0][4:6]}/{p[0][6:]}-{p[1][4:6]}/{p[1][6:]}" for p in pairs])
        cb.set_label("12-day pair in which L-band coherence collapsed (burn)")
        ax.set_xlim(ext[:2]); ax.set_ylim(ext[2:]); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"Fire spread from NISAR coherence loss, track {t} "
                     f"({'descending' if TRACKS[t] == 'D' else 'ascending'})\n"
                     f"held-out vs Sentinel-2 burn: precision {prec:.2f}, recall {rec:.2f}")
        plt.tight_layout()
        plt.savefig(os.path.join(OUT, f"spread_track{t}.png"), dpi=90)
        plt.close()
        prof = dict(driver="GTiff", height=sh[0], width=sh[1], count=1, dtype="int16",
                    crs="EPSG:32749", transform=tr, compress="deflate", nodata=-1)
        with rasterio.open(os.path.join(OUT, f"spread_track{t}_pair_index.tif"), "w", **prof) as ds:
            ds.write(np.where(burn, kstar, -1).astype(np.int16), 1)

    # combined date interval where both tracks see the burn
    if len(per_track) == 2:
        (pa, ba, ka, _), (pb, bb, kb, _) = per_track[90], per_track[155]
        a0 = np.array([day(p[0]) for p in pa])[ka]
        a1 = np.array([day(p[1]) for p in pa])[ka]
        b0 = np.array([day(p[0]) for p in pb])[kb]
        b1 = np.array([day(p[1]) for p in pb])[kb]
        both = ba & bb
        lo, hi = np.maximum(a0, b0), np.minimum(a1, b1)
        agree = both & (hi > lo)
        width = (hi - lo)[agree]
        report["combined"] = {"both_tracks_ha": float(both.sum() * RES * RES / 1e4),
                              "intervals_consistent": float(agree.sum() / max(both.sum(), 1)),
                              "median_interval_days": float(np.median(width)) if width.size else None}
        print(f"\n== tracks 90 + 155: burned in both {both.sum() * RES * RES / 1e4:,.0f} ha; "
              f"date intervals overlap for {agree.sum() / max(both.sum(), 1):.0%}; "
              f"median combined interval {np.median(width) if width.size else float('nan'):.0f} days")
    json.dump(report, open(os.path.join(OUT, "spread_report.json"), "w"), indent=2)
    print(f"\nSaved: {os.path.join(OUT, 'spread_report.json')} and spread_track*.png / *.tif")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=["fetch", "map"])
    a = ap.parse_args()
    {"fetch": stage_fetch, "map": stage_map}[a.stage](a)


if __name__ == "__main__":
    main()
