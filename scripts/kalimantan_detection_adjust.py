#!/usr/bin/env python3
"""SI review: does Sentinel-2 omission inside concessions hide an excess?

Among cloud-free cells with a VIIRS detection within ~300 m (Jun-Oct 2026), the S2 rule calls fewer
burned inside concessions than outside, within the same land cover (concession_checks.json canopy).
Here the detection rate d = P(S2 burned | VIIRS-seen, cloud-free) is estimated per land cover x tenure
(and per land cover x tenure x peak-DC band), each cell's burned value is divided by its group's d, and the
drought-matched ratio (SEQ[-1] + peak-DC band, as kalimantan_dc_stratum.py) is recomputed on that
outcome. d is held fixed in the bootstrap.

A lower d inside concessions may be omission (canopy, smoke) or real (fires seen by VIIRS but kept small),
so the adjusted ratio is an upper bound on what omission could hide, not a corrected estimate.
Writes output/fire/kalimantan_excess/detection_adjust.json.

    python scripts/kalimantan_detection_adjust.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_dc_stratum import peak_dc_bin  # noqa: E402
from kalimantan_excess_burn import DATA, NBOOT, OUT, SEQ, matched  # noqa: E402

RES = os.path.join(OUT, "detection_adjust.json")


def main():
    import numpy as np
    import pandas as pd
    import rasterio
    from scipy import ndimage

    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"),
                         columns=sorted(set(["r", "c", "zone", "valid", "burned", "block"] + SEQ[-1])))
    df["dc_bin"] = peak_dc_bin(df)
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, shape = rasterio.Affine(*grid["transform"]), tuple(grid["shape"])
    r, c = df.r.to_numpy(), df.c.to_numpy()
    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"))
    day = ((pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)).dt.normalize()
           - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy()))
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1]) & (day >= 152) & (day < 305)
    seen = np.zeros(shape, bool)
    seen[rr[ok], cc[ok]] = True
    df["viirs_cell"] = ndimage.binary_dilation(seen, np.ones((3, 3), bool))[r, c]   # as concession_checks
    d = df[df.valid].reset_index(drop=True)

    blocks = np.unique(d.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    W = np.random.default_rng(42).multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                                              size=NBOOT).astype(float)
    full = SEQ[-1] + ["dc_bin"]
    out = {"detection_rates": {}, "ratios": []}
    seen_cells = d[d.viirs_cell]
    for name, keys in (("cover x tenure", ["lc", "zone"]), ("cover x tenure x DC band", ["lc", "zone", "dc_bin"])):
        rate = seen_cells.groupby(keys).burned.mean().rename("d")
        n = seen_cells.groupby(keys).size().rename("n")
        dd = d.merge(pd.concat([rate, n], axis=1).reset_index(), on=keys, how="left")
        # thin groups (< 200 VIIRS-seen cells) fall back to the cover x tenure rate
        if name != "cover x tenure":
            base = seen_cells.groupby(["lc", "zone"]).burned.mean().rename("d0").reset_index()
            dd = dd.merge(base, on=["lc", "zone"], how="left")
            dd["d"] = np.where(dd.n >= 200, dd.d, dd.d0)
        dd["d"] = dd.d.clip(lower=0.02)
        y = dd.burned.to_numpy(float) / dd.d.to_numpy()
        if name == "cover x tenure":
            out["detection_rates"] = {f"{int(a)}|{int(b)}": float(x) for (a, b), x in rate.items()}
        for zc, kind in ((3, "oil palm"), (2, "pulpwood")):
            m = dd.zone.isin([1, zc]).to_numpy()
            s = dd[m].reset_index(drop=True)
            t = (s.zone == zc).to_numpy()
            for lab, val in (("S2 as observed", s.burned.to_numpy(float)), (f"detection-adjusted ({name})", y[m])):
                if lab == "S2 as observed" and name != "cover x tenure":
                    continue
                pt, pc, cov, bs = matched(s, t, full, val, W, bidx)
                q = bs[:, 0] / bs[:, 1]
                lo, hi = np.percentile(q, [2.5, 97.5])
                out["ratios"].append({"treated": kind, "outcome": lab, "ratio": float(pt / pc), "ci": [float(lo), float(hi)],
                                      "treated_mean": float(pt), "control_mean": float(pc), "coverage": float(cov)})
                print(f"  {kind:<9} {lab:<46} x{pt / pc:.3f} [{lo:.3f}, {hi:.3f}]", flush=True)
    json.dump(out, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
