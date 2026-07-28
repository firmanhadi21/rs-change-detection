#!/usr/bin/env python3
"""Forest-history scenario — multi-epoch deforestation from NDVI.

Give N date windows (4–5 typical) and this maps *when* forest was lost, not just
a before/after pair. Loss is defined relative to each pixel's own baseline NDVI
(robust to forest type, season, and TM/OLI differences): a pixel that started as
forest (baseline NDVI > forest threshold) is "lost" at the first epoch its NDVI
falls more than `drop` below that baseline.

Outputs:
  * a "year of loss" map — each originally-forested pixel coloured by the epoch it
    was cleared (green = still forest), so the deforestation front over time is visible;
  * a forest-area trajectory chart — intact original forest remaining at each epoch;
  * per-epoch NDVI GeoTIFFs and stats.json (forest area/%, loss per period, total).

Water is masked (MNDWI). --sensor landsat reaches the archive back to 1984; the
default Sentinel-2 covers 2015+. Backend: needs --backend gee.
"""

import json
import math
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

FOREST_THR = 0.6                  # baseline NDVI above this = "forest" at epoch 1
DROP_THR = 0.2                    # NDVI fall below baseline that counts as loss
DEFAULT_EPOCHS = [("2016-01-01", "2017-12-31"), ("2019-01-01", "2020-12-31"),
                  ("2022-01-01", "2023-12-31"), ("2024-01-01", "2025-12-31")]


# ----------------------------- GEE building blocks -----------------------------
def _ndvi_epoch(aoi, win, sensor):
    """Water-masked NDVI median composite for one epoch. Returns (ndvi, scene_count)."""
    from .indices import s2_median, l_sr_median
    if sensor == "landsat":
        img, n = l_sr_median(aoi, *win)
        ndvi = img.normalizedDifference(["NIR", "RED"])
        mndwi = img.normalizedDifference(["GREEN", "SWIR1"])
    else:
        img, n = s2_median(aoi, *win)
        ndvi = img.normalizedDifference(["B8", "B4"])
        mndwi = img.normalizedDifference(["B3", "B11"])
    return ndvi.updateMask(mndwi.lt(0)).rename("ndvi"), n


def _loss_year(ndvis, forest_thr, drop_thr):
    """Build the loss-epoch image + per-epoch intact-forest masks.

    loss=0 where still forest; loss=e where first dropped at epoch e; masked
    outside the baseline forest. Also returns intact[e] (forest not yet lost).
    """
    import ee
    base = ndvis[0]
    forest0 = base.gt(forest_thr)
    loss = ee.Image(0)
    ever = ee.Image(0)                       # cumulative "has dropped" flag
    intact = [forest0]                       # epoch 0: all baseline forest intact
    for e in range(1, len(ndvis)):
        drop_e = base.subtract(ndvis[e]).gt(drop_thr).And(forest0)
        newly = drop_e.And(ever.Not())
        loss = loss.where(newly, e)
        ever = ever.Or(drop_e)
        intact.append(forest0.And(ever.Not()))
    return loss.updateMask(forest0).rename("loss"), forest0, intact


def _area_ha(mask, aoi, scale):
    import ee
    a = (mask.multiply(ee.Image.pixelArea()).rename("area")
         .reduceRegion(ee.Reducer.sum(), aoi, scale, maxPixels=int(1e10),
                       bestEffort=True).get("area"))
    return a


# ----------------------------- rendering -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _add_basemap(ax):
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron,
                       attribution_size=5)
    except Exception as e:  # noqa: BLE001
        print(f"  (basemap skipped: {e.__class__.__name__})")


def _render_loss_map(tif, bbox, run_dir, name, years):
    import numpy as np
    import rasterio
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    plt = _plt()
    with rasterio.open(tif) as ds:
        a = ds.read(1).astype("float64")
    # 255 = not forest at baseline (unmask fill) → transparent. Value 0 is a real
    # class (still forest), so do NOT treat the download's nodata=0 tag as missing.
    a[a == 255] = np.nan
    w, s, e, n = bbox
    # 0 = still forest (green); 1..N-1 = lost at that epoch (sequential warm).
    nloss = len(years) - 1
    warm = plt.get_cmap("YlOrRd", max(nloss, 1))
    colors = ["#1a9850"] + [warm(i / max(nloss - 1, 1)) for i in range(nloss)]
    cmap = ListedColormap(colors); cmap.set_bad((0, 0, 0, 0))
    norm = BoundaryNorm(np.arange(-0.5, nloss + 1, 1), cmap.N)
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    ax.imshow(a, extent=[w, e, s, n], origin="upper", cmap=cmap, norm=norm,
              interpolation="nearest", alpha=0.85, zorder=2)
    handles = [Patch(facecolor=colors[0], label=f"Masih hutan ({years[0]})")]
    for i in range(nloss):
        handles.append(Patch(facecolor=colors[i + 1],
                             label=f"Hilang → {years[i + 1]}"))
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9,
              title="Kehilangan hutan")
    ax.set_title(f"Riwayat kehilangan hutan — {name}\n"
                 f"kapan tiap piksel hutan hilang ({years[0]}–{years[-1]})",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "forest_loss_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


def _render_trajectory(run_dir, name, years, forest_ha):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    ax.plot(years, forest_ha, "o-", color="#1a9850", lw=2.2, ms=6)
    ax.fill_between(years, forest_ha, color="#1a9850", alpha=0.12)
    base = forest_ha[0] or 1
    for x, y in zip(years, forest_ha):
        ax.annotate(f"{100*y/base:.0f}%", (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8, color="#166534")
    lost = forest_ha[0] - forest_ha[-1]
    ax.set_title(f"Hutan tersisa (dari tutupan awal) — {name}\n"
                 f"hilang {lost:,.0f} ha ({100*lost/base:.0f}%) {years[0]}→{years[-1]}",
                 fontsize=12, fontweight="bold")
    ax.set_ylabel("Luas hutan asli tersisa (ha)"); ax.set_xlabel("Tahun")
    ax.set_ylim(bottom=0); ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "forest_trajectory.png")
    fig.savefig(out); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        epochs=None, sensor="s2", forest_thr=FOREST_THR, drop_thr=DROP_THR):
    """Multi-epoch deforestation: year-of-loss map + forest-area trajectory (GEE)."""
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"forest-history needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("forest-history currently needs --backend gee.")
    import ee
    from .gee_utils import initialize_ee, square_aoi, download_geotiff
    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    eps = epochs or DEFAULT_EPOCHS
    if len(eps) < 2:
        raise SystemExit("forest-history needs at least 2 epochs (via --epochs).")
    years = [int(w[0][:4]) for w in eps]
    scale = 30

    ndvis, counts = [], []
    for win in eps:
        ndvi, n = _ndvi_epoch(aoi, win, sensor)
        if n == 0:
            raise SystemExit(f"No {sensor} scenes in {win[0]}..{win[1]} — widen the window.")
        ndvis.append(ndvi.clip(aoi)); counts.append(n)
        print(f"  epoch {win[0][:4]}: {n} scenes")

    loss, forest0, intact = _loss_year(ndvis, forest_thr, drop_thr)

    # Areas: intact original forest at each epoch (server-side, one fetch).
    areas = ee.List([_area_ha(m, aoi, scale) for m in intact]).getInfo()
    forest_ha = [round((a or 0) / 1e4, 1) for a in areas]           # m² → ha

    tif = os.path.join(run_dir, "forest_loss.tif")
    if download_geotiff(loss.toByte().unmask(255), aoi, tif, scale=scale) is not None:
        _render_loss_map(tif, bbox, run_dir, name, years)
    else:
        print("  (loss map skipped: download failed — try a smaller --radius)")
    _render_trajectory(run_dir, name, years, forest_ha)

    lost = round(forest_ha[0] - forest_ha[-1], 1)
    per_period = [round(forest_ha[i] - forest_ha[i + 1], 1) for i in range(len(years) - 1)]
    stats = {"run_id": run_id, "scenario": "forest-history", "name": name,
             "sensor": ("Landsat (archive to 1984)" if sensor == "landsat" else "Sentinel-2"),
             "method": "relative-drop from baseline NDVI, water-masked",
             "forest_threshold": forest_thr, "drop_threshold": drop_thr,
             "epochs": [list(w) for w in eps], "years": years, "scenes_per_epoch": counts,
             "forest_ha_by_epoch": dict(zip(years, forest_ha)),
             "loss_per_period_ha": {f"{years[i]}→{years[i+1]}": per_period[i]
                                    for i in range(len(per_period))},
             "total_loss_ha": lost,
             "total_loss_pct": round(100 * lost / (forest_ha[0] or 1), 1)}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nForest {years[0]}→{years[-1]} [{name}]: {forest_ha[0]:,.0f} → "
          f"{forest_ha[-1]:,.0f} ha  (−{lost:,.0f} ha, −{stats['total_loss_pct']:.0f}%)")
    return stats
