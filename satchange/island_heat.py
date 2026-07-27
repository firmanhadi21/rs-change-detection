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
L8 = "LANDSAT/LC08/C02/T1_L2"
L9 = "LANDSAT/LC09/C02/T1_L2"
ERA5_MONTHLY = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
ERA5_DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"

DEFAULT_START_YEAR = 2000
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
def _annual_series(coll, band, aoi, scale, years):
    """Server-side annual mean of `band` over `aoi` for each year (one fetch)."""
    import ee
    yl = ee.List(years)

    def per(y):
        y = ee.Number(y)
        s = ee.Date.fromYMD(y, 1, 1)
        e = ee.Date.fromYMD(y, 12, 31).advance(1, "day")
        img = coll.select(band).filterDate(s, e).mean()
        v = img.reduceRegion(ee.Reducer.mean(), aoi, scale,
                             maxPixels=int(1e9), bestEffort=True).get(band)
        return ee.Feature(None, {"year": y, "v": v})

    fc = ee.FeatureCollection(yl.map(per))
    return fc.aggregate_array("year").getInfo(), fc.aggregate_array("v").getInfo()


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


def _lst_landsat(aoi, years):
    coll = _landsat_lst_coll(aoi)
    lyrs = [y for y in years if y >= LST_MIN_YEAR]
    return _annual_series(coll, "lst", aoi, 100, lyrs)


def _era5_wetbulb_series(aoi, years):
    """Annual mean air temp, dewpoint → RH → wet-bulb (°C) over the AOI."""
    import ee
    coll = ee.ImageCollection(ERA5_MONTHLY)
    yt, tv = _annual_series(coll, "temperature_2m", aoi, 11132, years)
    yd, dv = _annual_series(coll, "dewpoint_temperature_2m", aoi, 11132, years)
    out_t, out_wb = [], []
    for i, y in enumerate(yt):
        t, d = tv[i], dv[i]
        if t is None or d is None:
            out_t.append(None); out_wb.append(None); continue
        tc, tdc = t - 273.15, d - 273.15
        out_t.append(round(tc, 2))
        out_wb.append(round(_wetbulb(tc, _rh_from_dew(tc, tdc)), 2))
    return yt, out_t, out_wb


def _heat_metrics(aoi, years, thr):
    """Per year: days with peak wet-bulb ≥ thr, and the annual max daily wet-bulb.

    Uses ERA5-Land daily-MAX air temperature (afternoon peak) with daily-mean
    dewpoint → peak humid heat. Daily-mean temperature never reaches the danger
    threshold in the tropics, so the peak is the physically meaningful quantity.
    Returns (years, days_over_thr, annual_max_wetbulb). Guarded by the caller.
    """
    import ee
    coll = ee.ImageCollection(ERA5_DAILY)

    def wb(im):
        t = im.select("temperature_2m_max").subtract(273.15)
        d = im.select("dewpoint_temperature_2m").subtract(273.15)
        es = t.expression("6.112*exp(17.62*T/(243.12+T))", {"T": t})
        e = d.expression("6.112*exp(17.62*D/(243.12+D))", {"D": d})
        rh = e.divide(es).multiply(100).clamp(1, 100)
        tw = t.expression(
            "T*atan(0.151977*sqrt(RH+8.313659)) + atan(T+RH) - atan(RH-1.676331)"
            " + 0.00391838*pow(RH,1.5)*atan(0.023101*RH) - 4.686035",
            {"T": t, "RH": rh})
        return tw.rename("wb").copyProperties(im, ["system:time_start"])

    wbc = coll.map(wb)

    def per(y):
        y = ee.Number(y)
        s = ee.Date.fromYMD(y, 1, 1)
        e = ee.Date.fromYMD(y, 12, 31).advance(1, "day")
        yc = wbc.filterDate(s, e)
        days = yc.map(lambda im: im.gte(thr)).sum()
        dv = days.reduceRegion(ee.Reducer.mean(), aoi, 11132,
                               maxPixels=int(1e9), bestEffort=True).get("wb")
        mv = yc.max().reduceRegion(ee.Reducer.mean(), aoi, 11132,
                                   maxPixels=int(1e9), bestEffort=True).get("wb")
        return ee.Feature(None, {"year": y, "days": dv, "maxwb": mv})

    fc = ee.FeatureCollection(ee.List(years).map(per))
    return (fc.aggregate_array("year").getInfo(),
            fc.aggregate_array("days").getInfo(),
            fc.aggregate_array("maxwb").getInfo())


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
                        "Wet-bulb maks. harian")
        ax2.axhline(WETBULB_DANGER, ls="--", color="#e08214", lw=1,
                    label=f"Berbahaya {WETBULB_DANGER:.0f} °C")
        ax2.axhline(WETBULB_EXTREME, ls="--", color="#b2182b", lw=1,
                    label=f"Ekstrem {WETBULB_EXTREME:.0f} °C")
        sub = f"  ({mtr:+.2f} °C/dekade)" if mtr is not None else ""
        ax2.set_title(f"Puncak panas lembab: wet-bulb maksimum harian per tahun{sub}",
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


def _aggregate(aoi, bbox, years, thr, run_dir, name):
    import ee
    print("  SST (OISST)…")
    ys, sst = _sst_series(aoi, years)
    print("  LST (Landsat thermal, land-masked)…")
    ly, lst = _lst_landsat(aoi, years)
    print("  wet-bulb (ERA5-Land)…")
    _, t2m, wetbulb = _era5_wetbulb_series(aoi, years)
    try:
        print("  peak humid heat (ERA5-Land daily wet-bulb)…")
        hy, heat_days, max_wb = _heat_metrics(aoi, years, thr)
        hd_map = dict(zip(hy, heat_days)); mw_map = dict(zip(hy, max_wb))
        heat_days = [hd_map.get(y) for y in ys]
        max_wb = [mw_map.get(y) for y in ys]
    except Exception as e:  # noqa: BLE001 — heavy optional step
        print(f"  (peak-heat metrics skipped: {e.__class__.__name__})")
        heat_days = [None] * len(ys); max_wb = [None] * len(ys)
    series = {"years": ys, "sst": sst, "lst_years": ly, "lst": lst,
              "wetbulb": wetbulb, "air_temp": t2m,
              "heat_days": heat_days, "max_wetbulb": max_wb}
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
        wetbulb_thr=WETBULB_DANGER):
    """Island SST/LST/wet-bulb trend analysis (GEE backend)."""
    for mod in ("numpy", "matplotlib", "shapely"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"island-heat needs {mod}: pip install 'satchange[maps]'")
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
        stats = _run_per_island(aoi, islands_file, years, wetbulb_thr, run_dir, name)
    else:
        series = _aggregate(aoi, bbox, years, wetbulb_thr, run_dir, name)
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
    hd = [(y, v) for y, v in zip(series["years"], series["heat_days"]) if v is not None]
    mw = series.get("max_wetbulb", [None] * len(series["years"]))
    mw_tr, _ = _trend(series["years"], mw)
    mwv = [(y, v) for y, v in zip(series["years"], mw) if v is not None]
    return {
        "sst_trend_c_per_decade": sst_tr, "sst_change_c": sst_ch,
        "lst_trend_c_per_decade": lst_tr, "lst_change_c": lst_ch,
        "wetbulb_trend_c_per_decade": wb_tr, "wetbulb_change_c": wb_ch,
        "peak_wetbulb_trend_c_per_decade": mw_tr,
        "peak_wetbulb_latest_c": (round(mwv[-1][1], 2) if mwv else None),
        "heat_days_first": (round(hd[0][1], 1) if hd else None),
        "heat_days_last": (round(hd[-1][1], 1) if hd else None),
        "sst_series": _series_dict(series["years"], series["sst"]),
        "lst_series": _series_dict(series["lst_years"], series["lst"]),
        "wetbulb_series": _series_dict(series["years"], series["wetbulb"]),
        "peak_wetbulb_series": _series_dict(series["years"], mw),
        "heat_days_series": _series_dict(series["years"], series["heat_days"]),
    }


def _run_per_island(aoi, islands_file, years, thr, run_dir, name):
    import ee
    polys = _load_polygons(islands_file)
    if not polys:
        raise SystemExit("No island polygons found in --islands-file.")
    print(f"  per-island: {len(polys)} islands")
    # SST + wet-bulb are regional → computed once over the AOI.
    _, sst = _sst_series(aoi, years)
    _, _t, wetbulb = _era5_wetbulb_series(aoi, years)
    sst_tr, _ = _trend(years, sst)
    wb_tr, _ = _trend(years, wetbulb)
    rows = []
    for nm, geom, gj in polys:
        eeg = ee.Geometry(gj)
        ly, lst = _lst_landsat(eeg, years)
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
              f"LST {stats['lst_trend_c_per_decade']}  ·  "
              f"wet-bulb {stats['wetbulb_trend_c_per_decade']}")
        if stats.get("peak_wetbulb_latest_c") is not None:
            print(f"Peak daily wet-bulb: {stats['peak_wetbulb_latest_c']} °C latest "
                  f"({stats['peak_wetbulb_trend_c_per_decade']:+} °C/decade); "
                  f"danger ≥{WETBULB_DANGER:.0f}, extreme ≥{WETBULB_EXTREME:.0f}. "
                  f"Days ≥ threshold: {stats['heat_days_first']} → {stats['heat_days_last']}")
