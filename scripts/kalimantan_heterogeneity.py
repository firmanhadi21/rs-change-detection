#!/usr/bin/env python3
"""Which concessions burn more than matched unpermitted land? (WP2 heterogeneity, Kalimantan)

Units are the oil-palm concessions and wood-fibre permits of kalimantan_concession_checks.py
(per_concession_matched.csv: matched ratio, block-bootstrap CI, BH-FDR class). Per unit we add:

  planting (Descals et al. 2024, BIOPAMA/GlobalOilPalm/v1_2, 30 m, planted to 2021):
      ind_share, small_share   industrial / smallholder closed-canopy palm, share of unit area
      recent_share             palm planted 2016-2021, share of unit area
      old_share                palm planted <= 2005, share of unit area
  permit status (GFW type/po_legalst): HGU (title), in process, location permit, unknown
  company group: member of a named group (vs "No group")
  RSPO (GFW rspo_oil_palm v20200401, membership as of 2020): share of unit area in certified
      RSPO-member concessions, and in uncertified RSPO-member concessions
  overlap: oil palm -> share in a wood-fibre permit; wood fibre -> share in an oil-palm concession
  terrain/cover from the matched sample: mean peat depth, forest share, log area

Two models per concession type, covariates standardised (per SD; shares and binaries as is):
  logit   P(class_fdr == "excess")                      (BH q <= 0.05)
  WLS     log matched ratio, weights 1/se^2 with se from the bootstrap CI, HC1 errors
          (units with zero burned area drop out of WLS; they stay in the logit)
Permit age is not modelled: only 175 of 1,845 GFW permit numbers carry a year.
The own-ignition share (lineage) is reported, not modelled: it is downstream of the
behaviour being explained.

    python scripts/kalimantan_heterogeneity.py --stage covariates   # Earth Engine, cached
    python scripts/kalimantan_heterogeneity.py --stage model
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import CONC, DATA, HTI, KAL, OUT  # noqa: E402

UNITS = os.path.join(OUT, "per_concession_matched.csv")
RSPO = os.path.join(DATA, "gfw_rspo_2020_kalimantan.gpkg")
COV = os.path.join(DATA, "heterogeneity_covariates.csv")
EA = 6933                 # equal-area CRS for overlaps
BATCH = 40                # features per Earth Engine reduceRegions call
STATUS = (("HGU in process", "in process"), ("Proses", "in process"), ("HGU", "title"), ("Sudah HGU", "title"),
          ("Ijin Lokasi", "location permit"), ("Izin Lokasi", "location permit"),
          ("Ijin Prinsip", "location permit"), ("Pencadangan", "location permit"),
          ("Informasi Lahan", "location permit"))     # first matching prefix wins; else unknown
SHARE_STEP = 0.1          # area shares enter per 10 percentage points


def status_of(s):
    return next((v for k, v in STATUS if s.startswith(k)), "unknown")


def load_units():
    import geopandas as gpd
    import pandas as pd
    P = pd.read_csv(UNITS)
    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]].reset_index(drop=True)
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    src = {"oil palm": op, "pulpwood": hti}
    P["geometry"] = [src[k].geometry.iloc[i - 1] for k, i in zip(P.kind, P.id)]
    t = op["type"].fillna("").str.strip()           # op.type would be the geometry type
    raw = t.where(t != "", op["po_legalst"].fillna("").str.strip())
    P["status_raw"] = [raw.iloc[i - 1] if k == "oil palm" else "" for k, i in zip(P.kind, P.id)]
    return gpd.GeoDataFrame(P, crs=4326), op, hti


def stage_covariates():
    import ee
    import geopandas as gpd
    import pandas as pd
    from earthchange.gee_utils import initialize_ee

    import shapely
    from shapely.geometry import MultiPolygon

    def polygonal(g):
        g = shapely.force_2d(g)                 # GFW oil palm is 3D; Earth Engine rejects Z
        parts = [p for p in shapely.get_parts(shapely.make_valid(g)) if p.geom_type in ("Polygon", "MultiPolygon")]
        polys = [q for p in parts for q in (p.geoms if p.geom_type == "MultiPolygon" else [p])]
        return MultiPolygon(polys) if polys else None

    P, op, hti = load_units()
    P["geometry"] = P.geometry.map(polygonal)
    ov_path = COV.replace(".csv", "_overlaps.csv")
    if os.path.exists(ov_path):
        cov = pd.read_csv(ov_path)
        print(f"overlaps from {ov_path}")
    else:
        cov = overlaps(P, op, hti)
        cov.to_csv(ov_path, index=False)
    descals(P, cov)


def overlaps(P, op, hti):
    import geopandas as gpd
    import pandas as pd
    pe = P.to_crs(EA)
    area = pe.area
    rs = gpd.read_file(RSPO).to_crs(EA)
    rs["geometry"] = rs.geometry.make_valid()
    cert = rs[rs.rspocert.astype(str).str.lower() == "true"].union_all()
    memb = rs[rs.rspocert.astype(str).str.lower() != "true"].union_all().difference(cert)
    htiu = hti.to_crs(EA).geometry.make_valid().union_all()
    opu = op.to_crs(EA).geometry.make_valid().union_all()
    cov = pd.DataFrame({"kind": P.kind, "id": P.id})
    cov["rspo_cert_share"] = pe.intersection(cert).area / area
    cov["rspo_member_share"] = pe.intersection(memb).area / area
    cov["other_permit_share"] = [g.intersection(htiu if k == "oil palm" else opu).area / a
                                 for g, k, a in zip(pe.geometry, P.kind, area)]
    print("overlaps done")
    return cov


def descals(P, cov):
    """Descals planting shares per unit (Earth Engine)."""
    import ee
    import pandas as pd
    import shapely
    from earthchange.gee_utils import initialize_ee
    initialize_ee()
    ic = ee.ImageCollection("BIOPAMA/GlobalOilPalm/v1_2")
    cls = ic.select("classification").mosaic()
    py = ic.select("planting_year").mosaic().unmask(0)
    img = (cls.eq(1).rename("ind")
           .addBands(cls.eq(2).rename("small"))
           .addBands(cls.gte(1).And(py.gte(2016)).rename("recent"))
           .addBands(cls.gte(1).And(py.gt(0)).And(py.lte(2005)).rename("old"))
           .addBands(ee.Image.constant(1).rename("all")))
    simp = [g.simplify(0.0005).buffer(0) if g is not None else None for g in P.geometry]
    simp = [s if s is not None and not s.is_empty else g for s, g in zip(simp, P.geometry)]
    rows = []
    for s in range(0, len(P), BATCH):
        feats = [ee.Feature(ee.Geometry(json.loads(shapely.to_geojson(g))), {"k": int(s + j)})
                 for j, g in enumerate(simp[s:s + BATCH]) if g is not None]
        res = img.reduceRegions(ee.FeatureCollection(feats), ee.Reducer.sum(), scale=30, tileScale=8).getInfo()
        for f in res["features"]:
            pr = f["properties"]
            n = pr.get("all") or float("nan")
            rows.append({"k": pr["k"], "ind_share": pr["ind"] / n, "small_share": pr["small"] / n,
                         "recent_share": pr["recent"] / n, "old_share": pr["old"] / n})
        print(f"  descals {min(s + BATCH, len(P))}/{len(P)}")
    d = pd.DataFrame(rows).set_index("k").reindex(range(len(P)))
    cov = pd.concat([cov.reset_index(drop=True), d.reset_index(drop=True)], axis=1)
    cov.to_csv(COV, index=False)
    print(f"Saved: {COV} ({len(cov)} units)")


def fit(D, cols, label):
    import numpy as np
    import statsmodels.api as sm
    out = {"n": int(len(D)), "n_excess": int(D.excess.sum())}
    X = sm.add_constant(D[cols].astype(float), has_constant="add")
    try:
        lg = sm.Logit(D.excess.astype(float), X).fit(disp=0, cov_type="HC1")
        out["logit"] = {c: {"or": float(np.exp(lg.params[c])), "lo": float(np.exp(lg.conf_int().loc[c, 0])),
                            "hi": float(np.exp(lg.conf_int().loc[c, 1])), "p": float(lg.pvalues[c])} for c in cols}
        out["logit_pseudo_r2"] = float(lg.prsquared)
    except Exception as e:                      # perfect separation etc.
        out["logit_error"] = str(e)
        print(f"  logit failed: {e}")
    W = D[(D.ratio > 0) & (D.ci_lo > 0)].copy()
    se = (np.log(W.ci_hi) - np.log(W.ci_lo)) / (2 * 1.96)
    W = W[np.isfinite(se) & (se > 0)]
    se = se[W.index]
    wl = sm.WLS(np.log(W.ratio), sm.add_constant(W[cols].astype(float), has_constant="add"),
                weights=1 / se ** 2).fit(cov_type="HC1")
    out["wls"] = {c: {"x": float(np.exp(wl.params[c])), "lo": float(np.exp(wl.conf_int().loc[c, 0])),
                      "hi": float(np.exp(wl.conf_int().loc[c, 1])), "p": float(wl.pvalues[c])} for c in cols}
    out["wls_n"], out["wls_r2"] = int(len(W)), float(wl.rsquared)
    print(f"\n== {label}: n={out['n']} (excess {out['n_excess']}), WLS n={out['wls_n']} R2={out['wls_r2']:.2f}"
          + (f", logit pseudo-R2={out['logit_pseudo_r2']:.2f}" if "logit" in out else ""))
    print(f"  {'covariate':<26}{'odds ratio [95% CI]':>28}{'p':>8}   {'ratio x [95% CI]':>24}{'p':>8}")
    for c in cols:
        lgc = out.get("logit", {}).get(c)
        w = out["wls"][c]
        ls = f"{lgc['or']:6.2f} [{lgc['lo']:5.2f}, {lgc['hi']:6.2f}]{lgc['p']:8.3f}" if lgc else " " * 32
        print(f"  {c:<26}{ls:>36}   {w['x']:6.2f} [{w['lo']:4.2f}, {w['hi']:5.2f}]{w['p']:8.3f}")
    return out


def stage_model():
    import numpy as np
    import pandas as pd
    P, _, _ = load_units()
    P = pd.DataFrame(P.drop(columns="geometry"))
    cov = pd.read_csv(COV)
    D = P.merge(cov, on=["kind", "id"], how="left")
    D["excess"] = D.class_fdr.eq("excess")
    D["status"] = D.status_raw.map(status_of)
    D["grouped"] = (~D.group.fillna("No group").isin(["No group", "NoName", ""])).astype(int)
    D["log_area"] = np.log(D.area_km2)
    D["depth_m"] = D.mean_depth_cm / 100
    D["unplanted_share"] = (1 - D.ind_share - D.small_share).clip(0, 1)
    for s in ("in process", "location permit", "unknown"):
        D["st_" + s.replace(" ", "_")] = D.status.eq(s).astype(int)
    z = lambda x: (x - x.mean()) / x.std()      # noqa: E731
    shares = ["ind_share", "small_share", "recent_share", "rspo_cert_share", "rspo_member_share",
              "other_permit_share"]
    for c in shares:
        D[c + "_10pp"] = D[c] / SHARE_STEP
    out = {"descriptives": {}, "models": {}}

    # descriptives: excess vs rest
    desc = ["depth_m", "forest_share", "ind_share", "small_share", "recent_share", "old_share", "area_km2",
            "rspo_cert_share", "rspo_member_share", "other_permit_share", "grouped", "own_ignition_share"]
    for kind, g in D.groupby("kind"):
        t = g.groupby("excess")[desc].median().T.rename(columns={True: "excess", False: "rest"})
        t["excess_mean"] = g[g.excess][desc].mean()
        t["rest_mean"] = g[~g.excess][desc].mean()
        out["descriptives"][kind] = t.round(4).to_dict()
        print(f"\n{kind}: medians/means, excess (n={int(g.excess.sum())}) vs rest (n={int((~g.excess).sum())})")
        print(t.round(3).to_string())
        if kind == "oil palm":
            print(pd.crosstab(g.status, g.excess, margins=True).to_string())

    # oil palm
    O = D[D.kind == "oil palm"].copy()
    for c in ("depth_m", "forest_share", "log_area"):
        O[c + "_z"] = z(O[c])
    op_cols = ["depth_m_z", "forest_share_z", "log_area_z", "ind_share_10pp", "small_share_10pp",
               "recent_share_10pp", "st_in_process", "st_location_permit", "st_unknown", "grouped",
               "rspo_cert_share_10pp", "rspo_member_share_10pp", "other_permit_share_10pp"]
    out["models"]["oil palm"] = fit(O, op_cols, "oil palm")

    # wood fibre
    H = D[D.kind == "pulpwood"].copy()
    for c in ("depth_m", "forest_share", "log_area"):
        H[c + "_z"] = z(H[c])
    h_cols = ["depth_m_z", "forest_share_z", "log_area_z", "ind_share_10pp", "small_share_10pp", "grouped",
              "other_permit_share_10pp"]
    out["models"]["pulpwood"] = fit(H, h_cols, "pulpwood")

    out["scaling"] = {k: {c: float(D[D.kind == k][c].std()) for c in ("depth_m", "forest_share", "log_area")}
                      for k in ("oil palm", "pulpwood")}
    D.drop(columns=["status_raw"]).to_csv(os.path.join(OUT, "heterogeneity_units.csv"), index=False)
    json.dump(out, open(os.path.join(OUT, "heterogeneity.json"), "w"), indent=1, default=float)
    print(f"\nSaved: {OUT}/heterogeneity.json, heterogeneity_units.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["covariates", "model"], required=True)
    a = ap.parse_args()
    {"covariates": stage_covariates, "model": stage_model}[a.stage]()
