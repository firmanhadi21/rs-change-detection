#!/usr/bin/env python3
"""Population-change scenario — two GHSL epochs as a forest of 3D spikes.

Compares gridded population (GHSL GHS_POP) between two epochs (default
1990 & 2020) and classifies every cell:

  * grey    — present in both years (change within the neutral band, ±1%)
  * green   — gained population since the earlier year
  * magenta — lost population since the earlier year

Spike height (in the 2.5-D render and the forge3d export) is the *larger* of
the two populations on a log scale, so bigger settlements stand taller.

Outputs (in the run directory):
  * pop_change_map.png     — flat 2-D gained/lost/present map
  * pop_spikes.png         — 2.5-D "forest of spikes" (painter's-algorithm oblique view)
  * pop_change_class.tif   — class raster (1 present / 2 gained / 3 lost)
  * pop_<y1>.tif, pop_<y2>.tif — the two aggregated population grids
  * pop_cells.csv          — one row per drawn cell (lon, lat, pop1, pop2, delta,
                             pct, class, height) — ready for forge3d 3D rendering
  * stats.json

Inspired by Miloš Popović's GHSL population-spike maps. Backend: needs --backend gee.
"""

import json
import math
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

# GHS_POP P2023A epochs available in Earth Engine (5-yearly).
GHSL_EPOCHS = (1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010,
               2015, 2020, 2025, 2030)
NATIVE_M = 100                    # GHS_POP P2023A native cell (metres)
DEFAULT_YEARS = (1990, 2020)
NEUTRAL_PCT = 1.0                 # |Δ| within this % of the earlier year = "present"
MIN_POP = 150                     # cells below this (larger epoch) are not drawn
TARGET_COLS = 380                 # auto cell size aims for ~this many columns across

# Colours (light-theme palette from the reference graphic).
C_PRESENT = "#c8c6bf"
C_GAINED = "#1a7f5a"
C_LOST = "#b0217a"

# City labels for the poster, keyed by AOI name (lower-case, spaces→_). (name, lon, lat)
CITY_LABELS = {
    "jawa": [("Jakarta", 106.85, -6.20), ("Bekasi", 106.99, -6.24),
             ("Bogor", 106.80, -6.60), ("Tangerang", 106.63, -6.18),
             ("Bandung", 107.61, -6.91), ("Cirebon", 108.55, -6.73),
             ("Tegal", 109.14, -6.87), ("Pekalongan", 109.68, -6.89),
             ("Semarang", 110.42, -6.97), ("Yogyakarta", 110.37, -7.80),
             ("Surakarta", 110.83, -7.56), ("Surabaya", 112.75, -7.25),
             ("Malang", 112.63, -7.98), ("Kediri", 112.01, -7.82),
             ("Madiun", 111.52, -7.63), ("Jember", 113.70, -8.17),
             ("Cilacap", 109.02, -7.73), ("Banyuwangi", 114.37, -8.22)],
    "sumatera": [("Medan", 98.67, 3.59), ("Padang", 100.37, -0.95),
                 ("Palembang", 104.76, -2.98), ("Pekanbaru", 101.45, 0.51),
                 ("Bandar Lampung", 105.27, -5.43), ("Banda Aceh", 95.32, 5.55),
                 ("Jambi", 103.61, -1.61), ("Bengkulu", 102.26, -3.79),
                 ("Batam", 104.03, 1.13), ("Pematangsiantar", 99.06, 2.96)],
    "kalimantan": [("Pontianak", 109.34, -0.02), ("Banjarmasin", 114.59, -3.32),
                   ("Samarinda", 117.15, -0.50), ("Balikpapan", 116.83, -1.24),
                   ("Palangkaraya", 113.92, -2.21), ("Tarakan", 117.59, 3.30),
                   ("Singkawang", 108.98, 0.91)],
    "sulawesi": [("Makassar", 119.42, -5.15), ("Manado", 124.85, 1.49),
                 ("Palu", 119.87, -0.90), ("Kendari", 122.51, -3.99),
                 ("Gorontalo", 123.06, 0.54), ("Parepare", 119.62, -4.01),
                 ("Baubau", 122.61, -5.47)],
    "papua": [("Jayapura", 140.72, -2.53), ("Sorong", 131.25, -0.88),
              ("Manokwari", 134.06, -0.86), ("Merauke", 140.40, -8.49),
              ("Timika", 136.89, -4.55), ("Nabire", 135.51, -3.36),
              ("Biak", 136.08, -1.18), ("Wamena", 138.94, -4.10)],
    "bali": [("Denpasar", 115.22, -8.67), ("Singaraja", 115.10, -8.11)],
    "nusa_tenggara": [("Mataram", 116.12, -8.58), ("Kupang", 123.61, -10.18),
                      ("Bima", 118.73, -8.46)],
    "nusa_tenggara_barat": [("Mataram", 116.12, -8.58), ("Bima", 118.73, -8.46),
                            ("Sumbawa Besar", 117.43, -8.50), ("Praya", 116.27, -8.71)],
    "nusa_tenggara_timur": [("Kupang", 123.61, -10.18), ("Ende", 121.66, -8.84),
                            ("Maumere", 122.21, -8.62), ("Waingapu", 120.26, -9.65),
                            ("Labuan Bajo", 119.89, -8.49), ("Atambua", 124.89, -9.11)],
    "maluku": [("Ambon", 128.19, -3.70), ("Ternate", 127.38, 0.79),
               ("Tual", 132.75, -5.63)],
    "indonesia": [("Jakarta", 106.85, -6.20), ("Surabaya", 112.75, -7.25),
                  ("Bandung", 107.61, -6.91), ("Medan", 98.67, 3.59),
                  ("Semarang", 110.42, -6.97), ("Makassar", 119.42, -5.15),
                  ("Palembang", 104.76, -2.98), ("Denpasar", 115.22, -8.67),
                  ("Balikpapan", 116.83, -1.24), ("Jayapura", 140.72, -2.53)],
}


# ----------------------------- GEE building blocks -----------------------------
def _resolve_aoi(country, bbox, lon, lat, radius):
    """Return an ee.Geometry for the requested area of interest."""
    import ee
    if country:
        fc = (ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
              .filter(ee.Filter.eq("country_na", country)))
        if fc.size().getInfo() == 0:
            raise SystemExit(f"--country {country!r} not found in LSIB. "
                             "Use the English country name, e.g. 'Indonesia'.")
        return fc.geometry()
    if bbox:
        return ee.Geometry.Rectangle(list(bbox))
    from .gee_utils import square_aoi
    return square_aoi(lon, lat, radius)


def _pop_epoch(year, cell_m):
    """GHS_POP for the nearest epoch, summed up to a `cell_m` grid. Returns (img, ep)."""
    import ee
    ep = min(GHSL_EPOCHS, key=lambda e: abs(e - year))
    img = ee.Image(f"JRC/GHSL/P2023A/GHS_POP/{ep}").select("population_count")
    img = img.updateMask(img.gte(0))          # GHS_POP fills no-data with -200
    factor = max(1, round(cell_m / NATIVE_M))
    if factor > 1:
        # Sum the native 100 m population counts into each coarse cell.
        img = (img.reduceResolution(ee.Reducer.sum().unweighted(),
                                    maxPixels=min(factor * factor + 4, 65535))
               .reproject(img.projection().atScale(cell_m)))
    return img.rename("pop"), ep


def _fetch_tile(img, region, cell_m, tp):
    """Download one tile as a GeoTIFF at fixed scale. Returns tp or None on failure."""
    import ee  # noqa: F401
    from .gee_utils import _fetch
    try:
        url = img.getDownloadURL({"region": region, "scale": cell_m, "crs": "EPSG:4326",
                                  "format": "GEO_TIFF", "filePerBand": False})
        _fetch(url, tp)
        return tp
    except Exception as e:  # noqa: BLE001
        print(f"    tile failed ({e.__class__.__name__}) — skipped")
        return None


def _mosaic(tiles, out_path):
    """Merge tile GeoTIFFs into one, clean up the tiles, return out_path."""
    import rasterio
    from rasterio.merge import merge
    if len(tiles) == 1:
        os.replace(tiles[0], out_path)
        return out_path
    srcs = [rasterio.open(t) for t in tiles]
    mosaic, transform = merge(srcs)
    prof = srcs[0].profile
    prof.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform)
    for sc in srcs:
        sc.close()
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(mosaic[0], 1)
    for t in tiles:
        os.remove(t)
    print(f"Saved: {os.path.normpath(out_path)}  ({mosaic.shape[2]}×{mosaic.shape[1]} cells, "
          f"{len(tiles)} tiles)")
    return out_path


def _download_agg(img, box, cell_m, out_path, max_deg=4.0):
    """Download an aggregated image, tiling the region so each Earth Engine request
    only computes its own native pixels (a national reduceResolution in one request
    exceeds the compute limit). Small AOIs download as a single tile — no overhead.
    """
    import math
    import ee
    w, s, e, n = box
    nx = max(1, math.ceil((e - w) / max_deg))
    ny = max(1, math.ceil((n - s) / max_deg))
    if nx * ny > 1:
        print(f"  tiling download: {nx}×{ny} = {nx*ny} tiles at {cell_m/1000:.1f} km")
    tiles = []
    for j in range(ny):
        for i in range(nx):
            tw, te = w + (e - w) * i / nx, w + (e - w) * (i + 1) / nx
            ts, tn = s + (n - s) * j / ny, s + (n - s) * (j + 1) / ny
            region = ee.Geometry.Rectangle([tw, ts, te, tn])
            tp = _fetch_tile(img, region, cell_m,
                             out_path.replace(".tif", f"__t{j}_{i}.tif"))
            if tp:
                tiles.append(tp)
        if nx * ny > 1:
            print(f"    row {j+1}/{ny} done ({len(tiles)} tiles)")
    return _mosaic(tiles, out_path) if tiles else None


def _auto_cell_m(bbox):
    """Pick a cell size (metres) so the map is ~TARGET_COLS cells wide."""
    w, s, e, n = bbox
    mid = math.radians((s + n) / 2)
    width_km = (e - w) * 111.32 * max(math.cos(mid), 0.1)
    cell_km = width_km / TARGET_COLS
    cell_km = min(max(cell_km, 1.0), 25.0)      # clamp 1..25 km
    return round(cell_km * 1000)


# ----------------------------- classification -----------------------------
def _classify(p1, p2, neutral_pct, min_pop):
    """Numpy arrays -> (cls, delta, pct, height). cls: 0 none,1 present,2 gain,3 loss."""
    import numpy as np
    p1 = np.nan_to_num(p1, nan=0.0)
    p2 = np.nan_to_num(p2, nan=0.0)
    bigger = np.maximum(p1, p2)
    delta = p2 - p1
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(p1 > 0, 100.0 * delta / p1,
                       np.where(p2 > 0, 999.0, 0.0))     # brand-new cells: big +%
    cls = np.zeros(p1.shape, dtype="uint8")
    drawn = bigger >= min_pop
    gain = drawn & (pct > neutral_pct)
    loss = drawn & (pct < -neutral_pct)
    present = drawn & ~gain & ~loss
    cls[present] = 1
    cls[gain] = 2
    cls[loss] = 3
    with np.errstate(divide="ignore", invalid="ignore"):
        height = np.where(bigger > 0, np.log10(bigger), 0.0)
    return cls, delta, pct, height


def _country_geojson(aoi):
    """Simplified GeoJSON of the AOI outline (fetched once, reused across regions)."""
    try:
        return aoi.simplify(maxError=2000).getInfo()    # ~2 km simplify keeps it cheap
    except Exception as e:  # noqa: BLE001
        print(f"  (country outline fetch failed: {e.__class__.__name__})")
        return None


def _rasterize_mask(gj, box, shape):
    """Boolean grid (shape) True inside the GeoJSON outline, for numpy-side clipping."""
    if gj is None:
        return None
    try:
        from rasterio.features import rasterize
        from rasterio.transform import from_bounds
        transform = from_bounds(*box, shape[1], shape[0])
        m = rasterize([(gj, 1)], out_shape=shape, transform=transform,
                      fill=0, all_touched=True, dtype="uint8")
        return m.astype(bool)
    except Exception as e:  # noqa: BLE001
        print(f"  (country clip skipped: {e.__class__.__name__})")
        return None


# ----------------------------- rendering -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _read(tif):
    import numpy as np
    import rasterio
    with rasterio.open(tif) as ds:
        a = ds.read(1, masked=True).astype("float64").filled(0.0)
        b = ds.bounds
    a = np.where(a < 0, 0.0, a)                # defensively drop any no-data fill
    return a, [b.left, b.bottom, b.right, b.top]


def _render_flat_map(cls, bbox, run_dir, name, years, counts):
    import numpy as np
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    plt = _plt()
    w, s, e, n = bbox
    disp = cls.astype("float64")
    disp[cls == 0] = np.nan
    cmap = ListedColormap([C_PRESENT, C_GAINED, C_LOST])
    cmap.set_bad((0, 0, 0, 0))
    norm = BoundaryNorm([0.5, 1.5, 2.5, 3.5], cmap.N)
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.imshow(disp, extent=[w, e, s, n], origin="upper", cmap=cmap, norm=norm,
              interpolation="nearest")
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    ax.set_aspect(1 / math.cos(math.radians((s + n) / 2)))
    handles = [Patch(facecolor=C_GAINED, label=f"gained since {years[0]}"),
               Patch(facecolor=C_LOST, label=f"lost since {years[0]}"),
               Patch(facecolor=C_PRESENT, label="present in both years")]
    ax.legend(handles=handles, loc="lower left", fontsize=9, framealpha=0.92)
    ax.set_title(f"Population change {years[0]}–{years[1]} — {name}\n"
                 f"{counts[0]/1e6:.1f} M → {counts[1]/1e6:.1f} M people",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.35)
    fig.tight_layout()
    out = os.path.join(run_dir, "pop_change_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


def _spike_collection(cls, height, bbox, dark=False):
    """Build the oblique 2.5-D spike geometry for one grid.

    Painter's-algorithm PolyCollection (far/north drawn first) with the ground
    plane receding north (far rows higher and sheared right) so spikes separate
    into a "forest". Returns (PolyCollection, xlim, ylim) or (None, None, None).
    """
    import numpy as np
    from matplotlib.collections import PolyCollection
    w, s, e, n = bbox
    rows, colsN = cls.shape
    lons = w + (np.arange(colsN) + 0.5) * (e - w) / colsN
    lats = n - (np.arange(rows) + 0.5) * (n - s) / rows
    hmax = float(height.max()) if height.size else 1.0
    hmin = float(height[cls > 0].min()) if (cls > 0).any() else 0.0
    span = max(hmax - hmin, 1e-6)
    lat_span, lon_span = n - s, e - w
    tilt, shear = 0.50, 0.45              # plane squash, farthest-row rightward shift
    vscale = 0.55 * lat_span             # tallest spike height
    halfw = 0.42 * lon_span / colsN      # spike base half-width (lon units)
    fg = {1: C_PRESENT, 2: ("#2fe38f" if dark else C_GAINED),
          3: ("#ff36c0" if dark else C_LOST)}
    verts, facecolors = [], []
    for r in range(rows):                # far (north) → near (south)
        depth = (lats[r] - s) / lat_span
        y0 = s + (lats[r] - s) * tilt
        xshift = shear * depth * lon_span
        for c in range(colsN):
            k = cls[r, c]
            if k == 0:
                continue
            hn = (height[r, c] - hmin) / span
            x = lons[c] + xshift
            verts.append([(x - halfw, y0), (x + halfw, y0), (x, y0 + hn * vscale)])
            facecolors.append(fg[k])
    if not verts:
        return None, None, None
    coll = PolyCollection(verts, facecolors=facecolors, edgecolors="none",
                          linewidths=0, antialiased=True)
    xlim = (w - halfw, e + shear * lon_span + halfw)
    ylim = (s - 0.02 * lat_span, s + lat_span * tilt + vscale + 0.06 * lat_span)
    return coll, xlim, ylim


def _place_spikes(ax, coll, xlim, ylim, bbox):
    """Add a spike collection to an axis with the right extent and aspect."""
    s, n = bbox[1], bbox[3]
    ax.add_collection(coll)
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_aspect(1 / math.cos(math.radians((s + n) / 2)))
    ax.axis("off")


def _write_cells_csv(cls, p1, p2, delta, pct, height, bbox, run_dir, years):
    """One row per drawn cell — a generic per-cell table for custom 3-D tools.

    (The built-in forge3d GPU render, --forge3d, uses the height GeoTIFF + class
    overlay written by forge3d_render.py, not this CSV.)
    """
    import numpy as np
    w, s, e, n = bbox
    rows, colsN = cls.shape
    lon = w + (np.arange(colsN) + 0.5) * (e - w) / colsN
    lat = n - (np.arange(rows) + 0.5) * (n - s) / rows
    out = os.path.join(run_dir, "pop_cells.csv")
    label = {1: "present", 2: "gained", 3: "lost"}
    with open(out, "w") as f:
        f.write(f"lon,lat,pop_{years[0]},pop_{years[1]},delta,pct,class,height\n")
        rr, cc = np.where(cls > 0)
        for r, c in zip(rr.tolist(), cc.tolist()):
            f.write(f"{lon[c]:.5f},{lat[r]:.5f},{p1[r,c]:.1f},{p2[r,c]:.1f},"
                    f"{delta[r,c]:.1f},{pct[r,c]:.2f},{label[int(cls[r,c])]},"
                    f"{height[r,c]:.4f}\n")
    print(f"Cells: {os.path.normpath(out)}  ({int((cls>0).sum()):,} cells) "
          "— per-cell table for custom 3D tools (built-in GPU render: --forge3d)")
    return out


# Main island groups of Indonesia (lon w, lat s, lon e, lat n). Chosen roughly
# disjoint; each is clipped to the country outline so neighbours (Malaysia on
# Borneo, PNG on New Guinea) drop out.
INDONESIA_REGIONS = {
    "Sumatera":             (95.0, -6.0, 106.2, 6.1),
    "Jawa":                 (105.0, -8.9, 114.6, -5.8),
    "Bali":                 (114.4, -8.9, 115.8, -8.0),
    "Nusa_Tenggara_Barat":  (115.8, -9.3, 119.3, -8.0),
    "Nusa_Tenggara_Timur":  (118.9, -11.1, 125.2, -7.9),
    "Kalimantan":           (108.8, -4.2, 119.0, 3.5),
    "Sulawesi":             (118.8, -6.1, 125.2, 2.1),
    "Maluku":               (125.2, -8.5, 130.9, 2.6),
    "Papua":                (130.9, -9.2, 141.1, 0.9),
}
REGION_PRESETS = {"indonesia": INDONESIA_REGIONS}


def _write_class_raster(cls, src_tif, box1, run_dir):
    try:
        import rasterio
        from rasterio.transform import from_bounds
        with rasterio.open(src_tif) as ds0:
            prof = ds0.profile
        prof.update(dtype="uint8", count=1, nodata=0,
                    height=cls.shape[0], width=cls.shape[1],
                    transform=from_bounds(*box1, cls.shape[1], cls.shape[0]))
        with rasterio.open(os.path.join(run_dir, "pop_change_class.tif"), "w", **prof) as dst:
            dst.write(cls, 1)
    except Exception as e:  # noqa: BLE001
        print(f"  (class raster skipped: {e.__class__.__name__})")


def _fetch_terrain(box, cell_m, run_dir):
    """Download an SRTM elevation grid on the same grid, for the poster's
    hillshaded terrain basemap. Best-effort — the poster falls back to a flat
    silhouette if this fails."""
    import ee
    out = os.path.join(run_dir, "terrain.tif")
    if os.path.exists(out):
        return out
    try:
        dem = ee.Image("CGIAR/SRTM90_V4").select("elevation")
        return _download_agg(dem, box, cell_m, out)
    except Exception as e:  # noqa: BLE001
        print(f"  (terrain basemap skipped: {e.__class__.__name__})")
        return None


def _process_area(box, cell_m, years, neutral_pct, min_pop, run_dir, name, run_id,
                  clip_gj=None, forge3d=False, forge3d_prep_only=False):
    """Download two epochs over `box`, classify, optionally clip to a country outline,
    and write per-area outputs. Returns a result dict, or None if the download fails.
    """
    import numpy as np
    y1, y2 = years
    img1, ep1 = _pop_epoch(y1, cell_m)
    img2, ep2 = _pop_epoch(y2, cell_m)
    tif1 = os.path.join(run_dir, f"pop_{ep1}.tif")
    tif2 = os.path.join(run_dir, f"pop_{ep2}.tif")
    if _download_agg(img1, box, cell_m, tif1) is None or \
       _download_agg(img2, box, cell_m, tif2) is None:
        return None
    _fetch_terrain(box, cell_m, run_dir)
    p1, box1 = _read(tif1)
    p2, _ = _read(tif2)
    r = min(p1.shape[0], p2.shape[0]); c = min(p1.shape[1], p2.shape[1])
    p1, p2 = p1[:r, :c], p2[:r, :c]
    mask = None
    if clip_gj is not None:                       # keep only cells inside the country
        mask = _rasterize_mask(clip_gj, box1, p1.shape)
        if mask is not None:
            p1 = np.where(mask, p1, 0.0); p2 = np.where(mask, p2, 0.0)
    cls, delta, pct, height = _classify(p1, p2, neutral_pct, min_pop)
    _write_class_raster(cls, tif1, box1, run_dir)
    tot1, tot2 = float(p1.sum()), float(p2.sum())
    _render_flat_map(cls, box1, run_dir, name, (y1, y2), (tot1, tot2))
    _render_poster(p1, p2, box1, run_dir, name, (y1, y2), neutral_pct, min_pop,
                   dark=False, clip_mask=mask)
    _render_poster(p1, p2, box1, run_dir, name, (y1, y2), neutral_pct, min_pop,
                   dark=True, clip_mask=mask)
    _write_cells_csv(cls, p1, p2, delta, pct, height, box1, run_dir, (y1, y2))
    if forge3d or forge3d_prep_only:
        from . import forge3d_render
        forge3d_render.render(tif1, tif2, run_dir, name, (y1, y2),
                              neutral_pct=neutral_pct, min_pop=min_pop,
                              prep_only=forge3d_prep_only)
    gained_pop = float(delta[cls == 2].sum()); lost_pop = float(-delta[cls == 3].sum())
    stats = {"run_id": run_id, "scenario": "population-change", "name": name,
             "dataset": "GHSL GHS_POP P2023A", "epochs": [ep1, ep2],
             "cell_km": round(cell_m / 1000, 2), "aoi_bbox": [round(v, 4) for v in box],
             "neutral_pct": neutral_pct, "min_pop": min_pop,
             f"pop_{ep1}": round(tot1), f"pop_{ep2}": round(tot2),
             "net_change": round(tot2 - tot1),
             "net_change_pct": round(100 * (tot2 - tot1) / (tot1 or 1), 2),
             "cells_gained": int((cls == 2).sum()), "cells_lost": int((cls == 3).sum()),
             "cells_present": int((cls == 1).sum()),
             "pop_gained": round(gained_pop), "pop_lost": round(lost_pop)}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"  {name}: {tot1/1e6:.2f} M → {tot2/1e6:.2f} M  "
          f"(net {(tot2-tot1)/1e6:+.2f} M, {stats['net_change_pct']:+.1f}%)")
    return {"name": name, "cls": cls, "height": height, "box": box1,
            "tot1": tot1, "tot2": tot2, "ep1": ep1, "ep2": ep2, "stats": stats}


def _render_region_panel(results, run_dir, years, title):
    """One dark figure: a spike forest per island group, laid out on a grid."""
    import math as _m
    from matplotlib.patches import Patch
    plt = _plt()
    n = len(results)
    ncols = 4 if n > 4 else n
    nrows = _m.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 4.6 * nrows), dpi=150)
    bg = "#141414"
    fig.patch.set_facecolor(bg)
    axes = axes.ravel() if hasattr(axes, "ravel") else [axes]
    for ax in axes:
        ax.set_facecolor(bg); ax.axis("off")
    for ax, res in zip(axes, results):
        coll, xlim, ylim = _spike_collection(res["cls"], res["height"], res["box"], dark=True)
        pct = res["stats"]["net_change_pct"]
        ax.set_title(f"{res['name'].replace('_', ' ')}   {pct:+.0f}%\n"
                     f"{res['tot1']/1e6:.1f} → {res['tot2']/1e6:.1f} M",
                     fontsize=12, fontweight="bold", color="#eee", pad=4,
                     linespacing=1.3)
        if coll is None:
            continue
        _place_spikes(ax, coll, xlim, ylim, res["box"])
    handles = [Patch(facecolor="#2fe38f", label=f"gained since {years[0]}"),
               Patch(facecolor="#ff36c0", label=f"lost since {years[0]}"),
               Patch(facecolor=C_PRESENT, label="present in both")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=11,
               facecolor="#222", edgecolor="#444", labelcolor="#eee",
               bbox_to_anchor=(0.5, 0.005))
    fig.suptitle(f"Population change {years[0]}–{years[1]} — {title} by main island",
                 fontsize=20, fontweight="bold", color="#fff", y=0.985)
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    out = os.path.join(run_dir, "pop_islands_panel.png")
    fig.savefig(out, facecolor=bg); plt.close(fig)
    print(f"\nIslands panel: {os.path.normpath(out)}")


# ----------------------------- infographic poster -----------------------------
# Cities per epoch grid cell (~5 km) below this population are not a "city centre".
POSTER_CELL_KM = 5.0
CITY_MIN = 45000
PEAK_FOOTPRINT = 5


def _poster_palette(dark):
    if dark:
        return dict(bg="#141414", ground="#333333", body="#8a8a8a",
                    gain="#2fe38f", loss="#ff3b3b", text="#eeeeee",
                    sub="#b9b9b9", faint="#8a8a8a")
    return dict(bg="#f3f0ea", ground="#d7d3c8", body="#9a978d",
                gain="#1a9e6a", loss="#d21f1f", text="#20242a",
                sub="#555b62", faint="#7a7f86")


def _coarsen_sum(a, f):
    """Block-sum an array by an integer factor (population-preserving down-sample)."""
    if f <= 1:
        return a
    r = (a.shape[0] // f) * f; c = (a.shape[1] // f) * f
    return a[:r, :c].reshape(r // f, f, c // f, f).sum(axis=(1, 3))


def _detect_cities(p1, p2, box):
    """Cities = local population maxima. Returns (lon, lat, row, col, thr)."""
    import numpy as np
    from scipy.ndimage import maximum_filter
    w, s, e, n = box
    rows, cols = p1.shape
    lons = w + (np.arange(cols) + 0.5) * (e - w) / cols
    lats = n - (np.arange(rows) + 0.5) * (n - s) / rows
    cell_km = (e - w) / cols * 111.0 * max(math.cos(math.radians((s + n) / 2)), 0.1)
    thr = CITY_MIN * (cell_km / POSTER_CELL_KM) ** 2      # scale threshold to cell area
    bigger = np.maximum(p1, p2)
    peaks = (bigger == maximum_filter(bigger, size=PEAK_FOOTPRINT, mode="constant")) \
        & (bigger >= thr)
    pr, pc = np.where(peaks)
    return lons[pc], lats[pr], pr, pc, int(thr)


def _city_catchments(clon, clat, p1, p2, box, max_km=25.0):
    """Sum each city's population over its catchment for both epochs.

    Every populated cell is assigned to its nearest city (within max_km), so a
    city's growth is judged on the whole urban area — not the single peak cell,
    whose saturated core can read "stable" while the city booms around it
    (e.g. Jakarta, Bandung).
    """
    import numpy as np
    from scipy.spatial import cKDTree
    w, s, e, n = box
    rows, cols = p1.shape
    kx = 111.32 * max(math.cos(math.radians((s + n) / 2)), 0.1)
    lons = w + (np.arange(cols) + 0.5) * (e - w) / cols
    lats = n - (np.arange(rows) + 0.5) * (n - s) / rows
    tree = cKDTree(np.c_[clon * kx, clat * 110.57])
    rr, cc = np.where((p1 > 0) | (p2 > 0))
    pts = np.c_[lons[cc] * kx, lats[rr] * 110.57]
    dist, idx = tree.query(pts, distance_upper_bound=max_km)
    ok = np.isfinite(dist)
    csum1 = np.zeros(clon.size); csum2 = np.zeros(clon.size)
    np.add.at(csum1, idx[ok], p1[rr[ok], cc[ok]])
    np.add.at(csum2, idx[ok], p2[rr[ok], cc[ok]])
    return csum1, csum2


def _city_spikes(clon, clat, cpop1, cpop2, cdy, box, pal, neutral_pct):
    """Two-tone spikes (grey body to 1990 level, coloured tip for the change).

    `cdy` lifts each spike base by its cell's terrain height in axis units.
    """
    import numpy as np
    w, s, e, n = box
    lon_span, lat_span = e - w, n - s
    cbig = np.maximum(cpop1, cpop2)
    lo, hi = math.log10(max(cbig.min(), 1)), math.log10(max(cbig.max(), 1))

    def hn(x):
        return min(1.0, max(0.0, (math.log10(max(x, 1)) - lo) / max(hi - lo, 1e-6)))

    tilt, shear = 0.58, 0.26
    vscale, halfw = 0.34 * lat_span, 0.008 * lon_span
    body_v, tip_v, tip_c = [], [], []
    for k in np.argsort(cbig):                    # small first, big drawn in front
        by = s + (clat[k] - s) * tilt + cdy[k]
        bx = clon[k] + shear * ((clat[k] - s) / lat_span) * lon_span
        h_max = hn(cbig[k]) * vscale
        h_min = hn(min(cpop1[k], cpop2[k])) * vscale
        pct = 100.0 * (cpop2[k] - cpop1[k]) / max(cpop1[k], 1)
        col = (pal["body"] if abs(pct) <= neutral_pct
               else pal["gain"] if pct > 0 else pal["loss"])
        if col != pal["body"]:
            # The log scale squeezes a +35% change to a sliver at the top of a
            # tall spike, and the cone tapers to a few pixels there — keep
            # changed tips at least the top 30% so the colour reads.
            h_min = min(h_min, 0.70 * h_max)
        hw = (lambda h: halfw * (1 - h / h_max)) if h_max > 0 else (lambda h: halfw)
        body_v.append([(bx - halfw, by), (bx + halfw, by),
                       (bx + hw(h_min), by + h_min), (bx - hw(h_min), by + h_min)])
        tip_c.append(col)
        tip_v.append([(bx - hw(h_min), by + h_min), (bx + hw(h_min), by + h_min),
                      (bx, by + h_max)])
    xlim = (w - halfw, e + shear * lon_span + halfw)
    ylim = (s - 0.03 * lat_span,
            s + lat_span * tilt + vscale + 0.10 * lat_span)

    def proj(lon, lat, h):
        return lon + shear * ((lat - s) / lat_span) * lon_span, s + (lat - s) * tilt + h
    return body_v, tip_v, tip_c, xlim, ylim, proj, hn, vscale, tilt, shear


ELEV_MAX_M = 3500.0               # Java's volcanoes; normalises terrain relief
ELEV_RELIEF = 0.07                # peak terrain lift, as a fraction of lat-span


def _load_terrain(run_dir, factor, shape):
    """Terrain grid coarsened (mean) to the poster grid, or None."""
    import numpy as np
    path = os.path.join(run_dir, "terrain.tif")
    if not os.path.exists(path):
        return None
    try:
        te, _ = _read(path)
        te = _coarsen_sum(te, factor) / max(factor * factor, 1)
        r = min(te.shape[0], shape[0]); c = min(te.shape[1], shape[1])
        out = np.zeros(shape, dtype="float64")
        out[:r, :c] = np.maximum(te[:r, :c], 0.0)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  (terrain read skipped: {e.__class__.__name__})")
        return None


def _ground_quads(land, box, elev=None, pal=None):
    """Ground parallelograms + facecolors + per-cell lift.

    With `elev`, the ground is a hillshaded terrain basemap: each land cell is
    lifted by its elevation and shaded (LightSource from the NW), so the
    island's relief reads. Without it, a flat grey silhouette. Returns
    (quads, colors, dy) where dy is the per-cell lift grid in axis units.
    """
    import numpy as np
    from matplotlib.colors import LightSource, to_rgb
    w, s, e, n = box
    rows, cols = land.shape
    lon_span, lat_span = e - w, n - s
    dlon, dlat = lon_span / cols, lat_span / rows
    lons = w + (np.arange(cols) + 0.5) * dlon
    lats = n - (np.arange(rows) + 0.5) * dlat
    tilt, shear = 0.58, 0.26

    dy = np.zeros((rows, cols))
    shade = None
    if elev is not None:
        try:
            from scipy.ndimage import gaussian_filter
            elev = gaussian_filter(elev, sigma=1.2)   # soften stair-step banding
        except Exception:  # noqa: BLE001
            pass
        dy = np.clip(elev / ELEV_MAX_M, 0, 1) * ELEV_RELIEF * lat_span
        cell_m = dlon * 111320.0 * max(math.cos(math.radians((s + n) / 2)), 0.1)
        ls = LightSource(azdeg=315, altdeg=45)
        shade = ls.hillshade(elev, vert_exag=6.0, dx=cell_m, dy=cell_m)
    base = np.array(to_rgb(pal["ground"]))

    def proj(lon, lat, h):
        return lon + shear * ((lat - s) / lat_span) * lon_span, s + (lat - s) * tilt + h
    quads, colors = [], []
    for i in range(rows):                          # far (north) → near (south)
        lat = lats[i]
        for j in range(cols):
            if not land[i, j]:
                continue
            lon, h = lons[j], dy[i, j]
            hx, hy = dlon * 0.53, dlat * 0.53      # slight overlap: no cracks on lift
            quads.append([proj(lon - hx, lat + hy, h), proj(lon + hx, lat + hy, h),
                          proj(lon + hx, lat - hy, h), proj(lon - hx, lat - hy, h)])
            if shade is not None:
                colors.append(tuple(np.clip(base * (0.62 + 0.55 * shade[i, j]), 0, 1)))
            else:
                colors.append(tuple(base))
    return quads, colors, dy


def _poster_labels(ax, clon, clat, cpop1, cpop2, cdy, name, box, pal, proj, hn, vscale):
    """Label known cities by attaching each name to its nearest city spike."""
    import numpy as np
    labels = CITY_LABELS.get(name.lower().replace(" ", "_"), [])
    if not labels or clon.size == 0:
        return
    cbig = np.maximum(cpop1, cpop2)
    matched = []
    for nm, lo_, la_ in labels:
        k = int(np.argmin((clon - lo_) ** 2 + (clat - la_) ** 2))
        if (clon[k] - lo_) ** 2 + (clat[k] - la_) ** 2 <= 0.25 ** 2:
            matched.append((nm, k, float(cbig[k])))
    matched.sort(key=lambda m: -m[2])
    placed = []
    for nm, k, _ in matched:
        if any((clon[k] - clon[j]) ** 2 + (clat[k] - clat[j]) ** 2 < 0.30 ** 2 for j in placed):
            continue
        placed.append(k)
        bx, _by = proj(clon[k], clat[k], 0)
        ytop = box[1] + (clat[k] - box[1]) * 0.58 + cdy[k] + hn(cbig[k]) * vscale
        ax.annotate(nm, (bx, ytop), textcoords="offset points", xytext=(0, 4),
                    ha="center", fontsize=9, fontweight="bold", color=pal["text"], zorder=8)


def _render_poster(p1, p2, box, run_dir, name, years, neutral_pct, min_pop, dark,
                   clip_mask=None):
    """Miloš-style poster: one two-tone spike per city on a terrain basemap.

    `clip_mask` (full-res bool, True inside the country) also clips the terrain
    ground so neighbouring countries don't render as part of the island.
    """
    try:
        import numpy as np  # noqa: F401
        from scipy.ndimage import maximum_filter  # noqa: F401
    except ImportError:
        print("  (poster skipped: needs scipy — pip install 'earthchange[maps]')")
        return
    import numpy as np
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Rectangle
    plt = _plt()
    pal = _poster_palette(dark)
    factor = max(1, round(POSTER_CELL_KM / (((box[2] - box[0]) / p1.shape[1]) * 111.0)))
    q1, q2 = _coarsen_sum(p1, factor), _coarsen_sum(p2, factor)
    r = min(q1.shape[0], q2.shape[0]); c = min(q1.shape[1], q2.shape[1])
    q1, q2 = q1[:r, :c], q2[:r, :c]
    clon, clat, crow, ccol, thr = _detect_cities(q1, q2, box)
    if clon.size == 0:
        print("  (poster skipped: no city centres above threshold)")
        return
    # City totals over nearest-city catchments — not the single (often
    # saturated) peak cell, so a booming metro with a stable core reads green.
    cp1, cp2 = _city_catchments(clon, clat, q1, q2, box)
    elev = _load_terrain(run_dir, factor, q1.shape)
    land = np.maximum(q1, q2) > 0
    if elev is not None:
        land = land | (elev > 1.0)               # unpopulated mountains are still land
    if clip_mask is not None:                    # drop neighbouring countries' terrain
        qm = _coarsen_sum(clip_mask.astype("float64"), factor) > 0
        rm = min(qm.shape[0], land.shape[0]); cm = min(qm.shape[1], land.shape[1])
        land[:rm, :cm] &= qm[:rm, :cm]
        land[rm:, :] = False; land[:, cm:] = False
    gv, gc, dy = _ground_quads(land, box, elev=elev, pal=pal)
    cdy = dy[crow, ccol]
    body_v, tip_v, tip_c, xlim, ylim, proj, hn, vscale, tilt, shear = \
        _city_spikes(clon, clat, cp1, cp2, cdy, box, pal, neutral_pct)

    y1, y2 = years
    tot1, tot2 = float(p1.sum()), float(p2.sum())
    fig = plt.figure(figsize=(14, 8.0), dpi=150)
    fig.patch.set_facecolor(pal["bg"])
    ax = fig.add_axes([0.02, 0.09, 0.96, 0.56]); ax.set_facecolor(pal["bg"])
    ax.add_collection(PolyCollection(gv, facecolors=gc, edgecolors=gc, linewidths=0.3))
    ax.add_collection(PolyCollection(body_v, facecolors=pal["body"], edgecolors="none"))
    ax.add_collection(PolyCollection(tip_v, facecolors=tip_c, edgecolors="none"))
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_aspect(1 / math.cos(math.radians((box[1] + box[3]) / 2)))
    ax.axis("off")
    _poster_labels(ax, clon, clat, cp1, cp2, cdy, name, box, pal, proj, hn, vscale)

    fig.text(0.035, 0.945, f"Population change by city, {y1}–{y2}", fontsize=15, color=pal["sub"])
    title = name.replace("_", " ").upper()
    tfs = 52 if len(title) <= 12 else max(28, int(52 * 12 / len(title)))
    fig.text(0.033, 0.845, title, fontsize=tfs,
             fontweight="bold", color=pal["text"], family="serif")
    fig.text(0.035, 0.785, f"{tot1/1e6:.1f} M people in {y1}   →   {tot2/1e6:.1f} M in {y2}",
             fontsize=15, fontweight="bold", color=pal["text"])
    fig.text(0.035, 0.755, f"{clon.size} cities · each spike = a city, height ∝ its "
             "population (log).", fontsize=12.5, color=pal["sub"])
    lx = 0.62
    for i, (col, lab) in enumerate([(pal["gain"], f"grew since {y1} (green tip)"),
                                     (pal["loss"], f"shrank since {y1} (red tip)"),
                                     (pal["body"], f"{y1} level (grey)")]):
        y = 0.94 - i * 0.032
        fig.patches.append(Rectangle((lx, y), 0.02, 0.022, transform=fig.transFigure,
                                     facecolor=col, edgecolor="none"))
        fig.text(lx + 0.03, y + 0.003, lab, fontsize=12, color=pal["text"])
    fig.text(lx, 0.80, "Ground: shaded terrain. Tip colour = change of the whole city\n"
             "(every cell within 25 km of its peak), not just the centre cell.",
             fontsize=10.5, color=pal["sub"], linespacing=1.4, va="top")
    fig.text(0.035, 0.02, f"Data: GHSL GHS_POP (R2023A, {y1} & {y2}) + SRTM terrain. "
             f"Cities = local population peaks ≥ {thr:,}; change summed over "
             "nearest-city catchments.", fontsize=8.5, color=pal["faint"])
    fig.text(0.965, 0.02, "earthchange · inspired by Miloš Popović",
             fontsize=8.5, color=pal["faint"], ha="right")
    out = os.path.join(run_dir, "pop_poster_dark.png" if dark else "pop_poster.png")
    fig.savefig(out, facecolor=pal["bg"]); plt.close(fig)
    print(f"Poster: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def _run_regions(regions, country, years, cell_km, neutral_pct, min_pop,
                 run_dir, run_id):
    """Run the scenario per island group, then assemble a combined panel + totals."""
    aoi = _resolve_aoi(country, None, None, None, None)
    gj = _country_geojson(aoi)
    results = []
    for rname, box in regions.items():
        sub = os.path.join(run_dir, rname)
        os.makedirs(sub, exist_ok=True)
        cell_m = round(cell_km * 1000) if cell_km else _auto_cell_m(list(box))
        print(f"\n=== {rname}  cell={cell_m/1000:.1f} km ===")
        res = _process_area(list(box), cell_m, years, neutral_pct, min_pop,
                            sub, rname, run_id, clip_gj=gj)
        if res:
            results.append(res)
    if not results:
        raise SystemExit("No island group produced output.")
    _render_region_panel(results, run_dir, years, country or "Indonesia")
    tot1 = sum(r["tot1"] for r in results); tot2 = sum(r["tot2"] for r in results)
    agg = {"run_id": run_id, "scenario": "population-change",
           "mode": "by-island", "country": country, "epochs": list(years),
           "note": "regional boxes are ~disjoint; the sum is an approximate national total",
           "regions": {r["name"]: r["stats"] for r in results},
           "pop_earlier": round(tot1), "pop_later": round(tot2),
           "net_change": round(tot2 - tot1),
           "net_change_pct": round(100 * (tot2 - tot1) / (tot1 or 1), 2)}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(agg, f, indent=2)
    print(f"\nBy-island total {years[0]}→{years[1]}: {tot1/1e6:.1f} M → {tot2/1e6:.1f} M "
          f"({agg['net_change_pct']:+.1f}%)")
    for r in sorted(results, key=lambda x: x["stats"]["net_change_pct"], reverse=True):
        print(f"  {r['name']:<15} {r['stats']['net_change_pct']:+6.1f}%   "
              f"{r['tot1']/1e6:6.2f} → {r['tot2']/1e6:6.2f} M")
    return agg


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        country=None, bbox=None, years=DEFAULT_YEARS, cell_km=None,
        neutral_pct=NEUTRAL_PCT, min_pop=MIN_POP, dark=False, regions=None,
        forge3d=False, forge3d_prep_only=False):
    """Two-epoch GHSL population change: poster + map + optional forge3d GPU 3-D.

    `regions` (a name→bbox dict, e.g. INDONESIA_REGIONS) runs the scenario per
    island group and assembles a combined panel instead of one national frame.
    `forge3d` also renders a true GPU 3-D spike map via the forge3d library.
    """
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"population-change needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("population-change currently needs --backend gee (GHSL GHS_POP).")
    if len(years) != 2:
        raise SystemExit("population-change needs exactly two years, e.g. --pop-years 1990,2020")
    from .gee_utils import initialize_ee
    initialize_ee(config_key)
    y1, y2 = sorted(years)

    if regions:
        if not country:
            raise SystemExit("--regions needs --country (for the clip outline), e.g. "
                             "--country Indonesia")
        return _run_regions(regions, country, (y1, y2), cell_km, neutral_pct, min_pop,
                            run_dir, run_id)

    aoi = _resolve_aoi(country, bbox, lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    box = [min(xs), min(ys), max(xs), max(ys)]
    cell_m = round(cell_km * 1000) if cell_km else _auto_cell_m(box)
    print(f"  AOI {box[0]:.2f},{box[1]:.2f},{box[2]:.2f},{box[3]:.2f}  "
          f"cell={cell_m/1000:.1f} km")
    gj = _country_geojson(aoi) if country else None
    res = _process_area(box, cell_m, (y1, y2), neutral_pct, min_pop,
                        run_dir, name, run_id, clip_gj=gj,
                        forge3d=forge3d, forge3d_prep_only=forge3d_prep_only)
    if res is None:
        raise SystemExit("GHS_POP download failed — try a larger --cell-km or smaller area.")
    print(f"\nPopulation {res['ep1']}→{res['ep2']} [{name}]: {res['tot1']/1e6:.2f} M → "
          f"{res['tot2']/1e6:.2f} M  ({res['stats']['net_change_pct']:+.1f}%)")
    return res["stats"]
