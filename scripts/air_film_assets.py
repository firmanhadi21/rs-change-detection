"""Assets for the film and infographic 'Jejak di Perairan' (part 4: mining and turbidity in Weda Bay and Sagea Lake).

Reads output/malut_forest/water/ (analysis.json, pressure.json, deepsea_check.json, sirad_rgb_2019_2023_2026.png)
and reuses public/tambang/peta_tambang.jpg and public/periksa/sagea_s2.jpg.
Makes with Earth Engine:
  sedimen_2019.jpg, sedimen_2024.jpg   median TSS (Nechad 2010, 665/865 nm) over 2019-2020 and 2024-2025 on the south
                                       coast of Weda Bay (the AOI of the user's SIRAD script), over muted Sentinel-2 land
  zona.jpg                             the near-mine (<= 2 km) and far-coast (> 15 km) water zones
Writes video/narasi-karhutla/public/air/ and src/airData.json.

    conda run -n base python -I scripts/air_film_assets.py
"""
import json, sys, shutil, urllib.request
from pathlib import Path
from PIL import Image
R = Path("/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection")
sys.path.insert(0, str(R))
from earthchange.gee_utils import initialize_ee
from earthchange.forest_account import DRIVERS
initialize_ee(str(Path.home() / ".secrets/gee-sa.json")); import ee
W = R / "output/malut_forest/water"; V = R / "video/narasi-karhutla"; P = V / "public/air"; P.mkdir(parents=True, exist_ok=True)
A = json.load(open(W / "analysis.json")); PR = json.load(open(W / "pressure.json"))["years"]

AOI = [127.81261749158566, 0.3492338315698112, 128.19301910291378, 0.5538477298898448]   # user's SIRAD AOI
aoi = ee.Geometry.Rectangle(AOI)
cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi).linkCollection(cs, ["cs"])
def tss(img):
    r665 = img.select("B4").divide(10000); r865 = img.select("B8").divide(10000)
    t665 = r665.multiply(355.85).divide(ee.Image(1).subtract(r665.divide(0.1728)))
    t865 = r865.multiply(2971.93).divide(ee.Image(1).subtract(r865.divide(0.2115)))
    t = t665.where(r665.gt(0.07), t865)
    ok = (img.select("SCL").eq(6).And(img.select("cs").gte(0.65)).And(img.select("B11").divide(10000).lt(0.03))
          .And(img.normalizedDifference(["B3", "B11"]).gt(0)).And(t.gt(0)).And(t.lt(2000)))
    return t.updateMask(ok).rename("tss")
# Two-year medians of every scene exceed the interactive memory limit, so the composites are made once by a batch
# export to an Earth Engine asset (30 m, AOI) and the thumbnails are drawn from that.
import time
ASSET = "projects/ee-efha94/assets/malut_tss_median"
try:
    ee.data.getAsset(ASSET); print("asset exists", flush=True)
except Exception:
    comp = ee.Image.cat([
        s2.filterDate("2019-01-01", "2021-01-01").map(tss).median().rename("tss2019"),
        s2.filterDate("2024-01-01", "2026-01-01").map(tss).median().rename("tss2024"),
        s2.filterDate("2025-01-01", "2026-01-01").map(lambda i: i.updateMask(i.select("cs").gte(0.6))).median()
          .select(["B4", "B3", "B2"]).toFloat()])
    task = ee.batch.Export.image.toAsset(image=comp, description="malut_tss_median", assetId=ASSET, region=aoi,
                                         scale=30, crs="EPSG:4326", maxPixels=1e10)
    task.start(); print("export", task.id, flush=True)
    while task.status()["state"] not in ("COMPLETED", "FAILED", "CANCELLED"): time.sleep(30)
    print("export", task.status()["state"], task.status().get("error_message", ""), flush=True)
MED = ee.Image(ASSET)
land = MED.select(["B4", "B3", "B2"]).visualize(min=0, max=2500, gamma=1.2)
grey = land.reduce(ee.Reducer.mean())
land_m = (land.multiply(0.45).add(ee.Image.cat([grey, grey, grey]).rename(["vis-red", "vis-green", "vis-blue"]).multiply(0.3))
          .toByte())   # muted land (band names must match for add)
PAL = ["0b2a4a", "1f5f8b", "3f9ab0", "8cc5a8", "d9c27a", "c98b3e", "9c5a22", "6b3412"]       # clear -> murky
def thumb(img, name, dims=1200):
    url = img.getThumbURL({"region": aoi, "dimensions": dims, "format": "png"})
    for t in range(4):
        try:
            open(P / name.replace(".jpg", ".png"), "wb").write(urllib.request.urlopen(url, timeout=600).read()); break
        except Exception as e:
            body = e.read()[:300] if hasattr(e, "read") else b""
            print("retry", name, t, e, body, flush=True)
            if t == 3: raise
    Image.open(P / name.replace(".jpg", ".png")).convert("RGB").save(P / name, quality=90)
    (P / name.replace(".jpg", ".png")).unlink()
for tag in ("2019", "2024"):
    t = MED.select(f"tss{tag}")
    vis = t.log10().visualize(min=0, max=1.3, palette=PAL)          # 1 .. 20 g/m3, log scale
    thumb(land_m.blend(vis), f"sedimen_{tag}.jpg"); print("sedimen", tag, flush=True)
# zones (same definitions as tss_series.py, pinned to 30 m)
P30 = ee.Projection("EPSG:4326").atScale(30)
box = ee.Geometry.Rectangle([127.70, 0.15, 128.40, 0.75])
sea = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gte(90)
mine = ee.Image(DRIVERS).select("classification").eq(2).unmask(0)
px = ee.Image.pixelArea().sqrt()
dmine = mine.selfMask().fastDistanceTransform(256).sqrt().multiply(px)
dland = sea.Not().selfMask().fastDistanceTransform(256).sqrt().multiply(px)
nolake = ee.Image(1).paint(ee.Geometry.Point([128.068, 0.488]).buffer(3000), 0)
near = sea.And(dmine.lte(2000)).And(nolake).unmask(0).reproject(P30)
far = sea.And(dland.lte(2000)).And(dmine.gt(15000)).And(nolake).unmask(0).reproject(P30)
cells = mine.reproject(ee.Projection("EPSG:4326").atScale(1000))
# schematic base for the whole bay (the Sentinel-2 composite covers only the SIRAD AOI): land / sea from MODIS MOD44W
water = ee.ImageCollection("MODIS/006/MOD44W").sort("system:time_start", False).first().select("water_mask")
base = water.visualize(min=0, max=1, palette=["2A2F36", "0F1A24"])
zimg = (base.blend(cells.selfMask().visualize(palette=["FF5A1F"], opacity=0.85))
        .blend(near.selfMask().visualize(palette=["FFB020"])).blend(far.selfMask().visualize(palette=["9AA3AD"])))
url = zimg.getThumbURL({"region": box, "dimensions": 1200, "format": "png"})
open(P / "zona.png", "wb").write(urllib.request.urlopen(url, timeout=600).read())
Image.open(P / "zona.png").convert("RGB").save(P / "zona.jpg", quality=90); (P / "zona.png").unlink()
print("zona", flush=True)
shutil.copy(W / "sirad_rgb_2019_2023_2026.png", P / "sirad.png")
shutil.copy(V / "public/tambang/peta_tambang.jpg", P / "peta_tambang.jpg")
shutil.copy(V / "public/periksa/sagea_s2.jpg", P / "sagea.jpg")

Y = A["yearly"]
yrs = [str(y) for y in range(2019, 2026)]                # 2026 has 2 paired dates (Jan-Jun): left out of the chart
lake = {y: Y[y].get("lake_med") for y in Y if "lake_med" in Y[y] and int(y) <= 2025}
D = {
    "rasio": {y: round(Y[y]["ratio"], 2) for y in yrs},
    "rasio_ci": {y: [round(float(__import__("math").exp(v)), 2) for v in Y[y]["d_ci"]] for y in yrs},
    "n_tanggal": {y: Y[y]["n"] for y in yrs},
    "dekat": {y: round(Y[y]["near_med"], 1) for y in yrs}, "jauh": {y: round(Y[y]["ref_med"], 1) for y in yrs},
    "danau": {y: round(v, 1) for y, v in lake.items()},
    "tren_pct": round(A["trend_d"]["pct_per_yr"]), "tren_ci": [round(100 * (__import__("math").exp(v) - 1)) for v in A["trend_d"]["ci"]],
    "tren_p": round(A["trend_d"]["p"], 3), "per1000": round(A["reg_d_open"]["pct_per_1000ha"]),
    "per1000_ci": [round(100 * (__import__("math").exp(v) - 1)) for v in A["reg_d_open"]["ci"]], "per1000_p": round(A["reg_d_open"]["p"], 3),
    "hujan_p": round(A["reg_d_open"]["rain_p"], 2), "n_pasang": A["n_dates"]["paired"],
    "terbuka": {y: round(PR[y]["weda_cells"]["dw_open"]) for y in PR},
    "sirad": {y: round(PR[y]["weda_cells"]["sirad_drop"]) for y in PR},
    "danau_dasar": {y: round(PR[y]["sagea_basin"]["dw_open"]) for y in PR},
    "danau_n": A["n_dates"]["lake"],
}
json.dump(D, open(V / "src/airData.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(D, ensure_ascii=False)[:1500])
