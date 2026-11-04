#!/usr/bin/env python3
"""Where did Kalimantan's 2026 concession fires start? Ignition lineage, island-wide (WP3).

Scales ketapang_fire_origin.py's detection-level parent tree to every VIIRS
detection of 2026 over Kalimantan (data/kalimantan/viirs_2026.parquet, built by
kalimantan_excess_burn.py --stage viirs; 'low' confidence dropped). Each
detection gets one parent, the nearest detection within PARENT_KM seen in the
PARENT_H hours before it (same rule, same code: ketapang_fire_origin.trace).
A detection without a parent is an ignition; following parents gives each
detection's root ignition.

Tenure of a detection (and so of its root):
  oil palm   GFW oil palm concessions (c. 2012), one unit per polygon; takes
             precedence where it overlaps a wood-fibre permit (as in
             kalimantan_excess_burn.py, zone 3)
  pulpwood   GFW wood-fibre (HTI) permits, one unit per polygon
  open       Indonesian land outside both ("unpermitted")
  MY/BN      Malaysian or Brunei Borneo (Natural Earth 1:10m)
Detections off land (sea, other islands) are kept as parents but not reported.

Reported for the main season (Jul-Oct, UTC+7):
  entry      share of detections inside a concession whose root ignition lay in
             the SAME concession, in another concession, on open land, or across
             the border; a root within EDGE_KM of a concession boundary is
             counted separately (inside and outside cannot be told apart there)
  escape     share of detections on open land whose root lay in a concession
  density    ignitions (all, and isolated: no fire within NEAR_KM in the NEAR_H
             hours before) per 1,000 km2 of each tenure
  per unit   own-ignition share and ignition counts per concession
  SENS       the attribution for 1 km/48 h, 1.5/96 and 3/168
Check: the four Ketapang concessions must reproduce ketapang_origin/summary.json
(1.5 km / 96 h: PT AM 0.77, PT SKM 0.97, PT MKK 0.83, PT SPAS 0.54).

Same limits as the Ketapang script: an ignition is fire first SEEN there; cloud,
smoke and >PARENT_H hours of unseen smouldering create false ignitions;
boundaries are c. 2012.

    conda run -n base python scripts/kalimantan_fire_lineage.py
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from ketapang_fire_origin import (EDGE_KM, FOUR, NEAR_H, NEAR_KM, PARENT_H,  # noqa: E402
                                  PARENT_KM, SEASON, SENS, prior_within, trace)
from kalimantan_excess_burn import CONC, DATA, HTI, KAL  # noqa: E402

VIIRS = os.path.join(DATA, "viirs_2026.parquet")
NE = os.path.join(DATA, "ne_countries", "ne_10m_admin_0_countries.zip")
OUT = os.path.join(os.path.dirname(DATA), "..", "output", "fire", "kalimantan_lineage")
PROJ = "+proj=laea +lat_0=0 +lon_0=114 +datum=WGS84 +units=m"   # equal-area, Borneo-centred
CHECK = {"PT AM": 0.77, "PT SKM": 0.97, "PT MKK": 0.83, "PT SPAS": 0.54}


def tenure(g, op, hti, land):
    """unit id (>=0 concession index into `units`, -1 open, -2 MY/BN, -3 off land)."""
    import geopandas as gpd
    import numpy as np
    unit = np.full(len(g), -3)
    for poly, code in ((land[land.cc == "BN"], -2), (land[land.cc == "IDN"], -1)):
        j = gpd.sjoin(g[["geometry"]], poly[["geometry"]], how="inner", predicate="within")
        unit[np.unique(j.index.to_numpy())] = code
    for layer in (hti, op):                        # oil palm written last = precedence
        j = gpd.sjoin(g[["geometry"]], layer[["uid", "geometry"]], how="inner", predicate="within")
        j = j[~j.index.duplicated()]
        unit[j.index.to_numpy()] = j.uid.to_numpy()
    return unit


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.normpath(OUT))
    ap.add_argument("--no-sens", action="store_true", help="main setting only")
    a = ap.parse_args()

    import geopandas as gpd
    import numpy as np
    import pandas as pd

    os.makedirs(a.out, exist_ok=True)
    x0, y0, x1, y1 = KAL

    # --- tenure layers ------------------------------------------------------
    op = gpd.read_file(CONC).to_crs(4326).cx[x0:x1, y0:y1].reset_index(drop=True)
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    for g_ in (op, hti):
        g_["geometry"] = g_.geometry.make_valid()
    op["kind"], hti["kind"] = "oil palm", "pulpwood"
    op["label"] = op.company.fillna(op.name)
    hti["label"] = hti.name
    units = pd.concat([op[["kind", "label", "group_comp", "geometry"]],
                       hti[["kind", "label", "group_comp", "geometry"]]], ignore_index=True)
    units["uid"] = np.arange(len(units))
    op["uid"] = units.uid[:len(op)].to_numpy()
    hti["uid"] = units.uid[len(op):].to_numpy()
    four = {}
    for acr, name in FOUR.items():
        s = op[op.company.str.contains(name, case=False, na=False)]
        if len(s) != 1:
            raise SystemExit(f"{name}: {len(s)} polygons in {CONC}")
        four[acr] = int(s.uid.iloc[0])

    ne = gpd.read_file(NE).to_crs(4326)
    ne = ne[ne.ADM0_A3.isin(["IDN", "MYS", "BRN"])].explode(index_parts=False)
    ne = ne.cx[x0:x1, y0:y1].reset_index(drop=True)
    ne["area"] = ne.to_crs(PROJ).area
    borneo = ne.loc[ne.area.idxmax(), "geometry"]                      # Borneo, the largest piece
    ne = ne[ne.intersects(borneo.buffer(0.3))]                         # Borneo + near-shore islands
    land = gpd.GeoDataFrame({"cc": np.where(ne.ADM0_A3 == "IDN", "IDN", "BN")},
                            geometry=ne.geometry.to_numpy(), crs=4326).dissolve("cc").reset_index()

    # --- detections ---------------------------------------------------------
    det = pd.read_parquet(VIIRS)
    n_all = len(det)
    det = det[det.confidence >= 1].sort_values("acq_epoch", kind="stable").reset_index(drop=True)
    print(f"{n_all:,} VIIRS detections, {len(det):,} nominal/high")
    loc = pd.to_datetime(det.acq_epoch, unit="s") + pd.Timedelta(hours=7)
    det["month"] = loc.dt.month
    g = gpd.GeoDataFrame(det[["lon", "lat"]], geometry=gpd.points_from_xy(det.lon, det.lat), crs=4326)
    gp = g.to_crs(PROJ)
    xy = np.c_[gp.geometry.x, gp.geometry.y] / 1000.0
    t = det.acq_epoch.to_numpy(float)
    print("tenure join ...")
    unit = tenure(g, op, hti, land)
    kind = np.full(len(det), "off land", dtype=object)
    kind[unit == -1], kind[unit == -2] = "open", "MY/BN"
    kind[unit >= 0] = units.kind.to_numpy()[unit[unit >= 0]]
    season = det.month.between(*SEASON).to_numpy()
    print(pd.Series(kind[season]).value_counts().to_string())

    # --- lineage ------------------------------------------------------------
    settings = [(PARENT_KM, PARENT_H)] + ([] if a.no_sens else [s for s in SENS if s != (PARENT_KM, PARENT_H)])
    sens, main_par, main_root = {}, None, None
    conc_bnd = gpd.GeoDataFrame(geometry=units.to_crs(PROJ).boundary, crs=PROJ)
    for km, hh in settings:
        print(f"tracing lineage, parent within {km} km / {hh} h ...")
        par, root = trace(xy, t, km, hh)
        ru = unit[root]
        inside = season & (unit >= 0)
        sens[f"{km}km_{hh}h"] = {
            "ignitions_season": int(((par == -1) & season).sum()),
            "share_inside_from_same_concession": float((ru[inside] == unit[inside]).mean()),
            "four": {acr: float((ru[season & (unit == u)] == u).mean()) for acr, u in four.items()}}
        print(json.dumps(sens[f"{km}km_{hh}h"], indent=1))
        if (km, hh) == (PARENT_KM, PARENT_H):
            main_par, main_root = par, root
    par, root = main_par, main_root
    for acr, u in four.items():
        got = sens[f"{PARENT_KM}km_{PARENT_H}h"]["four"][acr]
        flag = "ok" if abs(got - CHECK[acr]) < 0.03 else "DIFFERS"
        print(f"check {acr}: {got:.3f} vs Ketapang {CHECK[acr]:.2f}  {flag}")

    roots = np.flatnonzero(par == -1)
    print(f"edge distance for {len(roots):,} ignitions ...")
    rg = gp.iloc[roots][["geometry"]].reset_index(drop=True)
    nj = gpd.sjoin_nearest(rg, conc_bnd, how="left", max_distance=EDGE_KM * 1000, distance_col="dist")
    nj = nj[~nj.index.duplicated()]
    edge_root = np.zeros(len(det), bool)
    edge_root[roots] = nj.dist.notna().to_numpy()
    print("isolation of ignitions ...")
    prior = np.full(len(det), -1)
    prior[roots] = prior_within(xy, t, roots, NEAR_KM, NEAR_H)

    ru, rk, re_ = unit[root], kind[root], edge_root[root]

    # --- entry: what lit the fire inside concessions --------------------------
    def entry(m):
        same = ru[m] == unit[m]
        e = re_[m]
        return {"detections": int(m.sum()),
                "same_concession": float((same & ~e).mean()),
                "same_concession_edge_root": float((same & e).mean()),
                "other_concession": float(((ru[m] >= 0) & ~same).mean()),
                "open_land": float((rk[m] == "open").mean()),
                "my_bn": float((rk[m] == "MY/BN").mean()),
                "off_land": float((rk[m] == "off land").mean())}
    res = {"settings": {"parent": [PARENT_KM, PARENT_H], "edge_km": EDGE_KM, "near": [NEAR_KM, NEAR_H],
                        "season_months": list(SEASON)},
           "n_detections": len(det), "sensitivity": sens, "entry": {}, "escape": {}, "density": {}}
    for k in ("oil palm", "pulpwood"):
        res["entry"][k] = entry(season & (kind == k))
    for k in ("open", "MY/BN"):
        m = season & (kind == k)
        res["escape"][k] = {"detections": int(m.sum()),
                            "from_oil_palm": float((rk[m] == "oil palm").mean()),
                            "from_pulpwood": float((rk[m] == "pulpwood").mean()),
                            "from_edge_roots": float(re_[m].mean())}

    # --- ignition density -----------------------------------------------------
    areas = {"oil palm": None, "pulpwood": None}
    up = units.to_crs(PROJ)
    opu = up[up.kind == "oil palm"].union_all()
    htu = up[up.kind == "pulpwood"].union_all().difference(opu)
    idn = land[land.cc == "IDN"].to_crs(PROJ).union_all()
    areas = {"oil palm": opu.intersection(idn).area, "pulpwood": htu.intersection(idn).area,
             "open": idn.difference(opu).difference(htu).area}
    sr = roots[season[roots]]
    for k, A in areas.items():
        m = kind[sr] == k
        km2 = A / 1e6
        res["density"][k] = {"area_km2": km2, "ignitions": int(m.sum()),
                             "isolated": int((m & (prior[sr] == 0)).sum()),
                             "per_1000km2": 1000 * m.sum() / km2,
                             "isolated_per_1000km2": 1000 * (m & (prior[sr] == 0)).sum() / km2,
                             "detections_per_1000km2": 1000 * (season & (kind == k)).sum() / km2}

    # --- per concession ---------------------------------------------------------
    m = season & (unit >= 0)
    d = pd.DataFrame({"uid": unit[m], "same": ru[m] == unit[m], "edge": re_[m], "rk": rk[m]})
    per = d.groupby("uid").agg(detections=("same", "size"), own=("same", "mean"),
                               own_edge=("edge", "mean"),
                               from_open=("rk", lambda s: (s == "open").mean()))
    ig = pd.Series(unit[sr][unit[sr] >= 0]).value_counts().rename("ignitions")
    iso = pd.Series(unit[sr][(unit[sr] >= 0) & (prior[sr] == 0)]).value_counts().rename("isolated_ignitions")
    per = per.join(ig).join(iso).fillna({"ignitions": 0, "isolated_ignitions": 0})
    per = units.drop(columns="geometry").set_index("uid").join(per, how="inner")
    per["area_ha"] = up.set_index("uid").area.loc[per.index] / 1e4
    per = per.sort_values("detections", ascending=False)
    per.to_csv(os.path.join(a.out, "per_concession.csv"))
    big = per[per.detections >= 100]
    res["per_concession_summary"] = {
        "concessions_with_season_fire": int(len(per)),
        "with_100plus_detections": int(len(big)),
        "median_own_share_100plus": float(big.own.median()),
        "share_100plus_mostly_own": float((big.own >= 0.5).mean()),
        "top10_share_of_concession_detections": float(per.detections.head(10).sum() / per.detections.sum())}

    pd.DataFrame({"lon": det.lon, "lat": det.lat, "acq_epoch": det.acq_epoch, "unit": unit,
                  "parent": par, "root": root, "edge_root": edge_root, "prior": prior}) \
        .to_parquet(os.path.join(a.out, "lineage.parquet"))
    json.dump(res, open(os.path.join(a.out, "summary.json"), "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("entry", "escape", "density", "per_concession_summary")},
                     indent=1, default=float))
    print(per.head(15)[["kind", "label", "detections", "own", "own_edge", "from_open", "ignitions"]]
          .round(3).to_string())
    print(f"Saved: {a.out}")


if __name__ == "__main__":
    sys.exit(main())
