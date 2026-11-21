"""Assets for the film and infographic 'Jejak Tambang Nikel di Maluku Utara' (open and disturbed ground inside the
WRI/Google mining cells, label-adjusted with 150 hand-labelled check points).

Reads output/malut_forest/ (province_grid.npz, regencies.geojson) and output/malut_forest/mining_malut/
(areas.json, check_eval.json, years_adjusted.json, check/points_private.json, check/db/, check/chips/).
Writes video/narasi-karhutla/public/tambang/*.jpg and src/tambangData.json.

    conda run -n base python -I scripts/tambang_film_assets.py
"""
import json, sys, glob, shutil
from pathlib import Path
import numpy as np
from PIL import Image
R = Path("/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection")
sys.path.insert(0, str(R))
from earthchange.gee_utils import initialize_ee
from earthchange.forest_account import DRIVERS
from earthchange.timelapse import fetch_frame
from earthchange import embeddings as E
initialize_ee(str(Path.home() / ".secrets/gee-sa.json")); import ee
S = R / "output/malut_forest"; M = S / "mining_malut"; LB = S / "embeddings/labeller"
V = R / "video/narasi-karhutla"; P = V / "public/tambang"; P.mkdir(parents=True, exist_ok=True)
JELAGA, DARAT, KAPUR, ABU = "#0A0C0F", "#1B2029", "#E8EBEE", "#7E8792"
BARA, NYALA = (255, 90, 31), (255, 176, 32)
NAMA = {"Halmahera Tengah": "Halmahera Tengah", "Halmahera Selatan": "Halmahera Selatan", "Halmahera Timur": "Halmahera Timur",
        "Pulau Taliabu": "Pulau Taliabu", "Halmahera Utara": "Halmahera Utara", "Halmahera Barat": "Halmahera Barat"}

def pixels(img, bb, W, H, strip=270):
    """ee.Image -> numpy (H, W) on an exact lon/lat grid, fetched in row strips (computePixels)."""
    x0, y0, x1, y1 = bb; dx, dy = (x1 - x0) / W, (y1 - y0) / H
    out = []
    for r in range(0, H, strip):
        h = min(strip, H - r)
        for t in range(4):
            try:
                a = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY",
                                           "grid": {"dimensions": {"width": W, "height": h}, "crsCode": "EPSG:4326",
                                                    "affineTransform": {"scaleX": dx, "shearX": 0, "translateX": x0,
                                                                        "shearY": 0, "scaleY": -dy, "translateY": y1 - r * dy}}})
                break
            except Exception as e:
                print("retry", t, str(e)[:100], flush=True)
                if t == 3: raise
        out.append(np.asarray(a[a.dtype.names[0]] if a.dtype.names else a))
    return np.vstack(out)

# ----------------------------------------------------------------- figures
A = json.load(open(M / "areas.json")); EV = json.load(open(M / "check_eval.json")); YA = json.load(open(M / "years_adjusted.json"))
KEYS = ["<=2019/unchanged"] + [str(y) for y in range(2020, 2026)]
reg = []
for r, d in A["regencies"].items():
    s = lambda c: sum(v for k, v in d.items() if k.startswith(c + "|"))
    e = EV["estimates"][r]
    reg.append({"nama": NAMA[r], "sel": round(s("open") + s("disturbed") + s("other")), "peta_terbuka": round(s("open")),
                "peta_plus": round(s("open") + s("disturbed")), "terbuka": e["open"], "plus": e["open_dist"],
                "tahun": [YA["by_regency_open_dist"][r][k] for k in KEYS]})
reg.sort(key=lambda x: -x["plus"][0])
conf = EV["confusion"]
grp = lambda c, ks: sum(c.get(k, 0) for k in ks)
cek = {s: {"terbuka": grp(conf[s], ["bare", "built"]), "terganggu": grp(conf[s], ["disturbed"]),
           "vegetasi": grp(conf[s], ["forest", "shrub", "tree_crops", "water"]), "n": sum(conf[s].values())} for s in conf}
T = EV["estimates"]["Total"]
D = {"sel_ha": A["mining_cell_land_ha_100m"], "titik": EV["n"], "cek": cek,
     "total": {"peta_terbuka": T["map_open"], "peta_plus": T["map_open_dist"], "terbuka": T["open"], "plus": T["open_dist"]},
     "kabupaten": reg, "tahun": ["≤ 2019", "2020", "2021", "2022", "2023", "2024", "2025"],
     "tahun_peta": [YA["map_open_dist"][k] for k in KEYS], "tahun_plus": [YA["open_dist"][k] for k in KEYS],
     "tahun_terbuka": [YA["open"][k] for k in KEYS]}

# ------------------------------------------------------- province map of mining cells
g = np.load(S / "province_grid.npz"); x0, x1, y0, y1 = [float(v) for v in g["extent"]]
Wc, Hc = int(round((x1 - x0) / 0.009)), int(round((y1 - y0) / 0.009))
PETA_SAJA = "--peta" in sys.argv                     # redraw the two province maps only, from the cached grid
if PETA_SAJA and (M / "mining_cells_grid.npy").exists():
    mine = np.load(M / "mining_cells_grid.npy")
else:
    mine = pixels(ee.Image(DRIVERS).select("classification").eq(2).unmask(0).toByte(), (x0, y0, x1, y1), Wc, Hc)
    np.save(M / "mining_cells_grid.npy", mine)
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.patheffects as pe
from matplotlib.colors import to_rgb
from rasterio import features
from rasterio.transform import from_bounds
from shapely.geometry import shape, Point
regs = json.load(open(S / "regencies.geojson"))["features"]
H, W = g["f2000"].shape
prov = features.rasterize([(shape(r["geometry"]), 1) for r in regs], out_shape=(H, W), transform=from_bounds(x0, y0, x1, y1, W, H))
land = (g["land"] / 250.0) * prov
img = np.zeros((H, W, 3)); img[:] = to_rgb(JELAGA)
img = np.where(land[..., None] > 0.3, np.array(to_rgb(DARAT)), img)
mk = np.array(Image.fromarray(mine.astype("uint8") * 255).resize((W, H), Image.NEAREST)) > 0
from scipy.ndimage import maximum_filter
mk = maximum_filter(mk, size=7)                       # 1 km cells are ~2 px at province scale: widen to ~2 km to be seen
img[mk & (land > 0.3)] = np.array(BARA) / 255
def polys(gm):
    if gm.geom_type == "Polygon": return [gm]
    return [q for h in getattr(gm, "geoms", []) for q in polys(h)]
def peta(name, size, axrect, labels=True, boxes=()):
    fig = plt.figure(figsize=size, dpi=100, facecolor=JELAGA)
    ax = fig.add_axes(axrect); ax.set_facecolor(JELAGA)
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation="nearest")
    for r in regs:
        for q in polys(shape(r["geometry"])):
            ax.plot(*np.asarray(q.exterior.coords).T, color="#3A424D", lw=0.6)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")
    if labels:
        for x, y, t in [(127.75, 1.62, "Halmahera Utara"), (128.0, 0.78, "Halmahera Tengah"), (128.55, 1.25, "Halmahera Timur"),
                        (127.55, -1.05, "Halmahera Selatan"), (124.75, -1.45, "Pulau Taliabu"), (127.25, 1.25, "Halmahera Barat")]:
            ax.annotate(t, (x, y), ha="center", va="center", fontsize=size[0] * 0.8, color=KAPUR, fontweight="bold",
                        path_effects=[pe.withStroke(linewidth=5, foreground=JELAGA)])
    for (bx0, by0, bx1, by1) in boxes:
        ax.plot([bx0, bx1, bx1, bx0, bx0], [by0, by0, by1, by1, by0], color=KAPUR, lw=1.6)
    fig.savefig(P / name, facecolor=JELAGA, pil_kwargs={"quality": 90}); plt.close(fig)

# ------------------------------------------------------- zooms: one cluster of labelled bare ground per regency
pts = {p["id"]: p for p in json.load(open(M / "check/points_private.json"))}
lab = {}
for f in glob.glob(str(M / "check/db/mining_check/*.json")):
    d = json.load(open(f)); d = d.get("data", d); lab[d["point"]] = d["cls"]
shp = {r["properties"]["GAUL2_NAME"]: shape(r["geometry"]) for r in regs}
def regency(p):
    for n, s in shp.items():
        if s.contains(Point(p["lon"], p["lat"])): return n
zoom = {}
for r in ("Halmahera Tengah", "Halmahera Selatan", "Halmahera Timur"):
    xy = np.array([(p["lon"], p["lat"]) for k, p in pts.items() if lab.get(k) in ("bare", "built") and regency(p) == r])
    # densest point: most labelled-bare neighbours within 4 km
    dens = [((np.hypot(*(xy - q).T) < 0.036).sum()) for q in xy]
    cx, cy = xy[int(np.argmax(dens))]
    zoom[r] = (round(cx - 0.06, 4), round(cy - 0.054, 4), round(cx + 0.06, 4), round(cy + 0.054, 4))
D["zoom"] = {NAMA[k]: v for k, v in zoom.items()}
peta("peta_tambang.jpg", (19.2, 10.8), [0.37, 0.03, 0.62, 0.94])
peta("peta_tambang_kecil.jpg", (8.6, 9.4), [0.0, 0.0, 1.0, 1.0], labels=False, boxes=())
print("maps", flush=True)
if PETA_SAJA: sys.exit(0)

# classifier exactly as mining_malut2.py / mining_sample.py: AlphaEarth 2025, two RFs on the merged Weda/Sagea labels
d = np.load(LB / "point_features.npz")
merged = {f["properties"]["point"]: f["properties"]["class"] for f in json.load(open(LB / "labels_merged.geojson"))["features"]}
cls = np.array([merged[i] for i in d["ids"]]); keep = ~np.isin(cls, ["water", "unsure"])
Y1 = np.isin(cls, ["bare", "built"]).astype(int)[keep]; Y2 = np.isin(cls, ["bare", "built", "disturbed"]).astype(int)[keep]
Af = d["A"][keep]
def klass(bbg):
    im = E.aef_year(bbg, 2025); bands = im.bandNames().getInfo()
    def clf(y):
        fc = ee.FeatureCollection([ee.Feature(None, dict(zip(bands, map(float, Af[i])), cls=int(y[i]))) for i in range(len(y))])
        return im.classify(ee.Classifier.smileRandomForest(numberOfTrees=300, minLeafPopulation=2, seed=0).train(fc, "cls", bands))
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gte(50)
    return ee.Image(0).where(clf(Y2).eq(1), 2).where(clf(Y1).eq(1), 1).where(water, 0).unmask(0).toByte()
def mute(a): return a * 0.5 + 0.35 * a.mean(-1, keepdims=True)
def paint(a, m, col, al=0.85): a = a.copy(); a[m] = a[m] * (1 - al) + np.array(col) * al; return a
for r, bb in zoom.items():
    slug = r.split()[-1].lower()
    for y in (2019, 2025):
        if (P / f"{slug}_{y}.jpg").exists():              # frames are cached; delete them to refetch
            a = np.asarray(Image.open(P / f"{slug}_{y}.jpg").convert("RGB")).astype("f4"); continue
        for t in range(4):
            try: im, _ = fetch_frame(bb, y, 1200, "s2", 1, False); break
            except Exception as e:
                print("retry", t, e, flush=True)
                if t == 3: raise
        a = np.asarray(im.convert("RGB").resize((1200, 1080), Image.LANCZOS)).astype("f4")
        Image.fromarray(np.clip(a, 0, 255).astype("uint8")).save(P / f"{slug}_{y}.jpg", quality=88)
    cache = M / f"zoom_{slug}.npz"
    if cache.exists():
        z = np.load(cache); k, cell = z["k"], z["cell"]
    else:
        k = pixels(klass(ee.Geometry.Rectangle(list(bb))), bb, 1200, 1080, strip=216)
        cell = pixels(ee.Image(DRIVERS).select("classification").eq(2).unmask(0).toByte(), bb, 1200, 1080, strip=540)
        np.savez_compressed(cache, k=k, cell=cell)
    # Display only (the areas are label-adjusted). Inland water as for the Weda maps (label_expansion.py): JRC
    # occurrence >= 50 plus a 30 m strip. The muddy rivers running out of the mines are in neither JRC nor OSM (whose
    # channels don't follow them), and an MNDWI test flags bright mine ground instead, so thin open features are hidden
    # too: anything that does not survive a ~130 m morphological opening (rivers, and haul roads with them).
    from scipy.ndimage import binary_dilation, binary_opening
    wimg = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gte(50).toByte()
    water = binary_dilation(pixels(wimg, bb, 1200, 1080, strip=540).astype(bool), iterations=3)
    mapped = (k > 0) & (cell == 1) & ~water
    keep = binary_opening(mapped, iterations=6)
    Image.fromarray(((mapped & ~keep) * 255).astype("uint8")).save(M / f"zoom_{slug}_hidden.png")
    print(slug, "hidden share of mapped open+dist", round(1 - float(keep.sum()) / max(1, ((k > 0) & (cell == 1)).sum()), 3), flush=True)
    m = mute(a)
    m = paint(paint(m, (k == 2) & keep, NYALA), (k == 1) & keep, BARA)
    # outline the 1 km mining cells
    e = (cell == 1) & ~(np.roll(cell, 1, 0) == 1) | (cell == 1) & ~(np.roll(cell, 1, 1) == 1) | \
        (cell == 0) & (np.roll(cell, 1, 0) == 1) | (cell == 0) & (np.roll(cell, 1, 1) == 1)
    m[e] = (232, 235, 238)
    Image.fromarray(np.clip(m, 0, 255).astype("uint8")).save(P / f"{slug}_peta.jpg", quality=88)
    print("zoom", r, bb, flush=True)

# ------------------------------------------------------- example chips
ex = []
for want_map, want_lab in (("open", ("bare", "built")), ("disturbed", ("bare",)), ("disturbed", ("shrub",)), ("other", ("forest",))):
    k = next(k for k in sorted(pts) if pts[k]["map_class"] == want_map and lab.get(k) in want_lab)
    shutil.copy(M / f"check/chips/{k}_n.jpg", P / f"chip_{k}.jpg"); ex.append({"id": k, "peta": want_map, "label": lab[k]})
D["chips"] = ex
json.dump(D, open(V / "src/tambangData.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in D.items() if k != "kabupaten"}, ensure_ascii=False))
