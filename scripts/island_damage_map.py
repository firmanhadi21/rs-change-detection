"""Island-wide coherence change from all four tracks, normalised per track.

Frame 1148 does not cover Flores. It spans longitude 120.55 to 123.21 and
holds 191 of the 452 reports; the western third of the island, including
Labuan Bajo and the Manggarai highlands where the single largest cluster of
235 reports sits, falls outside it entirely. Complete coverage needs all four
products, and only by combining ascending with descending.

THE TRAP IN SIMPLY MOSAICKING THEM. The four pairs are not equivalent:

    asc f1148     06->18 Aug co-event, 25 Jul->06 Aug control   12d / 12d S1D
    asc f1153     06->18 Aug          , 25 Jul->06 Aug          12d / 12d S1D
    desc163 f620  09->21 Aug          , 28 Jul->09 Aug          12d / 12d S1D
    desc61  f620  02->20 Aug          , 21 Jul->02 Aug          18d CROSS / 12d

desc61's co-event pair is 18 days AND cross-mission (S1D paired with S1C)
against a 12-day same-mission control. That mismatch alone drives a scene-wide
coherence drop two to three times the matched tracks -- it already inflated
one analysis in this project before being caught. And desc61 is the ONLY
coverage west of 120.2, so pasting it in raw would paint apparent damage
across the western third of the island with no second track able to contradict
it.

So each track is normalised by subtracting its OWN scene-wide median drop
before combining. That removes the per-track offset, including desc61's
baseline artefact, and leaves the spatial structure that is the actual
question. What survives is relative: "this ground lost more coherence than the
rest of its own track", which is comparable across tracks in a way that raw
coherence drop is not.

WHAT NORMALISATION CANNOT FIX. It removes an offset, not a distortion. If the
18-day pair also decorrelates unevenly -- more on vegetation, less on rock --
the western third still carries a pattern the other tracks do not. Overlap
agreement is reported so the size of that residual problem is visible rather
than assumed, and the western third is flagged as single-track throughout.

    conda run -n insardev-test python scripts/island_damage_map.py
"""

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

REPO = os.path.expanduser("~/GitHub/rs-change-detection")
OUT = os.path.join(REPO, "output/coseismic")
REPORTS = os.path.join(REPO, "data/eq_reports.geojson")
EPI = (121.3517, -8.3101)

TRACKS = {
    "asc f1148": ("flores-coseismic-2026-asc-f1148-prepost-d2",
                  "flores-coseismic-2026-asc-f1148-prepre-d2", True),
    "asc f1153": ("flores-coseismic-2026-asc-f1153-prepost",
                  "flores-coseismic-2026-asc-f1153-prepre", True),
    "desc163": ("flores-coseismic-2026-desc163-f620-prepost-d2",
                "flores-coseismic-2026-desc163-f620-prepre-d2", True),
    # matched=False: 18-day cross-mission co-event vs 12-day control
    "desc61": ("flores-coseismic-2026-desc61-f621-prepost-d2",
               "flores-coseismic-2026-desc61-f621-prepre-d2", False),
}


def load(d, name):
    import rioxarray  # noqa: F401
    import xarray as xr
    hits = glob.glob(os.path.join(OUT, d, f"*_{name}.tif"))
    if not hits:
        return None
    da = xr.open_dataarray(hits[0], engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def track_blocks(label, co_d, ct_d, min_base, coast_px, step, min_px):
    """Median normalised coherence drop per lon/lat block for one track."""
    import xarray as xr
    from pyproj import Transformer
    from scipy import ndimage

    co, ct = load(co_d, "corr"), load(ct_d, "corr")
    wat = load(co_d, "water_mask")
    if co is None or ct is None or wat is None:
        print(f"  {label}: missing rasters, skipped")
        return {}, np.nan
    co, ct, wat = xr.align(co, ct, wat, join="inner")
    c2 = co.values.astype("float64")
    c1 = ct.values.astype("float64")

    ok = (np.isfinite(c1) & np.isfinite(c2) & (wat.values > 0)
          & (c1 >= min_base))
    if coast_px:
        ok &= ndimage.binary_erosion(
            np.isfinite(c1) & np.isfinite(c2) & (wat.values > 0),
            np.ones((3, 3)), iterations=coast_px, border_value=0)
    if ok.sum() < 1000:
        print(f"  {label}: too little qualifying ground, skipped")
        return {}, np.nan

    drop = c1 - c2
    med = float(np.median(drop[ok]))

    inv = Transformer.from_crs(co.rio.crs, "EPSG:4326", always_xy=True)
    xs = co[co.dims[-1]].values
    ys = co[co.dims[-2]].values
    X, Y = np.meshgrid(xs, ys)
    lon, lat = inv.transform(X[ok], Y[ok])
    val = drop[ok] - med                       # normalised, see the header

    key = (np.floor(lat / step).astype(np.int64) * 1_000_000
           + np.floor(lon / step).astype(np.int64))
    order = np.argsort(key)
    key, val = key[order], val[order]
    uniq, start = np.unique(key, return_index=True)
    ends = list(start[1:]) + [len(val)]
    meds = np.array([np.median(val[s:e]) for s, e in zip(start, ends)])
    cnt = np.array([e - s for s, e in zip(start, ends)])
    keep = cnt >= min_px
    print(f"  {label:>10}: {int(ok.sum()):>9,} px, raw median drop "
          f"{med:+.4f}, {int(keep.sum()):>6,} blocks")
    return dict(zip(uniq[keep], meds[keep])), med


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-baseline", type=float, default=0.3)
    ap.add_argument("--coast-px", type=int, default=10)
    ap.add_argument("--block-km", type=float, default=1.0)
    ap.add_argument("--min-px", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(OUT,
                                                  "island_damage_map.png"))
    a = ap.parse_args()

    step = a.block_km / 111.32
    grids, raw_med = {}, {}
    print("per-track blocks (drop normalised by each track's own median):")
    for label, (co_d, ct_d, matched) in TRACKS.items():
        g, m = track_blocks(label, co_d, ct_d, a.min_baseline, a.coast_px,
                            step, a.min_px)
        if g:
            grids[label] = g
            raw_med[label] = m
    if len(grids) < 2:
        sys.exit("need at least two tracks")

    print("\n  raw scene medians, before normalisation:")
    for k, v in raw_med.items():
        tag = "" if TRACKS[k][2] else "   <- baseline MISMATCHED"
        print(f"    {k:>10} {v:+.4f}{tag}")

    # Cross-track agreement wherever two matched tracks see the same block.
    print("\n  agreement between tracks on shared blocks:")
    labels = list(grids)
    for i, t1 in enumerate(labels):
        for t2 in labels[i+1:]:
            sh = set(grids[t1]) & set(grids[t2])
            if len(sh) < 100:
                continue
            v1 = np.array([grids[t1][k] for k in sh])
            v2 = np.array([grids[t2][k] for k in sh])
            r = float(np.corrcoef(v1, v2)[0, 1])
            print(f"    {t1:>10} vs {t2:<10} {len(sh):>6,} blocks  "
                  f"r = {r:+.3f}  median diff {np.median(v1-v2):+.4f}")

    # Combine: median of whatever tracks see each block.
    allk = set().union(*[set(g) for g in grids.values()])
    comb, ntr = {}, {}
    for k in allk:
        vs = [grids[t][k] for t in grids if k in grids[t]]
        comb[k] = float(np.median(vs))
        ntr[k] = len(vs)
    print(f"\n  combined: {len(comb):,} blocks of {a.block_km:.0f} km")
    for n in sorted(set(ntr.values())):
        c = sum(1 for v in ntr.values() if v == n)
        print(f"    seen by {n} track(s): {c:>6,} blocks "
              f"({100*c/len(comb):.0f}%)")

    keys = np.array(sorted(comb))
    lat = (keys // 1_000_000 + 0.5) * step
    lon = (keys % 1_000_000 + 0.5) * step
    val = np.array([comb[k] for k in keys])
    nt = np.array([ntr[k] for k in keys])

    west = lon < 120.2
    print(f"\n  west of 120.2 (desc61 is the only coverage): "
          f"{int(west.sum()):,} blocks")
    if west.any():
        print(f"    median normalised drop there {np.median(val[west]):+.4f}"
              f" vs {np.median(val[~west]):+.4f} elsewhere")
        print("    Interpret with care: single track, and the one track with")
        print("    a mismatched temporal baseline. Normalisation removes its")
        print("    offset, not any uneven pattern the longer pair imposes.")

    R = np.hypot((lon - EPI[0]) * 111.32 * np.cos(np.radians(lat)),
                 (lat - EPI[1]) * 111.32)
    print(f"\n  {'ring km':>10}{'blocks':>9}{'median':>10}{'p90':>9}")
    for r0, r1 in [(20, 30), (30, 40), (40, 50), (50, 65), (65, 90),
                   (90, 130), (130, 200)]:
        m = (R >= r0) & (R < r1)
        if m.sum() < 30:
            continue
        print(f"  {f'{r0}-{r1}':>10}{int(m.sum()):>9}"
              f"{np.median(val[m]):>10.4f}{np.percentile(val[m], 90):>9.4f}")

    d = json.load(open(REPORTS))
    rlon, rlat, rlv = [], [], []
    for f in d["features"]:
        c = (f.get("geometry") or {}).get("coordinates")
        if c:
            rlon.append(float(c[0])); rlat.append(float(c[1]))
            v = f["properties"].get("damage_level")
            rlv.append(v if isinstance(v, (int, float)) else -99)
    rlon = np.array(rlon); rlat = np.array(rlat); rlv = np.array(rlv)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(15, 9),
                           gridspec_kw={"height_ratios": [3, 2]})
    s = ax[0].scatter(lon, lat, c=val, s=2.5, cmap="RdBu_r",
                      vmin=-0.15, vmax=0.15, linewidths=0)
    sev = rlv >= 3
    ax[0].scatter(rlon[sev], rlat[sev], s=42, facecolors="none",
                  edgecolors="#111", linewidths=1.3, label="severe report")
    ax[0].plot(*EPI, "*", color="#111", ms=22, label="M7.7 epicentre")
    ax[0].axvline(120.2, color="#666", lw=1, ls="--")
    ax[0].text(120.22, rlat.min() - .05, "west of here: desc61 only",
               fontsize=8, color="#666")
    ax[0].set_aspect("equal")
    ax[0].set_title("Flores, all four tracks, coherence change normalised "
                    "per track\nred = lost more coherence than the rest of "
                    "its own track", fontsize=11, loc="left")
    ax[0].legend(fontsize=8.5, loc="upper right")
    fig.colorbar(s, ax=ax[0], shrink=.85, label="normalised drop")

    for n, col in ((1, "#c8a415"), (2, "#8fa8a0"), (3, "#4a7fa5"),
                   (4, "#1d4a54")):
        m = nt == n
        if m.any():
            ax[1].scatter(lon[m], lat[m], s=2.5, color=col, linewidths=0,
                          label=f"{n} track{'s' if n > 1 else ''} "
                                f"({int(m.sum()):,})")
    ax[1].set_aspect("equal")
    ax[1].set_title("how many tracks observe each block", fontsize=11,
                    loc="left")
    ax[1].legend(fontsize=8.5, loc="upper right", markerscale=4)
    fig.tight_layout()
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
