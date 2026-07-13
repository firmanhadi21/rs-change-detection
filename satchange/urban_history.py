#!/usr/bin/env python3
"""Urban-history scenario — built-up expansion & vegetation loss by decade.

Two independent views of how a metro area urbanised since 1980:

  * GHSL GHS-BUILT-S (EU JRC) — authoritative built-up SURFACE per epoch
    (1980-2025, 100 m), the internally-consistent cross-decade series. GEE only
    (not hosted on Planetary Computer).
  * Landsat surface reflectance (L5 TM + L8/9 OLI, L7 skipped for SLC-off) —
    NDBI built-up and NDVI vegetation per decade, for the vegetation-loss story.

Cross-sensor honesty: Landsat TM and OLI NDVI are NOT comparable across the
2011->2013 break, so the code never stitches them into one absolute trend. The
vegetation-decline line + loss map use same-sensor TM epochs (1990/2000/2010);
OLI epochs (2020/2025) are reported separately; full-span vegetation-to-urban
conversion is measured by GHSL (new_urban).

Backends:
  gee  — full analysis (GHSL + Landsat).
  mpc  — Landsat-only (GHSL is not on Planetary Computer); still gives the
         decadal NDBI/NDVI panel, vegetation loss, and charts.

Outputs per run: a decadal built-up PANEL, a first-built-decade value-added map
(GEE), vegetation_loss + new_urban maps, builtup_trend + vegetation_trend
charts, and stats.json.
"""

import os
import json

# Clear a stale external PROJ override (e.g. an OTB install exporting PROJ_LIB)
# so rasterio/contextily use their OWN bundled PROJ database (see mapmaker.py).
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

try:
    import ee
except ImportError:
    ee = None

GHSL_YEARS = [1980, 1990, 2000, 2010, 2020, 2025]
DECADE_YEARS = [1980, 1990, 2000, 2010, 2020]   # 5 classes for the first-built map
LANDSAT_YEARS = [1990, 2000, 2010, 2020, 2025]  # L5/8/9 (1980 = MSS, skipped)
TM_YEARS = [1990, 2000, 2010]                   # Landsat-5 TM — mutually comparable
OLI_YEARS = [2020, 2025]                        # Landsat-8/9 OLI — comparable to each other

BUILT_M2_THR = 2000.0   # GHSL: >20% of a 100 m cell built-up = "built"
NDBI_THR = 0.0          # Landsat NDBI > 0 ~ built-up / bare (trend proxy)
NDVI_VEG_THR = 0.30     # NDVI above this = vegetated
NDVI_GONE_THR = 0.20    # NDVI below this at the end = vegetation lost
NDVI_LOSS_DROP = -0.15  # min NDVI drop to count as loss

DECADE_PALETTE = ["fee5d9", "fcae91", "fb6a4a", "de2d26", "a50f15"]
DECADE_LABELS = ["by 1980 (core)", "1980s", "1990s", "2000s", "2010s (newest)"]

INTERP = ("Peta 'dekade pertama terbangun': inti pucat = terbangun sebelum 1980; "
          "merah tua = perluasan terbaru. Grafik = luas terbangun & penurunan vegetasi.")


# ============================ GEE backend ============================
def _ghsl(year):
    return ee.Image(f"JRC/GHSL/P2023A/GHS_BUILT_S/{year}").select("built_surface")


def _sum_km2(built_surface_m2, aoi):
    v = built_surface_m2.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=100,
        maxPixels=int(1e10), bestEffort=True).get("built_surface")
    return ee.Number(v).divide(1e6).getInfo()


def _pct(mask, aoi, scale):
    v = mask.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=scale,
                          maxPixels=int(1e10), bestEffort=True).getInfo()
    vals = [x for x in v.values() if x is not None]
    return (vals[0] * 100.0) if vals else 0.0


def _mean(img, aoi, scale):
    v = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=scale,
                         maxPixels=int(1e10), bestEffort=True).getInfo()
    vals = [x for x in v.values() if x is not None]
    return vals[0] if vals else None


def _run_gee(lat, lon, radius, name, run_dir, run_id, do_map, config_key):
    from .gee_utils import (initialize_ee, square_aoi, download_png, download_geotiff)
    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    aoi_km2 = (2 * radius) ** 2
    stats = {"name": name, "backend": "gee", "source": "GHSL GHS-BUILT-S + Landsat",
             "location": {"lat": lat, "lon": lon}, "radius_km": radius,
             "aoi_km2": round(aoi_km2, 1), "ghsl": {}, "landsat": {}}

    print("GHSL built-up per epoch:")
    epoch_masks = []
    for y in GHSL_YEARS:
        km2 = _sum_km2(_ghsl(y), aoi)
        stats["ghsl"][str(y)] = {"builtup_km2": round(km2, 1),
                                 "builtup_pct_aoi": round(100.0 * km2 / aoi_km2, 1)}
        epoch_masks.append(_ghsl(y).gt(BUILT_M2_THR).rename(f"y{y}"))
        print(f"  {y}: {km2:8.1f} km2  ({100.0*km2/aoi_km2:4.1f}% of AOI)")
    builtup_epochs = ee.Image.cat(epoch_masks).clip(aoi)  # 6-band panel source

    # first-built decade (GHSL)
    code = ee.Image(0)
    for i, y in enumerate(DECADE_YEARS, start=1):
        code = code.where(code.eq(0).And(_ghsl(y).gt(BUILT_M2_THR)), i)
    first_built = code.selfMask().clip(aoi).rename("first_built")

    # Landsat NDBI/NDVI per epoch
    from .indices import l_sr_median
    print("Landsat NDBI/NDVI per epoch:")
    ndvi_by_year = {}
    for y in LANDSAT_YEARS:
        img, n = l_sr_median(aoi, f"{y}-01-01", f"{y}-12-31")
        sensor = "TM (L5)" if y <= 2011 else "OLI (L8/9)"
        ndbi = img.normalizedDifference(["SWIR1", "NIR"])
        ndvi = img.normalizedDifference(["NIR", "RED"])
        ndvi_by_year[y] = ndvi
        stats["landsat"][str(y)] = {
            "scenes": n, "sensor": sensor,
            "builtup_ndbi_pct": round(_pct(ndbi.gt(NDBI_THR), aoi, 30), 1),
            "vegetation_pct": round(_pct(ndvi.gt(NDVI_VEG_THR), aoi, 30), 1),
            "mean_ndvi": round(_mean(ndvi, aoi, 30) or 0.0, 3)}
        r = stats["landsat"][str(y)]
        print(f"  {y}: scenes={n:3d} {sensor:9s} built={r['builtup_ndbi_pct']:4.1f}%  "
              f"veg={r['vegetation_pct']:4.1f}%  meanNDVI={r['mean_ndvi']:.3f}")

    # vegetation loss (same-sensor TM 1990->2010)
    y0, y1 = TM_YEARS[0], TM_YEARS[-1]
    nd0, nd1 = ndvi_by_year[y0], ndvi_by_year[y1]
    vl = (nd0.gt(NDVI_VEG_THR).And(nd1.lt(NDVI_GONE_THR))
          .And(nd1.subtract(nd0).lt(NDVI_LOSS_DROP)))
    veg_loss = vl.selfMask().clip(aoi).rename("veg_loss")
    stats["vegetation_loss_TM"] = {"from_year": y0, "to_year": y1,
                                   "sensor": "Landsat-5 TM (same sensor)",
                                   "pct_lost": round(_pct(vl, aoi, 30), 1)}

    # authoritative full-span new built-up (GHSL 1990->2025)
    new_urban = (_ghsl(2025).gt(BUILT_M2_THR).And(_ghsl(1990).gt(BUILT_M2_THR).Not())
                 .selfMask().clip(aoi).rename("new_urban"))
    new_km2 = _sum_km2(_ghsl(2025).subtract(_ghsl(1990)).max(0), aoi)
    stats["urban_conversion_GHSL"] = {"from_year": 1990, "to_year": 2025,
                                      "new_builtup_km2": round(new_km2, 1),
                                      "new_builtup_pct_aoi": round(100.0 * new_km2 / aoi_km2, 1)}
    stats["notes"] = _NOTES

    # download products
    products = {
        "first_built_decade": (first_built, {"min": 1, "max": len(DECADE_YEARS),
                                             "palette": DECADE_PALETTE}, 100),
        "vegetation_loss": (veg_loss, {"min": 0, "max": 1, "palette": ["1a9850"]}, 30),
        "new_urban": (new_urban, {"min": 0, "max": 1, "palette": ["7a0177"]}, 100),
    }
    for key, (img, vis, scale) in products.items():
        print(f"Downloading {key}...")
        download_png(img, aoi, os.path.join(run_dir, key + ".png"), vis=vis)
        download_geotiff(img, aoi, os.path.join(run_dir, key + ".tif"), scale=scale)
    print("Downloading builtup_epochs (panel source)...")
    epochs_tif = os.path.join(run_dir, "builtup_epochs.tif")
    download_geotiff(builtup_epochs.toByte(), aoi, epochs_tif, scale=100)

    _render_all(stats, run_dir, epochs_tif, GHSL_YEARS,
                os.path.join(run_dir, "first_built_decade.tif"))
    _write_stats(stats, run_dir, run_id, "gee")


# ============================ MPC backend ============================
def _run_mpc(lat, lon, radius, name, run_dir, run_id, do_map):
    import numpy as np
    from .mpc_backend import square_bbox, _l_sr_median, _write_tif, _despeckle
    print("Backend: Microsoft Planetary Computer (Landsat-only — GHSL not on MPC)")
    bbox = square_bbox(lon, lat, radius)
    aoi_km2 = (2 * radius) ** 2
    stats = {"name": name, "backend": "mpc", "source": "Landsat (MPC); GHSL unavailable on MPC",
             "location": {"lat": lat, "lon": lon}, "radius_km": radius,
             "aoi_km2": round(aoi_km2, 1), "landsat": {}}

    def nd(a, b):
        return (a - b) / (a + b)

    print("Landsat NDBI/NDVI per epoch (MPC):")
    ndvi_by_year, ndbi_mask_by_year, gbox = {}, {}, None
    for y in LANDSAT_YEARS:
        ds, n, gb = _l_sr_median(bbox, f"{y}-01-01", f"{y}-12-31", geobox=gbox)
        if ds is None:
            print(f"  {y}: no scenes — skipped")
            continue
        gbox = gbox or gb
        RED, NIR, SWIR1 = ds["RED"].values, ds["NIR"].values, ds["SWIR1"].values
        ndvi = nd(NIR, RED)
        ndbi = nd(SWIR1, NIR)
        valid = np.isfinite(ndvi)
        ndvi_by_year[y] = ndvi
        ndbi_mask_by_year[y] = (ndbi > NDBI_THR) & valid
        m = max(int(valid.sum()), 1)
        stats["landsat"][str(y)] = {
            "scenes": n, "sensor": "TM (L5)" if y <= 2011 else "OLI (L8/9)",
            "builtup_ndbi_pct": round(100.0 * int(((ndbi > NDBI_THR) & valid).sum()) / m, 1),
            "vegetation_pct": round(100.0 * int(((ndvi > NDVI_VEG_THR) & valid).sum()) / m, 1),
            "mean_ndvi": round(float(np.nanmean(ndvi)), 3)}
        r = stats["landsat"][str(y)]
        print(f"  {y}: scenes={n:3d} {r['sensor']:9s} built={r['builtup_ndbi_pct']:4.1f}%  "
              f"veg={r['vegetation_pct']:4.1f}%  meanNDVI={r['mean_ndvi']:.3f}")

    # vegetation loss (same-sensor TM 1990->2010)
    y0, y1 = TM_YEARS[0], TM_YEARS[-1]
    veg_loss = None
    if y0 in ndvi_by_year and y1 in ndvi_by_year:
        nd0, nd1 = ndvi_by_year[y0], ndvi_by_year[y1]
        vl = (nd0 > NDVI_VEG_THR) & (nd1 < NDVI_GONE_THR) & ((nd1 - nd0) < NDVI_LOSS_DROP)
        vl = _despeckle(vl & np.isfinite(nd0) & np.isfinite(nd1), min_size=8)
        m = max(int(np.isfinite(nd0).sum()), 1)
        stats["vegetation_loss_TM"] = {"from_year": y0, "to_year": y1,
                                       "sensor": "Landsat-5 TM (same sensor)",
                                       "pct_lost": round(100.0 * int(vl.sum()) / m, 1)}
        veg_loss = np.where(vl, 1.0, np.nan)
        _write_tif(os.path.join(run_dir, "vegetation_loss.tif"), veg_loss, gbox, False)
    stats["notes"] = _NOTES + " GHSL is GEE-only; run with --backend gee for the " \
        "authoritative 1980-2025 built-up series and first-built-decade map."

    extent = [bbox[0], bbox[2], bbox[1], bbox[3]]
    panel_years = [y for y in LANDSAT_YEARS if y in ndbi_mask_by_year]
    _render_mpc(stats, run_dir, extent,
                [ndbi_mask_by_year[y] for y in panel_years], panel_years, veg_loss)
    _write_stats(stats, run_dir, run_id, "mpc")


# ============================ rendering ============================
_NOTES = ("GHSL GHS-BUILT-S is the authoritative cross-decade built-up series "
          "(internally consistent). Landsat NDVI/NDBI absolute values are NOT "
          "comparable across the TM->OLI break (2011->2013): TM epochs "
          "(1990/2000/2010) form one comparable group, OLI (2020/2025) another. "
          "The vegetation-loss map uses TM-only 1990->2010.")


def _basemap(ax):
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron,
                       attribution=False)
    except Exception as e:  # noqa: BLE001
        print(f"  (basemap skipped: {e})")


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _render_charts(stats, run_dir):
    plt = _plt()
    written = []
    if stats.get("ghsl"):
        gy = [int(y) for y in stats["ghsl"]]
        gkm = [stats["ghsl"][str(y)]["builtup_km2"] for y in gy]
        fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
        ax.plot(gy, gkm, "-o", color="#a50f15")
        for x, yv in zip(gy, gkm):
            ax.annotate(f"{yv:.0f}", (x, yv), textcoords="offset points",
                        xytext=(0, 6), ha="center", fontsize=7, color="#a50f15")
        ax.set_xlabel("Year"); ax.set_ylabel("GHSL built-up area (km²)", color="#a50f15")
        ax.set_title(f"Built-up expansion (GHSL) — {stats['name']}")
        ax.grid(True, ls=":", alpha=0.5)
        fig.tight_layout(); fig.savefig(os.path.join(run_dir, "builtup_trend.png")); plt.close(fig)
        written.append("builtup_trend.png")

    ls = stats["landsat"]
    tmy = [y for y in TM_YEARS if str(y) in ls]
    oliy = [y for y in OLI_YEARS if str(y) in ls]

    def veg(ys):
        return [ls[str(y)]["vegetation_pct"] for y in ys]

    def ndvi(ys):
        return [ls[str(y)]["mean_ndvi"] for y in ys]

    fig, ax1 = plt.subplots(figsize=(7, 4.2), dpi=150)
    ax1.plot(tmy, veg(tmy), "-o", color="#1a9850", label="Vegetation % (TM, comparable)")
    if oliy:
        ax1.plot(oliy, veg(oliy), "D", color="#66bd63", label="Vegetation % (OLI, separate)")
        brk = (max(tmy) + min(oliy)) / 2.0
        ax1.axvline(brk, color="#999", ls="--", lw=1)
        ax1.annotate("TM→OLI sensor break\n(not comparable across it)",
                     xy=(brk, ax1.get_ylim()[0]), fontsize=6.5, color="#666",
                     ha="center", va="bottom")
    ax1.set_xlabel("Year"); ax1.set_ylabel("Vegetated area (% AOI, NDVI>0.3)", color="#1a9850")
    ax2 = ax1.twinx()
    ax2.plot(tmy, ndvi(tmy), "--^", color="#7f7f7f")
    if oliy:
        ax2.plot(oliy, ndvi(oliy), "^", color="#bdbdbd")
    ax2.set_ylabel("Mean NDVI", color="#7f7f7f")
    ax1.legend(fontsize=7, loc="upper right")
    ax1.set_title(f"Vegetation decline (Landsat) — {stats['name']}")
    ax1.grid(True, ls=":", alpha=0.5)
    fig.tight_layout(); fig.savefig(os.path.join(run_dir, "vegetation_trend.png")); plt.close(fig)
    written.append("vegetation_trend.png")
    print("Charts: " + ", ".join(written))


def _render_decade_map(tif, out_png, name):
    plt = _plt()
    import numpy as np
    import rasterio
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    with rasterio.open(tif) as src:
        arr = src.read(1, masked=True)
        b = src.bounds
    extent = [b.left, b.right, b.bottom, b.top]
    cmap = ListedColormap(["#" + c for c in DECADE_PALETTE])
    norm = BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5, 5.5], cmap.N)
    fig, ax = plt.subplots(figsize=(9, 9), dpi=150)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    _basemap(ax)
    ax.imshow(np.ma.filled(arr.astype(float), np.nan), extent=extent, origin="upper",
              cmap=cmap, norm=norm, alpha=0.85, zorder=3, interpolation="nearest")
    ax.set_title(f"When did it urbanise? First built-up decade (GHSL) — {name}",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.legend(handles=[Patch(facecolor="#" + c, label=l)
                       for c, l in zip(DECADE_PALETTE, DECADE_LABELS)],
              title="First built-up", loc="lower right", fontsize=8, framealpha=0.9)
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    fig.tight_layout(); fig.savefig(out_png); plt.close(fig)
    print(f"Value-added map: {os.path.basename(out_png)}")


def _panel(masks, years, extent, title, run_dir, areas=None):
    """Small-multiple panel: one built-up map per epoch over a light basemap."""
    plt = _plt()
    import numpy as np
    n = len(years)
    cols = 3 if n > 4 else n
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 4.2 * rows), dpi=140)
    axes = np.array(axes).reshape(-1)
    for k, (m, y) in enumerate(zip(masks, years)):
        ax = axes[k]
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        _basemap(ax)
        shown = np.where(np.asarray(m) > 0, 1.0, np.nan)
        ax.imshow(shown, extent=extent, origin="upper", cmap="autumn_r",
                  vmin=0, vmax=1, alpha=0.8, zorder=3, interpolation="nearest")
        sub = f"{y}"
        if areas and areas.get(y) is not None:
            sub += f"  ·  {areas[y]:.0f} km²"
        ax.set_title(sub, fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])
    for k in range(len(years), len(axes)):
        axes[k].axis("off")
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(run_dir, "builtup_panel.png")
    fig.savefig(out); plt.close(fig)
    print(f"Decadal panel: builtup_panel.png")


def _render_all(stats, run_dir, epochs_tif, years, first_built_tif):
    import rasterio
    _render_charts(stats, run_dir)
    _render_decade_map(first_built_tif,
                       os.path.join(run_dir, "first_built_decade_map.png"), stats["name"])
    with rasterio.open(epochs_tif) as src:
        bands = src.read()  # (n, y, x)
        b = src.bounds
    extent = [b.left, b.right, b.bottom, b.top]
    areas = {y: stats["ghsl"][str(y)]["builtup_km2"] for y in years}
    _panel([bands[i] for i in range(len(years))], years, extent,
           f"Built-up extent by decade (GHSL) — {stats['name']}", run_dir, areas)


def _render_mpc(stats, run_dir, extent, masks, years, veg_loss):
    _render_charts(stats, run_dir)
    _panel(masks, years, extent,
           f"Built-up extent by decade (Landsat NDBI>0) — {stats['name']}", run_dir)
    if veg_loss is not None:
        plt = _plt()
        import numpy as np
        fig, ax = plt.subplots(figsize=(9, 9), dpi=140)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        _basemap(ax)
        ax.imshow(veg_loss, extent=extent, origin="upper", cmap="Greens",
                  vmin=0, vmax=1, alpha=0.85, zorder=3, interpolation="nearest")
        ax.set_title(f"Vegetation lost 1990→2010 (Landsat TM) — {stats['name']}",
                     fontsize=12, fontweight="bold")
        fig.tight_layout()
        fig.savefig(os.path.join(run_dir, "vegetation_loss_map.png")); plt.close(fig)


def _write_stats(stats, run_dir, run_id, backend):
    payload = {"run_id": run_id, "scenario": "urban-history", "backend": backend, **stats}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nAll outputs -> output/{os.path.basename(run_dir)}/")


def run(backend, lat, lon, radius, name, run_dir, run_id, do_map=False, config_key=None):
    """Entry point called by detect.py for the urban-history scenario."""
    if backend == "mpc":
        _run_mpc(lat, lon, radius, name, run_dir, run_id, do_map)
    else:
        _run_gee(lat, lon, radius, name, run_dir, run_id, do_map, config_key)
