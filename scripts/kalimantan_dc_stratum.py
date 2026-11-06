#!/usr/bin/env python3
"""Robustness (review M1): the matched concession ratio with the cell's season-peak Drought Code band
added to the CEM strata, so concession land is compared only with unpermitted land that had the same
2026 drought (the drought followed latitude; island-wide controls could mix drought regimes).

Same sample, outcome, strata (SEQ[-1]) and 5 km block bootstrap as kalimantan_excess_burn.py --stage
match; DC from kalimantan_border_weather.py (dc_2026.npz), bands 0-300-400-500-600-700-max.

    python scripts/kalimantan_dc_stratum.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import DATA, NBOOT, OUT, SEQ, STEP, matched  # noqa: E402
from kalimantan_border_weather import DC_BANDS, DC_NPY  # noqa: E402

RES = os.path.join(OUT, "dc_stratum.json")


def main():
    import numpy as np
    import pandas as pd
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"),
                         columns=["r", "c", "zone", "valid", "burned", "block"] + SEQ[-1])
    df = df[df.valid].reset_index(drop=True)
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    z = np.load(DC_NPY, allow_pickle=True)
    dc, dates = z["dc"], pd.to_datetime(z["dates"])
    x0, yt, st = z["grid"]
    peak = dc[(dates >= "2026-07-01") & (dates < "2026-11-01")].max(axis=0)
    lon = grid["transform"][2] + (df.c.to_numpy() + 0.5) * STEP
    lat = grid["transform"][5] - (df.r.to_numpy() + 0.5) * STEP
    ey = np.clip(((yt - lat) / st).astype(int), 0, peak.shape[0] - 1)
    ex = np.clip(((lon - x0) / st).astype(int), 0, peak.shape[1] - 1)
    df["dc_bin"] = np.digitize(peak[ey, ex], DC_BANDS[1:-1]).astype(np.uint8)
    blocks = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    W = np.random.default_rng(42).multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                                              size=NBOOT).astype(float)
    out = []
    for zc, kind in ((3, "oil palm"), (2, "pulpwood")):
        d = df[df.zone.isin([1, zc])].reset_index(drop=True)
        t = (d.zone == zc).to_numpy()
        for name, keys in (("all strata", SEQ[-1]), ("all strata + peak-DC band", SEQ[-1] + ["dc_bin"])):
            pt, pc, cov, bs = matched(d, t, keys, d.burned.to_numpy(float), W, bidx)
            q = bs[:, 0] / bs[:, 1]
            lo, hi = np.percentile(q, [2.5, 97.5])
            out.append({"treated": kind, "matched_on": name, "treated_pct": 100 * pt, "control_pct": 100 * pc,
                        "ratio": pt / pc, "ci": [float(lo), float(hi)], "coverage": float(cov)})
            print(f"  {kind:<9} {name:<27} {100 * pt:.2f}% vs {100 * pc:.2f}%  x{pt / pc:.3f} [{lo:.3f}, {hi:.3f}]"
                  f"  cov {100 * cov:.1f}%", flush=True)
    # timing among burned cells (VIIRS first-fire day, Jun-Oct) and the Drought Code on that day, matched
    # with and without the peak-DC band (is the milder-drought result only a regional effect?)
    doy0 = (dates[0] - pd.Timestamp("2026-01-01")).days
    last = len(dates) - 1 + doy0
    day = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"), columns=["valid", "day"])
    df["day"] = day[day.valid].day.to_numpy()
    b = df[df.burned & (df.day >= 152) & (df.day < 305) & (df.day <= last)].reset_index(drop=True)
    b["dc_first"] = dc[b.day.to_numpy() - doy0, ey[b.index] if False else
                       np.clip(((yt - (grid["transform"][5] - (b.r.to_numpy() + 0.5) * STEP)) / st).astype(int), 0, peak.shape[0] - 1),
                       np.clip((((grid["transform"][2] + (b.c.to_numpy() + 0.5) * STEP) - x0) / st).astype(int), 0, peak.shape[1] - 1)]
    timing = []
    for zc, kind in ((3, "oil palm"), (2, "pulpwood")):
        d = b[b.zone.isin([1, zc])].reset_index(drop=True)
        t = (d.zone == zc).to_numpy()
        for name, keys in (("all strata", SEQ[-1]), ("all strata + peak-DC band", SEQ[-1] + ["dc_bin"])):
            for var in ("day", "dc_first"):
                pt, pc, cov, bs = matched(d, t, keys, d[var].to_numpy(float), W, bidx)
                g = bs[:, 0] - bs[:, 1]
                lo, hi = np.percentile(g, [2.5, 97.5])
                timing.append({"treated": kind, "matched_on": name, "variable": var, "treated_mean": pt,
                               "control_mean": pc, "gap": pt - pc, "ci": [float(lo), float(hi)], "coverage": float(cov)})
                print(f"  timing {kind:<9} {name:<27} {var:<9} gap {pt - pc:+.2f} [{lo:+.2f}, {hi:+.2f}]", flush=True)
    out = {"burned_share": out, "timing": timing}
    json.dump(out, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
