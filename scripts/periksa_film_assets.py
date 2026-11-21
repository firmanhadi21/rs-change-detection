"""Assets for the film 'Memeriksa Peta Tambang' (checking the Weda Bay / Sagea open-ground maps against hand labels).
Writes video/narasi-karhutla/public/periksa/*.jpg and src/periksaData.json from
output/malut_forest/embeddings/ (labeller/, map2025/, exp19_weda_aef/).
Run: conda run -n base python -I scripts/periksa_film_assets.py"""
import json, sys, shutil, glob
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from PIL import Image
R = Path("/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection")
sys.path.insert(0, str(R))
from earthchange.gee_utils import initialize_ee
from earthchange.timelapse import fetch_frame
E = R / "output/malut_forest/embeddings"; L = E / "labeller"; M = L / "map2025"
V = R / "video/narasi-karhutla"; P = V / "public/periksa"; P.mkdir(parents=True, exist_ok=True)
BARA, NYALA, ABU = (255, 90, 31), (255, 176, 32), (126, 135, 146)
initialize_ee(str(Path.home() / ".secrets/gee-sa.json"))

def base(bb, H):
    W = int(round(H * (bb[2] - bb[0]) / (bb[3] - bb[1])))
    for k in range(4):                                 # Earth Engine sometimes drops the connection
        try:
            img, _ = fetch_frame(bb, 2025, W, "s2", 1, False); break
        except Exception as e:
            print("retry", k, e, flush=True)
    else:
        raise SystemExit("Sentinel-2 frame failed 4 times")
    rgb = np.asarray(img.convert("RGB").resize((W, H), Image.LANCZOS)).astype("f4")
    return rgb, W
def onto(path, bb, W, H, dtype="uint8", nod=255):
    with rasterio.open(path) as r:
        out = np.full((H, W), nod, dtype)
        reproject(r.read(1), out, src_transform=r.transform, src_crs=r.crs, dst_transform=from_bounds(*bb, W, H),
                  dst_crs="EPSG:4326", resampling=Resampling.nearest, src_nodata=nod, dst_nodata=nod)
    return out
def mute(rgb): return rgb * 0.5 + 0.35 * rgb.mean(-1, keepdims=True)
def save(a, name): Image.fromarray(np.clip(a, 0, 255).astype("uint8")).save(P / name, quality=88)
def paint(a, m, col, alpha=0.88):
    a = a.copy(); a[m] = a[m] * (1 - alpha) + np.array(col) * alpha; return a

data = {}
for s, bb, H in (("weda", (127.88, 0.46, 128.04, 0.68), 1080), ("sagea", (128.035, 0.455, 128.105, 0.515), 1080)):
    rgb, W = base(bb, H)
    save(rgb, f"{s}_s2.jpg")
    cls = onto(M / f"aef_{s}_shore.tif", bb, W, H)
    fy = onto(M / f"aef_{s}_open_year.tif", bb, W, H, "int16", 0)
    mu = mute(rgb)
    save(paint(paint(mu, cls == 1, BARA), cls == 2, NYALA), f"{s}_baru.jpg")
    if s == "weda":                                    # old box-trained AlphaEarth map (open ground in 2025)
        # old box-trained AlphaEarth classes 2025 (old export: 0 = bare, 1 = built; its nodata tag 0 is wrong, so ignore it)
        with rasterio.open(E / "weda_aef/classes_2025.tif") as r:
            old = np.full((H, W), 255, "uint8")
            reproject(r.read(1), old, src_transform=r.transform, src_crs=r.crs, dst_transform=from_bounds(*bb, W, H),
                      dst_crs="EPSG:4326", resampling=Resampling.nearest, src_nodata=None)
        save(paint(mu, np.isin(old, (0, 1)) & (cls != 255), BARA), "weda_lama.jpg")
    open_ = np.isin(cls, (1, 2)); pre = open_ & (fy == 0)
    for y in range(2019, 2026):
        a = paint(mu, pre, ABU, 0.8)
        a = paint(a, open_ & (fy > 0) & (fy < y), BARA)
        a = paint(a, open_ & (fy == y), NYALA, 0.95)
        save(a, f"{s}_y{y}.jpg")
    data[s] = {"lebar": W, "tinggi": H, "bbox": bb}
    print(s, W, H, flush=True)

# example chips: contested points the labeller kept as shrub twice although both earlier maps said open
priv = {p["id"]: p for p in json.load(open(L / "points_private.json"))}
r1 = {f["properties"]["point"]: f["properties"]["class"] for f in json.load(open(L / "labels_clipboard.geojson"))["features"]}
r2 = {}
for p in glob.glob(str(L / "recheck_db/recheck/*.json")):
    d = json.load(open(p)); d = d.get("data", d); r2[d["point"]] = d["cls"]
OPEN = {"bare", "built"}
pick = [i for i in sorted(r2) if r1[i] == "shrub" and r2[i] == "shrub" and priv[i]["tessera"] in OPEN and priv[i]["aef"] in OPEN][:2]
pick += [i for i in sorted(r2) if r1[i] == "shrub" and r2[i] == "disturbed"][:1]
pick += [i for i in sorted(r2) if r1[i] in OPEN and r2[i] in OPEN][:1]
data["chips"] = []
for i in pick:
    shutil.copy(L / f"chips/{i}_n.jpg", P / f"chip_{i}.jpg")
    data["chips"].append({"id": i, "peta_lama": "terbuka", "label1": r1[i], "label2": r2[i]})

ev = json.load(open(L / "label_eval.json")); rc = json.load(open(L / "recheck_eval.json")); X = json.load(open(M / "expansion.json"))
def yrs(k): 
    o, d = X[k]["open"]["by_first_change"], X[k]["disturbed"]["by_first_change"]
    return {y: round(o[y] + d[y], 1) for y in o}
data.update({
    "titik": 300, "titik_dipakai": ev["n_points"], "terbuka_label": ev["open_labelled"],
    "lama": {"presisi_tessera": ev["old_tessera_points"]["precision"], "presisi_aef": ev["old_aef_points"]["precision"],
             "recall": 1.0, "skor_kotak": [0.914, 0.921], "weda_ha": [10568, 13862]},
    "cek_ulang": {"n": 101, "diperdebatkan": rc["contested"]["n"], "tetap": rc["contested"]["unchanged"],
                  "ke_terganggu": rc["contested"]["transitions"].get("shrub->disturbed", 0),
                  "kontrol": rc["control_open"]["n"] + rc["control_veg"]["n"],
                  "kontrol_tetap": rc["control_open"]["unchanged"] + rc["control_veg"]["unchanged"]},
    "baru_cv": {"aef": rc["cv_open_aef"], "tessera": rc["cv_open_tessera"]},
    "luas": {"weda_terbuka": rc["area_adjusted_2025_ha"]["weda_open"], "weda_plus": rc["area_adjusted_2025_ha"]["weda_open+disturbed"],
             "peta_aef_terbuka": X["weda_box_aef"]["open"]["2025_ha"], "peta_aef_terganggu": X["weda_box_aef"]["disturbed"]["2025_ha"]},
    "tahun_weda_aef": yrs("weda_box_aef"), "tahun_weda_tessera": yrs("weda_box_tessera"),
    "danau_aef": yrs("sagea_patch_aef"), "danau_tessera": yrs("sagea_patch_tessera"),
    "danau_2025": [round(X["sagea_patch_aef"]["open"]["2025_ha"] + X["sagea_patch_aef"]["disturbed"]["2025_ha"]),
                   round(X["sagea_patch_tessera"]["open"]["2025_ha"] + X["sagea_patch_tessera"]["disturbed"]["2025_ha"])],
    "danau_dw_2026": 61,
})
json.dump(data, open(V / "src/periksaData.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in data.items() if k not in ("weda", "sagea")}, ensure_ascii=False)[:1500])
