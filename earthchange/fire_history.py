#!/usr/bin/env python3
"""Fire-history scenario — multi-year burned area, fire recurrence and season.

Where does this area burn, when in the year, and how often? Unlike the `burn`
scenario (dNBR severity of one fire event), this builds the long record:

  * burned area per year from MODIS MCD64A1 (500 m, 2000-11 → present),
    split into peat and mineral soil;
  * a fire-recurrence map — how many distinct years each pixel burned, so
    repeat-burn hotspots stand out from one-off fires;
  * the fire season — burned area by calendar month across all years, which
    in Indonesia peaks in the Jul–Oct dry season (Aug–Sep in El Niño years);
  * active-fire hotspot counts per year (FIRMS/MODIS "titik panas").

Peat matters because peat fires drive the haze crises and most of the carbon.
By default peat is a **proxy**: OpenLandMap soil organic carbon ≥ --peat-thr.
Calibrated against Riau (3.8 Mha vs ~4.0 Mha official) and Jawa Barat (~0);
it over-predicts in Kalimantan, where official maps count only peat >50 cm.
For citable figures pass an authoritative peat map with --peat-file.

Backend: needs --backend gee.
"""

import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

BURN_IC = "MODIS/061/MCD64A1"          # 500 m monthly burned area, 2000-11 →
FIRMS_IC = "FIRMS"                     # MODIS active fire (hotspots), daily
SOC_IMG = "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02"
SOC_BAND = "b10"                       # 10 cm depth, raw units (see --peat-thr)
PEAT_THR = 30.0                        # raw SOC; calibrated on Riau/Jawa Barat
# Global 1 km peat thickness (GPM 2.0 extent, digital soil mapping), via the
# awesome-gee-community-catalog. Server-side, no download needed.
PEATGRIDS_IMG = "projects/sat-io/open-datasets/PEATGRIDS/THICKNESS_CM"
PEAT_SOURCES = ("soc", "peatgrids", "file")
DEFAULT_START = 2001                   # first full year of MCD64A1
BURN_SCALE = 500
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ----------------------------- GEE building blocks -----------------------------
def _is_raster(path):
    return bool(path) and path.lower().endswith((".tif", ".tiff", ".vrt"))


def _resolve_aoi(admin, bbox, lon, lat, radius):
    """AOI from an admin name (FAO GAUL level-1, else level-2), bbox, or square.

    Tries provinces first, then falls back to regencies/districts, so
    --admin works for both "Kalimantan Barat" and "Kubu Raya".
    """
    import ee
    from .gee_utils import square_aoi
    if admin:
        for lvl, field in (("level1", "ADM1_NAME"), ("level2", "ADM2_NAME")):
            fc = (ee.FeatureCollection(f"FAO/GAUL/2015/{lvl}")
                  .filter(ee.Filter.eq(field, admin)))
            if fc.size().getInfo() > 0:
                print(f"  admin: {admin} [GAUL {lvl}]")
                return fc.geometry()
        raise SystemExit(f"--admin {admin!r} not found in FAO GAUL level-1 or "
                         "level-2. Use the official spelling, e.g. "
                         "'Kalimantan Tengah' or 'Kubu Raya'.")
    if bbox:
        return ee.Geometry.Rectangle(list(bbox))
    return square_aoi(lon, lat, radius)


def _peat_mask(peat_source, peat_file, peat_thr):
    """Server-side peat mask + provenance label.

    Returns (ee.Image | None, label). None means the mask is a *local* raster
    (e.g. the Gumbricht GeoTIFF) and is applied after download instead.
    """
    import ee
    if peat_file and _is_raster(peat_file):
        return None, f"peat raster: {os.path.basename(peat_file)}"
    if peat_file:                                    # vector (GeoJSON) peat map
        with open(peat_file) as f:
            gj = json.load(f)
        feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry(ft["geometry"]))
                                   for ft in feats])
        return ee.Image(0).paint(fc, 1).gt(0), \
            f"peat map from {os.path.basename(peat_file)}"
    if peat_source == "peatgrids":
        thick = ee.Image(PEATGRIDS_IMG).select(0)
        return thick.gt(0).unmask(0), "peat: PEATGRIDS thickness > 0 (1 km)"
    soc = ee.Image(SOC_IMG).select(SOC_BAND)
    return soc.gte(peat_thr).unmask(0), \
        f"peat proxy: OpenLandMap SOC(10cm) >= {peat_thr:g} (raw units)"


def _local_peat_on_grid(peat_file, tif):
    """Read a local peat raster (e.g. Gumbricht) onto the burn raster's grid."""
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling
    with rasterio.open(tif) as ref:
        dst = np.zeros((ref.height, ref.width), dtype="uint8")
        with rasterio.open(peat_file) as src:
            reproject(source=rasterio.band(src, 1), destination=dst,
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=ref.transform, dst_crs=ref.crs,
                      resampling=Resampling.nearest)
    return dst == 1                                   # Gumbricht: 1 = peat


def _year_burn(year):
    """Burned-once-or-more mask for a calendar year (each pixel counted once)."""
    import ee
    ic = (ee.ImageCollection(BURN_IC)
          .filterDate(f"{year}-01-01", f"{year + 1}-01-01").select("BurnDate"))
    return ic.map(lambda im: im.gt(0)).max().unmask(0).rename("burn")


def _area_ha(mask, aoi, scale=BURN_SCALE):
    import ee
    return (mask.multiply(ee.Image.pixelArea()).rename("area")
            .reduceRegion(ee.Reducer.sum(), aoi, scale, maxPixels=int(1e10),
                          bestEffort=True).get("area"))


def _annual_series(aoi, years, peat):
    """Burned ha per year, split peat / mineral. One server round-trip."""
    import ee
    tot, pt = [], []
    for y in years:
        b = _year_burn(y).clip(aoi)
        tot.append(_area_ha(b, aoi))
        pt.append(_area_ha(b.And(peat), aoi))
    got = ee.List([ee.List(tot), ee.List(pt)]).getInfo()
    ha = lambda xs: [round((v or 0) / 1e4, 1) for v in xs]      # noqa: E731
    return ha(got[0]), ha(got[1])


def _season_series(aoi, years, scale=BURN_SCALE):
    """Burned ha by calendar month, summed over all years (fire season)."""
    import ee
    coll = (ee.ImageCollection(BURN_IC)
            .filterDate(f"{years[0]}-01-01", f"{years[-1] + 1}-01-01")
            .select("BurnDate"))
    out = []
    for m in range(1, 13):
        im = (coll.filter(ee.Filter.calendarRange(m, m, "month"))
              .map(lambda i: i.gt(0)).sum().unmask(0).clip(aoi))
        out.append(_area_ha(im, aoi, scale))
    got = ee.List(out).getInfo()
    return [round((v or 0) / 1e4, 1) for v in got]


def _hotspots(aoi, years):
    """FIRMS active-fire pixel-days per year (Indonesian 'titik panas')."""
    import ee
    out = []
    for y in years:
        ic = (ee.ImageCollection(FIRMS_IC)
              .filterDate(f"{y}-01-01", f"{y + 1}-01-01").select("T21"))
        cnt = ic.map(lambda i: i.gt(0)).sum().unmask(0).clip(aoi)
        out.append(cnt.reduceRegion(ee.Reducer.sum(), aoi, 1000,
                                    maxPixels=int(1e10), bestEffort=True).get("T21"))
    try:
        return [int(v or 0) for v in ee.List(out).getInfo()]
    except Exception as e:  # noqa: BLE001 — hotspots are a bonus series
        print(f"  (hotspot counts skipped: {e.__class__.__name__})")
        return None


def _frequency(aoi, years):
    """How many distinct years each pixel burned."""
    import ee
    imgs = [_year_burn(y) for y in years]
    return ee.ImageCollection(imgs).sum().rename("times").clip(aoi)


def _burn_stack(aoi, years):
    """One band per year, burned (1) / not (0) — for local analysis."""
    import ee
    return ee.Image.cat([_year_burn(y).rename(f"y{y}") for y in years]) \
        .toByte().clip(aoi)


def _cell_ha(ds):
    """Per-row cell area in hectares for a lon/lat raster."""
    import numpy as np
    t = ds.transform
    dlon, dlat = abs(t.a), abs(t.e)
    lat_top = t.f
    lats = lat_top - (np.arange(ds.height) + 0.5) * dlat
    return (dlat * 110574.0) * (dlon * 111320.0 * np.cos(np.radians(lats))) / 1e4


def _annual_local(stack_tif, years, peat_arr):
    """Annual burned ha (total, peat) and the recurrence grid, computed locally."""
    import numpy as np
    import rasterio
    with rasterio.open(stack_tif) as ds:
        a = ds.read().astype(bool)                    # (year, row, col)
        ha = _cell_ha(ds)[None, :, None]
        prof = ds.profile
    if peat_arr is not None:
        pk = peat_arr[:a.shape[1], :a.shape[2]]
        if pk.shape != a.shape[1:]:                   # pad if the peat clip is short
            pad = np.zeros(a.shape[1:], dtype=bool)
            pad[:pk.shape[0], :pk.shape[1]] = pk
            pk = pad
    else:
        pk = np.zeros(a.shape[1:], dtype=bool)
    tot = [round(float((a[i] * ha[0]).sum()), 1) for i in range(len(years))]
    pt = [round(float(((a[i] & pk) * ha[0]).sum()), 1) for i in range(len(years))]
    freq = a.sum(axis=0).astype("uint8")
    return tot, pt, freq, prof


def _write_freq(freq, prof, out):
    import rasterio
    prof = dict(prof)
    prof.update(count=1, dtype="uint8", nodata=0)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(freq, 1)
    return out


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


def _render_freq_map(tif, bbox, run_dir, name, years):
    """Fire-recurrence map: how many years each pixel burned."""
    import numpy as np
    import rasterio
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    plt = _plt()
    with rasterio.open(tif) as ds:
        a = ds.read(1).astype("float64")
    a[a <= 0] = np.nan                                   # never burned → transparent
    top = int(np.nanmax(a)) if np.isfinite(a).any() else 1
    top = max(top, 1)
    cmap_src = plt.get_cmap("YlOrRd", max(top, 3))
    colors = [cmap_src(i / max(top - 1, 1)) for i in range(top)]
    cmap = ListedColormap(colors); cmap.set_bad((0, 0, 0, 0))
    norm = BoundaryNorm(np.arange(0.5, top + 1.5, 1), cmap.N)
    w, s, e, n = bbox
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    ax.imshow(a, extent=[w, e, s, n], origin="upper", cmap=cmap, norm=norm,
              interpolation="nearest", alpha=0.85, zorder=2)
    handles = [Patch(facecolor=colors[i], label=f"{i + 1}×" + (" (berulang)" if i else ""))
               for i in range(top)]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9,
              title="Berapa kali terbakar")
    ax.set_title(f"Riwayat kebakaran — {name}\n"
                 f"jumlah tahun terbakar, {years[0]}–{years[-1]}",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "fire_frequency_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


def _render_year_chart(run_dir, name, years, tot, peat, hot, peat_label):
    """Burned area per year, peat vs mineral, with the hotspot series."""
    import numpy as np
    plt = _plt()
    mineral = [max(t - p, 0.0) for t, p in zip(tot, peat)]
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    x = np.arange(len(years))
    ax.bar(x, peat, color="#7f2704", label="Gambut (peat)")
    ax.bar(x, mineral, bottom=peat, color="#fdae6b", label="Tanah mineral")
    ax.set_xticks(x); ax.set_xticklabels([str(y) for y in years], rotation=45, fontsize=8)
    ax.set_ylabel("Luas terbakar (ha)")
    worst = int(np.argmax(tot))
    ax.annotate(f"{years[worst]}: {tot[worst]:,.0f} ha", (x[worst], tot[worst]),
                textcoords="offset points", xytext=(0, 8), ha="center",
                fontsize=9, fontweight="bold", color="#7f2704")
    if hot:
        ax2 = ax.twinx()
        ax2.plot(x, hot, "o-", color="#2b2b2b", lw=1.4, ms=3.5, label="Titik panas (FIRMS)")
        ax2.set_ylabel("Titik panas (piksel-hari)")
        ax2.legend(loc="upper right", fontsize=8)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title(f"Luas terbakar per tahun — {name}\n{peat_label}",
                 fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "fire_by_year.png")
    fig.savefig(out); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


def _render_season(run_dir, name, season, years):
    """Fire season: burned area by calendar month across all years."""
    import numpy as np
    plt = _plt()
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    x = np.arange(12)
    peak = int(np.argmax(season)) if any(season) else 0
    colors = ["#fdae6b"] * 12
    colors[peak] = "#7f2704"
    ax.bar(x, season, color=colors)
    ax.set_xticks(x); ax.set_xticklabels(MONTHS)
    ax.set_ylabel("Luas terbakar (ha, total semua tahun)")
    ax.set_title(f"Musim kebakaran — {name}\n"
                 f"puncak: {MONTHS[peak]} ({years[0]}–{years[-1]})",
                 fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "fire_season.png")
    fig.savefig(out); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


# ----------------------------- season vs baseline -----------------------------
def _hotspots_to_date(aoi, years, md_end):
    """FIRMS hotspot pixel-days for Jan 1 → `md_end` (MM-DD) in each year.

    The same calendar window every year, so a part-finished season can be
    compared honestly against history instead of against full years.
    """
    import ee
    out = []
    for y in years:
        ic = (ee.ImageCollection(FIRMS_IC)
              .filterDate(f"{y}-01-01", f"{y}-{md_end}").select("T21"))
        cnt = ic.map(lambda i: i.gt(0)).sum().unmask(0)
        out.append(cnt.reduceRegion(ee.Reducer.sum(), aoi, 1000,
                                    maxPixels=int(1e10), bestEffort=True).get("T21"))
    return [int(v or 0) for v in ee.List(out).getInfo()]


def _baseline_stats(years, vals, current):
    """Compare the current year against the full record and the recent decade.

    Reported separately because fire regimes shift: after the 2015 crisis
    Indonesian provinces dropped sharply, so a long-run mean understates how
    anomalous a current season is.
    """
    import numpy as np
    prior = [(y, v) for y, v in zip(years, vals) if y != current]
    cur = dict(zip(years, vals)).get(current)
    if cur is None or not prior:
        return None
    allp = [v for _, v in prior]
    recent = [v for y, v in prior if y >= current - 10]
    rank = sorted(allp + [cur], reverse=True).index(cur) + 1
    return {"current_year": current, "current": cur,
            "baseline_mean": round(float(np.mean(allp)), 1),
            "baseline_years": [prior[0][0], prior[-1][0]],
            "recent_mean": round(float(np.mean(recent)), 1) if recent else None,
            "recent_years": [max(min(y for y, _ in prior), current - 10),
                             current - 1],
            "ratio_vs_baseline": round(cur / max(np.mean(allp), 1), 2),
            "ratio_vs_recent": (round(cur / max(np.mean(recent), 1), 2)
                                if recent else None),
            "rank": rank, "of": len(allp) + 1}


def _render_baseline(run_dir, name, years, vals, md_end, bs):
    """Current season against the record: bars per year, current highlighted."""
    import numpy as np
    plt = _plt()
    fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    x = np.arange(len(years))
    cur_y = bs["current_year"]
    cols = ["#b30000" if y == cur_y else "#8a8a8a" if y == cur_y - 1
            else "#c8c4b8" for y in years]
    ax.bar(x, vals, color=cols)
    ax.axhline(bs["baseline_mean"], color="#7f2704", ls="--", lw=1.3,
               label=f"rata-rata {bs['baseline_years'][0]}–{bs['baseline_years'][1]}"
                     f" ({bs['baseline_mean']:,.0f})")
    if bs["recent_mean"] is not None:
        ax.axhline(bs["recent_mean"], color="#2f7fd1", ls=":", lw=1.5,
                   label=f"rata-rata {bs['recent_years'][0]}–{bs['recent_years'][1]}"
                         f" ({bs['recent_mean']:,.0f})")
    note = f"{cur_y}: {bs['current']:,}"
    if bs["ratio_vs_recent"] is not None:
        note += f"  (×{bs['ratio_vs_recent']:.1f} dekade terakhir · " \
                f"peringkat {bs['rank']}/{bs['of']})"
    ax.annotate(note, (len(years) - 1, bs["current"]),
                textcoords="offset points", xytext=(-6, 8), ha="right",
                fontsize=10, fontweight="bold", color="#b30000")
    ax.set_xticks(x); ax.set_xticklabels([str(y) for y in years],
                                         rotation=45, fontsize=8)
    ax.set_ylabel("titik panas (piksel-hari)")
    ax.set_title(f"Musim berjalan vs baseline — {name}\n"
                 f"FIRMS, 1 Jan – {md_end} (jendela tanggal sama tiap tahun)",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, axis="y", ls=":", alpha=0.35)
    fig.tight_layout()
    out = os.path.join(run_dir, "fire_vs_baseline.png")
    fig.savefig(out, facecolor="#faf8f4"); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


def _burned_series(aoi, years, peat, peat_file, run_dir, tif, box, name):
    """Annual burned ha (total, peat) + the recurrence GeoTIFF and its map.

    With a server-side peat mask the series is reduced in Earth Engine. With a
    local peat raster (e.g. Gumbricht) one per-year burn stack is downloaded
    and the whole computation runs locally on that grid.
    """
    from .gee_utils import download_geotiff
    if peat is None:
        stack = os.path.join(run_dir, "fire_burn_stack.tif")
        if download_geotiff(_burn_stack(aoi, years), aoi, stack,
                            scale=BURN_SCALE) is None:
            raise SystemExit("burn-stack download failed — try a smaller --radius "
                             "or a shorter year range.")
        peat_arr = _local_peat_on_grid(peat_file, stack)
        tot, pt, freq_arr, prof = _annual_local(stack, years, peat_arr)
        _write_freq(freq_arr, prof, tif)
        print(f"Saved: {os.path.normpath(tif)}")
        _render_freq_map(tif, box, run_dir, name, years)
        return tot, pt
    tot, pt = _annual_series(aoi, years, peat)
    if download_geotiff(_frequency(aoi, years).toByte(), aoi, tif,
                        scale=BURN_SCALE) is not None:
        _render_freq_map(tif, box, run_dir, name, years)
    else:
        print("  (frequency map skipped: download failed — try a smaller --radius)")
    return tot, pt


def _season_vs_baseline(aoi, start_year, run_dir, name):
    """Current season to date vs the same calendar window in every prior year.

    Uses FIRMS rather than MCD64A1 because burned area lags by months, so it
    cannot describe a season that is still running.
    """
    import datetime as _dt
    today = _dt.date.today()
    byears = list(range(start_year, today.year + 1))
    bvals = _hotspots_to_date(aoi, byears, today.strftime("%m-%d"))
    bs = _baseline_stats(byears, bvals, today.year)
    if not bs:
        print("  (baseline skipped: no data for the current year)")
        return None
    bs["window"] = f"Jan 1 – {today.strftime('%b %d')}"
    bs["hotspots_by_year"] = dict(zip(byears, bvals))
    _render_baseline(run_dir, name, byears, bvals, today.strftime("%d %b"), bs)
    print(f"  musim {bs['current_year']} s/d {bs['window']}: {bs['current']:,} "
          f"titik panas · ×{bs['ratio_vs_baseline']} rata-rata panjang" +
          (f" · ×{bs['ratio_vs_recent']} dekade terakhir"
           if bs["ratio_vs_recent"] else "") +
          f" · peringkat {bs['rank']}/{bs['of']}")
    return bs


# ----------------------------- multi-area comparison -----------------------------
def _render_areas_panel(results, run_dir, years):
    """One figure comparing several areas: per-area annual series + summaries."""
    import math as _m
    import numpy as np
    plt = _plt()
    names = list(results)
    n = len(names)
    fig = plt.figure(figsize=(15, 2.1 * n + 4.2), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    gs = fig.add_gridspec(n + 1, 3, height_ratios=[1] * n + [1.3],
                          hspace=0.62, wspace=0.28)
    x = np.arange(len(years))
    for i, nm in enumerate(names):
        s = results[nm]
        tot = [s["burned_ha_by_year"][y] for y in years]
        pt = [s["peat_burned_ha_by_year"][y] for y in years]
        mineral = [max(a - b, 0) for a, b in zip(tot, pt)]
        ax = fig.add_subplot(gs[i, :])
        ax.bar(x, pt, color="#7f2704", label="Gambut (peat)")
        ax.bar(x, mineral, bottom=pt, color="#fdae6b", label="Tanah mineral")
        ax.set_ylim(0, max(max(tot), 1) * 1.22)     # per-panel scale
        ax.set_xticks(x)
        ax.set_xticklabels([str(y) if i == n - 1 else "" for y in years],
                           rotation=45, fontsize=7.5)
        ax.set_ylabel("ha", fontsize=8)
        w = s["worst_year"]
        ax.annotate(f"{w}: {s['worst_year_ha']:,.0f} ha",
                    (years.index(w), s["worst_year_ha"]),
                    textcoords="offset points", xytext=(0, 4), ha="center",
                    fontsize=8, fontweight="bold", color="#7f2704")
        ax.set_title(f"{nm} — {s['total_burned_ha']:,.0f} ha total, "
                     f"{s['peat_share_pct']:.0f}% gambut, puncak {s['peak_month']}",
                     fontsize=10, fontweight="bold", loc="left")
        ax.grid(True, axis="y", ls=":", alpha=0.35)
        if i == 0:      # figure-level legend, so it can't cover a peak label
            fig.legend(*ax.get_legend_handles_labels(), loc="upper right",
                       fontsize=9, ncol=2, bbox_to_anchor=(0.99, 0.995))

    yy = np.arange(n)
    tots = [results[k]["total_burned_ha"] / 1e3 for k in names]
    peats = [results[k]["peat_burned_ha"] / 1e3 for k in names]
    axA = fig.add_subplot(gs[n, 0])
    axA.barh(yy, [t - p for t, p in zip(tots, peats)], left=peats, color="#fdae6b")
    axA.barh(yy, peats, color="#7f2704")
    axA.set_yticks(yy); axA.set_yticklabels(names, fontsize=8); axA.invert_yaxis()
    axA.set_xlabel(f"ribu ha terbakar {years[0]}–{years[-1]}", fontsize=8)
    axA.set_title("Total", fontsize=10, fontweight="bold", loc="left")
    axA.grid(True, axis="x", ls=":", alpha=0.35)

    axB = fig.add_subplot(gs[n, 1])
    shares = [results[k]["peat_share_pct"] for k in names]
    axB.barh(yy, shares, color="#7f2704")
    axB.set_yticks(yy); axB.set_yticklabels([]); axB.invert_yaxis()
    axB.set_xlabel("% luas terbakar di gambut", fontsize=8)
    axB.set_title("Porsi gambut", fontsize=10, fontweight="bold", loc="left")
    for i, v in enumerate(shares):
        axB.text(v + 1, i, f"{v:.0f}%", va="center", fontsize=8)
    axB.grid(True, axis="x", ls=":", alpha=0.35)

    axC = fig.add_subplot(gs[n, 2])
    for nm in names:
        se = [results[nm]["burned_ha_by_month"][m] for m in MONTHS]
        t = sum(se) or 1
        axC.plot(range(12), [100 * v / t for v in se], "o-", ms=3, lw=1.5, label=nm)
    axC.set_xticks(range(12)); axC.set_xticklabels(MONTHS, fontsize=7)
    axC.set_ylabel("% luas terbakar", fontsize=8)
    axC.set_title("Musim kebakaran", fontsize=10, fontweight="bold", loc="left")
    axC.legend(fontsize=6.5); axC.grid(True, ls=":", alpha=0.35)

    fig.suptitle(f"Riwayat karhutla {years[0]}–{years[-1]} — perbandingan wilayah\n"
                 "skala-y tiap panel berbeda (bandingkan besaran di panel Total)",
                 fontsize=14, fontweight="bold", y=0.995)
    out = os.path.join(run_dir, "fire_areas_comparison.png")
    fig.savefig(out, facecolor="#faf8f4", bbox_inches="tight"); plt.close(fig)
    print(f"\nComparison: {os.path.normpath(out)}")


def _run_areas(areas, kw, run_dir, run_id):
    """Run fire-history for several areas, then assemble a comparison panel."""
    results, order = {}, []
    for a in areas:
        sub = os.path.join(run_dir, a.replace(" ", "_"))
        os.makedirs(sub, exist_ok=True)
        print(f"\n=== {a} ===")
        try:
            st = run(**{**kw, "name": a, "run_dir": sub, "run_id": run_id,
                        "admin": a, "bbox": None})
            results[a] = st; order.append(a)
        except SystemExit as e:
            print(f"  skipped {a}: {e}")
        except Exception as e:  # noqa: BLE001 — one bad area shouldn't kill the run
            print(f"  skipped {a}: {e.__class__.__name__}: {e}")
    if not results:
        raise SystemExit("no area produced output.")
    years = results[order[0]]["years"]
    _render_areas_panel(results, run_dir, years)
    agg = {"run_id": run_id, "scenario": "fire-history", "mode": "areas",
           "areas": results,
           "ranking_by_burned_ha": sorted(
               ((k, v["total_burned_ha"]) for k, v in results.items()),
               key=lambda t: -t[1])}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(agg, f, indent=2)
    print(f"\n{'area':<22}{'burned ha':>12}{'peat%':>7}  worst  peak")
    for k, v in agg["ranking_by_burned_ha"]:
        s = results[k]
        print(f"  {k:<20}{v:>12,.0f}{s['peat_share_pct']:>6.0f}%  "
              f"{s['worst_year']}  {s['peak_month']}")
    return agg


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        start_year=DEFAULT_START, end_year=None, bbox=None,
        peat_file=None, peat_thr=PEAT_THR, peat_source="soc", admin=None,
        vs_baseline=False):
    """Multi-year fire history: recurrence map + annual/seasonal charts (GEE)."""
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"fire-history needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("fire-history currently needs --backend gee (MODIS MCD64A1).")
    import ee
    from .gee_utils import initialize_ee
    initialize_ee(config_key)

    import datetime as _dt
    # MCD64A1 starts 2000-11, so 2000 is a partial year — clamp to the first
    # full year (also catches --start-year's 2000 default from island-heat).
    start_year = max(int(start_year or DEFAULT_START), DEFAULT_START)
    end_year = int(end_year or (_dt.date.today().year - 1))
    if end_year < start_year:
        raise SystemExit(f"--end-year must be >= {start_year}.")
    years = list(range(start_year, end_year + 1))

    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    box = [min(xs), min(ys), max(xs), max(ys)]

    peat, peat_label = _peat_mask(peat_source, peat_file, peat_thr)
    print(f"  {peat_label}")
    print(f"  years {years[0]}–{years[-1]} ({len(years)})")

    tif = os.path.join(run_dir, "fire_frequency.tif")
    tot, pt = _burned_series(aoi, years, peat, peat_file, run_dir, tif, box, name)
    season = _season_series(aoi, years)
    hot = _hotspots(aoi, years)
    _render_year_chart(run_dir, name, years, tot, pt, hot, peat_label)
    _render_season(run_dir, name, season, years)

    baseline = _season_vs_baseline(aoi, start_year, run_dir, name) if vs_baseline \
        else None

    total_ha = round(sum(tot), 1)
    peat_ha = round(sum(pt), 1)
    worst = max(range(len(years)), key=lambda i: tot[i])
    aoi_ha = (_area_ha(ee.Image(1), aoi) or 0)
    aoi_ha = round(ee.Number(aoi_ha).getInfo() / 1e4, 1)
    peak_m = max(range(12), key=lambda i: season[i]) if any(season) else 0
    stats = {"run_id": run_id, "scenario": "fire-history", "name": name,
             "dataset": "MODIS MCD64A1 burned area + FIRMS hotspots",
             "peat_definition": peat_label,
             "years": years, "aoi_ha": aoi_ha,
             "burned_ha_by_year": dict(zip(years, tot)),
             "peat_burned_ha_by_year": dict(zip(years, pt)),
             "burned_ha_by_month": dict(zip(MONTHS, season)),
             "hotspots_by_year": dict(zip(years, hot)) if hot else None,
             "total_burned_ha": total_ha,
             "peat_burned_ha": peat_ha,
             "peat_share_pct": round(100 * peat_ha / (total_ha or 1), 1),
             "worst_year": years[worst], "worst_year_ha": tot[worst],
             "peak_month": MONTHS[peak_m],
             "mean_annual_ha": round(total_ha / len(years), 1),
             "season_vs_baseline": baseline,
             "note": ("burned area is summed per year; a pixel burning in several "
                      "years counts once per year, so the total exceeds the "
                      "distinct area burned")}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nFire {years[0]}–{years[-1]} [{name}]: {total_ha:,.0f} ha burned "
          f"({stats['mean_annual_ha']:,.0f} ha/yr), "
          f"{stats['peat_share_pct']:.0f}% on peat")
    print(f"  worst year {years[worst]} ({tot[worst]:,.0f} ha) · "
          f"season peaks in {MONTHS[peak_m]}")
    return stats
