#!/usr/bin/env python3
"""Maps, frames and figures for Part 3 of the concessions film ("Menembus
asap" / "Through the smoke"): how the 2026 fire moved across the Ketapang
coast, with VIIRS as the clock and NISAR L-band radar as the check on the
ground under the smoke.

Reads ketapang_nisar_spread.py's v2 output (spread_v2_fused.tif and
spread_v2_report.json), the VIIRS season file, the Sentinel-1 coherence
from the failed SBAS attempt and one NISAR coherence pair, and writes into
video/narasi-karhutla:

  public/radar/asap.jpg          Sentinel-2 on 2 Sep and 7 Sep: smoke
  public/radar/jam/dNNN.jpg      one frame per day, 1 Jul - 31 Oct: VIIRS
                                 detections, the last 2 days bright
  public/radar/koherensi.jpg     Sentinel-1 C-band vs NISAR L-band coherence
  public/radar/peta_radar.jpg    the radar "confirmed" burn over the S2 burn
  public/radar/pekan/wNN.jpg     one frame per week: confirmed burn by the
                                 middle of its radar window
  src/radarData.json             every figure the film shows or speaks

Same frame rules as Parts 1-2 (ketapang_film2_assets.figure): 1920x1080 on
the soot ground, map in the right column, the four by acronym.

STAGES  s2 (Earth Engine thumbnails) | all (everything else)
    conda run -n base python scripts/ketapang_film3_assets.py --stage s2
    conda run -n base python scripts/ketapang_film3_assets.py --stage all
"""

import argparse
import glob
import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
sys.path.insert(0, _REPO_ROOT)
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_nisar_spread import AOI, RES, ORIGIN, OUT as NOUT, CACHE, CONC, FOUR  # noqa: E402
from kalimantan_concession_film_assets import JELAGA, KAPUR, BARA, NYALA, ABU  # noqa: E402

FILM = os.path.join(_REPO_ROOT, "video", "narasi-karhutla")
PUB = os.path.join(FILM, "public", "radar")
DARAT = "#1B2029"
BEKAS = "#4A2C20"           # the Sentinel-2 burn, under the radar layer
SMOKE_DATES = ("2026-09-02", "2026-09-07")
D0 = "2026-07-01"
NDAYS = 123                 # 1 Jul - 31 Oct
COH_PAIR = "t90_20260620_20260702.npz"    # pre-fire NISAR pair, track 90
JPG = dict(pil_kwargs={"quality": 88})


def stage_s2(_a):
    import ee
    import requests
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    os.makedirs(PUB, exist_ok=True)
    g = ee.Geometry.Rectangle(list(AOI), None, False)
    col = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(g)
    for d in SMOKE_DATES:
        m = col.filterDate(d, ee.Date(d).advance(1, "day")).mosaic().clip(g)
        url = m.visualize(bands=["B4", "B3", "B2"], min=0, max=2500).getThumbURL(
            {"region": g, "dimensions": 1100, "format": "png"})
        p = os.path.join(PUB, f"s2_{d}.png")
        open(p, "wb").write(requests.get(url, timeout=600).content)
        print("saved", p)


# ------------------------------------------------------------------ helpers
def grid():
    from affine import Affine
    from pyproj import Transformer
    to_utm = Transformer.from_crs(4326, 32749, always_xy=True)
    (x0, y0), (x1, y1) = to_utm.transform(AOI[0], AOI[1]), to_utm.transform(AOI[2], AOI[3])
    tr = Affine(RES, 0, x0, 0, -RES, y1)
    sh = (int((y1 - y0) // RES), int((x1 - x0) // RES))
    return tr, sh, to_utm


def figure(extent):
    from ketapang_film2_assets import figure as f2
    return f2(extent)


def save(fig, name):
    import matplotlib.pyplot as plt
    p = os.path.join(PUB, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fig.savefig(p, facecolor=JELAGA, **(JPG if p.endswith(".jpg") else {}))
    plt.close(fig)
    return p


def label(ax, x, y, t, size=22):
    import matplotlib.patheffects as pe
    ax.annotate(t, (x, y), ha="center", va="center", fontsize=size, fontweight="bold", color=KAPUR,
                fontfamily="DejaVu Sans", path_effects=[pe.withStroke(linewidth=6, foreground=JELAGA)])


def rgb_base(land, s2b=None):
    import numpy as np
    from matplotlib.colors import to_rgb
    img = np.zeros(land.shape + (3,))
    img[:] = to_rgb(JELAGA)
    img[land] = to_rgb(DARAT)
    if s2b is not None:
        img[s2b & land] = to_rgb(BEKAS)
    return img


def main_all(_a):
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from affine import Affine
    from matplotlib.colors import to_rgb
    from rasterio import features
    from rasterio.warp import reproject, Resampling
    from scipy import ndimage

    os.makedirs(PUB, exist_ok=True)
    tr, sh, to_utm = grid()
    px_ha = RES * RES / 1e4
    ext = (tr.c, tr.c + sh[1] * RES, tr.f - sh[0] * RES, tr.f)
    day0 = pd.Timestamp(D0)
    doy0 = (day0 - pd.Timestamp("2026-01-01")).days

    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as src:
        bf = np.zeros(sh, np.float32)
        lf = np.zeros(sh, np.float32)
        reproject(src.read(2).astype(np.float32), bf, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.average)
        reproject((src.read(1) != 255).astype(np.float32), lf, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:32749", resampling=Resampling.average)
    land, s2b = lf >= 0.5, bf >= 0.5
    with rasterio.open(os.path.join(NOUT, "spread_v2_fused.tif")) as ds:
        assert ds.shape == sh, (ds.shape, sh)
        lo, hi, ncov, conf = ds.read(1), ds.read(2), ds.read(3), ds.read(4)
    fused = lo >= 0
    confirmed = (conf == 1) & fused
    mid = np.where(fused, 0.5 * (lo + hi), np.nan)

    conc = gpd.read_file(CONC).to_crs(32749)
    rows = []
    for acr, n in FOUR.items():
        s = conc[conc.company.str.contains(n, case=False, na=False)]
        rows.append({"acr": acr, "geometry": s.geometry.iloc[0]})
    conc4 = gpd.GeoDataFrame(rows, crs=32749)
    four = features.rasterize([(g, 1) for g in conc4.geometry], out_shape=sh, transform=tr,
                              dtype="uint8") > 0
    anyc = features.rasterize([(g, 1) for g in conc.geometry if g is not None], out_shape=sh,
                              transform=tr, dtype="uint8") > 0
    unc = land & ~anyc

    def outlines(ax, lw=1.8, size=22):
        conc4.boundary.plot(ax=ax, color=KAPUR, lw=lw)
        for _, r in conc4.iterrows():
            p = r.geometry.representative_point()
            label(ax, p.x, p.y, r.acr, size)

    # ---- smoke diptych (from --stage s2)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    tiles = [os.path.join(PUB, f"s2_{d}.png") for d in SMOKE_DATES]
    if all(os.path.exists(p) for p in tiles):
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
        im0 = Image.open(tiles[0])
        asp = im0.height / im0.width
        hh = 0.56
        ww = hh / asp * 10.8 / 19.2
        gap = 0.012
        for k, p in enumerate(tiles):
            ax = fig.add_axes([0.97 - (2 - k) * ww - (1 - k) * gap, 0.5 - hh / 2, ww, hh])
            ax.imshow(Image.open(p).convert("RGB"), interpolation="lanczos")
            ax.axis("off")
        print("Saved:", save(fig, "asap.jpg"))
    else:
        print("no S2 tiles: run --stage s2 first")

    # ---- VIIRS: one frame per day
    v = pd.read_csv(glob.glob(os.path.join(ORIGIN, "viirs_*.csv"))[0])
    v["t"] = pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)     # WIB
    v["d"] = (v.t.dt.normalize() - day0).dt.days
    vx, vy = to_utm.transform(v.lon.to_numpy(), v.lat.to_numpy())
    rr, cc = rasterio.transform.rowcol(tr, vx, vy)
    v["r"], v["c"] = np.asarray(rr), np.asarray(cc)
    v = v[(v.r >= 0) & (v.r < sh[0]) & (v.c >= 0) & (v.c < sh[1]) & (v.d >= 0) & (v.d < NDAYS)]
    v["zone"] = np.where(four[v.r, v.c], "four", np.where(unc[v.r, v.c], "unc", "other"))
    daily = v.groupby("d").size().reindex(range(NDAYS), fill_value=0)
    foot = np.ones((3, 3), bool)                        # square, like the 375 m pixel
    R_PX = int(round(187 / RES))                          # half a 375 m pixel
    base = rgb_base(land)
    dim, hot = np.array(to_rgb(BARA)) * 0.55, np.array(to_rgb(NYALA))
    seen = np.zeros(sh, bool)
    for d in range(NDAYS):
        now = np.zeros(sh, bool)
        s = v[v.d == d]
        now[s.r.to_numpy(), s.c.to_numpy()] = True
        now = ndimage.binary_dilation(now, foot, iterations=R_PX)
        recent = now.copy()
        if d:
            s1 = v[v.d == d - 1]
            m1 = np.zeros(sh, bool)
            m1[s1.r.to_numpy(), s1.c.to_numpy()] = True
            recent |= ndimage.binary_dilation(m1, foot, iterations=R_PX)
        img = base.copy()
        img[seen] = dim
        img[recent] = hot
        seen |= now
        fig, ax = figure(ext)
        ax.imshow(img, extent=ext, interpolation="nearest")
        outlines(ax)
        save(fig, f"jam/d{d:03d}.jpg")
    print(f"Saved: {NDAYS} daily frames in {PUB}/jam")

    # ---- C-band vs L-band coherence
    def coh_on_grid(arr, st, crs):
        dst = np.full(sh, np.nan, np.float32)
        reproject(arr, dst, src_transform=st, src_crs=crs, dst_transform=tr, dst_crs="EPSG:32749",
                  resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
        return dst
    with rasterio.open(os.path.join(ORIGIN, "insar", "coherence_mean.tif")) as src:
        a = src.read(1).astype(np.float32)
        a[a <= 0] = np.nan
        cS1 = coh_on_grid(a, src.transform, src.crs)
    z = np.load(os.path.join(CACHE, COH_PAIR))
    c = z["coh"].astype(np.float32)
    c[~np.isfinite(c) | (c <= 0)] = np.nan
    x, y = z["x"], z["y"]
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    cL = coh_on_grid(c, Affine(dx, 0, x[0] - dx / 2, 0, dy, y[0] - dy / 2), f"EPSG:{int(z['epsg'])}")
    both = land & np.isfinite(cS1) & np.isfinite(cL)
    med_s1, med_l = float(np.median(cS1[both])), float(np.median(cL[both]))
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    asp = sh[0] / sh[1]
    hh = 0.56
    ww = hh / asp * 10.8 / 19.2
    gap = 0.014
    for k, arr in enumerate((cS1, cL)):
        ax = fig.add_axes([0.97 - (2 - k) * ww - (1 - k) * gap, 0.5 - hh / 2 - 0.02, ww, hh])
        show = np.where(land, arr, np.nan)
        ax.set_facecolor(JELAGA)
        ax.imshow(show, cmap="gray", vmin=0, vmax=0.6, extent=ext, interpolation="nearest")
        conc4.boundary.plot(ax=ax, color=BARA, lw=1.2)
        ax.set_xlim(ext[:2]); ax.set_ylim(ext[2:]); ax.axis("off")
    print("Saved:", save(fig, "koherensi.jpg"))

    # ---- confirmed radar burn over the S2 burn
    fig, ax = figure(ext)
    img = rgb_base(land, s2b)
    img[confirmed] = to_rgb(BARA)
    ax.imshow(img, extent=ext, interpolation="nearest")
    outlines(ax)
    print("Saved:", save(fig, "peta_radar.jpg"))

    # ---- weekly frames: confirmed burn by window middle
    wk0 = pd.Timestamp("2026-07-02")
    wd0 = (wk0 - pd.Timestamp("2026-01-01")).days
    wk = np.where(confirmed, np.floor((mid - wd0) / 7), -99).astype(int)
    NW = 14                                          # 2 Jul - 7 Oct
    weekly = []
    for w in range(NW):
        img = rgb_base(land)
        img[confirmed & (wk < w) & (wk >= 0)] = dim
        img[confirmed & (wk < 0) & (wk > -99)] = dim
        img[confirmed & (wk == w)] = hot
        fig, ax = figure(ext)
        ax.imshow(img, extent=ext, interpolation="nearest")
        outlines(ax)
        save(fig, f"pekan/w{w:02d}.jpg")
        m = confirmed & (wk == w)
        weekly.append({"mulai": str((wk0 + pd.Timedelta(days=7 * w)).date()),
                       "empat": float((m & four).sum() * px_ha),
                       "luar": float((m & unc).sum() * px_ha)})
    print(f"Saved: {NW} weekly frames in {PUB}/pekan")

    # ---- timing: the four vs unconceded land, two clocks
    def dstr(doy):
        return (pd.Timestamp("2026-01-01") + pd.Timedelta(days=float(doy))).strftime("%Y-%m-%d")
    vi = v[(v.d >= 0)]
    first_cell = vi.groupby(["r", "c"]).d.min().reset_index()
    first_cell["zone"] = np.where(four[first_cell.r, first_cell.c], "four",
                                  np.where(unc[first_cell.r, first_cell.c], "unc", "other"))
    timing = {}
    for zname, zm in (("four", four), ("unc", unc)):
        mm = mid[confirmed & zm]
        fc = first_cell[first_cell.zone == zname].d + doy0
        timing[zname] = {
            "radar_mid_median": dstr(np.median(mm)),
            "radar_mid_q25_q75": [dstr(np.percentile(mm, 25)), dstr(np.percentile(mm, 75))],
            "radar_share_by_end_aug": float((mm < 243).mean()),
            "viirs_first_median": dstr(np.median(fc)),
            "viirs_first_share_by_end_aug": float((fc < 243).mean()),
            "viirs_detections": int((vi.zone == zname).sum()),
            "confirmed_ha": float((confirmed & zm).sum() * px_ha),
        }
    print(json.dumps(timing, indent=1))

    R = json.load(open(os.path.join(NOUT, "spread_v2_report.json")))
    F, C = R["fused"], R["confirmed"]
    bnd = R["boundary_first"]
    npairs = sum(len(R[f"track_{t}"]["pairs"]) for t in F["tracks"])
    D = {
        "_comment": ["Ditulis oleh scripts/ketapang_film3_assets.py dari keluaran",
                     "ketapang_nisar_spread.py (v2). Jangan ketik angka di sini dengan tangan."],
        "hari_mulai": D0,
        "hari_n": NDAYS,
        "viirs_harian": [int(x) for x in daily.tolist()],
        "viirs_total": int(daily.sum()),
        "viirs_puncak_hari": dstr(doy0 + int(daily.rolling(7, center=True).mean().idxmax())),
        "koherensi_s1": med_s1,
        "koherensi_nisar": med_l,
        "lintasan": len(F["tracks"]),
        "pasangan": npairs,
        "terkonfirmasi_ha": C["ha"],
        "terkonfirmasi_presisi": C["heldout_precision"],
        "terkonfirmasi_recall": C["heldout_recall"],
        "jendela_median_hari": F["window_days_median"],
        "jendela_le6_pct": 100 * F["share_window_le_6d"],
        "jeda_radar_hari": F["radar_minus_first_viirs_days_median"],
        "pekanan": weekly,
        "batas": [{"akronim": r["concession"], "dalam": r["inside_first"], "luar": r["outside_first"],
                   "sama": r["same_window"]} for r in bnd],
        "batas_total": {k: int(sum(r[x] for r in bnd)) for k, x in
                        (("dalam", "inside_first"), ("luar", "outside_first"), ("sama", "same_window"))},
        "waktu": timing,
    }
    with open(os.path.join(FILM, "src", "radarData.json"), "w") as f:
        json.dump(D, f, indent=1, ensure_ascii=False)
    show = {k: v_ for k, v_ in D.items() if k not in ("viirs_harian", "_comment")}
    print(json.dumps(show, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=["s2", "all"])
    a = ap.parse_args()
    {"s2": stage_s2, "all": main_all}[a.stage](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
