#!/usr/bin/env python3
"""Robustness of the peat-depth result in the concession heterogeneity model (WP2).

The main model (kalimantan_heterogeneity.py) uses depth_m = mean PEATGRIDS thickness over all
valid cells of a unit, which mixes how much peat a unit has with how deep it is, and rests on
one modelled 1 km map. Two checks:

1. DECOMPOSE. peat_share (BBSDLP peat cells / valid cells) and depth_on_peat (mean PEATGRIDS
   thickness over the unit's peat cells; 0 where it has none) enter together.
2. INDEPENDENT SOURCES. No second depth map is reachable (CIFOR/Gumbricht 2017 server down; the
   GFW mirror is extent only; Ministry of Agriculture depth-class maps are not public), so:
   a. edge_on_peat: mean distance (km) from the unit's peat cells to the nearest non-peat cell
      of the BBSDLP map. Tropical peat domes thicken toward their centres, so dome interior is
      a geometric depth proxy independent of PEATGRIDS; validated against PEATGRIDS here.
   b. gpm_share: share of the unit in the Greifswald Global Peatland Map 2.0 (1 km; peat
      dominated or peat in soil mosaic), in place of BBSDLP extent.
Same controls, units and models as the main heterogeneity model.

    python scripts/kalimantan_peat_depth_checks.py --stage features   # sample + Earth Engine, cached
    python scripts/kalimantan_peat_depth_checks.py --stage model
"""
import argparse
import contextlib
import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import DATA, HTI, OUT, PEAT  # noqa: E402
from kalimantan_heterogeneity import BATCH, SHARE_STEP, ee_features, fit, load_units, polygonal  # noqa: E402

UNITS = os.path.join(OUT, "heterogeneity_units.csv")
FEAT = os.path.join(DATA, "peat_check_covariates.csv")
GPM = "projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE"
PX_KM = 0.0018 * 111.32          # grid pixel, km (Kalimantan straddles the equator)
PEAT_MIN = 0.05                  # peat-bearing unit: > 5% of valid cells on BBSDLP peat
CONTROLS = ["forest_share_z", "log_area_z", "ind_share_10pp", "small_share_10pp", "recent_share_10pp",
            "st_in_process", "st_location_permit", "st_unknown", "grouped", "rspo_cert_share_10pp",
            "rspo_member_share_10pp", "other_permit_share_10pp"]
H_CONTROLS = ["forest_share_z", "log_area_z", "ind_share_10pp", "small_share_10pp", "grouped",
              "other_permit_share_10pp"]


def stage_features():
    import ee
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from scipy import ndimage
    from scipy.stats import spearmanr
    from earthchange.gee_utils import initialize_ee

    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"),
                         columns=["r", "c", "zone", "op", "valid", "peat", "thick"])
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, shape = rasterio.Affine(*grid["transform"]), tuple(grid["shape"])
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    hti_id = features.rasterize([(g, i + 1) for i, g in enumerate(hti.geometry.make_valid())],
                                out_shape=shape, transform=tr, dtype="int32")
    peat = features.rasterize([(g, 1) for g in gpd.read_file(PEAT).to_crs(4326).geometry.make_valid()],
                              out_shape=shape, transform=tr, dtype="uint8").astype(bool)
    edge_km = ndimage.distance_transform_edt(peat) * PX_KM            # 0 off peat
    r, c = df.r.to_numpy(), df.c.to_numpy()
    df["hti_id"], df["edge_km"] = hti_id[r, c], edge_km[r, c]
    dv = df[df.valid]

    onp = dv[dv.peat.astype(bool)]
    rho = spearmanr(onp.thick, onp.edge_km).statistic
    print(f"validation, peat cells (n={len(onp):,}): Spearman(PEATGRIDS thickness, distance to peat edge) = {rho:.2f}")
    bins = pd.cut(onp.edge_km, [0, 1, 2, 5, 10, 20, 1e3], right=False)
    print(onp.groupby(bins, observed=True).thick.agg(["size", "median", "mean"]).round(0).to_string())

    U = pd.read_csv(UNITS)[["kind", "id"]]
    rows = []
    for kind, i in zip(U.kind, U.id):
        m = (dv.op == i) if kind == "oil palm" else ((dv.zone == 2) & (dv.hti_id == i))
        s = dv[m.to_numpy()]
        pk = s[s.peat.astype(bool)]
        rows.append({"kind": kind, "id": i, "n_valid": len(s), "peat_share": pk.shape[0] / max(len(s), 1),
                     "depth_on_peat_cm": pk.thick.mean() if len(pk) else 0.0,
                     "edge_on_peat_km": pk.edge_km.mean() if len(pk) else 0.0})
    F = pd.DataFrame(rows)
    up = F[F.peat_share > 0]
    print(f"\nper unit with peat (n={len(up)}): Spearman(depth_on_peat, edge_on_peat) = "
          f"{spearmanr(up.depth_on_peat_cm, up.edge_on_peat_km).statistic:.2f}")

    # Greifswald Global Peatland Map 2.0 share per unit
    initialize_ee()
    P, _, _ = load_units()
    P["geometry"] = P.geometry.map(polygonal)
    key = P[["kind", "id"]].reset_index(drop=True)
    img = ee.Image(GPM).gte(1).unmask(0).rename("gpm")
    feats_all = ee_features(P)
    out = {}
    for s in range(0, len(feats_all), BATCH):
        res = img.reduceRegions(ee.FeatureCollection(feats_all[s:s + BATCH]), ee.Reducer.mean(),
                                scale=100, tileScale=8).getInfo()
        out.update({f["properties"]["k"]: f["properties"].get("mean") for f in res["features"]})
        print(f"  gpm {min(s + BATCH, len(feats_all))}/{len(feats_all)}")
    key["gpm_share"] = [out.get(k) for k in range(len(key))]
    F = F.merge(key, on=["kind", "id"], how="left")
    F.attrs["rho"] = rho
    F.to_csv(FEAT, index=False)
    json.dump({"spearman_cell_thick_vs_edge": float(rho)}, open(FEAT.replace(".csv", ".json"), "w"))
    print(f"Saved: {FEAT}")


def stage_model():
    import numpy as np
    import pandas as pd
    D = pd.read_csv(UNITS).merge(pd.read_csv(FEAT).rename(columns={"peat_share": "peat_share_chk"}),
                                 on=["kind", "id"], how="left")
    z = lambda x: (x - x.mean()) / x.std()      # noqa: E731
    out = {}
    for kind, controls in (("oil palm", CONTROLS), ("pulpwood", H_CONTROLS)):
        K = D[D.kind == kind].copy()
        K["excess"] = K.excess.astype(bool)
        for c in ("depth_m", "forest_share", "log_area", "depth_on_peat_cm", "edge_on_peat_km"):
            K[c + "_z"] = z(K[c])
        K["peat_share_10pp"] = K.peat_share_chk / SHARE_STEP
        K["gpm_share_10pp"] = K.gpm_share.fillna(0) / SHARE_STEP
        variants = {
            "V0 main: PEATGRIDS depth over unit": ["depth_m_z"],
            "V1 BBSDLP peat share + PEATGRIDS depth on peat": ["peat_share_10pp", "depth_on_peat_cm_z"],
            "V2 BBSDLP peat share + distance to peat edge": ["peat_share_10pp", "edge_on_peat_km_z"],
            "V3 BBSDLP peat share only": ["peat_share_10pp"],
            "V4 Greifswald peat share only": ["gpm_share_10pp"],
        }
        # depth within peat-bearing units only: across all units every peat measure is 0 for the
        # ~700 units without peat, which makes share and depth look collinear (rho ~0.97)
        Kp = K[K.peat_share_chk > PEAT_MIN].copy()
        for c in ("depth_on_peat_cm", "edge_on_peat_km"):
            Kp[c + "_z"] = z(Kp[c])
        variants.update({
            f"V5 peat units only (>{PEAT_MIN:.0%}): share + PEATGRIDS depth on peat":
                (["peat_share_10pp", "depth_on_peat_cm_z"], Kp),
            f"V6 peat units only (>{PEAT_MIN:.0%}): share + distance to peat edge":
                (["peat_share_10pp", "edge_on_peat_km_z"], Kp),
        })
        out[kind] = {}
        print(f"\n===== {kind}: n={len(K)}, excess={int(K.excess.sum())}; peat units n={len(Kp)}, "
              f"excess={int(Kp.excess.sum())}")
        print(f"  {'variant / term':<52}{'odds ratio [95% CI]':>26}{'p':>7}  {'ratio x [95% CI]':>22}{'p':>7}")
        for name, terms in variants.items():
            terms, data = terms if isinstance(terms, tuple) else (terms, K)
            with contextlib.redirect_stdout(io.StringIO()):
                res = fit(data, terms + controls, name)
            out[kind][name] = {t: {"logit": res.get("logit", {}).get(t), "wls": res["wls"][t]} for t in terms}
            print(f"  {name}")
            for t in terms:
                lg, w = res.get("logit", {}).get(t), res["wls"][t]
                ls = f"{lg['or']:5.2f} [{lg['lo']:4.2f}, {lg['hi']:5.2f}]{lg['p']:7.3f}" if lg else f"{'logit failed':>26}{'':7}"
                print(f"    {t:<48}{ls:>33}  {w['x']:5.2f} [{w['lo']:4.2f}, {w['hi']:4.2f}]{w['p']:7.3f}")
        print("  per-SD scaling:", {c: round(float(K[c].std()), 3) for c in
                                    ("depth_m", "depth_on_peat_cm", "edge_on_peat_km")})
    json.dump(out, open(os.path.join(OUT, "peat_depth_checks.json"), "w"), indent=1, default=float)
    print(f"\nSaved: {OUT}/peat_depth_checks.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["features", "model"], required=True)
    {"features": stage_features, "model": stage_model}[ap.parse_args().stage]()
