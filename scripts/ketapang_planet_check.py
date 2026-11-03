#!/usr/bin/env python3
"""PlanetScope (3 m) check: was the land that burned in the four Ketapang
concessions planted with oil palm before the fire?

ketapang_fire_origin.py concluded from the 30 m Descals et al. (2024) palm map
(stopping at 2021) and Hansen GFC that 99.7% of the 2026 burn inside PT AM,
PT SKM, PT MKK and PT SPAS was not palm. Two things could make that wrong:
palm planted 2022-2026 (too young for the map's closed-canopy class), and
palm the map missed. At 3 m PlanetScope shows what is on the ground: palm
blocks have a regular crown texture, a planting-road and drain grid on a
~250-300 m block spacing, and a uniform deep-red tone in NIR false colour;
cleared land, fern and shrub do not.

SITES. For each concession the 2.5 x 2.5 km window with the most burned land
in each of two classes is picked from the 25 m stack:
    unplanted   burned, not palm, forest cleared since 2001 or non-forest
    forest      burned, not palm, mapped by Hansen as forest still standing
plus one CONTROL window on the concessions' own mapped palm that did not
burn, so planted palm is seen in the same imagery for comparison.

IMAGERY. One pre-fire scene (PRE window, before the July ignitions) and one
post-fire scene (POST window) per site: the clearest PSScene that covers the
whole window, 4-band surface reflectance, clipped by the Orders API so only
the window's km2 are billed. Searching is free; nothing is ordered without
--confirm.

    conda run -n base python scripts/ketapang_planet_check.py            # plan
    conda run -n base python scripts/ketapang_planet_check.py --confirm  # order
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
ORIGIN = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin")
OUT = os.path.join(ORIGIN, "planet")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import CONC, FOUR, CLASSES  # noqa: E402

WIN_KM = 2.5
PRE = ("2026-05-01", "2026-07-10")
PRE_WIDE = ("2026-02-01", "2026-07-10")
POST = ("2026-08-25", "2026-11-02")   # haze: few clear scenes after mid-Sep
# --history: earlier dry-season scenes for the unplanted windows. Most were
# cleared in 2015-2016 or 2019-2021 (Hansen); palm planted after that would
# show by 2023 as young palms in rows on bare ground, which 3 m resolves.
HISTORY = {"2023": ("2023-05-01", "2023-07-31"),
           "2025": ("2025-05-01", "2025-08-15")}
CLEAR_STEPS = (85, 70, 50)    # % of the scene clear (udm2), tried in turn;
                               # post-fire haze rarely clears to 85
UNPLANTED = (5, 6, 7)          # class indices in CLASSES
FOREST = (4,)
PALM = (0, 1, 2, 3)


def load():
    import geopandas as gpd
    import rasterio
    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as ds:
        lc, burned, tr = ds.read(1), ds.read(2).astype(bool), ds.transform
    conc = gpd.read_file(CONC).to_crs(4326)
    conc["geometry"] = conc.geometry.make_valid()
    rows = []
    for acr, name in FOUR.items():
        s = conc[conc.company.str.contains(name, case=False, na=False)]
        rows.append(s.iloc[0].to_dict() | {"acr": acr})
    return lc, burned, tr, gpd.GeoDataFrame(rows, crs=4326)


def pick_sites(lc, burned, tr, conc4):
    import numpy as np
    from rasterio import features
    from scipy import ndimage
    n = int(round(WIN_KM * 1000 / 25))
    sites = []
    taken = np.zeros(lc.shape, bool)

    def best(score, inside, tag, acr):
        frac_in = ndimage.uniform_filter(inside.astype(np.float32), n)
        s = ndimage.uniform_filter(score.astype(np.float32), n)
        s[(frac_in < 0.8) | ndimage.maximum_filter(taken, n)] = -1
        r, c = np.unravel_index(np.argmax(s), s.shape)
        if s[r, c] <= 0:
            return
        h = n // 2
        r0, r1, c0, c1 = r - h, r - h + n, c - h, c - h + n
        taken[r0:r1, c0:c1] = True
        w, nn = tr * (c0, r0)
        e, ss = tr * (c1, r1)
        win = (slice(r0, r1), slice(c0, c1))
        cls = lc[win]
        sites.append({
            "site": f"{acr.replace('PT ', '')}-{tag}", "concession": acr,
            "kind": tag, "bbox": [w, ss, e, nn],
            "score_frac": float(s[r, c]),
            "burned_frac": float(burned[win].mean()),
            "palm_frac_descals": float(np.isin(cls, PALM).mean()),
            "class_frac": {CLASSES[k]: float((cls == k).mean())
                           for k in range(len(CLASSES)) if (cls == k).any()},
        })

    for _, rr in conc4.iterrows():
        inside = features.rasterize([(rr.geometry, 1)], out_shape=lc.shape,
                                    transform=tr, dtype="uint8") > 0
        best(inside & burned & np.isin(lc, UNPLANTED), inside, "unplanted", rr.acr)
        best(inside & burned & np.isin(lc, FOREST), inside, "forest", rr.acr)
    # control: the concessions' largest unburned mapped-palm block
    inside4 = features.rasterize([(g, 1) for g in conc4.geometry],
                                 out_shape=lc.shape, transform=tr,
                                 dtype="uint8") > 0
    best(inside4 & ~burned & np.isin(lc, PALM), inside4, "control-palm",
         "PT FOUR")
    return sites


def search_any(bbox, windows, key):
    for win in windows:
        for mc in CLEAR_STEPS:
            c = search(bbox, win, key, mc)
            if c:
                return c
    return []


def search(bbox, window, key, min_clear):
    """Clearest PSScene in window that covers the whole bbox."""
    import requests
    from shapely.geometry import box, shape
    from earthchange.planet_backend import DATA_API, ITEM_TYPE, _bbox_geojson, _check
    filt = {"type": "AndFilter", "config": [
        {"type": "GeometryFilter", "field_name": "geometry",
         "config": _bbox_geojson(bbox)},
        {"type": "DateRangeFilter", "field_name": "acquired",
         "config": {"gte": window[0] + "T00:00:00Z",
                    "lte": window[1] + "T23:59:59Z"}},
        {"type": "RangeFilter", "field_name": "clear_percent",
         "config": {"gte": min_clear}},
        {"type": "PermissionFilter", "config": ["assets:download"]},
    ]}
    r = requests.post(f"{DATA_API}/quick-search?_page_size=250", auth=(key, ""),
                      json={"item_types": [ITEM_TYPE], "filter": filt},
                      timeout=90)
    _check(r)
    b = box(*bbox)
    out = []
    for f in r.json().get("features", []):
        if not shape(f["geometry"]).buffer(0).contains(b):
            continue
        p = f["properties"]
        out.append({"id": f["id"], "acquired": p["acquired"][:16],
                    "clear": p.get("clear_percent"),
                    "cloud": p.get("cloud_cover"),
                    "instrument": p.get("instrument")})
    out.sort(key=lambda d: (-(d["clear"] or 0), d["acquired"]))
    return out


def km2(bbox):
    from earthchange.planet_backend import _bbox_km2
    return _bbox_km2(bbox)


# ------------------------------- render ---------------------------------
def _stretch(a, lo=2, hi=98):
    import numpy as np
    v = a[np.isfinite(a) & (a > 0)]
    if not v.size:
        return np.zeros_like(a)
    p0, p1 = np.percentile(v, [lo, hi])
    return np.clip((a - p0) / (p1 - p0 + 1e-9), 0, 1)


def rgb(a, bands=(2, 1, 0)):
    """One gain for all three bands (keeps hue honest), set on cloud-free
    pixels: SR blue above 0.12 is cloud or haze over this landscape."""
    import numpy as np
    x = np.dstack([a[b] for b in bands])
    clear = np.isfinite(a[0]) & (a[0] < 1200)
    if clear.sum() < 1000:
        clear = np.isfinite(a[0])
    v = x[clear]
    lo = np.percentile(v, 1)
    hi = np.percentile(v, 99.5)
    return np.clip((x - lo) / (hi - lo + 1e-9), 0, 1) ** 0.8


def read_ps(path):
    import numpy as np
    import rasterio
    with rasterio.open(path) as ds:
        a = ds.read().astype(np.float32)
        a[:, (a <= 0).all(0)] = np.nan       # PS SR fills outside the clip with 0
        return a, ds.transform, ds.crs, ds.bounds


def overlay(path_ps, lc, burned, tr25):
    """Burned and Descals-palm masks warped onto the PlanetScope grid."""
    import numpy as np
    from rasterio.warp import reproject, Resampling
    import rasterio
    with rasterio.open(path_ps) as ds:
        shp, dtr, dcrs = (ds.height, ds.width), ds.transform, ds.crs
    out = {}
    for name, arr in (("burned", burned.astype(np.uint8)),
                      ("palm", np.isin(lc, PALM).astype(np.uint8))):
        dst = np.zeros(shp, np.uint8)
        reproject(arr, dst, src_transform=tr25, src_crs="EPSG:4326",
                  dst_transform=dtr, dst_crs=dcrs, resampling=Resampling.nearest)
        out[name] = dst.astype(bool)
    return out


def render_site(site, pre, post, lc, burned, tr25, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D

    panels = []
    for tag, p in (("pre", pre), ("post", post)):
        if p and os.path.exists(p["tif"]):
            a, *_ = read_ps(p["tif"])
            b, g, r, nir = a[0], a[1], a[2], a[3]
            tc = rgb(a, (2, 1, 0))
            fc = np.dstack([_stretch(nir), _stretch(r), _stretch(g)])
            ndvi = (nir - r) / (nir + r + 1e-9)
            ov = overlay(p["tif"], lc, burned, tr25)
            panels.append((tag, p, tc, fc, ndvi, ov))
    if not panels:
        return None
    fig, axes = plt.subplots(len(panels), 2, figsize=(12, 6.2 * len(panels)),
                             dpi=150, squeeze=False)
    stats = {}
    for row, (tag, p, tc, fc, ndvi, ov) in zip(axes, panels):
        for ax, img, lab in ((row[0], tc, "true colour"),
                             (row[1], fc, "NIR false colour (veg. red)")):
            ax.imshow(img, interpolation="nearest")
            ax.contour(ov["burned"].astype(float), levels=[0.5],
                       colors="#ffd400", linewidths=0.7)
            ax.contour(ov["palm"].astype(float), levels=[0.5],
                       colors="#00e5ff", linewidths=0.7)
            ax.set_title(f"{tag}-fire  {p['acquired'][:10]}  ·  {lab}",
                         fontsize=10, loc="left")
            ax.set_xticks([])
            ax.set_yticks([])
        ok = np.isfinite(ndvi)
        stats[tag] = {
            "date": p["acquired"][:10],
            "ndvi_mean": float(np.nanmean(ndvi)),
            "ndvi_burned_mean": float(np.nanmean(ndvi[ov["burned"] & ok]))
            if (ov["burned"] & ok).any() else None,
            "ndvi_burned_std": float(np.nanstd(ndvi[ov["burned"] & ok]))
            if (ov["burned"] & ok).any() else None,
        }
    fig.legend(handles=[
        Line2D([], [], color="#ffd400", lw=1.5,
               label="burned Jul–Oct 2026 (Sentinel-2 dNBR, 25 m)"),
        Line2D([], [], color="#00e5ff", lw=1.5,
               label="mapped oil palm (Descals et al. 2024, to 2021)")],
        loc="lower center", ncol=2, fontsize=9, frameon=False)
    fig.suptitle(f"{site['concession']} · {site['kind']} window "
                 f"({WIN_KM} × {WIN_KM} km) · PlanetScope 3 m",
                 x=0.01, ha="left", fontsize=13, weight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")
    return stats


def render_sheet(sites, path):
    """Pre-fire true colour of every site, one row, same scale."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    have = [s for s in sites if s.get("pre") and os.path.exists(s["pre"]["tif"])]
    if not have:
        return
    cols = 3
    rows = int(np.ceil(len(have) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 5.3 * rows),
                             dpi=150, squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, s in zip(axes.ravel(), have):
        a, *_ = read_ps(s["pre"]["tif"])
        ax.imshow(rgb(a), interpolation="nearest")
        ax.set_title(f"{s['concession']} · {s['kind']}\npre-fire "
                     f"{s['pre']['acquired'][:10]} · Descals palm "
                     f"{100 * s['palm_frac_descals']:.0f}%", fontsize=9,
                     loc="left")
    fig.suptitle("Before the fire: PlanetScope 3 m true colour, "
                 f"{WIN_KM} km windows", x=0.01, ha="left", fontsize=13,
                 weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirm", action="store_true",
                    help="order and download (spends Planet quota)")
    ap.add_argument("--history", action="store_true",
                    help="earlier scenes (HISTORY) for the unplanted windows")
    ap.add_argument("--render-only", action="store_true",
                    help="re-draw from plan.json and the downloaded scenes")
    ap.add_argument("--planet-key", default=None)
    a = ap.parse_args()

    from earthchange.planet_backend import (_key, _order_clip, _wait_order,
                                            _download_sr)
    key = _key(a.planet_key)
    os.makedirs(OUT, exist_ok=True)
    lc, burned, tr25, conc4 = load()
    plan_path = os.path.join(OUT, "plan.json")
    if a.render_only or a.history:
        with open(plan_path) as f:
            sites = json.load(f)
    if a.history:
        return history(sites, key, a.confirm, plan_path)
    if a.render_only:
        return render_all(sites, lc, burned, tr25, plan_path)
    sites = pick_sites(lc, burned, tr25, conc4)
    total = 0.0
    for s in sites:
        for tag, wins in (("pre", (PRE, PRE_WIDE)), ("post", (POST,))):
            c = search_any(s["bbox"], wins, key)
            s[f"{tag}_candidates"] = c[:5]
            s[tag] = c[0] if c else None
            if s[tag]:
                s[tag]["tif"] = os.path.join(OUT, f"{s['site']}_{tag}.tif")
                total += km2(s["bbox"])
        pre, post = s["pre"], s["post"]
        print(f"{s['site']:<18} burned {100 * s['burned_frac']:3.0f}%  "
              f"palm(map) {100 * s['palm_frac_descals']:3.0f}%  "
              f"pre {pre['acquired'][:10] + ' clear ' + str(pre['clear']) if pre else '—':<22} "
              f"post {post['acquired'][:10] + ' clear ' + str(post['clear']) if post else '—'}")
    with open(plan_path, "w") as f:
        json.dump(sites, f, indent=2)
    print(f"\n{len(sites)} sites; estimated quota for the clipped orders: "
          f"{total:.0f} km²  (plan: {plan_path})")
    if not a.confirm:
        print("DRY RUN: nothing ordered. Re-run with --confirm.")
        return

    pending = []
    for s in sites:                    # submit everything, then wait
        for tag in ("pre", "post"):
            p = s[tag]
            if not p or os.path.exists(p["tif"]):
                continue
            print(f"ordering {s['site']} {tag} {p['id']} ...")
            p["order"] = _order_clip(p["id"], s["bbox"], key,
                                     f"ketapang_{s['site']}_{tag}")
            pending.append(p)
    with open(plan_path, "w") as f:
        json.dump(sites, f, indent=2)       # order ids survive a crash
    for p in pending:
        _download_sr(_wait_order(p["order"], key), p["tif"], key)
        print(f"  saved {os.path.basename(p['tif'])}")
    render_all(sites, lc, burned, tr25, plan_path)


def history(sites, key, confirm, plan_path):
    from earthchange.planet_backend import _order_clip, _wait_order, _download_sr
    todo, total = [], 0.0
    for s in sites:
        if s["kind"] != "unplanted":
            continue
        s.setdefault("history", {})
        for yr, win in HISTORY.items():
            prev = s["history"].get(yr)
            if prev and prev.get("order"):      # already ordered: never re-order
                p = prev
            else:
                c = search_any(s["bbox"], (win,), key)
                p = c[0] if c else None
            if p:
                p["tif"] = os.path.join(OUT, f"{s['site']}_{yr}.tif")
                total += km2(s["bbox"])
                todo.append((s, p))
            s["history"][yr] = p
            print(f"{s['site']:<16} {yr}: "
                  f"{p['acquired'][:10] + ' clear ' + str(p['clear']) if p else '—'}")
    print(f"history: {len(todo)} scenes, ≈{total:.0f} km²")
    if not confirm:
        print("DRY RUN: nothing ordered. Re-run with --history --confirm.")
        return
    for s, p in todo:
        if not os.path.exists(p["tif"]) and not p.get("order"):
            p["order"] = _order_clip(p["id"], s["bbox"], key,
                                     f"ketapang_{s['site']}_{p['acquired'][:4]}")
    with open(plan_path, "w") as f:
        json.dump(sites, f, indent=2)
    for s, p in todo:
        if not os.path.exists(p["tif"]):
            _download_sr(_wait_order(p["order"], key), p["tif"], key)
            print(f"  saved {os.path.basename(p['tif'])}")
    render_history(sites)


def render_history(sites):
    """Each unplanted window through time, beside the palm control (pre-fire)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ctrl = next(s for s in sites if s["kind"] == "control-palm")
    rows = [s for s in sites if s["kind"] == "unplanted"]
    cols = [("2023", lambda s: s["history"].get("2023")),
            ("2025", lambda s: s["history"].get("2025")),
            ("pre-fire 2026", lambda s: s["pre"]),
            ("after the fire", lambda s: s["post"])]
    fig, axes = plt.subplots(len(rows) + 1, len(cols),
                             figsize=(4.2 * len(cols), 4.4 * (len(rows) + 1)),
                             dpi=150, squeeze=False)
    for i, s in enumerate(rows + [ctrl]):
        for j, (lab, get) in enumerate(cols):
            ax = axes[i, j]
            ax.set_xticks([])
            ax.set_yticks([])
            p = get(s) if s is not ctrl or lab == "pre-fire 2026" else None
            if not p or not os.path.exists(p.get("tif", "")):
                ax.axis("off")
                continue
            a, *_ = read_ps(p["tif"])
            ax.imshow(rgb(a), interpolation="nearest")
            ax.set_title(f"{s['concession']} · {s['kind']}\n{lab}  "
                         f"{p['acquired'][:10]}", fontsize=8.5, loc="left")
    fig.suptitle("Unplanted windows through time, and planted palm for "
                 f"comparison (PlanetScope 3 m, {WIN_KM} km)", x=0.01,
                 ha="left", fontsize=13, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    p = os.path.join(OUT, "history_unplanted.png")
    fig.savefig(p)
    plt.close(fig)
    print(f"Saved: {p}")


def render_all(sites, lc, burned, tr25, plan_path):
    results = {}
    for s in sites:
        st = render_site(s, s["pre"], s["post"], lc, burned, tr25,
                         os.path.join(OUT, f"{s['site']}.png"))
        results[s["site"]] = {k: s[k] for k in ("concession", "kind", "bbox",
                                                "burned_frac",
                                                "palm_frac_descals")} | {
            "pre": s["pre"] and {k: s["pre"][k] for k in ("id", "acquired",
                                                          "clear")},
            "post": s["post"] and {k: s["post"][k] for k in ("id", "acquired",
                                                             "clear")},
            "ndvi": st}
    render_sheet(sites, os.path.join(OUT, "contact_sheet_prefire.png"))
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    with open(plan_path, "w") as f:
        json.dump(sites, f, indent=2)


if __name__ == "__main__":
    main()
