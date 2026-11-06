#!/usr/bin/env python3
"""Review round 2, M1: the robustness checks rerun on the primary (drought-matched) specification.

Primary strata are SEQ[-1] + the cell's season-peak Drought Code band (kalimantan_dc_stratum.py).
The earlier checks (kalimantan_concession_checks.py, kalimantan_robustness.py, kalimantan_balance.py)
were run on SEQ[-1] only. Here, each with the peak-DC band added:

  outcome   S2 burned on >= 1/4 of the cell; any VIIRS fire within ~300 m (Jun-Oct); VIIRS
            detections per cell (nominal/high, Jun-Oct) -- built as in kalimantan_concession_checks.py
  peat map  Greifswald GPM 2.0 peat + PEATGRIDS depth bins instead of BBSDLP (kalimantan_robustness R2)
  interior  controls >= 5 km from any concession and treated >= 5 km inside (kalimantan_robustness R1)
  leave-out each covariate that may be post-treatment: distance to settlement, burn history, land cover

Other seasons (2015-2023) are not rerun: the 2026 drought band does not apply to them.
Same 5 km block bootstrap (NBOOT, rng 42). Writes output/fire/kalimantan_excess/dc_robustness.json.

    python scripts/kalimantan_dc_robustness.py
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_dc_stratum import peak_dc_bin  # noqa: E402
from kalimantan_excess_burn import BANDS, DATA, NBOOT, OUT, SEQ, STACK, matched  # noqa: E402
from kalimantan_robustness import EXTRA, EXTRA_BANDS, PX_KM  # noqa: E402

RES = os.path.join(OUT, "dc_robustness.json")
LEAVE_OUT = {"distance to settlement": "settle_bin", "burn history": "hist", "land cover": "lc"}


def main():
    import numpy as np
    import pandas as pd
    import rasterio
    from scipy import ndimage

    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"),
                         columns=sorted(set(["r", "c", "zone", "valid", "burned", "block", "thick"] + SEQ[-1])))
    df["dc_bin"] = peak_dc_bin(df)
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, shape = rasterio.Affine(*grid["transform"]), tuple(grid["shape"])
    r, c = df.r.to_numpy(), df.c.to_numpy()

    # alternative outcomes, as kalimantan_concession_checks.py
    with rasterio.open(STACK) as ds:
        bfrac = ds.read(BANDS.index("bfrac") + 1)[r, c]
        okfrac = ds.read(BANDS.index("okfrac") + 1)[r, c]
    v = pd.read_parquet(os.path.join(DATA, "viirs_2026.parquet"))
    day = ((pd.to_datetime(v.acq_epoch, unit="s") + pd.Timedelta(hours=7)).dt.normalize()
           - pd.Timestamp("2026-01-01")).dt.days.to_numpy()
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(tr, v.lon.to_numpy(), v.lat.to_numpy()))
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    seen = np.zeros(shape, bool)
    seen[rr[ok], cc[ok]] = True
    near = ndimage.binary_dilation(seen, np.ones((3, 3), bool), iterations=3)[r, c]
    sea = ok & (day >= 152) & (day < 305)
    conf = v.confidence.to_numpy() >= 1
    cnt = np.zeros(shape, np.int32)
    np.add.at(cnt, (rr[sea & conf], cc[sea & conf]), 1)
    sseen = np.zeros(shape, bool)
    sseen[rr[sea], cc[sea]] = True
    df["burned25"] = df.valid & (bfrac * 4 >= okfrac) & (bfrac > 0) & near
    df["viirs_cell"] = ndimage.binary_dilation(sseen, np.ones((3, 3), bool))[r, c]
    df["viirs_count"] = cnt[r, c]

    # Greifswald peat, as kalimantan_robustness R2
    with rasterio.open(EXTRA) as ds:
        gpm = ds.read(EXTRA_BANDS.index("gpm") + 1)[r, c]
    df["gpm"] = gpm > 0
    df["depth_bin_gpm"] = np.where(df.gpm, np.digitize(df.thick, [1, 100, 200, 300]), 9).astype(np.uint8)

    # distances for the interior estimand, as kalimantan_robustness R1
    zone = np.zeros(shape, np.uint8)
    zone[r, c] = df.zone.to_numpy()
    conc = (zone == 2) | (zone == 3)
    df["d_out"] = (ndimage.distance_transform_edt(~conc) * PX_KM)[r, c]
    df["d_in"] = (ndimage.distance_transform_edt(conc) * PX_KM)[r, c]

    blocks = np.unique(df.block.to_numpy())
    bidx = pd.Series(np.arange(len(blocks)), index=blocks)
    W = np.random.default_rng(42).multinomial(len(blocks), np.ones(len(blocks)) / len(blocks),
                                              size=NBOOT).astype(float)
    full = SEQ[-1] + ["dc_bin"]
    rows = []

    def row(check, variant, d, z, keys, col):
        treat = (d.zone == z).to_numpy()
        pt, pc, cov, bs = matched(d, treat, keys, d[col].to_numpy(float), W, bidx)
        q = bs[:, 0] / np.where(bs[:, 1] > 0, bs[:, 1], np.nan)
        lo, hi = np.nanpercentile(q, [2.5, 97.5])
        kind = {3: "oil palm", 2: "pulpwood"}[z]
        rows.append({"check": check, "variant": variant, "treated": kind, "treated_mean": float(pt),
                     "control_mean": float(pc), "ratio": float(pt / pc), "ci": [float(lo), float(hi)],
                     "coverage": float(cov), "n_treated": int(treat.sum())})
        print(f"  {check:<9}{variant:<44}{kind:<10} x{pt / pc:.3f} [{lo:.3f}, {hi:.3f}]  cov {100 * cov:.1f}%",
              flush=True)

    valid = df[df.valid]
    for z in (3, 2):
        d = valid[valid.zone.isin([1, z])]
        row("primary", "S2 burned >= 1/2 (main outcome)", d, z, full, "burned")
        row("outcome", "S2 burned >= 1/4 of the cell", d, z, full, "burned25")
        da = df[df.zone.isin([1, z])]
        row("outcome", "any VIIRS fire within ~300 m, Jun-Oct", da, z, full, "viirs_cell")
        row("outcome", "VIIRS detections per cell, Jun-Oct", da, z, full, "viirs_count")
        row("peat map", "Greifswald GPM 2.0 peat + depth bins", d, z,
            ["gpm", "depth_bin_gpm"] + SEQ[-1][2:] + ["dc_bin"], "burned")
        d1 = d[((d.zone != 1) | (d.d_out >= 5)) & ((d.zone == 1) | (d.d_in >= 5))]
        row("interior", "controls >= 5 km out, treated >= 5 km in", d1, z, full, "burned")
        for name, col in LEAVE_OUT.items():
            row("leave-out", f"without {name}", d, z, [k for k in full if k != col], "burned")
    json.dump(rows, open(RES, "w"), indent=1)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
