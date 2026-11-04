#!/usr/bin/env python3
"""Did fire really arrive earlier inside the four Ketapang concessions?

Part 3 of the film states that, inside the four, fire came about a week
earlier than on unpermitted land (VIIRS median first detection 17 vs 23
Aug; radar 21 vs 29 Aug). Those are raw medians. Here the same comparison
is made like for like, on the matched sample ketapang_excess_burn.py
writes (100 m pixels, same strata, same 5 km blocks):

  date     day of first fire at each pixel that burned (Sentinel-2), from
           two independent clocks:
             VIIRS  first detection within ~300 m (WIB days)
             radar  middle of the fused NISAR window (spread_v2_fused.tif),
                    radar-confirmed pixels only
  ATT      mean date inside minus the stratum-weighted mean date of
           unconceded pixels in the same stratum (CEM), covariates added
           one at a time as in Part 2; also the share burned before
           1 September
  local    controls restricted to unconceded land within 5 km of a
           concession, and a boundary comparison (2 km either side)
  CI       5 km block bootstrap

Only pixels that burned enter, so this asks "when", given burning, not
"whether". Weather is shared across the area, so a timing gap is about the
land, the fuel or the people, not the season.

    conda run -n base python scripts/ketapang_timing_test.py
"""

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import FOUR, OUT as ORIGIN  # noqa: E402

SAMPLE = os.path.join(ORIGIN, "excess_peat_rf")
OUT = os.path.join(ORIGIN, "timing")
FUSED = os.path.join(ORIGIN, "nisar", "spread_v2_fused.tif")
NBOOT = 500
SEP1 = 243                    # day of 2026 (0 = 1 Jan) for 1 September
SEQ = [[], ["peat"], ["peat", "depth_bin"], ["peat", "depth_bin", "lc"],
       ["peat", "depth_bin", "lc", "hist"],
       ["peat", "depth_bin", "lc", "hist", "water_bin"],
       ["peat", "depth_bin", "lc", "hist", "water_bin", "settle_bin"],
       ["peat", "depth_bin", "lc", "hist", "water_bin", "settle_bin", "ign_bin"]]
NAMES = ["raw", "+ peat", "+ peat depth", "+ land cover", "+ burn history",
         "+ distance to water", "+ distance to settlement", "+ ignition density"]


def main():
    import numpy as np
    import pandas as pd
    import rasterio
    from affine import Affine
    from rasterio.warp import reproject, Resampling
    from scipy import ndimage

    os.makedirs(OUT, exist_ok=True)
    df = pd.read_parquet(os.path.join(SAMPLE, "sample.parquet"))
    G = json.load(open(os.path.join(SAMPLE, "sample_grid.json")))
    tr, shape = Affine(*G["transform"]), tuple(G["shape"])

    # ---- VIIRS clock: first detection per 100 m cell, spread over ~300 m
    v = pd.read_csv(glob.glob(os.path.join(ORIGIN, "viirs_*.csv"))[0])
    v["t"] = pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)
    v = v[(v.t >= "2026-06-01") & (v.t < "2026-11-01")]
    day = (v.t.dt.normalize() - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    rr, cc = rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy())
    rr, cc = np.asarray(rr) // 4, np.asarray(cc) // 4
    sh4 = (shape[0] // 4 + 1, shape[1] // 4 + 1)
    ok = (rr >= 0) & (rr < sh4[0]) & (cc >= 0) & (cc < sh4[1])
    first = np.full(sh4, 9999, np.int32)
    np.minimum.at(first, (rr[ok], cc[ok]), day[ok].astype(np.int32))
    first = ndimage.minimum_filter(first, size=3)
    df["d_viirs"] = first[df.r // 4, df.c // 4]
    df.loc[df.d_viirs == 9999, "d_viirs"] = np.nan

    # ---- radar clock: fused window middle, confirmed pixels only
    with rasterio.open(FUSED) as src:
        lo, hi, conf = src.read(1).astype(np.float32), src.read(2).astype(np.float32), src.read(4)
        mid = np.where((lo >= 0) & (conf == 1), 0.5 * (lo + hi), np.nan).astype(np.float32)
        dst = np.full(shape, np.nan, np.float32)
        reproject(mid, dst, src_transform=src.transform, src_crs=src.crs, dst_transform=tr,
                  dst_crs="EPSG:4326", resampling=Resampling.nearest, src_nodata=np.nan,
                  dst_nodata=np.nan)
    df["d_radar"] = dst[df.r, df.c]

    d0 = df[df.burned & df.zone.isin([1, 3])].copy()
    d0["near5"] = np.min(np.stack([d0[f"sd_{k}"].to_numpy() for k in FOUR]), axis=0) <= 5.0
    d0["sd_min"] = np.min(np.stack([d0[f"sd_{k}"].to_numpy() for k in FOUR]), axis=0)
    print(f"burned sample pixels: inside {int((d0.zone == 3).sum()):,}, unconceded "
          f"{int((d0.zone == 1).sum()):,}; VIIRS-dated {d0.d_viirs.notna().mean():.0%}, "
          f"radar-dated {d0.d_radar.notna().mean():.0%}")

    blocks = df.block.unique()
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    rng = np.random.default_rng(7)
    boot_w = rng.multinomial(len(blocks), np.ones(len(blocks)) / len(blocks), size=NBOOT)

    def cem(d, col, keys):
        """Matched mean-date gap (days, inside - outside) and gap in share
        burned before 1 Sep; block bootstrap."""
        d = d[d[col].notna()]
        t = (d.zone == 3).to_numpy()
        key = d[keys].astype(str).agg("|".join, axis=1) if keys else pd.Series("all", index=d.index)
        codes, uniq = pd.factorize(key)
        bi = bidx[d.block].to_numpy()
        nb, ns = len(blocks), len(uniq)
        x = d[col].to_numpy(float)
        early = (x < SEP1).astype(float)

        def tab(m, val):
            a = np.zeros((nb, ns))
            np.add.at(a, (bi[m], codes[m]), val[m])
            return a
        one = np.ones(len(d))
        T = [tab(t, one), tab(t, x), tab(t, early)]
        C = [tab(~t, one), tab(~t, x), tab(~t, early)]

        def att(w):
            tn, tx, te = (w @ a for a in T)
            cn, cx, ce = (w @ a for a in C)
            m = (tn > 0) & (cn > 0)
            W = tn[m].sum()
            return (tx[m].sum() / W - (tn[m] * cx[m] / cn[m]).sum() / W,
                    te[m].sum() / W - (tn[m] * ce[m] / cn[m]).sum() / W,
                    te[m].sum() / W, W / max(tn.sum(), 1))
        g, e, et, cov = att(np.ones(nb))
        bs = np.array([att(w)[:2] for w in boot_w])
        return {"gap_days": float(g), "gap_days_ci95": [float(np.nanpercentile(bs[:, 0], 2.5)),
                                                        float(np.nanpercentile(bs[:, 0], 97.5))],
                "p_later_or_same": float(np.mean(bs[:, 0] >= 0)),
                "inside_before_sep_pct": 100 * float(et),
                "gap_before_sep_pts": 100 * float(e),
                "gap_before_sep_ci95": [100 * float(np.nanpercentile(bs[:, 1], 2.5)),
                                        100 * float(np.nanpercentile(bs[:, 1], 97.5))],
                "treated_share_matched": float(cov), "n_inside": int(t.sum()), "n_outside": int((~t).sum())}

    rows = []
    for col, clock in (("d_viirs", "VIIRS"), ("d_radar", "radar")):
        for nm, keys in zip(NAMES, SEQ):
            r = cem(d0, col, keys)
            rows.append({"clock": clock, "control": "unconceded", "matched_on": nm, **r})
        full = SEQ[-1]
        r = cem(d0[(d0.zone == 3) | d0.near5], col, full)
        rows.append({"clock": clock, "control": "unconceded within 5 km", "matched_on": NAMES[-1], **r})
        for k in FOUR:
            d = d0[(d0.zone == 1) | d0[f"in_{k}"]]
            r = cem(d, col, full)
            rows.append({"clock": clock, "control": f"unconceded, {k} only", "matched_on": NAMES[-1], **r})
        d = d0[d0.peat]
        r = cem(d, col, full)
        rows.append({"clock": clock, "control": "unconceded, peat only", "matched_on": NAMES[-1], **r})
    tb = pd.DataFrame(rows)
    tb.to_csv(os.path.join(OUT, "timing_matched.csv"), index=False)
    pd.set_option("display.width", 200)
    print(tb[["clock", "control", "matched_on", "gap_days", "gap_days_ci95", "p_later_or_same",
              "inside_before_sep_pct", "gap_before_sep_pts", "treated_share_matched"]]
          .round(2).to_string(index=False))

    # ---- boundary: mean date in 500 m bins, 2 km each side, the four pooled
    bd = []
    near = d0[(d0.sd_min.abs() <= 2.0) & ((d0.zone == 3) | (d0.zone == 1))]
    for col, clock in (("d_viirs", "VIIRS"), ("d_radar", "radar")):
        q = near[near[col].notna()].copy()
        q["bin"] = np.floor(q.sd_min / 0.5) * 0.5 + 0.25
        g = q.groupby("bin")[col].agg(["mean", "size"]).reset_index()
        for _, rw in g.iterrows():
            bd.append({"clock": clock, "signed_km": rw["bin"], "mean_day": rw["mean"], "n": int(rw["size"])})
        ins_, out_ = q[(q.sd_min < 0) & (q.sd_min >= -1)], q[(q.sd_min > 0) & (q.sd_min <= 1)]
        print(f"boundary {clock}: within 1 km inside mean day {ins_[col].mean():.1f}, "
              f"outside {out_[col].mean():.1f} (gap {ins_[col].mean() - out_[col].mean():+.1f} d)")
    pd.DataFrame(bd).to_csv(os.path.join(OUT, "timing_boundary.csv"), index=False)

    rep = {"matched": rows, "boundary": bd}
    json.dump(rep, open(os.path.join(OUT, "timing_report.json"), "w"), indent=1, default=float)
    print(f"Saved: {OUT}/timing_matched.csv, timing_boundary.csv, timing_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
