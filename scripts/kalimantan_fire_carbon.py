"""Carbon cost of Kalimantan fires, 2001-2026, and the expected loss in 2027, by land status
(forest-area class, concessions, customary / adat territories when a map is supplied).

A spatially explicit valuation in the spirit of Strand et al. (2018, Nature Sustainability,
doi:10.1038/s41893-018-0175-0): every 500 m MODIS cell gets an emission (t CO2e) per fire, priced at
several carbon values, then summed by land category.

Emission factors (all checked against the source tables):
  Peat (organic soil) fires - IPCC 2013 Wetlands Supplement, ch. 2, Table 2.6 / 2.7:
    fuel consumption, tropical drained-peat wildfire 353 t d.m./ha (95% CI 170-536);
    prescribed fire on agricultural land 155 (82-228), used for fires inside oil palm;
    emission factors (g/kg d.m.): CO2-C 464 (-> 1701 g CO2), CH4 21.
  Above-ground biomass - IPCC 2006 vol. 4, ch. 2: Table 2.6 combustion factor 0.32 (primary tropical
    forest), 0.55 (all secondary tropical forests); Table 2.5 tropical forest EF (g/kg d.m.):
    CO2 1580, CH4 6.8, N2O 0.20.
  Biomass: ESA CCI AGB v6 (Mg/ha), epoch before the fire (2007, 2010, 2015, 2020, 2022).
  GWP100 (IPCC AR5): CH4 28, N2O 265.
  Carbon prices (US$/t CO2): 5 (Strand et al. 2018), 51 (US interagency value 2021) and
    185 (Rennert et al. 2022, Nature, doi:10.1038/s41586-022-05224-9; 5-95% range 44-413).

Stages:
    python scripts/kalimantan_fire_carbon.py --stage carbon [--adat path.gpkg]
Needs data/kalimantan_panel/{panel,cells}.parquet, agb.tif, y2026.tif (panel exports 'agb', 'y2026'),
status in cells.parquet (kalimantan_fire_factors.py --stage status) and, for 2027,
output/fire/kalimantan_palm_panel/fire_risk_2027.tif (kalimantan_fire_factors.py --stage forecast).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kalimantan_palm_fire_panel import DATA, OUT, CELL_KM, YEARS, PALM_MIN, _read  # noqa: E402

CELL_HA = CELL_KM ** 2 * 100
PEAT_FUEL = {"low": 170.0, "central": 353.0, "high": 536.0}        # t d.m./ha, wildfire, drained peat
PEAT_FUEL_AG = {"low": 82.0, "central": 155.0, "high": 228.0}      # prescribed fire, agricultural land
GWP_CH4, GWP_N2O = 28.0, 265.0
PEAT_EF = 464 * 44 / 12 / 1000 + 21 / 1000 * GWP_CH4              # t CO2e per t d.m.
BIO_EF = 1580 / 1000 + 6.8 / 1000 * GWP_CH4 + 0.20 / 1000 * GWP_N2O
CF_PRIMARY, CF_SECONDARY = 0.32, 0.55
PRICES = (5, 51, 185)
AGB_EPOCHS = (2007, 2010, 2015, 2020, 2022)
ADAT_DEFAULT = os.path.join(os.path.dirname(DATA), "kalimantan", "wilayah_adat_kalimantan.gpkg")


def _epoch(y):
    """Last biomass epoch before the fire year (2007 for the earliest years)."""
    prior = [e for e in AGB_EPOCHS if e < y]
    return prior[-1] if prior else AGB_EPOCHS[0]


def _adat(cells, path):
    """Cells whose centre lies in an adat / customary territory polygon (optional)."""
    import geopandas as gpd
    import numpy as np
    from rasterio import features
    if not path or not os.path.exists(path):
        return None
    _, tr, crs, shp = _read("env")
    g = gpd.read_file(path).to_crs(crs)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    ras = features.rasterize([(geom, 1) for geom in g.geometry.make_valid()], out_shape=shp,
                             transform=tr, dtype="uint8", all_touched=False)
    print(f"adat territories: {len(g)} polygons from {path}")
    return ras[cells.r.to_numpy(), cells.c.to_numpy()].astype(bool)


def stage_carbon(a):
    import numpy as np
    import pandas as pd
    import rasterio
    cells = pd.read_parquet(os.path.join(DATA, "cells.parquet"))
    n = len(cells)
    p = pd.read_parquet(os.path.join(DATA, "panel.parquet"), columns=["burn", "ind", "sh", "und"])
    T = len(YEARS)
    burn = p.burn.to_numpy().reshape(T, n).astype(bool)
    ind = p.ind.to_numpy().reshape(T, n)
    sh = p.sh.to_numpy().reshape(T, n)
    und = p.und.to_numpy().reshape(T, n)
    rr, cc = cells.r.to_numpy(), cells.c.to_numpy()
    Y = _read("y2026")[0]
    burn = np.vstack([burn, (Y["burn_2026"][rr, cc] > 0)[None]])
    ind, sh, und = (np.vstack([x, x[-1:]]) for x in (ind, sh, und))
    years = list(YEARS) + [2026]
    G = _read("agb")[0]
    agb = {e: G[f"agb_{e}"][rr, cc].astype(np.float32) for e in AGB_EPOCHS}
    peat = cells.peat.to_numpy()
    adat = _adat(cells, a.adat)

    def per_ha(t, level="central"):
        """t CO2e per ha if cell burns in year index t (previous-year land state)."""
        tl = max(t - 1, 0)
        in_palm = (ind[tl] >= PALM_MIN) | (sh[tl] >= PALM_MIN)
        fuel = np.where(in_palm, PEAT_FUEL_AG[level], PEAT_FUEL[level])
        e_peat = np.where(peat, fuel * PEAT_EF, 0.0)
        u = und[tl] / 100.0
        cf = u * CF_PRIMARY + (1 - u) * CF_SECONDARY
        e_bio = agb[_epoch(years[t])] * cf * BIO_EF
        return e_peat, e_bio

    # ---- per-year totals, and per-cell totals 2001-2025 (2026 reported separately: Jan-Sep only)
    rows = []
    cell_tot = np.zeros(n)
    for t, y in enumerate(years):
        b = burn[t]
        rec = {"year": y, "burned_km2": round(float(b.sum() * CELL_KM ** 2))}
        for lvl in ("low", "central", "high"):
            ep, eb = per_ha(t, lvl)
            rec[f"peat_MtCO2e_{lvl}"] = round(float((ep * b).sum() * CELL_HA / 1e6), 1)
            rec[f"total_MtCO2e_{lvl}"] = round(float(((ep + eb) * b).sum() * CELL_HA / 1e6), 1)
            if lvl == "central":
                rec["biomass_MtCO2e"] = round(float((eb * b).sum() * CELL_HA / 1e6), 1)
                if y <= 2025:
                    cell_tot += (ep + eb) * b * CELL_HA
        rows.append(rec)
    yr = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    yr.to_csv(os.path.join(OUT, "fire_carbon_by_year.csv"), index=False)
    pd.set_option("display.width", 220)
    print(yr.to_string(index=False))

    # ---- by land category, 2001-2025
    status = cells.status.fillna("none").to_numpy()
    soil = np.where(peat, "peat", "mineral")
    cats = {"status": status, "status_soil": np.char.add(np.char.add(status.astype(str), " / "), soil),
            "concession": np.where(cells.conc, "oil palm concession", np.where(cells.hti, "pulpwood concession", "outside concessions"))}
    if adat is not None:
        cats["adat"] = np.where(adat, "adat territory", "outside adat")
        cats["adat_soil"] = np.char.add(np.where(adat, "adat / ", "outside / "), soil)
    tot = cell_tot.sum()
    by = []
    for kind, lab in cats.items():
        for k in np.unique(lab):
            m = lab == k
            e = cell_tot[m].sum()
            by.append({"by": kind, "category": k, "area_km2": round(float(m.sum() * CELL_KM ** 2)),
                       "MtCO2e_2001_2025": round(e / 1e6, 1), "share_pct": round(100 * e / tot, 1),
                       "tCO2e_per_km2_per_yr": round(e / (m.sum() * CELL_KM ** 2) / 25, 1),
                       **{f"USD_bn_at_{pz}": round(e * pz / 1e9, 2) for pz in PRICES}})
    byc = pd.DataFrame(by)
    byc.to_csv(os.path.join(OUT, "fire_carbon_by_category.csv"), index=False)
    print("\n", byc.to_string(index=False))

    # ---- fire loss: area of productive land and intact forest burned (km2)
    loss = []
    for t, y in enumerate(years):
        tl = max(t - 1, 0)
        b = burn[t]
        loss.append({"year": y,
                     "industrial_palm_km2": round(float((b & (ind[tl] >= PALM_MIN)).sum() * CELL_KM ** 2)),
                     "smallholder_palm_km2": round(float((b & (sh[tl] >= PALM_MIN)).sum() * CELL_KM ** 2)),
                     "pulpwood_concession_km2": round(float((b & cells.hti.to_numpy()).sum() * CELL_KM ** 2)),
                     "intact_forest_km2": round(float((b & (und[tl] >= 90)).sum() * CELL_KM ** 2)),
                     **({"adat_km2": round(float((b & adat).sum() * CELL_KM ** 2))} if adat is not None else {})})
    lo = pd.DataFrame(loss)
    lo.to_csv(os.path.join(OUT, "fire_loss_area_by_year.csv"), index=False)
    print("\n", lo.to_string(index=False))

    # ---- expected loss 2027 = P(burn) x emission per ha, under normal and dry seasons
    res = {"params": {"peat_fuel_t_dm_ha": PEAT_FUEL, "peat_fuel_in_palm": PEAT_FUEL_AG,
                      "peat_tCO2e_per_t_dm": round(PEAT_EF, 3), "biomass_tCO2e_per_t_dm": round(BIO_EF, 3),
                      "cf_primary": CF_PRIMARY, "cf_secondary": CF_SECONDARY, "prices_usd": PRICES,
                      "cell_ha": round(CELL_HA, 2)},
           "total_2001_2025_MtCO2e": {lvl: round(float(yr[yr.year <= 2025][f"total_MtCO2e_{lvl}"].sum()), 0)
                                      for lvl in ("low", "central", "high")}}
    rp = os.path.join(OUT, "fire_risk_2027.tif")
    if os.path.exists(rp):
        with rasterio.open(rp) as ds:
            pr = {s: ds.read(i + 1)[rr, cc] for i, s in enumerate(("normal", "dry"))}
        t27 = len(years)                                    # land state end-2026 = carried forward
        ind, sh, und = (np.vstack([x, x[-1:]]) for x in (ind, sh, und))
        years.append(2027)
        ep, eb = per_ha(t27)
        e_cell = (ep + eb) * CELL_HA
        exp = {}
        for s in pr:
            ex = pr[s] * e_cell
            exp[s] = {"MtCO2e": round(float(ex.sum() / 1e6), 1),
                      **{f"USD_bn_at_{pz}": round(float(ex.sum() * pz / 1e9), 2) for pz in PRICES},
                      "by_status_MtCO2e": {k: round(float(ex[status == k].sum() / 1e6), 1) for k in np.unique(status)}}
            if adat is not None:
                exp[s]["adat_MtCO2e"] = round(float(ex[adat].sum() / 1e6), 1)
        res["expected_2027"] = exp
        print("\nexpected 2027:", json.dumps(exp, indent=1))
    else:
        print("\n(no fire_risk_2027.tif yet: run kalimantan_fire_factors.py --stage forecast first)")
    json.dump(res, open(os.path.join(OUT, "fire_carbon.json"), "w"), indent=1, default=float)
    print(json.dumps({k: v for k, v in res.items() if k != "expected_2027"}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", required=True, choices=["carbon"])
    ap.add_argument("--adat", default=ADAT_DEFAULT, help="adat / customary territory polygons (optional)")
    a = ap.parse_args()
    {"carbon": stage_carbon}[a.stage](a)


if __name__ == "__main__":
    main()
