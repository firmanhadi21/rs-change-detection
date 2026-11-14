#!/usr/bin/env python3
"""Sentinel-1 change scored against each pixel's own history (flash floods, slides).

A fixed dB threshold on one before/after pair (the `disturbance` scenario) is
blind to where a pixel normally swings: a terraced paddy or a river bar moves
several dB between any two passes, a closed forest hardly at all. This tests
the event pair against the same pixel's earlier pairs on the same track:

    z_pol  = (event change - mean of control changes) / SD of control changes
    zc     = (z_VV + z_VH) / sqrt(2)
    flag   = zc < --z-thr (default -2.5) and both VV and VH dropped by more
             than --drop-db (default 2 dB), in patches of >= --min-px pixels
    severe = zc < -4

The same test is then applied to the last control pair, scored against the
remaining controls, so every run reports its own false-alarm level next to the
event result. A flag density several times the control density is the signal;
a similar density is noise.

Two ways in:
  * --backend gee: Earth Engine S1 GRD (sigma0, dB), via the `disturbance`
    scenario with --history N (scenarios.run_disturbance).
  * --backend cdse: Copernicus Data Space, for when Earth Engine has not yet
    ingested the newest pass (it can lag a day or more). Scenes are found in
    the public OData catalogue; terrain-flattened gamma0 (Lee 5x5, Copernicus
    DEM 30) comes from the Sentinel Hub Process API and needs an OAuth client
    in CDSE_CLIENT_ID / CDSE_CLIENT_SECRET (environment or ./.env). The
    credentials are read, never printed.

Outputs (cdse): s1/<date>.tif, dem.tif, history_flags.tif (1 flagged, 2 severe),
history_flags.geojson, history_map.png, stats.json.
"""

import datetime as dt
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
MAX_PX = 2500                     # Process API limit per side


# ----------------------------- pure analysis (testable) -----------------------------
def to_db(a):
    return 10.0 * np.log10(np.clip(a, 1e-5, None))


def history_z(vv_db, vh_db):
    """Stacks (T, H, W) in dB, oldest first; the last pair is the event.

    Returns dict with zc (combined z of the event pair), dvv, dvh (event change)
    and n_control. Needs at least 3 control pairs (T >= 5) for a usable SD.
    """
    vv_db, vh_db = np.asarray(vv_db, "f4"), np.asarray(vh_db, "f4")
    if vv_db.shape[0] < 5:
        raise ValueError(f"need >= 5 dates (3 control pairs + event), got {vv_db.shape[0]}")
    dvv, dvh = np.diff(vv_db, axis=0), np.diff(vh_db, axis=0)
    return _score(dvv[:-1], dvh[:-1], dvv[-1], dvh[-1])


def _score(cvv, cvh, evv, evh):
    z = []
    for c, e in ((cvv, evv), (cvh, evh)):
        mu = c.mean(0)
        sd = np.maximum(c.std(0, ddof=1), 0.3)      # floor: a near-constant pixel is not infinitely sure
        z.append((e - mu) / sd)
    return {"zc": (z[0] + z[1]) / math.sqrt(2), "dvv": evv, "dvh": evh, "n_control": cvv.shape[0]}


def control_z(vv_db, vh_db):
    """The same score for the last control pair against the earlier controls."""
    dvv, dvh = np.diff(np.asarray(vv_db, "f4"), axis=0), np.diff(np.asarray(vh_db, "f4"), axis=0)
    return _score(dvv[:-2], dvh[:-2], dvv[-2], dvh[-2])


def flag(score, valid=None, z_thr=-2.5, drop_db=2.0, min_px=10, severe_z=-4.0):
    """Graded uint8 array: 0 none, 1 flagged, 2 severe; small patches removed."""
    from scipy import ndimage as ndi
    m = (score["zc"] < z_thr) & (score["dvv"] < -drop_db) & (score["dvh"] < -drop_db)
    if valid is not None:
        m &= valid
    lab, n = ndi.label(m)
    if n:
        sz = ndi.sum(m, lab, range(1, n + 1))
        m = np.isin(lab, 1 + np.flatnonzero(sz >= min_px))
    out = m.astype("uint8")
    out[m & (score["zc"] < severe_z)] = 2
    return out


def valley_floor(dem, slope, px, max_slope=8.0, max_rise=15.0, window_m=500, bank_m=50):
    """Valley floors: gentle slope and within `max_rise` m of the lowest ground in
    a `window_m` neighbourhood, widened by `bank_m` for the banks. Floods and
    their deposits live here; a flash-flood signal should be dense here and
    sparse on the hillsides."""
    from scipy import ndimage as ndi
    size = max(3, int(window_m / px))
    v = (slope < max_slope) & (dem - ndi.minimum_filter(dem, size=size) < max_rise)
    v = ndi.binary_opening(v, iterations=2)
    return ndi.binary_dilation(v, iterations=max(1, int(bank_m / px)))


def terrain_split(g_ev, g_ct, valley, hills):
    """Flag density (%) on valley floors and hillsides, event vs control."""
    pct = lambda g, m: round(100 * float(((g > 0) & m).sum()) / max(int(m.sum()), 1), 3)  # noqa: E731
    out = {"valley_floor": {"event_pct": pct(g_ev, valley), "control_pct": pct(g_ct, valley)},
           "hillside": {"event_pct": pct(g_ev, hills), "control_pct": pct(g_ct, hills)}}
    for v in out.values():
        v["ratio"] = round(v["event_pct"] / v["control_pct"], 1) if v["control_pct"] else None
    return out


def same_track(scenes, ref=None):
    """Dates on the reference scene's track. `scenes` are dicts with date (YYYY-MM-DD),
    direction and rel_orbit; the reference defaults to the newest scene."""
    if not scenes:
        return None, []
    ref = ref or max(scenes, key=lambda s: s["date"])
    dates = sorted({s["date"] for s in scenes
                    if s["direction"] == ref["direction"] and s["rel_orbit"] == ref["rel_orbit"]})
    return ref, dates


def utm_epsg(lon, lat):
    return (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1


# ----------------------------- CDSE client -----------------------------
def _creds():
    cid, sec = os.environ.get("CDSE_CLIENT_ID"), os.environ.get("CDSE_CLIENT_SECRET")
    if not (cid and sec) and os.path.exists(".env"):
        for line in open(".env"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k.strip() == "CDSE_CLIENT_ID" and not cid:
                    cid = v
                if k.strip() == "CDSE_CLIENT_SECRET" and not sec:
                    sec = v
    if not (cid and sec):
        raise SystemExit("CDSE backend needs CDSE_CLIENT_ID and CDSE_CLIENT_SECRET (environment "
                         "or ./.env): an OAuth client from the Copernicus Data Space dashboard.")
    return cid, sec


def token():
    cid, sec = _creds()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid,
                                   "client_secret": sec}).encode()
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body),
                                                timeout=60))["access_token"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"CDSE token request refused (HTTP {e.code}); the client may have "
                         "expired. Create a new one in the CDSE dashboard.")


def search_s1(lon, lat, start, end):
    """IW GRD scenes over a point, from the public OData catalogue (no login)."""
    q = {"$filter": ("Collection/Name eq 'SENTINEL-1' and contains(Name,'_IW_GRDH_') and "
                     f"OData.CSC.Intersects(area=geography'SRID=4326;POINT({lon} {lat})') and "
                     f"ContentDate/Start gt {start}T00:00:00.000Z and "
                     f"ContentDate/Start lt {end}T23:59:59.999Z"),
         "$orderby": "ContentDate/Start asc", "$top": "1000", "$expand": "Attributes"}
    url = ODATA_URL + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    data = json.load(urllib.request.urlopen(url, timeout=120))
    out = []
    for p in data.get("value", []):
        a = {x["Name"]: x.get("Value") for x in p.get("Attributes", [])}
        out.append({"date": p["ContentDate"]["Start"][:10], "time": p["ContentDate"]["Start"][11:16],
                    "direction": a.get("orbitDirection"), "rel_orbit": a.get("relativeOrbitNumber"),
                    "name": p["Name"]})
    return out


def _post(tok, body, path):
    req = urllib.request.Request(PROCESS_URL, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json", "Accept": "image/tiff"})
    try:
        data = urllib.request.urlopen(req, timeout=300).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Process API HTTP {e.code}: {e.read().decode()[:200]}")
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)


_S1_EVAL = """//VERSION=3
function setup(){return {input:["VV","VH","dataMask"],output:{bands:3,sampleType:"FLOAT32"}};}
function evaluatePixel(s){return [s.VV,s.VH,s.dataMask];}"""
_DEM_EVAL = """//VERSION=3
function setup(){return {input:["DEM"],output:{bands:1,sampleType:"FLOAT32"}};}
function evaluatePixel(s){return [s.DEM];}"""


def fetch_s1(tok, bounds, size, date, direction, path):
    body = {"input": {"bounds": bounds, "data": [{"type": "sentinel-1-grd", "dataFilter": {
        "timeRange": {"from": f"{date}T00:00:00Z", "to": f"{date}T23:59:59Z"},
        "acquisitionMode": "IW", "polarization": "DV", "orbitDirection": direction.upper(),
        "resolution": "HIGH"},
        "processing": {"backCoeff": "GAMMA0_TERRAIN", "orthorectify": True,
                       "demInstance": "COPERNICUS_30",
                       "speckleFilter": {"type": "LEE", "windowSizeX": 5, "windowSizeY": 5}}}]},
        "output": {"width": size, "height": size,
                   "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": _S1_EVAL}
    _post(tok, body, path)


def fetch_dem(tok, bounds, size, path):
    body = {"input": {"bounds": bounds, "data": [{"type": "dem",
                                                   "dataFilter": {"demInstance": "COPERNICUS_30"}}]},
            "output": {"width": size, "height": size,
                       "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
            "evalscript": _DEM_EVAL}
    _post(tok, body, path)


# ----------------------------- run (cdse backend) -----------------------------
def run_cdse(lat, lon, radius, name, run_dir, run_id, post=None, history=20,
             res=10.0, z_thr=-2.5, drop_db=2.0, min_ha=0.1):
    """Event = newest pass on the newest track inside --post (default: the last
    10 days); controls = the `history` previous passes on that track."""
    import rasterio
    from pyproj import Transformer
    today = dt.date.today()
    p0, p1 = post or ((today - dt.timedelta(days=10)).isoformat(), today.isoformat())
    recent = search_s1(lon, lat, p0, p1)
    if not recent:
        raise SystemExit(f"No Sentinel-1 IW GRD pass over {lat:.4f},{lon:.4f} in {p0}..{p1} "
                         "in the CDSE catalogue.")
    ref, _ = same_track(recent)
    back = (dt.date.fromisoformat(ref["date"]) - dt.timedelta(days=12 * (history + 2))).isoformat()
    _, dates = same_track(search_s1(lon, lat, back, ref["date"]), ref)
    dates = [d for d in dates if d <= ref["date"]][-(history + 2):]
    if len(dates) < 5:
        raise SystemExit(f"Only {len(dates)} passes on track {ref['direction']} {ref['rel_orbit']}: "
                         "need at least 5 (3 control pairs + the event pair).")
    print(f"Track {ref['direction'].lower()} rel. orbit {ref['rel_orbit']}: event "
          f"{dates[-2]} -> {dates[-1]}, {len(dates) - 2} control pairs from {dates[0]}")

    epsg = utm_epsg(lon, lat)
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    half = radius * 1000
    size = min(MAX_PX, int(round(2 * half / res)))
    bounds = {"bbox": [x - half, y - half, x + half, y + half],
              "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"}}
    sdir = os.path.join(run_dir, "s1")
    os.makedirs(sdir, exist_ok=True)
    tok = token()
    for d in dates:
        p = os.path.join(sdir, f"{d}.tif")
        if not os.path.exists(p):
            fetch_s1(tok, bounds, size, d, ref["direction"], p)
            print(f"  fetched {d}")
    dem_p = os.path.join(run_dir, "dem.tif")
    if not os.path.exists(dem_p):
        fetch_dem(tok, bounds, size, dem_p)

    vv, vh, ok = [], [], None
    for d in dates:
        with rasterio.open(os.path.join(sdir, f"{d}.tif")) as r:
            a = r.read()
            prof = r.profile
        vv.append(to_db(a[0])); vh.append(to_db(a[1]))
        ok = (a[2] > 0) if ok is None else ok & (a[2] > 0)
    with rasterio.open(dem_p) as r:
        dem = r.read(1).astype("f4")
    px = (2 * half) / size
    min_px = max(1, int(round(min_ha * 1e4 / px ** 2)))
    ev = history_z(vv, vh)
    ct = control_z(vv, vh)
    g_ev = flag(ev, ok, z_thr, drop_db, min_px)
    g_ct = flag(ct, ok, z_thr, drop_db, min_px)
    from scipy import ndimage as ndi
    dem = ndi.gaussian_filter(dem, 1.5)          # 30 m DEM on a 10 m grid: smooth the steps
    gy, gx = np.gradient(dem, px)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    steep = slope > 15
    valley = valley_floor(dem, slope, px)
    ha = px * px / 1e4
    n_ok = max(int(ok.sum()), 1)
    stats = {"run_id": run_id, "scenario": "disturbance", "backend": "cdse", "name": name,
             "method": f"per-pixel z vs {ev['n_control']} control pairs on the same track; "
                       f"flag zc < {z_thr} and VV, VH both < -{drop_db} dB; patches >= {min_ha} ha",
             "track": {"direction": ref["direction"], "rel_orbit": ref["rel_orbit"]},
             "event_pair": [dates[-2], dates[-1]], "control_dates": dates[:-1],
             "pixel_m": round(px, 2),
             "flagged_ha": round(float((g_ev > 0).sum() * ha), 2),
             "severe_ha": round(float((g_ev == 2).sum() * ha), 2),
             "flagged_steep_ha": round(float(((g_ev > 0) & steep).sum() * ha), 2),
             "flagged_flat_ha": round(float(((g_ev > 0) & ~steep).sum() * ha), 2),
             "flagged_pct": round(100 * float((g_ev > 0).sum()) / n_ok, 3),
             "control_flagged_pct": round(100 * float((g_ct > 0).sum()) / n_ok, 3),
             "control_pair": [dates[-3], dates[-2]]}
    stats["event_to_control_ratio"] = (round(stats["flagged_pct"] / stats["control_flagged_pct"], 1)
                                       if stats["control_flagged_pct"] else None)
    stats["by_terrain"] = terrain_split(g_ev, g_ct, valley & ok, ~valley & ok)
    p2 = prof.copy()
    p2.update(count=1, dtype="uint8", nodata=0, compress="deflate")
    with rasterio.open(os.path.join(run_dir, "history_flags.tif"), "w", **p2) as w:
        w.write(g_ev, 1)
    _geojson(g_ev, prof["transform"], epsg, os.path.join(run_dir, "history_flags.geojson"), ha)
    _quickmap(dem, g_ev, g_ct, px, stats, os.path.join(run_dir, "history_map.png"))
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps({k: stats[k] for k in ("event_pair", "flagged_ha", "flagged_pct",
                                            "control_flagged_pct", "event_to_control_ratio", "by_terrain")}, indent=1))
    return stats


def _geojson(g, transform, epsg, path, ha):
    from rasterio import features
    from pyproj import Transformer
    from shapely.geometry import mapping, shape
    from shapely.ops import transform as stf
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    m = g > 0
    feats = [{"type": "Feature",
              "properties": {"severe": int(v) == 2, "ha": round(shape(geom).area / 1e4, 2)},
              "geometry": mapping(stf(tr.transform, shape(geom)))}
             for geom, v in features.shapes(g, mask=m, transform=transform)]
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)


def _quickmap(dem, g_ev, g_ct, px, stats, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, ListedColormap
    hs = LightSource(315, 40).hillshade(dem, vert_exag=1.5, dx=px, dy=px)
    fig, axs = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=True)
    for ax, g, t in [(axs[0], g_ct, f"Control {stats['control_pair'][0]} → {stats['control_pair'][1]}: "
                                    f"{stats['control_flagged_pct']}% flagged"),
                     (axs[1], g_ev, f"Event {stats['event_pair'][0]} → {stats['event_pair'][1]}: "
                                    f"{stats['flagged_pct']}% flagged")]:
        ax.imshow(hs, cmap="gray")
        ax.imshow(np.ma.masked_where(g == 0, g), cmap=ListedColormap(["#fd8d3c", "#d7191c"]),
                  vmin=1, vmax=2, interpolation="nearest")
        ax.set_title(t, fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"Sentinel-1 change vs each pixel's own history ({stats['name']}). "
                 "Contains modified Copernicus Sentinel data", fontsize=10)
    fig.savefig(path, dpi=110)
    plt.close(fig)
