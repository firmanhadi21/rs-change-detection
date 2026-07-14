#!/usr/bin/env python3
"""PlanetScope close-up backend (Data + Orders API) for the hybrid workflow.

GHSL/Landsat (free, wide) locate the most-changed hotspot; this fetches a small,
quota-cheap PlanetScope close-up there. PlanetScope daily scenes are 4-band
(Blue/Green/Red/NIR) surface reflectance, so NDVI works at ~3 m — unlike the
RGB-only visual basemaps.

Quota safety: search is FREE (spends nothing). Nothing is ordered/downloaded
until you pass confirm=True. A clipped Orders API job only bills the small AOI
(~box_km²), not whole scenes.

Auth: PLANET_API_KEY env var or an explicit key. Never printed.

Needs: requests (already a dependency), rasterio, numpy, matplotlib.
"""

import os
import time
import calendar

# Clear a stale external PROJ override (e.g. an OTB install exporting PROJ_LIB)
# so rasterio uses its OWN bundled PROJ database (see mapmaker.py / mpc_backend.py).
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import requests

DATA_API = "https://api.planet.com/data/v1"
ORDERS_API = "https://api.planet.com/compute/ops/orders/v2"
ITEM_TYPE = "PSScene"
BUNDLE = "analytic_sr_udm2"   # 4-band surface reflectance + usable-data mask


KEY_FILES = ("~/.planet.json", "~/planet.conf", "~/.config/planet.json",
             "~/.config/planet.conf")


def _read_key_file(path):
    """Extract a Planet API key from a JSON ({"key"/"api_key": …}) or INI file."""
    if not os.path.exists(path):
        return None
    txt = open(path).read().strip()
    try:
        import json
        d = json.loads(txt)
        if isinstance(d, dict):
            return d.get("key") or d.get("api_key")
    except Exception:  # noqa: BLE001 — not JSON, try INI/key=value
        pass
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() in ("api_key", "key"):
            return v.strip().strip('"').strip("'")
    return None


def _key(explicit=None):
    """Resolve the Planet API key: explicit value/path, env, then key files.

    Priority: --planet-key (value or file path) > $PLANET_API_KEY > ~/.planet.json,
    ~/planet.conf, ~/.config/planet.{json,conf}. Never printed or transmitted to us.
    """
    if explicit:
        return _read_key_file(os.path.expanduser(explicit)) or explicit
    if os.environ.get("PLANET_API_KEY"):
        return os.environ["PLANET_API_KEY"]
    for path in KEY_FILES:
        k = _read_key_file(os.path.expanduser(path))
        if k:
            return k
    raise SystemExit(
        "PlanetScope needs an API key. Provide it any of these ways:\n"
        "  export PLANET_API_KEY=your_key\n"
        "  --planet-key your_key   (or a path to a JSON/INI key file)\n"
        "  a key file at ~/.planet.json or ~/planet.conf  ({\"key\": \"…\"}).")


def _month_window(ym):
    """'2018-07' -> ('2018-07-01T00:00:00Z', '2018-07-31T23:59:59Z')."""
    y, m = (int(x) for x in ym.split("-"))
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01T00:00:00Z", f"{y:04d}-{m:02d}-{last:02d}T23:59:59Z"


def _check(r):
    """Raise an actionable error (with Planet's response body) on HTTP failure."""
    if r.status_code >= 400:
        raise SystemExit(f"Planet API {r.status_code} at {r.url}: {r.text[:300]}")
    return r


def _bbox_geojson(bbox):
    w, s, e, n = bbox
    return {"type": "Polygon",
            "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def _bbox_km2(bbox):
    import math
    w, s, e, n = bbox
    midlat = (s + n) / 2.0
    return abs(e - w) * 111.32 * math.cos(math.radians(midlat)) * abs(n - s) * 110.57


def search_scenes(bbox, ym, key, cloud_max=0.1):
    """Data API quick-search for downloadable PSScenes over bbox in month `ym`.

    FREE — searching spends no quota. Returns candidates sorted by cloud cover.
    """
    start, end = _month_window(ym)
    filt = {"type": "AndFilter", "config": [
        {"type": "GeometryFilter", "field_name": "geometry", "config": _bbox_geojson(bbox)},
        {"type": "DateRangeFilter", "field_name": "acquired", "config": {"gte": start, "lte": end}},
        {"type": "RangeFilter", "field_name": "cloud_cover", "config": {"lte": cloud_max}},
        {"type": "PermissionFilter", "config": ["assets:download"]},
    ]}
    r = requests.post(f"{DATA_API}/quick-search", auth=(key, ""),
                      json={"item_types": [ITEM_TYPE], "filter": filt}, timeout=90)
    _check(r)
    out = []
    for f in r.json().get("features", []):
        p = f["properties"]
        out.append({"id": f["id"], "acquired": p.get("acquired", "")[:10],
                    "cloud": round(p.get("cloud_cover", 0) or 0, 3),
                    "instrument": p.get("instrument", "")})
    out.sort(key=lambda d: d["cloud"])
    return out


def _order_clip(item_id, bbox, key, name):
    body = {"name": name,
            "products": [{"item_ids": [item_id], "item_type": ITEM_TYPE,
                          "product_bundle": BUNDLE}],
            "tools": [{"clip": {"aoi": _bbox_geojson(bbox)}}]}
    r = requests.post(ORDERS_API, auth=(key, ""), json=body, timeout=90)
    _check(r)
    return r.json()["id"]


def _wait_order(order_id, key, poll=15, timeout=2400):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(f"{ORDERS_API}/{order_id}", auth=(key, ""), timeout=60)
        _check(r)
        j = r.json()
        state = j.get("state")
        if state in ("success", "partial"):
            return j
        if state == "failed":
            raise SystemExit(f"Planet order {order_id} failed: {j.get('last_message')}")
        print(f"  order {order_id[:8]}… {state}; waiting…")
        time.sleep(poll)
    raise SystemExit(f"Planet order {order_id} timed out after {timeout}s.")


def _download_sr(order_json, out_path, key):
    """Download the clipped surface-reflectance GeoTIFF from a finished order."""
    results = order_json.get("_links", {}).get("results", [])
    loc = next((r["location"] for r in results
                if r.get("name", "").endswith(".tif")
                and ("SR" in r["name"] or "AnalyticMS" in r["name"])), None)
    if loc is None:  # fall back to the first tif
        loc = next((r["location"] for r in results if r.get("name", "").endswith(".tif")), None)
    if loc is None:
        raise SystemExit("No GeoTIFF found in the Planet order results.")
    with requests.get(loc, stream=True, timeout=300) as resp:
        _check(resp)
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    return out_path


# --------------------------- analysis + render ---------------------------
def _red_nir(a):
    """(red, nir) bands regardless of Dove (4-band) or SuperDove (8-band) SR."""
    return (a[5], a[7]) if a.shape[0] >= 8 else (a[2], a[3])


def _rgb_idx(a):
    return (5, 3, 1) if a.shape[0] >= 8 else (2, 1, 0)


def _ndvi(a):
    import numpy as np
    red, nir = _red_nir(a)
    red, nir = red.astype("float32"), nir.astype("float32")
    denom = nir + red
    return np.where(denom > 0, (nir - red) / (denom + 1e-6), np.nan)


def _truecolor(a):
    import numpy as np
    ri, gi, bi = _rgb_idx(a)
    rgb = np.dstack([a[ri], a[gi], a[bi]]).astype("float32")
    valid = rgb.sum(axis=2) > 0
    v = rgb[valid] if valid.any() else rgb.reshape(-1, 3)
    lo, hi = np.nanpercentile(v, 2), np.nanpercentile(v, 98)
    out = np.clip((rgb - lo) / max(hi - lo, 1e-6), 0, 1)
    out[~valid] = 1.0  # white where a scene doesn't cover the cell
    return out


def analyze_and_render(pre_tif, post_tif, run_dir, name, meta):
    """NDVI before/after + true-color + a close-up infographic. Offline (no Planet).

    The two scenes rarely share a pixel grid (different footprints, and Dove vs
    SuperDove), so `post` is reprojected onto `pre`'s grid before differencing.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with rasterio.open(pre_tif) as sp:
        pre = sp.read().astype("float32")
        dst_crs, dst_tr, H, W = sp.crs, sp.transform, sp.height, sp.width
    with rasterio.open(post_tif) as sq:
        src = sq.read().astype("float32")
        post = np.zeros((src.shape[0], H, W), "float32")
        for b in range(src.shape[0]):
            reproject(src[b], post[b], src_transform=sq.transform, src_crs=sq.crs,
                      dst_transform=dst_tr, dst_crs=dst_crs, resampling=Resampling.bilinear)

    nd_pre, nd_post = _ndvi(pre), _ndvi(post)
    dnd = nd_post - nd_pre
    veg_pre = np.isfinite(nd_pre) & (nd_pre > 0.3)
    loss = veg_pre & (dnd < -0.2)
    valid = max(int(np.isfinite(nd_pre).sum()), 1)
    stats = {**meta,
             "mean_ndvi_pre": round(float(np.nanmean(nd_pre)), 3),
             "mean_ndvi_post": round(float(np.nanmean(nd_post)), 3),
             "veg_lost_pct": round(100.0 * int(loss.sum()) / valid, 1),
             "resolution_m": 3}

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.4), dpi=140)
    axes[0].imshow(_truecolor(pre)); axes[0].set_title(f"True colour · {meta.get('pre_date','pre')}")
    axes[1].imshow(_truecolor(post)); axes[1].set_title(f"True colour · {meta.get('post_date','post')}")
    im = axes[2].imshow(dnd, cmap="RdYlGn", vmin=-0.6, vmax=0.6)
    axes[2].set_title("ΔNDVI (red = vegetation lost)")
    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=axes[2], fraction=0.046, pad=0.04)
    fig.suptitle(f"PlanetScope close-up (~3 m) — {name}  ·  "
                 f"vegetation lost {stats['veg_lost_pct']:.1f}%", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(os.path.join(run_dir, "planet_closeup.png"), facecolor="white")
    fig.savefig(os.path.join(run_dir, "planet_closeup.pdf"), facecolor="white")
    plt.close(fig)
    print(f"Planet close-up: planet_closeup.png/.pdf  (veg lost {stats['veg_lost_pct']:.1f}%)")
    return stats


# ------------------------------- orchestration -------------------------------
def run_closeup(bbox, hotspot, pre_month, post_month, run_dir, name,
                key=None, confirm=False, cloud_max=0.1, quota_km2=None):
    """Hybrid PlanetScope close-up. Dry-run (search + quota) unless confirm=True."""
    key = _key(key)
    area = _bbox_km2(bbox)
    print(f"\nPlanetScope close-up @ hotspot {hotspot['lat']}, {hotspot['lon']}  "
          f"(box ≈ {area:.0f} km²)")
    picks = {}
    for tag, ym in (("pre", pre_month), ("post", post_month)):
        cands = search_scenes(bbox, ym, key, cloud_max)
        print(f"  {tag} {ym}: {len(cands)} downloadable scene(s) ≤{int(cloud_max*100)}% cloud")
        for c in cands[:3]:
            print(f"      {c['acquired']}  cloud {c['cloud']*100:4.1f}%  {c['id']}")
        if not cands:
            raise SystemExit(f"No PlanetScope scenes for {tag} {ym} over the hotspot "
                             f"(≤{int(cloud_max*100)}% cloud). Widen the month or cloud limit.")
        picks[tag] = cands[0]

    cost = area * 2
    print(f"\nEstimated quota to fetch both (clipped): ≈ {cost:.0f} km²"
          + (f"  of your {quota_km2:.0f} km²/month" if quota_km2 else ""))
    if not confirm:
        print("DRY RUN — nothing ordered. Re-run with --planet-confirm to order & download.")
        return {"dry_run": True, "hotspot": hotspot,
                "pre": picks["pre"], "post": picks["post"], "est_quota_km2": round(cost, 1)}

    tifs = {}
    for tag in ("pre", "post"):
        print(f"  ordering {tag} scene {picks[tag]['id']} (clipped)…")
        oid = _order_clip(picks[tag]["id"], bbox, key, f"satchange_{name}_{tag}")
        oj = _wait_order(oid, key)
        tifs[tag] = _download_sr(oj, os.path.join(run_dir, f"planet_{tag}.tif"), key)
        print(f"    saved {os.path.basename(tifs[tag])}")

    meta = {"hotspot": hotspot, "pre_date": picks["pre"]["acquired"],
            "post_date": picks["post"]["acquired"],
            "pre_cloud": picks["pre"]["cloud"], "post_cloud": picks["post"]["cloud"]}
    stats = analyze_and_render(tifs["pre"], tifs["post"], run_dir, name, meta)
    return {"dry_run": False, **stats}
