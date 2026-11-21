"""Data and assets for part 6, 'Ke Mana Uangnya?' (where does the nickel money go?), North Maluku.

Every figure is copied from output/malut_forest/welfare/SOURCES.md (grade in brackets: a = read in the BPS/BI
document, b = secondhand quoting the publisher, c = search snippet). Computations here are simple ratios and
differences. Writes output/malut_forest/welfare/welfare.json and video/narasi-karhutla/src/uangData.json, and copies
three images already made for parts 3-5 into public/uang/.

    conda run -n base python -I scripts/uang_film_assets.py
"""
import json, shutil
from pathlib import Path
R = Path("/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection")
W = R / "output/malut_forest/welfare"; V = R / "video/narasi-karhutla"; P = V / "public/uang"; P.mkdir(parents=True, exist_ok=True)

MINING = ["Halmahera Tengah", "Halmahera Selatan", "Halmahera Timur"]
NONMINING = ["Halmahera Barat", "Kepulauan Sula", "Halmahera Utara", "Pulau Morotai", "Pulau Taliabu", "Kota Ternate", "Kota Tidore Kepulauan"]
# 2.1 poverty P0 (%), March, 2019 [a] and 2025 [a]
P0 = {"Halmahera Barat": (8.59, 7.90), "Halmahera Tengah": (14.12, 9.16), "Kepulauan Sula": (8.98, 7.65),
      "Halmahera Selatan": (5.03, 4.81), "Halmahera Utara": (4.55, 4.35), "Halmahera Timur": (15.39, 10.54),
      "Pulau Morotai": (7.27, 4.49), "Pulau Taliabu": (7.53, 6.63), "Kota Ternate": (3.14, 3.34),
      "Kota Tidore Kepulauan": (6.10, 6.54)}
P0_PROV = (6.77, 5.81)
POOR_HALTENG = (7.81, 5.61)                    # thousand people, 2019 / 2025 [a]
# 1.3 PDRB per capita ADHB, thousand Rp [a]
PDRB_CAP = {"Halmahera Tengah": {2017: 36572, 2018: 40518, 2019: 44283, 2020: 58226, 2021: 166922, 2022: 359993, 2023: 479057, 2024: 532124, 2025: 870960},
            "Halmahera Barat": {2019: 19303, 2025: 22782}, "Halmahera Selatan": {2019: 31217, 2025: 114370},
            "Halmahera Timur": {2019: 37302, 2025: 83278}, "Kota Ternate": {2019: 46086, 2025: 76451}}
PDRB_HALTENG_2025 = 54961                      # Rp bn [a]
POP_REGISTRY_2024 = 106500                     # Dukcapil [b]
# Susenas nominal per-capita expenditure, Rp per month: Halteng 2018-2025 [b]; others 2025 [c]
SPEND_HALTENG = {2018: 1194428, 2019: 1297624, 2020: 1461771, 2021: 1287024, 2022: 1318967, 2023: 2051218, 2024: 2227076, 2025: 2216767}
SPEND_2025 = {"Halmahera Barat": 1192853, "Halmahera Selatan": 1336792, "Halmahera Timur": 1700451, "Kota Ternate": 2370000}
# 3.2 IPM new series 2021 / 2024 [a]; 3.3 adjusted expenditure 2024 (thousand Rp/yr) [a]
IPM = {"Halmahera Tengah": (68.38, 70.94), "Halmahera Barat": (67.20, 69.20), "Halmahera Timur": (67.70, 70.35),
       "Halmahera Selatan": (65.88, 68.43), "Maluku Utara": (69.56, 71.84)}
ADJ_EXP_2024 = {"Halmahera Tengah": 9140, "Maluku Utara": 9320, "Halmahera Barat": 8426}
# 8.1 manufacturing employment, province [a]; 8.2 park workforce [b]
MANUF_JOBS = {"Agu 2018": 28365, "Agu 2020": 31482, "Agu 2022": 116038, "Feb 2025": 163650}
PARK = {"workers": 81000, "malut_pct": 40, "around_mine_pct": 35}
# 6.2 expenditure shares of province PDRB, % [a]
SHARE = {"2018": {"rumah_tangga": 54.83, "investasi": 27.41}, "2022": {"rumah_tangga": 34.91, "investasi": 65.96}}
# 10 fiscal [b]; 11 ownership [a]/[b]; 9 tax holiday [c]
APBD_HALTENG_2026 = 1839.03                    # Rp bn, revenue budget
DBH_HALTENG = 1100                             # Rp bn, ~2024
PMA_SHARE_Q2_2026 = 98.14                      # % of realised investment, Malut [a]

def chg(a, b): return round(b - a, 2)
mine_d = {k: chg(*P0[k]) for k in MINING}
non_d = {k: chg(*P0[k]) for k in NONMINING}
hal = PDRB_CAP["Halmahera Tengah"]
out = {
    "poverty_change_2019_2025_pp": {"mining": mine_d, "nonmining": non_d,
                                    "nonmining_mean": round(sum(non_d.values()) / len(non_d), 2), "province": chg(*P0_PROV)},
    "poverty": {k: list(v) for k, v in P0.items()}, "poverty_province": list(P0_PROV), "poor_halteng_thousand": list(POOR_HALTENG),
    "halteng_pdrb_cap": hal, "halteng_spend_month": SPEND_HALTENG,
    "halteng_growth_2019_2025": {"pdrb_cap_x": round(hal[2025] / hal[2019], 1),
                                 "spend_x": round(SPEND_HALTENG[2025] / SPEND_HALTENG[2019], 2)},
    "halteng_spend_year_thousand": {y: round(v * 12 / 1000) for y, v in SPEND_HALTENG.items()},
}
ratio = {}
for k, v in SPEND_2025.items():
    ratio[k] = round(PDRB_CAP[k][2025] / (v * 12 / 1000), 1)
ratio["Halmahera Tengah"] = round(hal[2025] / (SPEND_HALTENG[2025] * 12 / 1000), 1)
alt = PDRB_HALTENG_2025 * 1e6 / POP_REGISTRY_2024                     # thousand Rp per registered resident
out["production_to_spending_2025"] = ratio
out["halteng_ratio_registry_pop"] = round(alt / (SPEND_HALTENG[2025] * 12 / 1000), 1)
out["halteng_spend_per_100_production"] = [round(100 * SPEND_HALTENG[2025] * 12 / 1000 / hal[2025], 1),
                                           round(100 * SPEND_HALTENG[2025] * 12 / 1000 / alt, 1)]
out["halteng_ratio_2019"] = round(hal[2019] / (SPEND_HALTENG[2019] * 12 / 1000), 1)
out["ipm"] = {k: list(v) for k, v in IPM.items()}; out["adj_exp_2024"] = ADJ_EXP_2024
out["manuf_jobs"] = MANUF_JOBS; out["park"] = PARK; out["expenditure_shares"] = SHARE
out["fiscal"] = {"apbd_halteng_2026_rp_bn": APBD_HALTENG_2026, "pdrb_halteng_2025_rp_bn": PDRB_HALTENG_2025,
                 "apbd_share_pct": round(100 * APBD_HALTENG_2026 / PDRB_HALTENG_2025, 1), "dbh_halteng_rp_bn": DBH_HALTENG}
out["pma_share_pct"] = PMA_SHARE_Q2_2026
out["grades"] = {"pdrb": "a", "poverty_2019_2025": "a", "spend_halteng": "b", "spend_others_2025": "c", "ipm": "a",
                 "manuf_jobs": "a", "park": "b (company statement)", "apbd": "b", "dbh": "b", "pma": "a", "tax_holiday": "c"}
json.dump(out, open(W / "welfare.json", "w"), indent=1, ensure_ascii=False)
json.dump(out, open(V / "src/uangData.json", "w"), indent=1, ensure_ascii=False)
for src, dst in (("public/biaya/malam_2025.jpg", "malam_2025.jpg"), ("public/biaya/weda_s2.jpg", "weda_s2.jpg"),
                 ("public/biaya/peta_tambang.jpg", "peta_tambang.jpg")):
    shutil.copy(V / src, P / dst)
print(json.dumps({k: out[k] for k in ("poverty_change_2019_2025_pp", "halteng_growth_2019_2025", "production_to_spending_2025",
                                      "halteng_ratio_registry_pop", "halteng_spend_per_100_production", "halteng_ratio_2019", "fiscal")}, indent=1, ensure_ascii=False))
