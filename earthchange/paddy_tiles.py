"""A tile index for a national paddy-drought run, built from the paddy layer.

An island is the right unit to publish and report on. It is the wrong unit to
compute on: Sumatera's bounding box is about 1.85 million km2 and holds 1.77
million ha of paddy, so asking for the island is asking for a hundred thousand
times more pixels than the crop in it. Earth Engine refuses a single request
over 50,331,648 bytes anyway -- measured, with the real 85-period stack, a
0.25 degree tile is twice over and a 0.125 degree tile comes back in 15.5 MB
and 11 seconds.

So the country is cut into 0.125 degree tiles, every tile that holds no paddy
is dropped, and what is left is ordered by how much paddy it holds. The order
matters more than it looks: the distribution is extremely skewed, and a run
that stops early has still covered most of the rice.

Islands come back as a label on each tile, for grouping the outputs.
"""
import csv
import os

TILE_DEG = 0.125            # 13.9 km: the largest that fits one request
CELL_DEG = 0.01             # the fraction grid the index is measured on

# Priority order resolves the overlaps: the Sunda strait belongs to Jawa, the
# Makassar strait to Sulawesi. Rectangles, not coastlines -- a tile only needs
# a label, and anything that misses lands in "lain" rather than in the wrong
# island.
ISLANDS = [
    ("Jawa", (105.0, 114.7, -8.9, -5.8)),
    ("Bali-NusaTenggara", (114.4, 125.2, -11.1, -8.0)),
    ("Sumatera", (94.9, 107.0, -6.3, 6.1)),
    ("Kalimantan", (108.0, 119.3, -4.4, 4.5)),
    ("Sulawesi", (118.0, 125.5, -6.2, 2.2)),
    ("Maluku", (125.2, 135.0, -8.6, 3.1)),
    ("Papua", (130.8, 141.1, -9.3, 0.6)),
]
FIELDS = ("tile_id", "island", "lon_min", "lat_min", "lon_max", "lat_max",
          "lon_c", "lat_c", "paddy_ha")


def island_of(lon, lat):
    for name, (a, b, c, d) in ISLANDS:
        if a <= lon < b and c <= lat < d:
            return name
    return "lain"


def paddy_fraction(paddy_file, cell_deg=CELL_DEG, progress=None):
    """Paddy share of each `cell_deg` cell, read in strips.

    The national layer is 3.1 billion pixels, so it is never held in memory:
    one strip of cells at a time, block-averaged down. Returns (frac, bounds).
    """
    import numpy as np
    import rasterio
    with rasterio.open(paddy_file) as ds:
        agg = int(round(cell_deg / ds.res[0]))
        if agg < 1:
            raise SystemExit(
                f"{os.path.basename(paddy_file)} is coarser than the "
                f"{cell_deg} degree index grid; pass a finer cell_deg")
        ow, oh = ds.width // agg, ds.height // agg
        frac = np.zeros((oh, ow), dtype="float32")
        for r in range(oh):
            win = rasterio.windows.Window(0, r * agg, ow * agg, agg)
            s = ds.read(1, window=win) > 0
            frac[r] = s.reshape(agg, ow, agg).mean(axis=(0, 2))
            if progress and r % 200 == 0:
                progress(r, oh)
        return frac, ds.bounds


def index(paddy_file, tile_deg=TILE_DEG, cell_deg=CELL_DEG, min_ha=0.0,
          progress=None):
    """Tiles that hold paddy, richest first, as a list of dicts.

    `min_ha` drops the slivers: nationally, 0.125 degree tiles holding under
    1 ha are a long tail that costs a request each and adds nothing.
    """
    import numpy as np
    frac, b = paddy_fraction(paddy_file, cell_deg, progress)
    cell_ha = (cell_deg * 111320.0) ** 2 / 1e4
    ha = frac * cell_ha
    nz = ha > 0
    lons = b.left + (np.arange(frac.shape[1]) + 0.5) * cell_deg
    lats = b.top - (np.arange(frac.shape[0]) + 0.5) * cell_deg
    LON, LAT = np.meshgrid(lons, lats)

    # Tiles are keyed off the layer's own bounds, so the same layer always
    # yields the same tile ids -- a run can be resumed, and two runs compared.
    ti = ((b.top - LAT[nz]) / tile_deg).astype(int)
    tj = ((LON[nz] - b.left) / tile_deg).astype(int)
    isl = [island_of(x, y) for x, y in zip(LON[nz], LAT[nz])]

    tiles = {}
    for key, area, name in zip(zip(ti.tolist(), tj.tolist()), ha[nz].tolist(), isl):
        t = tiles.setdefault(key, {"ha": 0.0, "isl": {}})
        t["ha"] += area
        t["isl"][name] = t["isl"].get(name, 0.0) + area

    rows = []
    for (i, j), t in tiles.items():
        if t["ha"] < min_ha:
            continue
        lat_hi, lon_lo = b.top - i * tile_deg, b.left + j * tile_deg
        rows.append({
            "tile_id": f"t{i:04d}_{j:04d}",
            "island": max(t["isl"], key=t["isl"].get),
            "lon_min": round(lon_lo, 6), "lat_min": round(lat_hi - tile_deg, 6),
            "lon_max": round(lon_lo + tile_deg, 6), "lat_max": round(lat_hi, 6),
            "lon_c": round(lon_lo + tile_deg / 2, 6),
            "lat_c": round(lat_hi - tile_deg / 2, 6),
            "paddy_ha": round(t["ha"], 1),
        })
    rows.sort(key=lambda r: (-r["paddy_ha"], r["tile_id"]))
    return rows


def select(rows, islands=None, coverage=None, limit=None):
    """Narrow an index: by island, by share of the paddy covered, by count.

    `coverage=0.9` keeps the richest tiles that together hold 90% of the paddy
    in the selection -- nationally that is about a third of the tiles, because
    the rice is concentrated and the tail is thin.
    """
    out = list(rows)
    if islands:
        want = {s.lower() for s in islands}
        out = [r for r in out if r["island"].lower() in want]
    if coverage:
        total = sum(r["paddy_ha"] for r in out)
        keep, run = [], 0.0
        for r in out:                       # already richest-first
            keep.append(r)
            run += r["paddy_ha"]
            if total and run >= coverage * total:
                break
        out = keep
    if limit:
        out = out[:limit]
    return out


def summarise(rows):
    """Tiles and hectares per island, for the line printed before a run."""
    out = {}
    for r in rows:
        g = out.setdefault(r["island"], {"tiles": 0, "paddy_ha": 0.0})
        g["tiles"] += 1
        g["paddy_ha"] += r["paddy_ha"]
    for g in out.values():
        g["paddy_ha"] = round(g["paddy_ha"], 1)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["paddy_ha"]))


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS))
        w.writeheader()
        w.writerows({k: r[k] for k in FIELDS} for r in rows)
    return path


def read_csv(path):
    with open(path) as f:
        rows = []
        for r in csv.DictReader(f):
            r = dict(r)
            for k in ("lon_min", "lat_min", "lon_max", "lat_max", "lon_c",
                      "lat_c", "paddy_ha"):
                r[k] = float(r[k])
            rows.append(r)
    return rows


def write_geojson(rows, path):
    """The index as polygons, so the tiling can be looked at in QGIS."""
    import json
    feats = [{
        "type": "Feature",
        "properties": {k: r[k] for k in ("tile_id", "island", "paddy_ha")},
        "geometry": {"type": "Polygon", "coordinates": [[
            [r["lon_min"], r["lat_min"]], [r["lon_max"], r["lat_min"]],
            [r["lon_max"], r["lat_max"]], [r["lon_min"], r["lat_max"]],
            [r["lon_min"], r["lat_min"]]]]},
    } for r in rows]
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    return path
