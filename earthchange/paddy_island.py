"""Paddy drought for a whole island: tile it, run it, mosaic it, publish it.

The island is the unit of work. Not because it is a convenient size to compute
-- it is far too big for that -- but because it is the unit people report and
publish on, and because it is finishable: one island is a job that starts,
resumes and ends, and its outputs stand on their own at drought.ownmap.id.

Underneath, the island is cut into 0.125 degree (13.9 km) tiles holding paddy.
That size is measured, not chosen: Earth Engine refuses a single request over
50,331,648 bytes, and with the real 85-period VH stack a 0.25 degree tile is
twice over the limit while a 0.125 degree tile returns in 15.5 MB and 11
seconds. See paddy_tiles.

What makes this affordable rather than merely possible:

  * Tiles share one grid, exactly (paddy_data.grid_transform), so the mosaic is
    a windowed copy with no resampling -- and a tile can be recomputed on its
    own without disturbing its neighbours.
  * The forecast is one 27 km field for the island, downloaded once. Per tile it
    would be hundreds of requests for the same numbers.
  * Every tile is a directory. A finished tile is never refetched, so an
    interrupted island resumes where it stopped, and a failed tile is retried
    alone.
  * Tiles are visited richest-first, so an island that is stopped early has
    still covered most of its rice.

Tiles run in separate PROCESSES, because the phenology is a per-pixel Python
loop -- 31 seconds on a dense tile against about a second of I/O -- and threads
would serialise on the GIL, so workers would buy nothing. A consequence worth
knowing: a script that calls run() must guard its entry point, or the spawned
children re-import it and spawn again:

    if __name__ == "__main__":
        paddy_island.run("Jawa", "LBS.tif", "out/Jawa")

The console script does this already; a bare `python myrun.py` does not.
"""
import datetime as dt
import json
import os
import time

import numpy as np

from . import paddy_data as pdata
from . import paddy_drought as pdr
from . import paddy_tiles as ptiles
from . import paddy_water as pw

# Layers worth mosaicking for the island. The per-tile runs write more (supply,
# demand, the raw indices); these are the ones a map or a report reads.
MOSAIC = {
    "paddy": "uint8", "planting_doy": "float32", "delay_days": "float32",
    "delay_class": "uint8", "adequacy": "float32", "adequacy_class": "uint8",
    "anomaly": "float32", "anomaly_class": "uint8", "outlook_class": "uint8",
    "puso": "uint8",
    # Which sensor dated each planting: 1 optical, 0 radar. Not a product to
    # colour a map with, but the thing to look at when two calendar arms give
    # different answers for a province.
    "calendar_arm": "float32",
}
NODATA = {"uint8": {"delay_class": 255, "adequacy_class": pw.ADEQUACY_NODATA,
                    "anomaly_class": pw.ADEQUACY_NODATA,
                    "outlook_class": pw.ADEQUACY_NODATA,
                    "paddy": None, "puso": None}}
GFS_GRID_DEG = 0.05          # ~5.5 km: finer than GFS, coarse enough to be one file


ISLAND_ALERT_MIN_HA = 5.0    # the smallest patch worth sending someone to see


def default_workers():
    """Concurrent tiles: bounded by cores, because the phenology is CPU-bound.

    A dense tile is about 31 seconds of per-pixel Python against a second of
    I/O, so the machine's cores set the rate. Two are left for everything else,
    and 8 is the ceiling -- beyond that the Earth Engine downloads, not the
    cores, become the queue.
    """
    return max(1, min(8, (os.cpu_count() or 4) - 2))

# Where the scenario's own framing does not fit the island, the island says so.
# The water balance compares ETa with an irrigated crop's requirement; on rice
# that is rainfed or tidal, a deficit against that requirement is the normal
# state of the system, not a failure of a canal that does not exist.
ISLAND_NOTES = {
    "Kalimantan": {
        "id": "Sebagian besar sawah Kalimantan adalah lahan pasang surut dan "
              "sawah hujan, bukan daerah irigasi teknis. Deteksi tanam tetap "
              "berlaku, tetapi 'kecukupan air' di sini dibaca sebagai "
              "penyimpangan dari kebiasaan petak itu (lapisan anomali), bukan "
              "sebagai kinerja layanan irigasi.",
        "en": "Most paddy in Kalimantan is tidal or rainfed, not a gravity "
              "irrigation scheme. Planting detection still applies, but "
              "'water adequacy' here should be read as a departure from the "
              "field's own habit (the anomaly layer), not as irrigation "
              "service performance.",
    },
    "Papua": {
        "id": "Sawah Papua tersebar dan sebagian besar bukan irigasi teknis; "
              "angka pulau berasal dari ubin yang sedikit, jadi rapuh.",
        "en": "Papua's paddy is scattered and largely not scheme-irrigated; the "
              "island figures rest on few tiles and are correspondingly fragile.",
    },
    "Maluku": {
        "id": "Sawah Maluku sangat sedikit (sekitar 0,4% nasional); angka pulau "
              "bersifat indikatif.",
        "en": "Maluku holds very little paddy (about 0.4% of the national "
              "total); island figures are indicative.",
    },
}


def _say(msg):
    print(msg, flush=True)


def safe_name(area):
    """A file-name stem from an area name: 'Jawa Barat' -> 'JawaBarat'."""
    return "".join(c for c in str(area).title() if c.isalnum())


def island_bbox(rows, pad=0.0):
    """The bounding box of a set of tiles."""
    return (min(r["lon_min"] for r in rows) - pad,
            min(r["lat_min"] for r in rows) - pad,
            max(r["lon_max"] for r in rows) + pad,
            max(r["lat_max"] for r in rows) + pad)


def shared_forecast(bbox, out_path, outlook_days, grid_deg=GFS_GRID_DEG):
    """Download the island's GFS field once. Returns (path, run_time) or (None, None)."""
    import ee
    from .gee_utils import download_geotiff
    run_time = pdata.latest_gfs_run()
    if run_time is None:
        return None, None
    if not pdr.usable_raster(out_path):
        # Padded for the same reason the WaPOR window is: tiles at the island's
        # edge upsample this field locally, and without neighbours beyond the
        # boundary their outer ring would interpolate from nothing.
        pad = 3 * grid_deg
        rect = ee.Geometry.Rectangle([bbox[0] - pad, bbox[1] - pad,
                                      bbox[2] + pad, bbox[3] + pad])
        img = pdata.gfs_daily(rect, run_time, outlook_days)
        if not download_geotiff(img, rect, out_path, scale=grid_deg * pdata.DEG_M,
                                crs_transform=pdata.grid_transform(
                                    grid_deg, (0.0, 0.0))):
            return None, None
    return out_path, run_time


def tile_dir(tiles_root, tile_id):
    """Where one tile's products live, directly under the tile root.

    The root itself carries the "tiles" segment -- run() defaults it to
    run_dir/tiles -- so adding another here doubled it for any caller that
    passed a root explicitly, and a shared cache then failed to match the
    tiles already in it.
    """
    return os.path.join(tiles_root, tile_id)


def tile_done(run_dir, tile_id):
    """A tile is done when its own stats.json exists."""
    return os.path.exists(os.path.join(tile_dir(run_dir, tile_id), "stats.json"))


INPUT_PREFIXES = ("paddy_vh_", "paddy_aeti_", "paddy_ret_", "paddy_gfs_")


def drop_inputs(d):
    """Delete a finished tile's downloaded stacks, keeping its products.

    A tile's VH and WaPOR stacks are about 40 MB; its products are about 200 KB.
    Nationally that is the difference between 200 GB and 1 GB, and the stacks
    are refetchable -- whereas a resumed run skips the tile entirely, because
    what marks it done is its stats.json.
    """
    freed = 0
    for f in os.listdir(d):
        if f.startswith(INPUT_PREFIXES) and f.endswith(".tif"):
            p = os.path.join(d, f)
            freed += os.path.getsize(p)
            os.remove(p)
    return freed


def run_tile(tile, run_dir, as_of, paddy_file, gfs=(None, None),
             keep_inputs=False, quiet=True, workdir=None, **kw):
    """One tile, in its own directory. Returns (tile_id, status, detail).

    Module-level and picklable on purpose: tiles run in separate PROCESSES.
    The phenology is a per-pixel Python loop -- 45 seconds on a dense tile --
    so threads would serialise on the GIL and more workers would buy nothing.
    """
    if workdir:
        os.chdir(workdir)          # a spawned process starts wherever it likes
    pdr._QUIET = quiet             # module state does not survive a spawn
    tid = tile["tile_id"]
    d = tile_dir(run_dir, tid)
    if tile_done(run_dir, tid):
        return tid, "cached", None
    os.makedirs(d, exist_ok=True)
    bbox = (tile["lon_min"], tile["lat_min"], tile["lon_max"], tile["lat_max"])
    try:
        got = pdr.run("gee", tile["lat_c"], tile["lon_c"], None, tid, d, tid,
                      as_of=as_of, paddy_file=paddy_file, bbox=bbox,
                      gfs_file=gfs[0], gfs_run=gfs[1], on_empty="skip",
                      do_map=False, publish=False, **kw)
    except Exception as e:                        # noqa: BLE001 — one tile only
        with open(os.path.join(d, "error.txt"), "w") as f:
            f.write(f"{type(e).__name__}: {e}\n")
        return tid, "failed", f"{type(e).__name__}: {str(e)[:160]}"
    if got is None or got.get("empty"):
        # Recorded, so a resume does not try it again: an empty tile is an
        # answer, not a gap -- and the reason travels with it, because "the
        # radar left a 4-period hole here" is not the same as "no paddy".
        note = {"tile_id": tid, "empty": True, "paddy_ha": 0.0}
        note.update(got or {})
        with open(os.path.join(d, "stats.json"), "w") as f:
            json.dump(note, f)
        if not keep_inputs:
            drop_inputs(d)
        return tid, "empty", note.get("reason")
    if not keep_inputs:
        drop_inputs(d)
    return tid, "ok", got["stats"].get("paddy_ha")


def mosaic_aligned(paths, out_path, dtype, nodata=None):
    """Lay tiles into one raster by window, with no resampling.

    Every tile is on the same grid, so each lands on a whole-pixel offset --
    which is the entire point of aligning the grid to the paddy layer. Written
    tile by tile, so an island never has to fit in memory.
    """
    import rasterio
    from rasterio.transform import Affine
    if not paths:
        return None
    heads = []
    for p in paths:
        with rasterio.open(p) as src:
            heads.append((p, src.bounds, src.transform, src.crs))
    step_x = abs(heads[0][2].a)
    step_y = abs(heads[0][2].e)
    left = min(h[1].left for h in heads)
    right = max(h[1].right for h in heads)
    bottom = min(h[1].bottom for h in heads)
    top = max(h[1].top for h in heads)
    width = int(round((right - left) / step_x))
    height = int(round((top - bottom) / step_y))
    transform = Affine(step_x, 0.0, left, 0.0, -step_y, top)
    fill = (nodata if nodata is not None else
            (np.nan if dtype.startswith("float") else 0))
    prof = {"driver": "GTiff", "width": width, "height": height, "count": 1,
            "dtype": dtype, "crs": heads[0][3], "transform": transform,
            "compress": "deflate", "tiled": True, "blockxsize": 256,
            "blockysize": 256, "BIGTIFF": "IF_SAFER"}
    if nodata is not None:
        prof["nodata"] = nodata
    elif dtype.startswith("float"):
        prof["nodata"] = float("nan")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with rasterio.open(out_path, "w", **prof) as dst:
        blank = np.full((dst.block_shapes[0][0], width), fill, dtype=dtype)
        for _, win in dst.block_windows(1):       # fill first: tiles are sparse
            dst.write(blank[:win.height, :win.width], 1, window=win)
        for p, b, t, _ in heads:
            col = int(round((b.left - left) / step_x))
            row = int(round((top - b.top) / step_y))
            with rasterio.open(p) as src:
                data = src.read(1)
                if src.nodata is not None and not dtype.startswith("float"):
                    data = np.where(data == src.nodata, fill, data)
            dst.write(data.astype(dtype), 1,
                      window=rasterio.windows.Window(col, row, data.shape[1],
                                                     data.shape[0]))
    return out_path


def roll_up(rows, tiles_root, area, as_of, tiles_run):
    """Area totals from the per-tile stats: hectares add, medians do not.

    Class hectares are summed. A median season length is taken across tiles
    weighted by paddy area, which is not the same as the median over pixels and
    is labelled as what it is.

    A caution for provinces: these totals are per TILE, and a tile on a border
    belongs to two provinces, so summing them counts that tile in both. For a
    provincial figure use admin_totals, which masks the mosaic with the boundary.
    """
    per_tile, tot = [], {}
    lengths, weights, delays = [], [], []
    for r in rows:
        p = os.path.join(tile_dir(tiles_root, r["tile_id"]), "stats.json")
        if not os.path.exists(p):
            continue
        with open(p) as f:
            s = json.load(f)
        if s.get("empty"):
            per_tile.append({"tile_id": r["tile_id"], "paddy_ha": 0.0,
                             "empty": True, "reason": s.get("reason"),
                             "orbit_pass": s.get("orbit_pass"),
                             "longest_gap": s.get("longest_gap"),
                             "index_paddy_ha": r["paddy_ha"]})
            continue
        cov = s.get("radar_coverage") or {}
        per_tile.append({
            "tile_id": r["tile_id"], "island": r["island"],
            "paddy_ha": s.get("paddy_ha"), "planted_ha": s.get("planted_ha"),
            "not_planted_pct": s.get("not_planted_pct"),
            "median_delay_days": s.get("median_delay_days"),
            "season_length_days_median": s.get("season_length_days_median"),
            "puso_candidates_ha": s.get("puso_candidates_ha"),
            "orbit_pass": s.get("orbit_pass"),
            "empty_periods": cov.get("empty_periods"),
            "longest_gap": cov.get("longest_gap"),
        })
        for key in ("paddy_ha", "planted_ha", "not_planted_ha",
                    "puso_candidates_ha", "puso_no_canopy_ha",
                    "puso_starved_ha"):
            if s.get(key) is not None:
                tot[key] = round(tot.get(key, 0.0) + s[key], 1)
        for group in ("planting_delay_ha", "adequacy_ha", "anomaly_ha",
                      "outlook_ha"):
            g = tot.setdefault(group, {})
            for label, ha in (s.get(group) or {}).items():
                g[label] = round(g.get(label, 0.0) + ha, 1)
        if s.get("season_length_days_median") and s.get("paddy_ha"):
            lengths.append(s["season_length_days_median"])
            weights.append(s["paddy_ha"])
        if s.get("median_delay_days") is not None:
            delays.append(s["median_delay_days"])

    if tot.get("paddy_ha"):
        tot["not_planted_pct"] = round(
            100.0 * tot.get("not_planted_ha", 0.0) / tot["paddy_ha"], 1)
    if lengths:
        order = np.argsort(lengths)
        w = np.cumsum(np.asarray(weights, dtype="float64")[order])
        tot["season_length_days_median"] = float(
            np.asarray(lengths)[order][np.searchsorted(w, w[-1] / 2)])
        tot["season_length_note"] = ("area-weighted median of per-tile medians, "
                                     "not the median over pixels")
    if delays:
        tot["median_delay_days"] = round(float(np.median(delays)), 1)
        tot["median_delay_note"] = "median of per-tile medians"
    scored = [p for p in per_tile if not p.get("empty")]
    blank = [p for p in per_tile if p.get("empty")]
    orbits = {}
    for p in scored:
        if p.get("orbit_pass"):
            orbits[p["orbit_pass"]] = orbits.get(p["orbit_pass"], 0) + 1
    tot.update({
        "scenario": "drought-paddy", "island": area, "area": area,
        "as_of": str(as_of),
        "tiles": {"in_index": len(rows), "run": tiles_run,
                  "with_products": len(scored), "empty": len(blank),
                  # Paddy the index knows about but no product covers: the
                  # honest denominator for an island total.
                  "unscored_paddy_ha": round(
                      sum(p.get("index_paddy_ha", 0.0) for p in blank), 1),
                  "orbit_pass": orbits},
        "per_tile": per_tile,
    })
    return tot


def admin_totals(written, geom, lang="id"):
    """Hectares per class INSIDE a boundary, from the mosaics themselves.

    The per-tile roll-up cannot give a provincial figure: a tile on a border
    belongs to two provinces, and counting it whole in each inflates both. Here
    the boundary is burned onto the mosaic's own grid and the classes are summed
    only where it says, so a border runs through a tile rather than around it.
    """
    import numpy as np
    import rasterio
    from rasterio.features import rasterize

    ref = written.get("paddy") or next(iter(written.values()))
    with rasterio.open(ref) as src:
        profile = src.profile.copy()
        lat = (src.bounds.top + src.bounds.bottom) / 2.0
    inside = rasterize([(geom, 1)], out_shape=(profile["height"],
                                               profile["width"]),
                       transform=profile["transform"], fill=0,
                       all_touched=False, dtype="uint8").astype(bool)
    area_ha = pdr.pixel_area_ha(profile, lat)

    def read(layer):
        with rasterio.open(written[layer]) as src:
            return src.read(1)

    out = {}
    if "paddy" in written:
        paddy = (read("paddy") > 0) & inside
        out["paddy_ha"] = round(float(paddy.sum()) * area_ha, 1)
    for layer, table in (("delay_class", pw.DELAY_CLASSES),
                         ("adequacy_class", pw.ADEQUACY_CLASSES),
                         ("anomaly_class", pw.ANOMALY_CLASSES),
                         ("outlook_class", pw.ADEQUACY_CLASSES)):
        if layer not in written:
            continue
        arr = read(layer)
        key = {"delay_class": "planting_delay_ha",
               "adequacy_class": "adequacy_ha",
               "anomaly_class": "anomaly_ha",
               "outlook_class": "outlook_ha"}[layer]
        out[key] = {}
        for cid, _lo, _hi, labels, _colour in table:
            label = labels[lang if lang in labels else "en"]
            out[key][label] = round(
                float(((arr == cid) & inside).sum()) * area_ha, 1)
    if "delay_class" in written:
        arr = read("delay_class")
        planted = np.isin(arr, [0, 1, 2, 3]) & inside
        not_planted = (arr == pw.NOT_PLANTED) & inside
        out["planted_ha"] = round(float(planted.sum()) * area_ha, 1)
        out["not_planted_ha"] = round(float(not_planted.sum()) * area_ha, 1)
        total = out.get("paddy_ha") or 0.0
        out["not_planted_pct"] = (round(100.0 * out["not_planted_ha"] / total, 1)
                                  if total else None)
    if "puso" in written:
        out["puso_candidates_ha"] = round(
            float(((read("puso") == 1) & inside).sum()) * area_ha, 1)
    out["method"] = "mosaic masked by the boundary, not summed per tile"
    return out


def run(area, paddy_file, run_dir, kind="island", calendar=None,
        tiles_dir=None, admin_cache=None, as_of=None, coverage=None, limit=None,
        tile_deg=ptiles.TILE_DEG, min_ha=1.0, workers=None,
        index_file=None, publish=True, lang="id", outlook_days=14,
        seasons_back=pdr.DEFAULT_SEASONS_BACK, season_days=pdr.DEFAULT_SEASON_DAYS,
        kc_mode="curve110", orbit_pass="auto", quiet_tiles=True,
        config_key=None, keep_inputs=False):
    """Everything for one area: index, tiles, mosaics, roll-up, web bundle.

    `kind` is "island" or "province". A province is the unit an agency reports
    on, so it is the one that matters operationally; an island is the one that
    tiles cleanly. Both are only groupings of the same tiles, which is why
    `tiles_dir` exists: point two province runs at one cache and the tiles on
    their shared border are computed once, not twice.

    `calendar` selects the crop-calendar arm ("full_sar" or "hybrid"). Tile
    caches must not be shared BETWEEN arms -- the products differ -- so the
    caller gives each arm its own directory.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from .gee_utils import initialize_ee
    as_of = as_of or dt.date.today()
    workers = workers or default_workers()
    calendar = calendar or pdr.DEFAULT_CALENDAR
    os.makedirs(run_dir, exist_ok=True)
    tiles_dir = tiles_dir or os.path.join(run_dir, "tiles")
    os.makedirs(tiles_dir, exist_ok=True)
    # Once, here: the island's own forecast download comes before any tile.
    # Each tile process initialises its own client.
    initialize_ee(config_key)

    # --- the index ---------------------------------------------------------
    cache = index_file or os.path.join(run_dir, "tile_index_all.csv")
    if os.path.exists(cache):
        rows_all = ptiles.read_csv(cache)
        _say(f"tile index: {len(rows_all):,} tiles (from {os.path.basename(cache)})")
    else:
        _say(f"building the tile index from {os.path.basename(paddy_file)} "
             f"at {tile_deg} deg...")
        rows_all = ptiles.index(paddy_file, tile_deg, min_ha=min_ha)
        ptiles.write_csv(rows_all, cache)
        _say(f"  {len(rows_all):,} tiles hold paddy")
    if kind == "province":
        if not rows_all or not rows_all[0].get("province"):
            # Provinces are not in the index yet: tag it once, from GAUL.
            _say("  tagging the index with provinces (FAO GAUL 2025)...")
            polys = ptiles.admin_polygons("Indonesia", cache=admin_cache)
            ptiles.assign_admin(rows_all, polys)
            ptiles.write_csv(rows_all, cache)
        rows = ptiles.select(rows_all, provinces=[area], coverage=coverage,
                             limit=limit)
        known = sorted({r.get("province") for r in rows_all if r.get("province")})
    else:
        rows = ptiles.select(rows_all, islands=[area], coverage=coverage,
                             limit=limit)
        known = [n for n, _ in ptiles.ISLANDS]
    if not rows:
        raise SystemExit(f"no tiles for {kind} {area!r}. Known: "
                         f"{', '.join(known)}")
    ptiles.write_csv(rows, os.path.join(run_dir, "tile_index.csv"))
    ptiles.write_geojson(rows, os.path.join(run_dir, "tile_index.geojson"))
    total_ha = sum(r["paddy_ha"] for r in rows)
    bbox = island_bbox(rows)
    _say(f"\n=== {area} ({kind}, calendar {calendar}) ===")
    _say(f"  {len(rows):,} tiles, {total_ha:,.0f} ha of paddy in the index, bbox "
         f"{bbox[0]:.2f},{bbox[1]:.2f} -> {bbox[2]:.2f},{bbox[3]:.2f}")
    cached = sum(1 for r in rows if tile_done(tiles_dir, r["tile_id"]))
    _say(f"  as of {as_of}, {seasons_back} baseline season(s), {workers} workers"
         f"{f', {cached} tiles already in the cache' if cached else ''}")

    # --- one forecast for the whole area ----------------------------------
    gfs = shared_forecast(bbox, os.path.join(run_dir, "gfs_area.tif"),
                          outlook_days)
    _say(f"  forecast: {'GFS run ' + gfs[1].strftime('%Y-%m-%d %H:%M UTC') if gfs[1] else 'none available'}")

    # --- the tiles ---------------------------------------------------------
    kw = dict(season_days=season_days, seasons_back=seasons_back,
              kc_mode=kc_mode, orbit_pass=orbit_pass, outlook_days=outlook_days,
              lang=lang, config_key=config_key, calendar=calendar)
    done = {"ok": 0, "cached": 0, "empty": 0, "failed": 0}
    started = time.time()
    cwd = os.getcwd()              # relative paths (the paddy layer) must survive
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_tile, r, tiles_dir, as_of, paddy_file, gfs,
                               keep_inputs, quiet_tiles, cwd, **kw)
                   for r in rows]
        # As they finish, not in the order they were queued. Waiting on the
        # queue order means the first slow tile hides the progress of every
        # tile behind it: 31 tiles done and not one line printed.
        for n, fut in enumerate(as_completed(futures), start=1):
            tid, status, detail = fut.result()
            done[status] = done.get(status, 0) + 1
            if status == "failed":
                print(f"  [{n}/{len(rows)}] {tid} FAILED — {detail}", flush=True)
            elif n % 10 == 0 or n == len(rows):
                rate = (time.time() - started) / n
                left = (len(rows) - n) * rate / 60
                print(f"  [{n}/{len(rows)}] {tid} {status}; "
                      f"{rate:.0f} s/tile, ~{left:.0f} min left "
                      f"({done['ok']} ok, {done['cached']} cached, "
                      f"{done['empty']} empty, {done['failed']} failed)",
                      flush=True)
    _say(f"  tiles: {done}")

    # --- mosaics -----------------------------------------------------------
    _say(f"  mosaicking {area} (windowed copy: tiles share one grid)...")
    written = {}
    prefix = safe_name(area)
    for layer, dtype in MOSAIC.items():
        paths = [os.path.join(tile_dir(tiles_dir, r["tile_id"]),
                              f"paddy_{layer}_{r['tile_id']}.tif")
                 for r in rows]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            continue
        out = os.path.join(run_dir, f"{prefix}_{layer}.tif")
        got = mosaic_aligned(paths, out, dtype,
                             NODATA.get(dtype, {}).get(layer))
        if got:
            written[layer] = got
    _say(f"  {len(written)} rasters for {area}")

    # --- the numbers -------------------------------------------------------
    stats = roll_up(rows, tiles_dir, area, as_of, len(rows))
    if kind == "province" and written:
        # The figure to quote. The per-tile sums stay in the file beside it, and
        # the difference between them is the border tiles counted twice.
        polys = ptiles.admin_polygons("Indonesia", cache=admin_cache)
        if area in polys:
            exact = admin_totals(written, polys[area], lang)
            _say(f"  within the province boundary: "
                 f"{exact.get('paddy_ha', 0):,.0f} ha of paddy "
                 f"(per-tile sum {stats.get('paddy_ha', 0):,.0f} ha — the "
                 f"difference is tiles shared with a neighbour)")
            stats["per_tile_totals"] = {k: stats.get(k) for k in (
                "paddy_ha", "planted_ha", "not_planted_ha", "not_planted_pct",
                "planting_delay_ha", "adequacy_ha", "anomaly_ha", "outlook_ha",
                "puso_candidates_ha")}
            stats.update(exact)
            stats["boundary"] = {"source": ptiles.GAUL1, "name": area}
    stats.update({
        "kind": kind, "calendar_arm": calendar,
        "tile_deg": tile_deg, "paddy_extent_source": os.path.basename(paddy_file),
        "grid": {"deg": pdata.LBS_GRID_DEG, "m": round(pdata.grid_metres(), 3),
                 "aligned_to": os.path.basename(paddy_file), "crs": "EPSG:4326"},
        "native_m": pdr.NATIVE_M,
        "bbox": list(bbox),
        "index_paddy_ha": round(total_ha, 1),
        "sources": {"radar": "Sentinel-1 GRD VH " + orbit_pass,
                    "eta": pdata.WAPOR_AETI[0], "et0": pdata.WAPOR_RET[0],
                    "forecast": pdata.GFS},
        "outlook": {"gfs_run": gfs[1].isoformat() if gfs[1] else None,
                    "lead_days_wanted": pdr.LEAD_ACTIONABLE_DAYS,
                    "basis": "rainfall only; irrigation deliveries not forecast"},
    })
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    _print(stats, area)

    if publish and written:
        _say(f"\n  building the {kind} web bundle...")
        web = publish_island(run_dir, written, stats, lang)
        alerts = ", ".join(
            f"{v['file']} {v['features']:,} poly {v['mb']} MB"
            for v in (web.get("alert_counts") or {}).values())
        _say(f"  web/: {len(web.get('cog', {}))} COGs, legend.json, "
             f"summary.json")
        if alerts:
            _say(f"  alerts: {alerts}")
    return {"rasters": written, "stats": stats, "tiles": done}


def island_caveats(island, lang="id", grid_m=None):
    """The scenario's limits, plus anything this island adds to them."""
    from . import paddy_publish as ppub
    out = list(ppub.caveats(lang, grid_m))
    note = ISLAND_NOTES.get(island)
    if note:
        out.insert(0, note.get(lang, note["en"]))
    return out


def publish_island(run_dir, written, stats, lang="id"):
    """The island's web bundle, same contract as a single run's."""
    import rasterio
    from . import paddy_publish as ppub
    out_dir = os.path.join(run_dir, "web")
    os.makedirs(os.path.join(out_dir, "cog"), exist_ok=True)
    web = {"cog": {}}
    for key in ppub.LAYERS:
        src = written.get(key)
        if src and os.path.exists(src):
            web["cog"][key] = ppub.to_cog(src, os.path.join(out_dir, "cog",
                                                            f"{key}.tif"))
    # An area's alert layer is not a single AOI's scaled up, and its three kinds
    # are not one kind of thing. Written one file per kind, with a floor per
    # kind, so the map loads the layer it is showing and "not planted" across a
    # dry-season province does not drag 22 MB of polygons behind the two layers
    # somebody would actually act on.
    web["alerts"] = {}
    counts = {}
    # A republish must not leave the previous shape of this layer beside the new
    # one. An area's alerts are per-kind files; a combined alerts.geojson here is
    # an older bundle's, and two contradictory versions of one layer is worse
    # than either.
    stale = os.path.join(out_dir, "alerts.geojson")
    if os.path.exists(stale):
        os.remove(stale)
    if all(k in written for k in ("adequacy_class", "delay_class", "puso")):
        with rasterio.open(written["paddy"]) as ds:
            prof = ds.profile.copy()
        lat = (stats["bbox"][1] + stats["bbox"][3]) / 2.0
        area_ha = pdr.pixel_area_ha(prof, lat)
        per_kind = ppub.alerts_geojson(
            written, prof, area_ha, lang, min_ha=ISLAND_ALERT_MIN_HA,
            per_kind_min_ha=ppub.ALERT_MIN_HA, by_kind=True)
        for kind, coll in per_kind.items():
            path = os.path.join(out_dir, f"alerts_{kind}.geojson")
            with open(path, "w") as f:
                json.dump(coll, f)
            web["alerts"][kind] = path
            counts[kind] = {"features": len(coll["features"]),
                            "min_ha": coll["min_ha"],
                            "mb": round(os.path.getsize(path) / 1e6, 2),
                            "file": os.path.basename(path)}
    web["alert_counts"] = counts
    grid = stats.get("grid", {})
    with open(os.path.join(out_dir, "legend.json"), "w") as f:
        json.dump(ppub.legend(lang, grid.get("m"), stats.get("native_m")),
                  f, indent=2)
    web["legend"] = os.path.join(out_dir, "legend.json")
    summary = {
        "scenario": "drought-paddy", "island": stats.get("island"),
        "as_of": stats.get("as_of"), "bbox": stats.get("bbox"),
        "tiles": stats.get("tiles"), "tile_deg": stats.get("tile_deg"),
        "headline": {k: stats.get(k) for k in (
            "paddy_ha", "planted_ha", "not_planted_ha", "not_planted_pct",
            "median_delay_days", "season_length_days_median",
            "adequacy_ha", "anomaly_ha", "outlook_ha", "puso_candidates_ha")},
        "resolution": {"grid": grid, "native_m": stats.get("native_m"),
                       "note": {"id": "Lapisan air berasal dari WaPOR 300 m, "
                                      "bukan ukuran per petak.",
                                "en": "The water layers come from WaPOR at "
                                      "300 m, not field-level measurement."}},
        "sources": stats.get("sources"), "outlook": stats.get("outlook"),
        "alerts": {
            "by_kind": counts,
            "note": {"id": "Satu berkas per jenis, dengan ambang luas "
                           "berbeda: 'belum tanam' hanya blok besar, sebab "
                           "lapisan delay_class sudah memuat seluruhnya.",
                     "en": "One file per kind, with a floor per kind: 'not "
                           "planted' keeps only large blocks, since the "
                           "delay_class raster already carries all of it."},
        },
        "caveats": island_caveats(stats.get("island"), lang, grid.get("m")),
        "layers": list(web["cog"]),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    web["summary"] = os.path.join(out_dir, "summary.json")
    return web


def finalise(run_dir, tiles_dir, admin_cache=None, lang="id", publish=True):
    """Re-derive an area's products from tiles that already exist.

    Everything after the tiles -- mosaic, roll-up, boundary masking, bundle --
    is a pure function of the tile directory, so it can be redone without
    touching Earth Engine. Needed more often than it sounds: a run whose
    mosaicking step was interrupted, a bundle written before a fix to the
    publishing code, or a tile cache that moved.

    Reads what the area is from the run's own stats.json and tile_index.csv.
    """
    stats_path = os.path.join(run_dir, "stats.json")
    index_path = os.path.join(run_dir, "tile_index.csv")
    if not (os.path.exists(stats_path) and os.path.exists(index_path)):
        raise SystemExit(f"{run_dir}: needs stats.json and tile_index.csv to "
                         f"know what it was")
    with open(stats_path) as f:
        old = json.load(f)
    rows = ptiles.read_csv(index_path)
    area = old.get("area") or old.get("island")
    kind = old.get("kind", "island")
    calendar = old.get("calendar_arm") or old.get("calendar")
    as_of = old.get("as_of")
    prefix = safe_name(area)
    _say(f"re-deriving {area} ({kind}, {calendar}) from {len(rows):,} tiles "
         f"in {os.path.basename(tiles_dir)}")

    written = {}
    for layer, dtype in MOSAIC.items():
        paths = [os.path.join(tile_dir(tiles_dir, r["tile_id"]),
                              f"paddy_{layer}_{r['tile_id']}.tif")
                 for r in rows]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            continue
        got = mosaic_aligned(paths, os.path.join(run_dir, f"{prefix}_{layer}.tif"),
                             dtype, NODATA.get(dtype, {}).get(layer))
        if got:
            written[layer] = got
    covered = len([1 for r in rows
                   if tile_done(tiles_dir, r["tile_id"])])
    _say(f"  {len(written)} rasters from {covered:,} of {len(rows):,} tiles")

    stats = roll_up(rows, tiles_dir, area, as_of, len(rows))
    if kind == "province" and written:
        polys = ptiles.admin_polygons("Indonesia", cache=admin_cache)
        if area in polys:
            exact = admin_totals(written, polys[area], lang)
            stats["per_tile_totals"] = {k: stats.get(k) for k in (
                "paddy_ha", "planted_ha", "not_planted_ha", "not_planted_pct",
                "planting_delay_ha", "adequacy_ha", "anomaly_ha", "outlook_ha",
                "puso_candidates_ha")}
            stats.update(exact)
            stats["boundary"] = {"source": ptiles.GAUL1, "name": area}
    # Carry over what only the original run knew.
    for key in ("kind", "calendar_arm", "tile_deg", "paddy_extent_source",
                "grid", "native_m", "bbox", "index_paddy_ha", "sources",
                "outlook"):
        if key in old:
            stats.setdefault(key, old[key])
            stats[key] = old[key]
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    _print(stats, area)
    if publish and written:
        web = publish_island(run_dir, written, stats, lang)
        alerts = ", ".join(f"{v['file']} {v['features']:,} poly {v['mb']} MB"
                           for v in (web.get("alert_counts") or {}).values())
        _say(f"  web/: {len(web.get('cog', {}))} COGs; alerts: {alerts}")
    return stats


def national(base_dir, out_dir=None, lang="id"):
    """Roll finished islands into one national summary.

    Deliberately not a national mosaic: a 50 m layer over the whole archipelago
    is 3.1 billion pixels per band, and nobody reads Indonesia at 50 m in one
    image. What is national is the arithmetic and the index of islands -- a map
    site loads the island it is showing.

    Islands that have not run are named as missing rather than treated as zero,
    with the hectares the index says they hold, so the coverage of the national
    figure is visible instead of implied.
    """
    out_dir = out_dir or base_dir
    islands, missing = {}, {}
    for name, _ in ptiles.ISLANDS:
        p = os.path.join(base_dir, name, "stats.json")
        if os.path.exists(p):
            with open(p) as f:
                islands[name] = json.load(f)
        else:
            missing[name] = None

    idx = os.path.join(base_dir, "tile_index_all.csv")
    if os.path.exists(idx):
        per_island = ptiles.summarise(ptiles.read_csv(idx))
        for name in missing:
            missing[name] = (per_island.get(name) or {}).get("paddy_ha", 0.0)

    tot = {}
    for s in islands.values():
        for key in ("paddy_ha", "planted_ha", "not_planted_ha",
                    "puso_candidates_ha"):
            if s.get(key) is not None:
                tot[key] = round(tot.get(key, 0.0) + s[key], 1)
        for group in ("planting_delay_ha", "adequacy_ha", "anomaly_ha",
                      "outlook_ha"):
            g = tot.setdefault(group, {})
            for label, ha in (s.get(group) or {}).items():
                g[label] = round(g.get(label, 0.0) + ha, 1)
    if tot.get("paddy_ha"):
        tot["not_planted_pct"] = round(
            100.0 * tot.get("not_planted_ha", 0.0) / tot["paddy_ha"], 1)

    from . import paddy_publish as ppub
    summary = {
        "scenario": "drought-paddy", "scope": "national",
        "as_of": next((s.get("as_of") for s in islands.values()), None),
        "headline": tot,
        "islands": {
            name: {"paddy_ha": s.get("paddy_ha"),
                   "planted_ha": s.get("planted_ha"),
                   "not_planted_pct": s.get("not_planted_pct"),
                   "anomaly_ha": s.get("anomaly_ha"),
                   "tiles": s.get("tiles"),
                   "path": f"{name}/", "web": f"{name}/web/"}
            for name, s in islands.items()},
        "islands_not_run": {k: {"index_paddy_ha": v} for k, v in missing.items()},
        "coverage": {
            "paddy_ha_scored": tot.get("paddy_ha", 0.0),
            "paddy_ha_not_run": round(sum(v or 0.0 for v in missing.values()), 1),
            "note": {"id": "Angka nasional hanya mencakup pulau yang sudah "
                           "dijalankan; sisanya didaftar, bukan dianggap nol.",
                     "en": "The national figures cover only the islands that "
                           "have run; the rest are listed, not counted as zero."},
        },
        "caveats": ppub.caveats(lang, pdata.grid_metres()),
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "national_summary.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    _say(f"national summary: {len(islands)} island(s) rolled up "
         f"({tot.get('paddy_ha', 0):,.0f} ha), "
         f"{len(missing)} not run -> {os.path.basename(path)}")
    return summary


def _print(stats, island):
    t = pdr.T.get("id")
    _say(f"\n=== {island} — {t['paddy']} ===")
    _say(f"  {t['paddy']}: {stats.get('paddy_ha', 0):,.0f} ha  |  "
         f"{t['planted']}: {stats.get('planted_ha', 0):,.0f} ha  |  "
         f"{t['not_planted']}: {stats.get('not_planted_ha', 0):,.0f} ha "
         f"({stats.get('not_planted_pct')}%)")
    if stats.get("season_length_days_median"):
        _say(f"  {t['season']}: median {stats['season_length_days_median']} days "
             f"(area-weighted across tiles)")
    for group, label in (("anomaly_ha", t["anomaly"]),
                         ("adequacy_ha", t["si"]),
                         ("outlook_ha", t["outlook"])):
        for name, ha in (stats.get(group) or {}).items():
            _say(f"    {label:<26s} {name:<28s} {ha:>12,.0f} ha")
    _say(f"  {t['puso']}: {stats.get('puso_candidates_ha', 0):,.0f} ha — "
         f"candidates for a field check, not a verdict")
    tiles = stats.get("tiles", {})
    _say(f"  tiles: {tiles.get('with_products')} with products, "
         f"{tiles.get('empty')} empty, of {tiles.get('in_index')} in the index")
