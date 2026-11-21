"""Assets for the film and infographic 'Harga di Balik Nikel' (part 5: economic value vs environmental costs of
nickel in North Maluku). Reads output/malut_forest/economics/econ.json (from tmp/malut/econ_analysis.py, inputs in
SOURCES.md). Makes VIIRS night-light images of Weda Bay (annual median of monthly VCMSLCFG avg_rad, 2019 and the
latest full year) and copies peta_tambang.jpg / weda_s2.jpg. Writes video/narasi-karhutla/public/biaya/ and
src/biayaData.json.

    conda run -n base python -I scripts/biaya_film_assets.py
"""
import json, sys, shutil, urllib.request
from pathlib import Path
from PIL import Image
R = Path("/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection")
sys.path.insert(0, str(R))
from earthchange.gee_utils import initialize_ee
initialize_ee(str(Path.home() / ".secrets/gee-sa.json")); import ee
E = json.load(open(R / "output/malut_forest/economics/econ.json"))
V = R / "video/narasi-karhutla"; P = V / "public/biaya"; P.mkdir(parents=True, exist_ok=True)
box = ee.Geometry.Rectangle([127.70, 0.30, 128.30, 0.70])
col = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG").select("avg_rad")
last = ee.Date(col.aggregate_max("system:time_start")).get("year").getInfo()
full = last if ee.Date(col.aggregate_max("system:time_start")).get("month").getInfo() == 12 else last - 1
water = ee.ImageCollection("MODIS/006/MOD44W").sort("system:time_start", False).first().select("water_mask")
base = water.visualize(min=0, max=1, palette=["1B2029", "0A0C0F"])
yrs = {}
for y in (2019, full):
    img = col.filterDate(f"{y}-01-01", f"{y + 1}-01-01").median()
    vis = img.sqrt().updateMask(img.gt(0.6)).visualize(min=0.7, max=8, palette=["3A2A10", "9c5a22", "FF5A1F", "FFB020", "FFF2C8"])
    url = base.blend(vis).getThumbURL({"region": box, "dimensions": 1200, "format": "png"})
    open(P / f"malam_{y}.png", "wb").write(urllib.request.urlopen(url, timeout=600).read())
    Image.open(P / f"malam_{y}.png").convert("RGB").save(P / f"malam_{y}.jpg", quality=90); (P / f"malam_{y}.png").unlink()
    yrs[y] = round(img.reduceRegion(ee.Reducer.sum(), box, 500, maxPixels=1e9).getInfo()["avg_rad"])
    print("malam", y, yrs[y], flush=True)
shutil.copy(V / "public/tambang/peta_tambang.jpg", P / "peta_tambang.jpg")
shutil.copy(V / "public/periksa/weda_s2.jpg", P / "weda_s2.jpg")
Y = E["years"]
D = {
    "tahun": [str(y) for y in range(2019, 2026)],
    "nilai_tambah": {y: Y[y]["gva_total_rp_tn"] for y in Y},
    "tambang": {y: Y[y]["gva_mining_rp_tn"] for y in Y}, "olah": {y: Y[y]["gva_manuf_rp_tn"] for y in Y},
    "kapasitas_gw": {"2023": 1.87, "2025": 6.37},                       # CREA/GEM, July snapshots
    "co2_mt": {y: Y[y]["coal_co2_mt"] for y in Y if "coal_co2_mt" in Y[y]},
    "co2_scc": {y: Y[y]["coal_rp_tn"]["scc"] for y in Y if "coal_rp_tn" in Y[y]},
    "co2_eu": {y: Y[y]["coal_rp_tn"]["eu"] for y in Y if "coal_rp_tn" in Y[y]},
    "kesehatan": E["health_2025_indicative_rp_tn"],
    "karbon_hutan_2025": [Y["2025"]["forest_carbon_rp_tn"]["eu_low"], Y["2025"]["forest_carbon_rp_tn"]["scc_high"]],
    "ekosistem_2025": Y["2025"]["ecosystem_rp_tn"],
    "jumlah_2023_2025": E["sum_2023_2025"],
    "dbh_halteng": 1.1, "dbh_provinsi": [0.317, 0.568], "royalti_nasional_2025": 19,
    "malam": {str(k): v for k, v in yrs.items()}, "malam_tahun": [2019, full],
}
json.dump(D, open(V / "src/biayaData.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(D, ensure_ascii=False)[:1200])
