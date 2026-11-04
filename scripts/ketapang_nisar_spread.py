#!/usr/bin/env python3
"""Fire spread on the Ketapang coast from NISAR L-band radar (v2).

v1 used coherence loss from one or two tracks: recall 0.76-0.79 against the
Sentinel-2 burn, but precision only ~0.49, and 12-24 day dating. v2 adds:

  1. BACKSCATTER. A burn also changes the radar return: canopy, fern and
     litter go, so cross-polarised (HV) volume scattering drops; HH changes
     with the wet ash and exposed peat. Each coherence dip must come with an
     HV (and HH) change across the same dates, from the GCOV products.
     Water and flood margins (JRC Global Surface Water occurrence) are
     masked: flooding also breaks coherence.
  2. FIVE TRACKS (90 D, 162 D, 54 A, 154 A, 155 A). Each pixel's burn window
     is the INTERSECTION of the windows from every track that sees it, so
     tracks offset by days narrow it from 12-24 days.

Per track, pair k (t_k -> t_k+1), on a common 40 m UTM grid (3x3 median):
  dip_k  = mean(coh_{k-1}, coh_{k+1}) - coh_k   (interior pairs only),
           minus the AOI-wide median dip of that pair
  dHV_k  = HV_dB(t_k+1) - HV_dB(t_k),  dHH_k likewise (backscatter, RTC gamma0)
  k*     = argmax dip; burned if dip >= T1 and the backscatter change at k*
           passes T2. T1, T2 and the sign of the backscatter rule are chosen
           by F1 against the S2 burn on even 5 km checkerboard blocks and
           scored on odd blocks (never used for any choice).
Fusion across tracks: burned if detected by >= half of the tracks that
cover the pixel (at least one); date window = intersection of the
detecting tracks' windows (if they disagree, the strongest track's).

Inside or outside first: for every burned patch that crosses a concession
boundary, the earliest window in the 1 km band inside vs the 1 km band
outside.

Data: NISAR L2 GUNW (20 m coherence) and GCOV (20 m HH/HV) provisional,
only the HDF5 chunks over the AOI are range-read from ASF (~/.netrc).

STAGES  water (env base, Earth Engine) | fetch | map   (fetch/map: env insardev)
    conda run -n base python scripts/ketapang_nisar_spread.py --stage water
    conda run -n insardev python scripts/ketapang_nisar_spread.py --stage fetch
    conda run -n insardev python scripts/ketapang_nisar_spread.py --stage map
"""

import argparse
import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import CONC, FOUR, PEAT, _DATA_ROOT  # noqa: E402

ORIGIN = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin")
OUT = os.path.join(ORIGIN, "nisar")
NIS = os.path.join(_DATA_ROOT, "data", "nisar_ketapang")
CACHE = os.path.join(NIS, "coh20")
GCACHE = os.path.join(NIS, "gcov20")
WATER = os.path.join(NIS, "jrc_occurrence_30m.tif")
AOI = (110.00, -2.10, 110.58, -1.45)
W = "science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/"
GC = "science/LSAR/GCOV/grids/frequencyA/"
TRACKS = {90: "D", 162: "D", 54: "A", 154: "A", 155: "A"}
RES = 40.0
BLOCK_M = 5000
WATER_OCC = 5             # % of months with water, 1984-2021: flood-prone
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


def _search(level):
    import geopandas as gpd
    import pandas as pd
    import requests
    import shapely
    box = shapely.geometry.box(*AOI)
    r = requests.get(SEARCH, params={"dataset": "NISAR", "intersectsWith": box.wkt, "output": "geojson",
                                     "maxResults": 2000, "processingLevel": level}, timeout=300)
    g = gpd.GeoDataFrame.from_features(r.json()["features"], crs=4326)
    g["cov"] = g.geometry.intersection(box).area / box.area
    parts = g.sceneName.str.split("_")
    if level == "GUNW":
        g["ref"], g["rep"] = parts.str[11].str[:8], parts.str[13].str[:8]
        g["days"] = (pd.to_datetime(g.rep) - pd.to_datetime(g.ref)).dt.days
    else:
        g["date"] = g.startTime.str[:10].str.replace("-", "")
    return g[g["cov"] > 0.15]


def scenes():
    """Per track, the chain of consecutive shortest pairs."""
    g = _search("GUNW")
    out = []
    for t in TRACKS:
        s = g[g.pathNumber == t].sort_values(["ref", "days", "cov"], ascending=[True, True, False])
        s = s.drop_duplicates("ref")
        chain, last = [], None
        for row in s.itertuples():
            if last is None or row.ref == last:
                chain.append(row)
                last = row.rep
        out += chain
    return out


def gcov_scenes():
    """Per track and date, the GCOV frame covering most of the AOI."""
    g = _search("GCOV")
    g = g[g.pathNumber.isin(list(TRACKS))]
    return list(g.sort_values("cov", ascending=False).drop_duplicates(["pathNumber", "date"]).itertuples())


def stage_water(a):
    """JRC surface-water occurrence over the AOI (needs Earth Engine)."""
    import ee
    from earthchange.gee_utils import initialize_ee, download_geotiff
    initialize_ee()
    os.makedirs(NIS, exist_ok=True)
    img = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).toUint8()
    ok = download_geotiff(img, ee.Geometry.Rectangle(list(AOI), None, False), WATER, scale=30)
    print("saved" if ok else "FAILED", WATER)


def _crop(h, base, names, x0, x1, y0, y1):
    import numpy as np
    xs, ys = h[base + "xCoordinates"][()], h[base + "yCoordinates"][()]
    ci = np.flatnonzero((xs >= x0) & (xs <= x1))
    ri = np.flatnonzero((ys >= y0) & (ys <= y1))
    if len(ci) < 10 or len(ri) < 10:
        return None
    sl = (slice(ri[0], ri[-1] + 1), slice(ci[0], ci[-1] + 1))
    return {n: h[base + p][sl] for n, p in names.items()}, xs[ci], ys[ri]


def stage_fetch(a):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import h5py
    import numpy as np
    import requests
    from pyproj import Transformer
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(GCACHE, exist_ok=True)
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])
    tls = threading.local()

    def sess():
        if not hasattr(tls, "s"):
            tls.s = requests.Session()
        return tls.s

    jobs = []
    for row in scenes():
        p = os.path.join(CACHE, f"t{row.pathNumber}_{row.ref}_{row.rep}.npz")
        jobs.append(("coh", row, p))
    for row in gcov_scenes():
        p = os.path.join(GCACHE, f"t{row.pathNumber}_{row.date}.npz")
        jobs.append(("gcov", row, p))

    def one(job):
        kind, row, p = job
        if os.path.exists(p):
            return f"have {os.path.basename(p)}"
        local = os.path.join(NIS, os.path.basename(row.url))
        fo = open(local, "rb") if os.path.exists(local) else RangeFile(row.url, sess())
        with h5py.File(fo, "r") as h:
            if kind == "coh":
                r = _crop(h, W, {"coh": "HH/coherenceMagnitude"}, x0, x1, y0, y1)
                epsg = int(h[W + "HH/projection"][()])
            else:
                r = _crop(h, GC, {"hh": "HHHH", "hv": "HVHV"}, x0, x1, y0, y1)
                epsg = int(h[GC + "projection"][()])
        if r is None:
            return f"no overlap {row.sceneName}"
        d, x, y = r
        if kind == "coh":
            np.savez_compressed(p, coh=d["coh"].astype(np.float16), x=x, y=y, epsg=epsg)
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                db = {k: (10 * np.log10(v.astype(np.float32))).astype(np.float16) for k, v in d.items()}
            np.savez_compressed(p, hh=db["hh"], hv=db["hv"], x=x, y=y, epsg=epsg)
        return f"saved {os.path.basename(p)} ({getattr(fo, 'fetched', 0) / 1e6:.0f} MB read)"

    print(f"{len(jobs)} items ({sum(j[0] == 'coh' for j in jobs)} coherence pairs, "
          f"{sum(j[0] == 'gcov' for j in jobs)} backscatter dates)")
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(one, jobs):
            print(" ", msg, flush=True)


# ---------------------------------------------------------------------- map
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

    os.makedirs(OUT, exist_ok=True)
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])
    tr = Affine(RES, 0, x0, 0, -RES, y1)
    sh = (int((y1 - y0) // RES), int((x1 - x0) // RES))
    px_ha = RES * RES / 1e4
    day = lambda s: (pd.Timestamp(s) - pd.Timestamp("2026-01-01")).days   # noqa: E731

    def med3(x):
        st_ = np.stack([np.roll(np.roll(x, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)])
        with np.errstate(all="ignore"):
            return np.nanmedian(st_, axis=0)

    def on_grid(p, key, average_linear=False):
        z = np.load(p)
        c = z[key].astype(np.float32)
        c[~np.isfinite(c)] = np.nan
        if key == "coh":
            c[c <= 0] = np.nan
        x, y = z["x"], z["y"]
        dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
        st = Affine(dx, 0, x[0] - dx / 2, 0, dy, y[0] - dy / 2)
        if average_linear:                       # average power, not dB
            c = 10 ** (c / 10)
        dst = np.full(sh, np.nan, np.float32)
        reproject(c, dst, src_transform=st, src_crs=f"EPSG:{int(z['epsg'])}", dst_transform=tr,
                  dst_crs="EPSG:32749", resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
        if average_linear:
            with np.errstate(all="ignore"):
                dst = 10 * np.log10(dst)
        return med3(dst)

    # ---- reference rasters
    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as src:
        bf = np.zeros(sh, np.float32)
        lf = np.zeros(sh, np.float32)
        reproject(src.read(2).astype(np.float32), bf, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.average)
        reproject((src.read(1) != 255).astype(np.float32), lf, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.average)
    land = lf >= 0.5
    wet = np.zeros(sh, bool)
    if os.path.exists(WATER):
        wo = np.zeros(sh, np.float32)
        with rasterio.open(WATER) as src:
            reproject(src.read(1).astype(np.float32), wo, src_transform=src.transform, src_crs=src.crs,
                      dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.max)
        wet = ndimage.binary_dilation(wo >= WATER_OCC, iterations=2)          # + 80 m margin
        print(f"water / flood-margin mask: {wet[land].mean():.1%} of land")
    else:
        print("no water mask (run --stage water)")
    land_ok = land & ~wet
    s2b, s2u = (bf >= 0.5) & land_ok, (bf == 0) & land_ok
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
    vday = ndimage.minimum_filter(vday, size=int(2 * 400 / RES) + 1)
    yy, xx = np.indices(sh)
    blk = ((yy * RES // BLOCK_M) + (xx * RES // BLOCK_M)) % 2
    cal, te = blk == 0, blk == 1

    conc = gpd.read_file(CONC).to_crs(32749)
    cmask = {acr: features.rasterize(
        [(g, 1) for g in conc[conc.company.str.contains(n, case=False, na=False)].geometry],
        out_shape=sh, transform=tr, dtype="uint8") > 0 for acr, n in FOUR.items()}
    anyc = features.rasterize([(g, 1) for g in conc.geometry if g is not None], out_shape=sh,
                              transform=tr, dtype="uint8") > 0

    def score(burn, mask):
        tp, fp = (burn & s2b & mask).sum(), (burn & s2u & mask).sum()
        fn = (~burn & s2b & mask).sum()
        p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        return float(p), float(r), float(2 * p * r / max(p + r, 1e-9))

    report = {"water_mask_share_of_land": float(wet[land].mean())}
    tracks = {}
    for t in TRACKS:
        files = sorted(glob.glob(os.path.join(CACHE, f"t{t}_*.npz")))
        if len(files) < 4:
            print(f"track {t}: {len(files)} pairs, skipped")
            continue
        pairs = [tuple(os.path.basename(f)[:-4].split("_")[1:]) for f in files]
        K = len(files)
        G = np.stack([on_grid(f, "coh") for f in files])
        cover = np.isfinite(G).sum(0) >= K - 2
        D = np.full_like(G, np.nan)
        for k in range(1, K - 1):
            D[k] = np.nanmean(np.stack([G[k - 1], G[k + 1]]), axis=0) - G[k]
            D[k] -= np.nanmedian(D[k][land_ok & np.isfinite(D[k])])
        # backscatter change across each pair's dates (nearest GCOV date)
        gfiles = {os.path.basename(f)[:-4].split("_")[1]: f
                  for f in glob.glob(os.path.join(GCACHE, f"t{t}_*.npz"))}
        have_bs = all(p[0] in gfiles and p[1] in gfiles for p in pairs[1:-1])
        dHV = np.full_like(G, np.nan)
        dHH = np.full_like(G, np.nan)
        if have_bs:
            cache = {}

            def bs(dt, pol):
                if (dt, pol) not in cache:
                    cache[(dt, pol)] = on_grid(gfiles[dt], pol, average_linear=True)
                return cache[(dt, pol)]
            for k in range(1, K - 1):
                dHV[k] = bs(pairs[k][1], "hv") - bs(pairs[k][0], "hv")
                dHH[k] = bs(pairs[k][1], "hh") - bs(pairs[k][0], "hh")
                for arr in (dHV, dHH):
                    arr[k] -= np.nanmedian(arr[k][land_ok & np.isfinite(arr[k])])
        Dz = np.where(np.isfinite(D), D, -9)
        kstar = Dz.argmax(0)
        dmax = Dz.max(0)
        hv_at = np.take_along_axis(dHV, kstar[None], 0)[0]
        hh_at = np.take_along_axis(dHH, kstar[None], 0)[0]
        valid = cover & land_ok
        # choose T1 and the backscatter rule by F1 on calibration blocks
        best = (-1, None)
        rules = {"coherence only": lambda T2: np.ones(sh, bool)}
        if have_bs:
            rules.update({"HV drop": lambda T2: hv_at <= -T2,
                          "HV or HH change": lambda T2: (np.abs(hv_at) >= T2) | (np.abs(hh_at) >= T2),
                          "HV drop or HH rise": lambda T2: (hv_at <= -T2) | (hh_at >= T2)})
        scan = []
        for name, rule in rules.items():
            for T2 in ([0.0] if name == "coherence only" else np.arange(0.25, 3.01, 0.25)):
                bsok = rule(T2)
                for T1 in np.arange(0.04, 0.31, 0.02):
                    burn = valid & (dmax >= T1) & bsok
                    f1 = score(burn, cal)[2]
                    scan.append((name, float(T2), float(T1), f1))
                    if f1 > best[0]:
                        best = (f1, (name, float(T2), float(T1)))
        name, T2, T1 = best[1]
        if have_bs:      # does backscatter separate burned from false dips at all?
            cand = valid & (dmax >= T1) & cal
            for lab_, m in (("S2-burned", cand & s2b), ("S2-unburned", cand & s2u)):
                print(f"   t{t} dip>={T1:.2f} {lab_:12} n={m.sum():>7}  dHV median {np.nanmedian(hv_at[m]):+.2f} "
                      f"[{np.nanpercentile(hv_at[m], 25):+.2f},{np.nanpercentile(hv_at[m], 75):+.2f}]  "
                      f"dHH median {np.nanmedian(hh_at[m]):+.2f}")
            for rn in rules:
                if rn == "coherence only":
                    continue
                for T2_ in (0.5, 1.0, 2.0):
                    pp, rr_, ff = score(valid & (dmax >= T1) & rules[rn](T2_), cal)
                    print(f"   t{t} {rn:20} T2 {T2_:.1f}: P {pp:.2f} R {rr_:.2f} F1 {ff:.2f}")
        burn = valid & (dmax >= T1) & rules[name](T2)
        prec, rec, f1 = score(burn, te)
        co = [s for s in scan if s[0] == "coherence only"]
        cbest = max(co, key=lambda s: s[3])
        cburn = valid & (dmax >= cbest[2])
        cp, crc, cf = score(cburn, te)
        # high-precision "confirmed" layer: the most recall at precision >= 0.70
        # on calibration blocks, coherence dip AND backscatter change
        conf, conf_r = np.zeros(sh, bool), None
        if have_bs:
            bestc = (-1, None)
            for rn in [r_ for r_ in rules if r_ != "coherence only"]:
                for T2_ in np.arange(0.25, 3.01, 0.25):
                    bsok = rules[rn](T2_)
                    for T1_ in np.arange(0.04, 0.31, 0.02):
                        pp, rr_, _ = score(valid & (dmax >= T1_) & bsok, cal)
                        if pp >= 0.70 and rr_ > bestc[0]:
                            bestc = (rr_, (rn, float(T2_), float(T1_)))
            if bestc[1]:
                rn, T2_, T1_ = bestc[1]
                conf = valid & (dmax >= T1_) & rules[rn](T2_)
                cp_, cr_, cf_ = score(conf, te)
                conf_r = {"rule": rn, "T_backscatter_dB": T2_, "T_dip": T1_,
                          "heldout_precision": cp_, "heldout_recall": cr_, "heldout_f1": cf_}
                print(f"   t{t} CONFIRMED layer '{rn}' dip>={T1_:.2f} bs {T2_:.2f} dB: "
                      f"held-out P {cp_:.2f} R {cr_:.2f}")
        t0 = np.array([day(p[0]) for p in pairs])
        t1 = np.array([day(p[1]) for p in pairs])
        tracks[t] = dict(pairs=pairs, burn=burn, k=kstar, lo=t0[kstar], hi=t1[kstar], cover=valid,
                         strength=dmax, conf=conf)
        r = {"pairs": [f"{p[0]}-{p[1]}" for p in pairs], "backscatter": have_bs,
             "rule": name, "T_backscatter_dB": T2, "T_dip": T1,
             "heldout_precision": prec, "heldout_recall": rec, "heldout_f1": f1,
             "coherence_only_heldout": {"precision": cp, "recall": crc, "f1": cf},
             "cover_share_of_land": float(valid[land].mean()), "confirmed_layer": conf_r}
        report[f"track_{t}"] = r
        print(f"== track {t}{TRACKS[t]}: {K} pairs, backscatter {'yes' if have_bs else 'NO'}, "
              f"rule '{name}' dip>={T1:.2f} bs {T2:.2f} dB; held-out P {prec:.2f} R {rec:.2f} F1 {f1:.2f}  "
              f"(coherence only: P {cp:.2f} R {crc:.2f})  covers {valid[land].mean():.0%} of land")

    # ---- fusion across tracks
    T = list(tracks)
    ncov = sum(tracks[t]["cover"].astype(int) for t in T)
    ndet = sum((tracks[t]["burn"]).astype(int) for t in T)
    fused = (ndet >= 1) & (ndet >= np.ceil(ncov / 2)) & land_ok
    lo = np.full(sh, -9999)
    hi = np.full(sh, 9999)
    for t in T:
        b = tracks[t]["burn"]
        lo = np.where(b, np.maximum(lo, tracks[t]["lo"]), lo)
        hi = np.where(b, np.minimum(hi, tracks[t]["hi"]), hi)
    bad = fused & (hi <= lo)                   # windows disagree: strongest track
    if bad.any():
        sel = np.stack([np.where(tracks[t]["burn"], tracks[t]["strength"], -9) for t in T]).argmax(0)
        for i, t in enumerate(T):
            m = bad & (sel == i)
            lo[m], hi[m] = tracks[t]["lo"][m], tracks[t]["hi"][m]
    confirmed = np.any([tracks[t]["conf"] for t in T], axis=0) & fused
    cp_, cr_, cf_ = score(confirmed, te)
    report["confirmed"] = {"heldout_precision": cp_, "heldout_recall": cr_, "heldout_f1": cf_,
                           "ha": float(confirmed.sum() * px_ha)}
    print(f"\n== confirmed (fused AND dip+backscatter on any track): held-out P {cp_:.2f} R {cr_:.2f}, "
          f"{confirmed.sum() * px_ha:,.0f} ha")
    fp_, fr_, ff_ = score(fused, te)
    width = (hi - lo)[fused]
    mid = 0.5 * (lo + hi)
    both = fused & (vday < 9999)
    lag = (mid - vday)[both]
    inwin = ((vday >= lo - 3) & (vday < hi + 3))[both]       # 3 d slack for the 375 m pixel
    report["fused"] = {"tracks": T, "heldout_precision": fp_, "heldout_recall": fr_, "heldout_f1": ff_,
                       "burned_ha": float(fused.sum() * px_ha),
                       "window_days_median": float(np.median(width)),
                       "window_days_p75": float(np.percentile(width, 75)),
                       "share_window_le_6d": float((width <= 6).mean()),
                       "windows_disagreed_share": float(bad.sum() / max(fused.sum(), 1)),
                       "radar_minus_first_viirs_days_median": float(np.median(lag)),
                       "first_viirs_within_window_pm3d": float(inwin.mean()),
                       "radar_burned_no_viirs_ha": float((fused & s2b & (vday == 9999)).sum() * px_ha)}
    print(f"\n== fused {T}: held-out P {fp_:.2f} R {fr_:.2f} F1 {ff_:.2f}; window median "
          f"{np.median(width):.0f} d (<=6 d for {(width <= 6).mean():.0%}); radar - first VIIRS "
          f"{np.median(lag):+.0f} d; first VIIRS inside window (+-3 d) {inwin.mean():.0%}")

    # ---- inside or outside first, at the boundary
    rows = []
    lab, n = ndimage.label(fused)
    for acr, m in cmask.items():
        din = ndimage.distance_transform_edt(m) * RES
        dout = ndimage.distance_transform_edt(~m) * RES
        band_in, band_out = m & (din <= 1000), ~m & ~anyc & (dout <= 1000)
        ids = np.intersect1d(np.unique(lab[fused & band_in]), np.unique(lab[fused & band_out]))
        ids = ids[ids > 0]
        cnt = {"inside_first": 0, "outside_first": 0, "same_window": 0, "ha": 0.0}
        for i in ids:
            pi, po = (lab == i) & band_in, (lab == i) & band_out
            if pi.sum() < 10 or po.sum() < 10:
                continue
            ei, eo = np.percentile(mid[pi], 10), np.percentile(mid[po], 10)
            k = "same_window" if abs(ei - eo) < 4 else ("inside_first" if ei < eo else "outside_first")
            cnt[k] += 1
            cnt["ha"] += float(((lab == i) & (band_in | band_out)).sum() * px_ha)
        rows.append({"concession": acr, **cnt})
    report["boundary_first"] = rows
    print("\nburn patches crossing each boundary (earliest 10% of dates, 1 km bands):")
    print(pd.DataFrame(rows).to_string(index=False))

    # ---- area per week, inside the four vs unconceded
    wk = np.where(fused, (mid // 7).astype(int), -1)
    tl = []
    for w_ in sorted(set(wk[fused].tolist())):
        m = wk == w_
        row = {"week_start": str((pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * w_)).date()),
               "unconceded_ha": float((m & ~anyc).sum() * px_ha)}
        for acr, cm in cmask.items():
            row[acr] = float((m & cm).sum() * px_ha)
        tl.append(row)
    report["weekly"] = tl
    pd.DataFrame(tl).to_csv(os.path.join(OUT, "spread_v2_weekly.csv"), index=False)

    prof = dict(driver="GTiff", height=sh[0], width=sh[1], count=4, dtype="int16", crs="EPSG:32749",
                transform=tr, compress="deflate", nodata=-1)
    with rasterio.open(os.path.join(OUT, "spread_v2_fused.tif"), "w", **prof) as ds:
        ds.write(np.where(fused, lo, -1).astype(np.int16), 1)
        ds.write(np.where(fused, hi, -1).astype(np.int16), 2)
        ds.write(np.where(land_ok, ncov, -1).astype(np.int16), 3)
        ds.write(np.where(land_ok, confirmed, -1).astype(np.int16), 4)
        ds.descriptions = ("window start (day of 2026, 0 = 1 Jan)", "window end", "tracks covering",
                           "confirmed by backscatter (1)")
    json.dump(report, open(os.path.join(OUT, "spread_v2_report.json"), "w"), indent=2, default=float)
    plot(fused, mid, sh, tr, conc, cmask, report)
    print(f"\nSaved: {OUT}/spread_v2_report.json, spread_v2_fused.tif, spread_v2_map.png, spread_v2_weekly.csv")


def plot(fused, mid, sh, tr, conc, cmask, report):
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ext = (tr.c, tr.c + sh[1] * RES, tr.f - sh[0] * RES, tr.f)
    fig, ax = plt.subplots(figsize=(10, 11))
    ax.set_facecolor("#dddddd")
    d0, d1 = 182, 292                                   # 1 Jul - 19 Oct
    im = ax.imshow(np.where(fused, mid, np.nan), cmap="inferno", vmin=d0, vmax=d1, extent=ext,
                   interpolation="nearest")
    conc.cx[ext[0]:ext[1], ext[2]:ext[3]].boundary.plot(ax=ax, color="#555", lw=0.4)
    for acr, n in FOUR.items():
        g = conc[conc.company.str.contains(n, case=False, na=False)]
        g.boundary.plot(ax=ax, color="k", lw=1.4)
        c = g.geometry.iloc[0].representative_point()
        ax.annotate(acr, (c.x, c.y), fontsize=11, weight="bold", ha="center",
                    bbox=dict(fc="white", alpha=0.7, lw=0))
    ticks = [182, 197, 213, 228, 244, 259, 274, 289]
    cb = plt.colorbar(im, ax=ax, ticks=ticks, shrink=0.7)
    cb.ax.set_yticklabels([(pd.Timestamp("2026-01-01") + pd.Timedelta(days=d)).strftime("%d %b") for d in ticks])
    cb.set_label("burn date (middle of the fused radar window)")
    f = report["fused"]
    ax.set_xlim(ext[:2]); ax.set_ylim(ext[2:]); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"Fire spread from NISAR L-band, {len(f['tracks'])} tracks fused\n"
                 f"held-out vs Sentinel-2: precision {f['heldout_precision']:.2f}, recall "
                 f"{f['heldout_recall']:.2f}; median window {f['window_days_median']:.0f} days")
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, "spread_v2_map.png"), dpi=90)
    plt.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=["water", "fetch", "map"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    {"water": stage_water, "fetch": stage_fetch, "map": stage_map}[a.stage](a)


if __name__ == "__main__":
    main()
