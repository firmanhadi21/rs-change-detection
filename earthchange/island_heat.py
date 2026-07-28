#!/usr/bin/env python3
"""Island heat scenario — SST, LST and humid-heat (wet-bulb) trends for islands.

Motivated by the growing concern that the threat to small tropical islands is not
only sea-level rise but rising heat *and humidity*: as air saturates, sweat stops
evaporating and the body can no longer shed heat. This builds observed time series
(no climate-model projections) from Earth Engine:

  * SST  — sea-surface temperature of the surrounding ocean (NOAA OISST, 1981+)
  * LST  — land-surface temperature of the island(s) (Landsat thermal, land-masked;
           resolves small sub-km islands that MODIS 1 km cannot)
  * Wet-bulb — 2 m air temperature + dewpoint → wet-bulb temperature (ERA5-Land),
           the metric behind "dangerous humid heat", plus dangerous-days-per-year.

Two modes (``--island-mode``):
  * ``aggregate``  — one AOI over a cluster; land/ocean masking separates LST (all
                     island land) from SST (surrounding sea). One series each.
  * ``per-island`` — a separate LST series per island polygon (``--islands-file``);
                     SST and wet-bulb stay shared (they are regional/coarse).

Backend: needs --backend gee.
"""

import json
import math
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

OISST = "NOAA/CDR/OISST/V2_1"
MODIS_SST = "NASA/OCEANDATA/MODIS-Aqua/L3SMI"    # 4 km SST in °C (for the change map)
MODIS_LST = "MODIS/061/MYD11A2"                  # Aqua 8-day 1 km LST (clean series)
L8 = "LANDSAT/LC08/C02/T1_L2"
L9 = "LANDSAT/LC09/C02/T1_L2"
ERA5_MONTHLY = "ECMWF/ERA5/MONTHLY"              # GLOBAL ERA5 (covers ocean; ERA5-Land does not)

DEFAULT_START_YEAR = 2000
MODIS_MIN_YEAR = 2003              # MODIS Aqua full years
LST_MIN_YEAR = 2013                # Landsat 8/9 Collection-2 L2 (clean, cross-consistent)
WETBULB_DANGER = 28.0              # °C wet-bulb — dangerous humid heat
WETBULB_EXTREME = 31.0            # °C wet-bulb — extreme / survivability risk
CURRENT_YEAR = 2026


# ----------------------------- humid-heat physics -----------------------------
def _rh_from_dew(t_c, td_c):
    """Relative humidity (%) from air temp and dewpoint (°C), Magnus formula."""
    es = 6.112 * math.exp(17.62 * t_c / (243.12 + t_c))
    e = 6.112 * math.exp(17.62 * td_c / (243.12 + td_c))
    return max(0.0, min(100.0, e / es * 100.0))


def _wetbulb(t_c, rh):
    """Wet-bulb temperature (°C) from air temp (°C) and RH (%), Stull (2011)."""
    rh = max(1.0, min(100.0, rh))
    return (t_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
            + math.atan(t_c + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)


# ----------------------------- GEE series helpers -----------------------------
def _annual_series(coll, band, aoi, scale, years, how="mean"):
    """Server-side annual statistic of `band` over `aoi` for each year (one fetch).

    `how` composites the year's images: 'mean' (annual mean) or 'max' (annual
    maximum, e.g. the hottest month's peak temperature).
    """
    import ee
    yl = ee.List(years)

    def per(y):
        y = ee.Number(y)
        s = ee.Date.fromYMD(y, 1, 1)
        e = ee.Date.fromYMD(y, 12, 31).advance(1, "day")
        yc = coll.select(band).filterDate(s, e)
        img = yc.max() if how == "max" else yc.mean()
        red = ee.Dictionary(img.reduceRegion(ee.Reducer.mean(), aoi, scale,
                                             maxPixels=int(1e9), bestEffort=True))
        # Empty year (no images) or fully-masked AOI → dict lacks the band → None,
        # instead of throwing "Dictionary does not contain key".
        v = ee.Algorithms.If(red.contains(band), red.get(band), None)
        return ee.Feature(None, {"year": y, "v": v})

    fc = ee.FeatureCollection(yl.map(per))
    yv = _fc_columns(fc, ["year", "v"])
    return yv["year"], yv["v"]


def _fc_columns(fc, keys):
    """Fetch a FeatureCollection once and return aligned columns preserving None.

    Unlike separate aggregate_array() calls (which silently drop null entries and
    misalign the arrays), this keeps one value per feature per key — None where a
    year's reduceRegion returned no data.
    """
    feats = fc.getInfo()["features"]
    return {k: [f["properties"].get(k) for f in feats] for k in keys}


def _sst_series(aoi, years):
    import ee
    coll = ee.ImageCollection(OISST).map(
        lambda im: im.select("sst").multiply(0.01).rename("sst")
        .copyProperties(im, ["system:time_start"]))
    return _annual_series(coll, "sst", aoi, 25000, years)


def _landsat_lst_coll(aoi, ndvi_thr=0.2):
    """Landsat 8/9 LST (°C), masked to cloud-free vegetated island land.

    NDVI-based land masking is far more reliable than the QA water bit on tiny
    sub-km islands whose 100 m pixels are part-water. A higher `ndvi_thr` is used
    for the per-pixel change MAP (turbid Java-Sea water can leak past NDVI>0.2).
    """
    import ee

    def prep(im):
        qa = im.select("QA_PIXEL")
        clear = (qa.bitwiseAnd(1 << 1).eq(0)          # dilated cloud
                 .And(qa.bitwiseAnd(1 << 3).eq(0))    # cloud
                 .And(qa.bitwiseAnd(1 << 4).eq(0)))   # cloud shadow
        water = qa.bitwiseAnd(1 << 7).eq(0)           # QA water bit 0 → land
        nir = im.select("SR_B5").multiply(0.0000275).add(-0.2)
        red = im.select("SR_B4").multiply(0.0000275).add(-0.2)
        ndvi = nir.subtract(red).divide(nir.add(red))
        land = ndvi.gt(ndvi_thr).And(water)
        lst = (im.select("ST_B10").multiply(0.00341802).add(149.0)
               .subtract(273.15).rename("lst"))
        lst = lst.updateMask(clear).updateMask(land) \
                 .updateMask(lst.gt(5)).updateMask(lst.lt(55))   # drop non-physical
        return lst.copyProperties(im, ["system:time_start"])

    return (ee.ImageCollection(L8).merge(ee.ImageCollection(L9))
            .filterBounds(aoi).map(prep))


def _lst_modis(aoi, years):
    """MODIS Aqua (MYD11A2) 1 km daytime LST (°C) annual mean — many obs, low noise."""
    import ee
    coll = ee.ImageCollection(MODIS_LST).map(
        lambda im: im.select("LST_Day_1km").multiply(0.02).subtract(273.15)
        .rename("lst").copyProperties(im, ["system:time_start"]))
    myrs = [y for y in years if y >= MODIS_MIN_YEAR]
    return _annual_series(coll, "lst", aoi, 1000, myrs)


def _lst_landsat_series(aoi, years):
    coll = _landsat_lst_coll(aoi)
    lyrs = [y for y in years if y >= LST_MIN_YEAR]
    ly, lv = _annual_series(coll, "lst", aoi, 100, lyrs)
    return ly, lv, "Landsat 100 m"


def _lst_series(aoi, years, source="landsat"):
    """Island LST series.

    Default 'landsat': Landsat 100 m masked to vegetated island land (NDVI>0.2),
    which isolates island interior from both water and nearby mainland — the right
    choice for small/scattered islands, at the cost of more year-to-year noise (few
    clear scenes). 'modis': MODIS 1 km — a cleaner, denser series, best for a large
    island well separated from the mainland (its 1 km pixels are part-water on
    sub-km islands and pick up mainland if the AOI clips a coast).
    """
    if source == "modis":
        my, mv = _lst_modis(aoi, years)
        return my, mv, "MODIS 1 km"
    return _lst_landsat_series(aoi, years)


def _era5_series(aoi, years):
    """Global ERA5 monthly wet-bulb (°C): annual-mean and annual peak (hottest month).

    Global ERA5 (not ERA5-Land) is used because it covers the ocean — small islands
    sit in mostly-sea cells that ERA5-Land masks out. Peak = wet-bulb from the year's
    maximum monthly max-temperature with mean dewpoint (a robust, ocean-safe proxy for
    peak humid heat, in place of a land-only daily product).
    """
    import ee
    coll = ee.ImageCollection(ERA5_MONTHLY)
    yt, tmean = _annual_series(coll, "mean_2m_air_temperature", aoi, 27000, years)
    _, tmax = _annual_series(coll, "maximum_2m_air_temperature", aoi, 27000, years, how="max")
    _, dmean = _annual_series(coll, "dewpoint_2m_temperature", aoi, 27000, years)
    mean_wb, peak_wb = [], []
    for i in range(len(yt)):
        tm, dm, tx = tmean[i], dmean[i], tmax[i]
        if tm is None or dm is None:
            mean_wb.append(None)
        else:
            tc, tdc = tm - 273.15, dm - 273.15
            mean_wb.append(round(_wetbulb(tc, _rh_from_dew(tc, tdc)), 2))
        if tx is None or dm is None:
            peak_wb.append(None)
        else:
            txc, tdc = tx - 273.15, dm - 273.15
            peak_wb.append(round(_wetbulb(txc, _rh_from_dew(txc, tdc)), 2))
    return yt, mean_wb, peak_wb


# ----------------------------- analysis -----------------------------
def _trend(years, vals):
    """Linear trend in units/decade over the paired (year, value) points."""
    import numpy as np
    xy = [(y, v) for y, v in zip(years, vals) if v is not None and np.isfinite(v)]
    if len(xy) < 3:
        return None, None
    x = np.array([p[0] for p in xy], float)
    y = np.array([p[1] for p in xy], float)
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope * 10.0, 3), round(float(y[-1] - y[0]), 2)


def _series_dict(years, vals):
    return {int(y): (round(float(v), 2) if v is not None else None)
            for y, v in zip(years, vals)}


# ----------------------------- decadal change maps -----------------------------
def _end_periods(years, k=5):
    """Early and recent k-year windows at the two ends of the record."""
    k = min(k, max(2, len(years) // 3))
    return (years[0], years[0] + k - 1), (years[-1] - k + 1, years[-1])


def _sst_change_image(years):
    """MODIS-Aqua 4 km SST change (°C): recent mean − early mean."""
    import ee
    coll = ee.ImageCollection(MODIS_SST).select("sst")
    (e0, e1), (r0, r1) = _end_periods(years)
    early = coll.filterDate(f"{e0}-01-01", f"{e1}-12-31").mean()
    recent = coll.filterDate(f"{r0}-01-01", f"{r1}-12-31").mean()
    return recent.subtract(early).rename("sst_change"), (e0, e1), (r0, r1)


def _lst_change_image(aoi, years):
    """Landsat LST change (°C) over confident island land: recent − early mean.

    Stricter NDVI (0.4) plus a ≥2-observation requirement in BOTH windows keeps
    only reliable vegetated-land pixels, so turbid water and one-off noise stay
    transparent instead of speckling the map.
    """
    coll = _landsat_lst_coll(aoi, ndvi_thr=0.4)
    ly = [y for y in years if y >= LST_MIN_YEAR]
    (e0, e1), (r0, r1) = _end_periods(ly, k=4)
    ec = coll.filterDate(f"{e0}-01-01", f"{e1}-12-31")
    rc = coll.filterDate(f"{r0}-01-01", f"{r1}-12-31")
    diff = rc.mean().subtract(ec.mean())
    valid = ec.count().gte(2).And(rc.count().gte(2))
    return diff.updateMask(valid).rename("lst_change"), (e0, e1), (r0, r1)


def _change_map(diff_img, aoi, bbox, run_dir, key, title, vlim, scale):
    """Download a change image to GeoTIFF and render a diverging map (Δ°C)."""
    from .gee_utils import download_geotiff
    tif = os.path.join(run_dir, f"{key}.tif")
    if download_geotiff(diff_img.clip(aoi), aoi, tif, scale=scale) is None:
        print(f"  ({key}: download failed, map skipped)")
        return
    _render_change(tif, bbox, run_dir, f"{key}.png", title, vlim)


def _render_change(tif, bbox, run_dir, fname, title, vlim):
    import numpy as np
    import rasterio
    plt = _plt()
    with rasterio.open(tif) as ds:
        a = ds.read(1).astype("float64")
        if ds.nodata is not None:
            a[a == ds.nodata] = np.nan
    a[~np.isfinite(a)] = np.nan
    w, s, e, n = bbox
    fig, ax = plt.subplots(figsize=(9, 9), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    im = ax.imshow(a, extent=[w, e, s, n], origin="upper", cmap="RdBu_r",
                   vmin=-vlim, vmax=vlim, alpha=0.85, zorder=2)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02,
                 label="Perubahan suhu (Δ°C)  ·  merah = menghangat")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(os.path.join(run_dir, fname)); plt.close(fig)
    print(f"Map: {os.path.normpath(os.path.join(run_dir, fname))}")


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
    except Exception as e:  # noqa: BLE001 — basemap is optional
        print(f"  (basemap skipped: {e.__class__.__name__})")


def _fit_line(ax, years, vals, color, label):
    import numpy as np
    xy = [(y, v) for y, v in zip(years, vals) if v is not None and np.isfinite(v)]
    if len(xy) < 2:
        return None
    x = np.array([p[0] for p in xy], float); y = np.array([p[1] for p in xy], float)
    ax.plot(x, y, "o-", color=color, ms=3, lw=1.3, label=label)
    if len(xy) >= 3:
        m, b = np.polyfit(x, y, 1)
        ax.plot(x, m * x + b, "--", color=color, lw=1.0, alpha=0.7)
        return m * 10.0
    return None


def _render(run_dir, name, series, thr):
    plt = _plt()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 9), dpi=150,
                                   gridspec_kw={"height_ratios": [3, 2]})
    sst_t = _fit_line(ax1, series["years"], series["sst"], "#2166ac", "SST (laut)")
    lst_t = _fit_line(ax1, series["lst_years"], series["lst"], "#b2182b", "LST (darat)")
    wb_t = _fit_line(ax1, series["years"], series["wetbulb"], "#762a83",
                     "Wet-bulb (udara lembab)")
    parts = []
    for lbl, tr in (("SST", sst_t), ("LST", lst_t), ("Wet-bulb", wb_t)):
        if tr is not None:
            parts.append(f"{lbl} {tr:+.2f} °C/dekade")
    ax1.set_title(f"Suhu laut, darat & wet-bulb — {name}\n" + "   ·   ".join(parts),
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("°C"); ax1.grid(True, ls=":", alpha=0.4); ax1.legend(fontsize=8)

    mw = [(y, v) for y, v in zip(series["years"], series.get("max_wetbulb", []))
          if v is not None]
    if mw:
        mtr = _fit_line(ax2, [p[0] for p in mw], [p[1] for p in mw], "#d6604d",
                        "Wet-bulb bulan terpanas")
        ax2.axhline(WETBULB_DANGER, ls="--", color="#e08214", lw=1,
                    label=f"Berbahaya {WETBULB_DANGER:.0f} °C")
        ax2.axhline(WETBULB_EXTREME, ls="--", color="#b2182b", lw=1,
                    label=f"Ekstrem {WETBULB_EXTREME:.0f} °C")
        sub = f"  ({mtr:+.2f} °C/dekade)" if mtr is not None else ""
        ax2.set_title(f"Puncak panas lembab: wet-bulb bulan terpanas per tahun{sub}",
                      fontsize=11)
        ax2.set_ylabel("°C wet-bulb"); ax2.legend(fontsize=7, loc="best")
    else:
        ax2.set_title("Puncak panas lembab — data tidak tersedia", fontsize=11)
        ax2.set_ylabel("°C wet-bulb")
    ax2.set_xlabel("Tahun")
    ax2.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "island_heat.png")
    fig.savefig(out); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def _load_polygons(path):
    from shapely.geometry import shape
    gj = json.load(open(path))
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    out = []
    for i, ft in enumerate(feats):
        g = ft.get("geometry", ft)
        if g.get("type") in ("Polygon", "MultiPolygon"):
            props = ft.get("properties", {}) or {}
            nm = props.get("name") or props.get("Nama") or f"island_{i+1}"
            out.append((nm, shape(g), g))
    return out


def _aggregate(aoi, bbox, years, thr, run_dir, name, lst_source="landsat"):
    print("  SST (OISST)…")
    ys, sst = _sst_series(aoi, years)
    ly, lst, lst_src = _lst_series(aoi, years, lst_source)
    print(f"  LST ({lst_src})…")
    print("  wet-bulb (ERA5 global monthly)…")
    _, wetbulb, max_wb = _era5_series(aoi, years)
    # align wet-bulb series (ERA5 years == ys) to the SST year axis
    wb_map = dict(zip(ys, wetbulb)); mw_map = dict(zip(ys, max_wb))
    series = {"years": ys, "sst": sst, "lst_years": ly, "lst": lst, "lst_source": lst_src,
              "wetbulb": [wb_map.get(y) for y in ys], "max_wetbulb": [mw_map.get(y) for y in ys],
              "heat_days": [None] * len(ys)}
    _render(run_dir, name, series, thr)
    _change_maps(aoi, bbox, years, run_dir, name)
    return series


def _change_maps(aoi, bbox, years, run_dir, name):
    """Write three decadal change maps: SST (sea), LST (island land), combined."""
    sst_img = lst_img = None
    try:
        sst_img, ep, rp = _sst_change_image(years)
        print(f"  SST change map ({ep[0]}–{ep[1]} → {rp[0]}–{rp[1]})…")
        _change_map(sst_img, aoi, bbox, run_dir, "sst_change_map",
                    f"Perubahan SST {ep[0]}–{ep[1]} → {rp[0]}–{rp[1]} — {name}",
                    vlim=1.5, scale=4000)
    except Exception as ex:  # noqa: BLE001
        print(f"  (SST change map skipped: {ex.__class__.__name__})")
    try:
        lst_img, ep, rp = _lst_change_image(aoi, years)
        print(f"  LST change map ({ep[0]}–{ep[1]} → {rp[0]}–{rp[1]})…")
        _change_map(lst_img, aoi, bbox, run_dir, "lst_change_map",
                    f"Perubahan LST (darat) {ep[0]}–{ep[1]} → {rp[0]}–{rp[1]} — {name}",
                    vlim=3.0, scale=200)
    except Exception as ex:  # noqa: BLE001
        print(f"  (LST change map skipped: {ex.__class__.__name__})")
    if sst_img is None or lst_img is None:
        return
    try:
        print("  combined change map (LST darat + SST laut)…")
        combined = sst_img.blend(lst_img)     # LST painted on land, SST elsewhere
        _change_map(combined, aoi, bbox, run_dir, "combined_change_map",
                    f"Perubahan suhu gabungan: LST (darat) + SST (laut) — {name}",
                    vlim=3.0, scale=200)
    except Exception as ex:  # noqa: BLE001
        print(f"  (combined change map skipped: {ex.__class__.__name__})")


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        island_mode="aggregate", islands_file=None, start_year=DEFAULT_START_YEAR,
        wetbulb_thr=WETBULB_DANGER, lst_source="landsat"):
    """Island SST/LST/wet-bulb trend analysis (GEE backend)."""
    for mod in ("numpy", "matplotlib", "shapely"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"island-heat needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("island-heat currently needs --backend gee.")
    from .gee_utils import initialize_ee, square_aoi
    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    years = list(range(int(start_year), CURRENT_YEAR + 1))

    if island_mode == "per-island":
        if not islands_file:
            raise SystemExit("--island-mode per-island needs --islands-file "
                             "(GeoJSON polygons of the islands).")
        stats = _run_per_island(aoi, islands_file, years, wetbulb_thr, run_dir, name, lst_source)
    else:
        series = _aggregate(aoi, bbox, years, wetbulb_thr, run_dir, name, lst_source)
        stats = _summ(series, wetbulb_thr)

    stats.update({"run_id": run_id, "scenario": "island-heat", "mode": island_mode,
                  "start_year": start_year, "wetbulb_threshold_c": wetbulb_thr})
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2, default=str)
    _print_summary(stats)
    return stats


def _summ(series, thr):
    sst_tr, sst_ch = _trend(series["years"], series["sst"])
    lst_tr, lst_ch = _trend(series["lst_years"], series["lst"])
    wb_tr, wb_ch = _trend(series["years"], series["wetbulb"])
    mw = series.get("max_wetbulb", [None] * len(series["years"]))
    mw_tr, _ = _trend(series["years"], mw)
    mwv = [(y, v) for y, v in zip(series["years"], mw) if v is not None]
    return {
        "lst_source": series.get("lst_source"),
        "sst_trend_c_per_decade": sst_tr, "sst_change_c": sst_ch,
        "lst_trend_c_per_decade": lst_tr, "lst_change_c": lst_ch,
        "wetbulb_trend_c_per_decade": wb_tr, "wetbulb_change_c": wb_ch,
        "peak_wetbulb_trend_c_per_decade": mw_tr,
        "peak_wetbulb_latest_c": (round(mwv[-1][1], 2) if mwv else None),
        "sst_series": _series_dict(series["years"], series["sst"]),
        "lst_series": _series_dict(series["lst_years"], series["lst"]),
        "wetbulb_series": _series_dict(series["years"], series["wetbulb"]),
        "peak_wetbulb_series": _series_dict(series["years"], mw),
    }


def _run_per_island(aoi, islands_file, years, thr, run_dir, name, lst_source="landsat"):
    import ee
    polys = _load_polygons(islands_file)
    if not polys:
        raise SystemExit("No island polygons found in --islands-file.")
    print(f"  per-island: {len(polys)} islands")
    # SST + wet-bulb are regional → computed once over the AOI.
    ys, sst = _sst_series(aoi, years)
    yw, wetbulb, _ = _era5_series(aoi, years)
    sst_tr, _ = _trend(ys, sst)
    wb_tr, _ = _trend(yw, wetbulb)
    rows = []
    for nm, geom, gj in polys:
        eeg = ee.Geometry(gj)
        ly, lst, _src = _lst_series(eeg, years, lst_source)
        lst_tr, lst_ch = _trend(ly, lst)
        rows.append({"island": nm, "lst_trend_c_per_decade": lst_tr,
                     "lst_change_c": lst_ch,
                     "lst_series": _series_dict(ly, lst)})
        print(f"    {nm}: LST trend {lst_tr} °C/decade")
    rows.sort(key=lambda r: (r["lst_trend_c_per_decade"] is None,
                             -(r["lst_trend_c_per_decade"] or 0)))
    return {"shared_sst_trend_c_per_decade": sst_tr,
            "shared_wetbulb_trend_c_per_decade": wb_tr,
            "n_islands": len(rows), "islands": rows}


def _print_summary(stats):
    print()
    if stats["mode"] == "per-island":
        print(f"Island-heat [{stats['n_islands']} islands]  "
              f"shared SST {stats['shared_sst_trend_c_per_decade']} °C/dec, "
              f"wet-bulb {stats['shared_wetbulb_trend_c_per_decade']} °C/dec")
        for r in stats["islands"][:10]:
            print(f"  {r['island']:24s} LST {r['lst_trend_c_per_decade']} °C/decade")
    else:
        print(f"Island-heat trends (°C/decade):  "
              f"SST {stats['sst_trend_c_per_decade']}  ·  "
              f"LST {stats['lst_trend_c_per_decade']} ({stats.get('lst_source')})  ·  "
              f"wet-bulb {stats['wetbulb_trend_c_per_decade']}")
        if stats.get("peak_wetbulb_latest_c") is not None:
            print(f"Peak humid heat (hottest month): wet-bulb {stats['peak_wetbulb_latest_c']} °C "
                  f"latest ({stats['peak_wetbulb_trend_c_per_decade']:+} °C/decade); "
                  f"danger ≥{WETBULB_DANGER:.0f}, extreme ≥{WETBULB_EXTREME:.0f}")
