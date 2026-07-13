#!/usr/bin/env python3
"""Decadal urban-history analysis (Jakarta / Jabodetabek by default).

Combines two independent views of how a metro area urbanised, decade by decade:

  1. GHSL GHS-BUILT-S (EU JRC) — authoritative built-up SURFACE per epoch
     (1975-2030, 100 m), validated from the full Landsat archive. Gives the
     settlement-expansion story back to 1980 (no threshold tuning needed).
  2. Landsat surface reflectance (our own processing, L5 TM + L8/9 OLI, L7
     skipped for SLC-off) — NDBI built-up and NDVI vegetation per decade, so
     you also get the VEGETATION-LOSS story in the same run. Built-up is robust
     1990->now; 1980 is Landsat-MSS only (no SWIR) so it is GHSL-only.

Products written to output/<run>/:
  first_built_decade.{png,tif}  — each pixel coloured by the decade it first
                                   became built-up (GHSL). You see the city
                                   sprawl ring by ring.
  vegetation_loss.{png,tif}     — vegetation in the first Landsat epoch that was
                                   gone by the last (NDVI collapse).
  builtup_trend.png             — built-up area vs year (GHSL km2 + Landsat NDBI %).
  vegetation_trend.png          — vegetation % and mean NDVI vs year.
  stats.json                    — every number behind the charts.

Roads are NOT a target: at 30 m Landsat cannot resolve most streets. Major toll
/arterial corridors appear inside the built-up layer; for the street network use
OpenStreetMap or high-resolution imagery.

Usage:
  python3 examples/urban_history.py                       # Jabodetabek default
  python3 examples/urban_history.py --lat -6.2 --lon 106.85 --radius 45 -n jakarta
"""

import os
import sys
import json
import uuid
import argparse
from datetime import datetime

# Clear a stale external PROJ override (e.g. an OTB install exporting PROJ_LIB)
# so rasterio/contextily use their OWN bundled PROJ database (see mapmaker.py).
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import ee

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from satchange.gee_utils import initialize_ee, square_aoi, download_png, download_geotiff
from satchange.indices import l_sr_median

CONFIG_KEY = os.path.join(os.getcwd(), "scripts", "config", "ee-geodetic.json")
OUTPUT_ROOT = os.path.join(os.getcwd(), "output")

GHSL_YEARS = [1980, 1990, 2000, 2010, 2020, 2025]
DECADE_YEARS = [1980, 1990, 2000, 2010, 2020]   # 5 classes for the first-built map
LANDSAT_YEARS = [1990, 2000, 2010, 2020, 2025]  # L5/L8/9 only (1980 = MSS, skipped)

BUILT_M2_THR = 2000.0   # GHSL: >20% of a 100 m cell built-up = "built"
NDBI_THR = 0.0          # Landsat NDBI > 0 ~ built-up / bare (trend proxy)
NDVI_VEG_THR = 0.30     # NDVI above this = vegetated
NDVI_GONE_THR = 0.20    # NDVI below this at the end = vegetation lost
NDVI_LOSS_DROP = -0.15  # min NDVI drop to count as loss

# Sequential palette for the decade of first urbanisation (old -> new).
DECADE_PALETTE = ["fee5d9", "fcae91", "fb6a4a", "de2d26", "a50f15"]


# Landsat-5 TM and Landsat-8/9 OLI surface-reflectance NDVI are NOT directly
# comparable (OLI reads systematically higher), so we never stitch them into one
# absolute-NDVI trend. Instead:
#   * GHSL is the authoritative cross-decade BUILT-UP series (1980-2025).
#   * The vegetation-decline trend + loss map use only same-sensor TM epochs
#     (1990/2000/2010); OLI epochs (2020/2025) are reported separately.
#   * Full-span "vegetation consumed by urban" comes from GHSL (new built-up).
TM_YEARS = [1990, 2000, 2010]   # Landsat-5 TM — mutually comparable
OLI_YEARS = [2020, 2025]        # Landsat-8/9 OLI — comparable to each other only


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


def analyse(lat, lon, radius, name):
    aoi = square_aoi(lon, lat, radius)
    aoi_km2 = (2 * radius) ** 2  # square, half-side = radius
    stats = {"location": {"lat": lat, "lon": lon}, "radius_km": radius,
             "aoi_km2": round(aoi_km2, 1), "ghsl": {}, "landsat": {}}

    # ---- GHSL authoritative built-up per epoch ----
    print("GHSL built-up per epoch:")
    for y in GHSL_YEARS:
        km2 = _sum_km2(_ghsl(y), aoi)
        stats["ghsl"][str(y)] = {"builtup_km2": round(km2, 1),
                                 "builtup_pct_aoi": round(100.0 * km2 / aoi_km2, 1)}
        print(f"  {y}: {km2:8.1f} km2  ({100.0*km2/aoi_km2:4.1f}% of AOI)")

    # ---- first-built decade map (GHSL) ----
    code = ee.Image(0)
    for i, y in enumerate(DECADE_YEARS, start=1):
        built = _ghsl(y).gt(BUILT_M2_THR)
        code = code.where(code.eq(0).And(built), i)
    first_built = code.selfMask().clip(aoi).rename("first_built")

    # ---- Landsat NDBI built-up + NDVI vegetation per epoch ----
    print("Landsat NDBI/NDVI per epoch:")
    ndvi_by_year = {}
    for y in LANDSAT_YEARS:
        img, n = l_sr_median(aoi, f"{y}-01-01", f"{y}-12-31")
        sensor = "TM (L5)" if y <= 2011 else "OLI (L8/9)"
        ndbi = img.normalizedDifference(["SWIR1", "NIR"])
        ndvi = img.normalizedDifference(["NIR", "RED"])
        ndvi_by_year[y] = ndvi
        rec = {"scenes": n, "sensor": sensor,
               "builtup_ndbi_pct": round(_pct(ndbi.gt(NDBI_THR), aoi, 30), 1),
               "vegetation_pct": round(_pct(ndvi.gt(NDVI_VEG_THR), aoi, 30), 1),
               "mean_ndvi": round(_mean(ndvi, aoi, 30) or 0.0, 3)}
        stats["landsat"][str(y)] = rec
        print(f"  {y}: scenes={n:3d} {sensor:9s} built(NDBI>0)={rec['builtup_ndbi_pct']:4.1f}%  "
              f"veg={rec['vegetation_pct']:4.1f}%  meanNDVI={rec['mean_ndvi']:.3f}")

    # ---- vegetation-loss map: SAME-SENSOR TM only (1990 vs 2010) ----
    y0, y1 = TM_YEARS[0], TM_YEARS[-1]
    ndvi0, ndvi1 = ndvi_by_year[y0], ndvi_by_year[y1]
    veg_loss_mask = (ndvi0.gt(NDVI_VEG_THR).And(ndvi1.lt(NDVI_GONE_THR))
                     .And(ndvi1.subtract(ndvi0).lt(NDVI_LOSS_DROP)))
    veg_loss = veg_loss_mask.selfMask().clip(aoi).rename("veg_loss")
    stats["vegetation_loss_TM"] = {
        "from_year": y0, "to_year": y1, "sensor": "Landsat-5 TM (same sensor)",
        "pct_lost": round(_pct(veg_loss_mask, aoi, 30), 1)}
    print(f"Vegetation lost {y0}->{y1} (TM): {stats['vegetation_loss_TM']['pct_lost']:.1f}% of AOI")

    # ---- authoritative full-span land consumed by urban (GHSL 1990 -> 2025) ----
    built_1990 = _ghsl(1990).gt(BUILT_M2_THR)
    built_2025 = _ghsl(2025).gt(BUILT_M2_THR)
    new_urban = built_2025.And(built_1990.Not()).selfMask().clip(aoi).rename("new_urban")
    new_km2 = _sum_km2(_ghsl(2025).subtract(_ghsl(1990)).max(0), aoi)
    stats["urban_conversion_GHSL"] = {"from_year": 1990, "to_year": 2025,
                                      "new_builtup_km2": round(new_km2, 1),
                                      "new_builtup_pct_aoi": round(100.0 * new_km2 / aoi_km2, 1)}
    print(f"New built-up {1990}->2025 (GHSL): {new_km2:.1f} km2 "
          f"({100.0*new_km2/aoi_km2:.1f}% of AOI)")

    stats["notes"] = (
        "GHSL GHS-BUILT-S is the authoritative cross-decade built-up series "
        "(1980-2025, internally consistent). Landsat NDVI/NDBI absolute values "
        "are NOT comparable across the TM->OLI break (2011->2013): use the TM "
        "epochs (1990/2000/2010) as one comparable group and OLI (2020/2025) as "
        "another. The vegetation-loss map uses TM-only 1990->2010; the full-span "
        "vegetation-to-urban conversion is measured by GHSL (new_urban).")

    products = {
        "first_built_decade": (first_built,
                               {"min": 1, "max": len(DECADE_YEARS), "palette": DECADE_PALETTE}),
        "vegetation_loss": (veg_loss, {"min": 0, "max": 1, "palette": ["1a9850"]}),
        "new_urban": (new_urban, {"min": 0, "max": 1, "palette": ["7a0177"]}),
    }
    return aoi, stats, products


def render_charts(stats, run_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gy = [int(y) for y in stats["ghsl"]]
    gkm = [stats["ghsl"][str(y)]["builtup_km2"] for y in gy]
    tmy = [y for y in TM_YEARS if str(y) in stats["landsat"]]
    oliy = [y for y in OLI_YEARS if str(y) in stats["landsat"]]

    def veg(ys):
        return [stats["landsat"][str(y)]["vegetation_pct"] for y in ys]

    def ndvi(ys):
        return [stats["landsat"][str(y)]["mean_ndvi"] for y in ys]

    # built-up trend — GHSL only (authoritative, internally consistent)
    fig, ax1 = plt.subplots(figsize=(7, 4.2), dpi=150)
    ax1.plot(gy, gkm, "-o", color="#a50f15")
    ax1.set_xlabel("Year"); ax1.set_ylabel("GHSL built-up area (km²)", color="#a50f15")
    ax1.tick_params(axis="y", labelcolor="#a50f15")
    for x, y in zip(gy, gkm):
        ax1.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, 6),
                     ha="center", fontsize=7, color="#a50f15")
    ax1.set_title(f"Built-up expansion (GHSL GHS-BUILT-S) — {stats['name']}")
    ax1.grid(True, ls=":", alpha=0.5)
    fig.tight_layout(); fig.savefig(os.path.join(run_dir, "builtup_trend.png")); plt.close(fig)

    # vegetation trend — TM epochs as one comparable line, OLI epochs separate
    fig, ax1 = plt.subplots(figsize=(7, 4.2), dpi=150)
    ax1.plot(tmy, veg(tmy), "-o", color="#1a9850", label="Vegetation % (TM, comparable)")
    if oliy:
        ax1.plot(oliy, veg(oliy), "D", color="#66bd63", label="Vegetation % (OLI, separate)")
        brk = (max(tmy) + min(oliy)) / 2.0
        ax1.axvline(brk, color="#999", ls="--", lw=1)
        ax1.annotate("TM→OLI sensor break\n(values not comparable across it)",
                     xy=(brk, ax1.get_ylim()[0]), fontsize=6.5, color="#666",
                     ha="center", va="bottom")
    ax1.set_xlabel("Year"); ax1.set_ylabel("Vegetated area (% of AOI, NDVI>0.3)", color="#1a9850")
    ax1.tick_params(axis="y", labelcolor="#1a9850")
    ax2 = ax1.twinx()
    ax2.plot(tmy, ndvi(tmy), "--^", color="#7f7f7f")
    if oliy:
        ax2.plot(oliy, ndvi(oliy), "^", color="#bdbdbd")
    ax2.set_ylabel("Mean NDVI", color="#7f7f7f")
    ax2.tick_params(axis="y", labelcolor="#7f7f7f")
    ax1.legend(fontsize=7, loc="upper right")
    ax1.set_title(f"Vegetation decline (Landsat) — {stats['name']}")
    ax1.grid(True, ls=":", alpha=0.5)
    fig.tight_layout(); fig.savefig(os.path.join(run_dir, "vegetation_trend.png")); plt.close(fig)
    print("Charts: builtup_trend.png, vegetation_trend.png")


def render_decade_map(tif, out_png, name):
    """Value-added map of first-built decade: OSM basemap + discrete legend.

    Reads the already-downloaded EPSG:4326 GeoTIFF, so it needs no Earth Engine.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    import numpy as np
    import rasterio
    try:
        import contextily as cx
        has_cx = True
    except Exception:  # noqa: BLE001
        has_cx = False

    with rasterio.open(tif) as src:
        arr = src.read(1, masked=True)
        b = src.bounds
    extent = [b.left, b.right, b.bottom, b.top]

    labels = ["by 1980 (core)", "1980s", "1990s", "2000s", "2010s (newest)"]
    cmap = ListedColormap(["#" + c for c in DECADE_PALETTE])
    norm = BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5, 5.5], cmap.N)

    fig, ax = plt.subplots(figsize=(9, 9), dpi=150)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    if has_cx:
        try:
            cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron,
                           attribution=False)
        except Exception as e:  # noqa: BLE001
            print(f"  (basemap skipped: {e})")
    ax.imshow(np.ma.filled(arr.astype(float), np.nan), extent=extent, origin="upper",
              cmap=cmap, norm=norm, alpha=0.85, zorder=3, interpolation="nearest")
    ax.set_title(f"When did it urbanise? First built-up decade (GHSL) — {name}",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.legend(handles=[Patch(facecolor="#" + c, label=l)
                       for c, l in zip(DECADE_PALETTE, labels)],
              title="First built-up", loc="lower right", fontsize=8, framealpha=0.9)
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    fig.tight_layout(); fig.savefig(out_png); plt.close(fig)
    print(f"Value-added map: {os.path.basename(out_png)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, default=-6.2)
    ap.add_argument("--lon", type=float, default=106.85)
    ap.add_argument("--radius", type=float, default=45.0)
    ap.add_argument("-n", "--name", default="jabodetabek")
    args = ap.parse_args()

    initialize_ee(CONFIG_KEY)
    run_id = (f"{datetime.now():%Y%m%d-%H%M%S}_urbanhistory_{args.name}"
              f"_{uuid.uuid4().hex[:6]}")
    run_dir = os.path.join(OUTPUT_ROOT, run_id)
    os.makedirs(run_dir, exist_ok=True)
    print(f"Output folder: output/{run_id}/\n")

    aoi, stats, products = analyse(args.lat, args.lon, args.radius, args.name)
    stats["name"] = args.name

    for key, (img, vis) in products.items():
        png = os.path.join(run_dir, key + ".png")
        tif = os.path.join(run_dir, key + ".tif")
        print(f"Downloading {key}...")
        download_png(img, aoi, png, vis=vis)
        ghsl_layer = key in ("first_built_decade", "new_urban")
        download_geotiff(img, aoi, tif, scale=(100 if ghsl_layer else 30))

    render_charts(stats, run_dir)
    render_decade_map(os.path.join(run_dir, "first_built_decade.tif"),
                      os.path.join(run_dir, "first_built_decade_map.png"), args.name)
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nAll outputs -> output/{run_id}/")


if __name__ == "__main__":
    main()
