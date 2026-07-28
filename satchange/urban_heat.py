#!/usr/bin/env python3
"""Urban heat island scenario — surface UHI intensity (SUHII) and hot-spot maps.

Cities run hotter than their rural surroundings: dark impervious surfaces store
heat, vegetation that would cool by evapotranspiration is gone, and waste heat
adds on top. This measures the *surface* urban heat island from satellite land-
surface temperature (LST):

  * SUHII — mean LST over the built city minus mean LST over the rural ring, °C.
  * Hot-spot map — per-pixel LST anomaly vs the rural reference (where the city bakes).
  * Driver — how LST falls as vegetation (NDVI) rises, °C per 0.1 NDVI.
  * Decadal trend — SUHII at several epochs, as the city grows.

Urban vs rural is defined authoritatively from GHSL GHS-BUILT-S (built-surface
fraction), and the rural reference is restricted to a similar elevation band
(SRTM) so terrain doesn't confound the comparison. LST is Landsat thermal
(Collection-2 Level-2 surface temperature), 100 m — sharp enough for intra-city
detail. Backend: needs --backend gee (GHSL + Landsat thermal).
"""

import json
import math
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

# Landsat Collection-2 L2 surface-temperature sources for the detailed snapshot map.
# Skip L7 (SLC-off stripes). Each entry: (collection, ST band).
LST_SOURCES = [
    ("LANDSAT/LC09/C02/T1_L2", "ST_B10"),
    ("LANDSAT/LC08/C02/T1_L2", "ST_B10"),
    ("LANDSAT/LT05/C02/T1_L2", "ST_B6"),
]
MODIS_LST = "MODIS/061/MOD11A2"          # Terra 8-day 1 km LST, consistent sensor 2000+
GHSL_EPOCHS = (1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030)

URBAN_FRAC = 0.20                 # built-surface fraction ≥ this → "urban"
RURAL_FRAC = 0.05                 # built-surface fraction ≤ this → "rural" reference
ELEV_BAND_M = 100.0               # rural reference kept within ±this of urban mean elevation
DEFAULT_EPOCHS = [("2000-01-01", "2002-12-31"),
                  ("2013-01-01", "2015-12-31"),
                  ("2022-01-01", "2024-12-31")]


# ----------------------------- GEE building blocks -----------------------------
def _ghsl_frac(year):
    """GHSL built-surface fraction (0–1) at the nearest 5-yearly epoch."""
    import ee
    ep = min(GHSL_EPOCHS, key=lambda e: abs(e - year))
    return ee.Image(f"JRC/GHSL/P2023A/GHS_BUILT_S/{ep}").select("built_surface").divide(10000.0), ep


def _lst_coll(aoi, months=None):
    """Merged Landsat LST (°C) over land, cloud/water-masked — for the detail map.

    `months` optionally restricts to a month range (m0, m1) — e.g. the dry season,
    when the surface UHI reads cleanest and clouds are fewest.
    """
    import ee

    def make(coll_id, st_band):
        def prep(im):
            qa = im.select("QA_PIXEL")
            clear = (qa.bitwiseAnd(1 << 1).eq(0)          # dilated cloud
                     .And(qa.bitwiseAnd(1 << 3).eq(0))    # cloud
                     .And(qa.bitwiseAnd(1 << 4).eq(0)))   # cloud shadow
            land = qa.bitwiseAnd(1 << 7).eq(0)            # water bit 0 → land
            lst = (im.select(st_band).multiply(0.00341802).add(149.0)
                   .subtract(273.15).rename("lst"))
            lst = lst.updateMask(clear).updateMask(land) \
                     .updateMask(lst.gt(0)).updateMask(lst.lt(70))
            return lst.copyProperties(im, ["system:time_start"])
        return ee.ImageCollection(coll_id).filterBounds(aoi).map(prep)

    coll = make(*LST_SOURCES[0])
    for src in LST_SOURCES[1:]:
        coll = coll.merge(make(*src))
    if months:
        coll = coll.filter(ee.Filter.calendarRange(months[0], months[1], "month"))
    return coll


def _modis_lst(aoi, start, end, months=None):
    """MODIS Terra daytime LST (°C) median over a window — one consistent sensor
    for the decadal trend (Landsat mixes TM/OLI, which aren't comparable)."""
    import ee
    coll = (ee.ImageCollection(MODIS_LST).filterBounds(aoi).filterDate(start, end)
            .select("LST_Day_1km")
            .map(lambda im: im.multiply(0.02).subtract(273.15).rename("lst")
                 .copyProperties(im, ["system:time_start"])))
    if months:
        coll = coll.filter(ee.Filter.calendarRange(months[0], months[1], "month"))
    return coll


def _masks(aoi, built_frac, lst_img, scale):
    """Urban / rural-reference masks. Rural is non-built, non-water land kept to a
    similar elevation as the urban core (SRTM) so terrain doesn't bias SUHII."""
    import ee
    urban = built_frac.gte(URBAN_FRAC)
    rural0 = built_frac.lte(RURAL_FRAC).And(lst_img.select("lst").mask())
    elev = ee.Image("USGS/SRTMGL1_003")
    ue = elev.updateMask(urban).reduceRegion(
        ee.Reducer.mean(), aoi, scale, maxPixels=int(1e9), bestEffort=True).get("elevation")
    ue = ee.Number(ee.Algorithms.If(ue, ue, 0))
    rural = rural0.And(elev.gt(ue.subtract(ELEV_BAND_M))).And(elev.lt(ue.add(ELEV_BAND_M)))
    return urban, rural


def _suhii(lst_img, urban, rural, aoi, scale):
    """(urban mean LST, rural mean LST, SUHII) in °C over the AOI."""
    import ee
    lst = lst_img.select("lst")

    def m(mask):
        return lst.updateMask(mask).reduceRegion(
            ee.Reducer.mean(), aoi, scale, maxPixels=int(1e9), bestEffort=True).get("lst")
    # one round-trip for both means (server-side objects → Python numbers)
    u, r = ee.List([m(urban), m(rural)]).getInfo()
    u = None if u is None else round(u, 2)
    r = None if r is None else round(r, 2)
    return u, r


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


def _render_hotspot(tif, bbox, run_dir, name, suhii, rural_lst):
    import numpy as np
    import rasterio
    plt = _plt()
    with rasterio.open(tif) as ds:
        a = ds.read(1).astype("float64")
        if ds.nodata is not None:
            a[a == ds.nodata] = np.nan
    a[~np.isfinite(a)] = np.nan
    w, s, e, n = bbox
    fin = a[np.isfinite(a)]
    # Absolute LST with a robust p2–p98 range so intra-city hot spots read
    # differentially (an anomaly-vs-rural map saturates: the whole city is hot).
    lo = float(np.nanpercentile(fin, 2)) if fin.size else 25.0
    hi = float(np.nanpercentile(fin, 98)) if fin.size else 45.0
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    im = ax.imshow(a, extent=[w, e, s, n], origin="upper", cmap="inferno",
                   vmin=lo, vmax=hi, alpha=0.82, zorder=2)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02,
                      label="Suhu permukaan darat (°C)  ·  kuning = titik panas")
    if rural_lst is not None:
        cb.ax.axhline(rural_lst, color="#39a", lw=1.4)
    sub = f"SUHII = {suhii:+.1f} °C (kota − desa)" if suhii is not None else ""
    ax.set_title(f"Pulau panas perkotaan — {name}\n{sub}", fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "uhi_hotspot_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


def _render_trend(run_dir, name, rows):
    plt = _plt()
    import numpy as np
    pts = [(r["year"], r["suhii_c"]) for r in rows if r["suhii_c"] is not None]
    if len(pts) < 2:
        return
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    x = [p[0] for p in pts]; y = [p[1] for p in pts]
    ax.plot(x, y, "o-", color="#d6604d", lw=2, ms=6)
    for xi, yi in pts:
        ax.annotate(f"{yi:+.1f}", (xi, yi), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=9, color="#b2182b")
    if len(pts) >= 3:
        m, b = np.polyfit(x, y, 1)
        ax.plot(x, [m * xi + b for xi in x], "--", color="#b2182b", lw=1, alpha=.6,
                label=f"{m*10:+.2f} °C/dekade")
        ax.legend(fontsize=9)
    ax.axhline(0, color="#888", lw=.8)
    ax.set_title(f"Tren intensitas pulau panas perkotaan (SUHII) — {name}\n"
                 f"MODIS 1 km · sensor konsisten", fontsize=12, fontweight="bold")
    ax.set_ylabel("SUHII (°C)  ·  kota − desa"); ax.set_xlabel("Tahun")
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "uhi_trend.png")
    fig.savefig(out); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        epochs=None, months=None, scale=100):
    """Urban heat-island analysis: snapshot hot-spot map + SUHII + decadal trend."""
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"urban-heat needs {mod}: pip install 'satchange[maps]'")
    if backend == "mpc":
        raise SystemExit("urban-heat needs --backend gee (GHSL + Landsat thermal).")
    import ee
    from .gee_utils import initialize_ee, square_aoi, download_geotiff
    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    eps = epochs or DEFAULT_EPOCHS

    # --- decadal SUHII trend (MODIS: one consistent sensor 2000+; Landsat mixes
    #     TM/OLI, which aren't comparable across the 2011→2013 break) ---
    rows = []
    for (start, end) in eps:
        yr = int(start[:4])
        coll = _modis_lst(aoi, start, end, months)
        n = coll.size().getInfo()
        if n == 0:
            print(f"  epoch {yr}: no MODIS scenes — skipped")
            rows.append({"year": yr, "suhii_c": None, "scenes": 0})
            continue
        lst_img = coll.median().clip(aoi)
        built, ghsl_ep = _ghsl_frac(yr)
        urban, rural = _masks(aoi, built, lst_img, 1000)
        u, r = _suhii(lst_img, urban, rural, aoi, 1000)
        suhii = None if (u is None or r is None) else round(u - r, 2)
        print(f"  epoch {yr}: MODIS 8-day n={n:3d}  urban={u}  rural={r}  SUHII={suhii}  [GHSL {ghsl_ep}]")
        rows.append({"year": yr, "scenes": n, "urban_lst_c": u, "rural_lst_c": r,
                     "suhii_c": suhii, "ghsl_epoch": ghsl_ep})

    _render_trend(run_dir, name, rows)

    # --- snapshot: detailed Landsat hot-spot map + SUHII for the newest epoch ---
    last = eps[-1]
    coll = _lst_coll(aoi, months).filterDate(*last)
    if coll.size().getInfo() == 0:
        raise SystemExit("No clear Landsat scenes in the latest epoch for the hot-spot map.")
    lst_img = coll.median().clip(aoi)
    built, ghsl_ep = _ghsl_frac(int(last[0][:4]))
    urban, rural = _masks(aoi, built, lst_img, scale)
    u, r = _suhii(lst_img, urban, rural, aoi, scale)
    suhii = None if (u is None or r is None) else round(u - r, 2)

    tif = os.path.join(run_dir, "uhi_lst.tif")
    if download_geotiff(lst_img.select("lst").clip(aoi), aoi, tif, scale=scale) is not None:
        _render_hotspot(tif, bbox, run_dir, name, suhii, r)
    else:
        print("  (hot-spot map skipped: download failed — try a smaller --radius)")

    tr_vals = [x["suhii_c"] for x in rows if x["suhii_c"] is not None]
    stats = {"run_id": run_id, "scenario": "urban-heat", "name": name,
             "method": ("Snapshot: Landsat 100 m LST + GHSL urban/rural + SRTM "
                        "elevation-matched rural. Trend: MODIS 1 km (consistent sensor)."),
             "snapshot_period": list(last), "months": months,
             "snapshot_urban_lst_c": u, "snapshot_rural_lst_c": r, "snapshot_suhii_c": suhii,
             "trend_source": "MODIS 1 km (SUHII smaller than the 100 m snapshot — coarser pixels mix urban+rural)",
             "trend": rows}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nSUHII snapshot [{name}, {last[0][:4]}–{last[1][:4]}, Landsat 100 m]: "
          f"{suhii} °C (urban {u} − rural {r})")
    if len(tr_vals) >= 2:
        print(f"SUHII trend (MODIS 1 km): {tr_vals[0]:+.1f} → {tr_vals[-1]:+.1f} °C "
              f"over {rows[0]['year']}–{rows[-1]['year']}")
    return stats
