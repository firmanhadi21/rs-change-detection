#!/usr/bin/env python3
"""Haze scenario — fire smoke and air quality together, from satellites.

Fires are only half the story: what people actually feel is the smoke. This
joins the fire record to the air people breathe, day by day:

  * surface PM2.5 from CAMS (ECMWF near-real-time), classified with Indonesia's
    ISPU categories and the WHO 24-hour guideline;
  * the absorbing aerosol index from Sentinel-5P TROPOMI — a direct smoke-plume
    tracer, updated to within a day;
  * FIRMS active-fire hotspots over the same window, so you can see the fires
    that produced the smoke;
  * a smoke map: mean aerosol index over the episode with hotspots on top.

Useful for answering "how bad is the air right now, and which fires are doing
it" during a haze episode. Backend: needs --backend gee.
"""

import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

CAMS_IC = "ECMWF/CAMS/NRT"
CAMS_PM25 = "particulate_matter_d_less_than_25_um_surface"   # kg/m3
S5P_AAI = "COPERNICUS/S5P/OFFL/L3_AER_AI"
S5P_AAI_NRT = "COPERNICUS/S5P/NRTI/L3_AER_AI"
FIRMS_IC = "FIRMS"
WHO_24H = 15.0                       # WHO 2021 24-hour PM2.5 guideline, ug/m3
SMOKE_BUFFER_M = 250_000             # smoke map frame around the AOI (regional)
# Indonesian ISPU PM2.5 breakpoints (PermenLHK P.14/2020), ug/m3
ISPU = [(15.5, "Baik", "#2e9e4f"), (55.4, "Sedang", "#2f7fd1"),
        (150.4, "Tidak Sehat", "#e8a33d"), (250.4, "Sangat Tidak Sehat", "#d1372f"),
        (float("inf"), "Berbahaya", "#6b2020")]


def _ispu(v):
    for hi, name, col in ISPU:
        if v <= hi:
            return name, col
    return ISPU[-1][1], ISPU[-1][2]


# ----------------------------- series -----------------------------
def _days(start, end):
    """Inclusive date list — --haze-end YYYY-MM-DD includes that day."""
    import datetime as dt
    a = dt.date.fromisoformat(start); b = dt.date.fromisoformat(end)
    return [a + dt.timedelta(days=i) for i in range((b - a).days + 1)]


def _safe_sum(ic, band):
    """Sum a collection that may be empty for a given day.

    An empty ImageCollection sums to a band-less image, which then breaks
    unmask(). Merging in a zero image keeps the band present. This happens
    routinely at the end of the window, where sources have different latency
    (CAMS runs ahead of FIRMS by a few days).
    """
    import ee
    return ic.merge(ee.ImageCollection([ee.Image(0).rename(band)])).sum()


def _pm25_series(aoi, days, scale=40000):
    """Daily mean surface PM2.5 in ug/m3 (CAMS)."""
    import ee
    coll = ee.ImageCollection(CAMS_IC).select(CAMS_PM25)

    def one(d):
        s = ee.Date(d.isoformat())
        im = coll.filterDate(s, s.advance(1, "day")).mean().multiply(1e9)
        return im.reduceRegion(ee.Reducer.mean(), aoi, scale,
                               bestEffort=True).get(CAMS_PM25)
    return [None if v is None else round(v, 1)
            for v in ee.List([one(d) for d in days]).getInfo()]


def _aai_series(aoi, days, scale=10000):
    """Daily mean absorbing aerosol index (Sentinel-5P), offline + NRT."""
    import ee
    coll = (ee.ImageCollection(S5P_AAI).select("absorbing_aerosol_index")
            .merge(ee.ImageCollection(S5P_AAI_NRT)
                   .select("absorbing_aerosol_index")))

    def one(d):
        s = ee.Date(d.isoformat())
        im = coll.filterDate(s, s.advance(1, "day")).filterBounds(aoi).mean()
        return im.reduceRegion(ee.Reducer.mean(), aoi, scale,
                               bestEffort=True).get("absorbing_aerosol_index")
    return [None if v is None else round(v, 2)
            for v in ee.List([one(d) for d in days]).getInfo()]


def _hotspot_series(aoi, days, scale=1000):
    """Daily FIRMS active-fire pixel count over the AOI."""
    import ee
    coll = ee.ImageCollection(FIRMS_IC).select("T21")

    def one(d):
        s = ee.Date(d.isoformat())
        ic = coll.filterDate(s, s.advance(1, "day")).map(lambda i: i.gt(0))
        im = _safe_sum(ic, "T21").unmask(0)
        return im.reduceRegion(ee.Reducer.sum(), aoi, scale,
                               maxPixels=int(1e10), bestEffort=True).get("T21")
    return [int(v or 0) for v in ee.List([one(d) for d in days]).getInfo()]


# ----------------------------- rendering -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _render_timeline(run_dir, name, days, pm, aai, hot):
    """PM2.5 with ISPU bands, aerosol index, and hotspots on one timeline."""
    import numpy as np
    plt = _plt()
    fig, axes = plt.subplots(3, 1, figsize=(13, 9), dpi=150, sharex=True)
    fig.patch.set_facecolor("#faf8f4")
    x = np.arange(len(days))

    ax = axes[0]
    lo = 0
    for hi, label, col in ISPU:
        top = min(hi, max([v for v in pm if v is not None] + [1]) * 1.25)
        if lo < top:
            ax.axhspan(lo, top, color=col, alpha=0.16, lw=0)
            ax.text(0.2, (lo + top) / 2, label, fontsize=7.5, va="center",
                    color=col, fontweight="bold")
        lo = hi
        if lo > max([v for v in pm if v is not None] + [1]) * 1.25:
            break
    vals = [np.nan if v is None else v for v in pm]
    ax.plot(x, vals, "o-", color="#20242a", lw=1.8, ms=3.5)
    ax.axhline(WHO_24H, color="#0b6", ls="--", lw=1.2,
               label=f"pedoman WHO 24 jam ({WHO_24H:g})")
    ax.set_ylabel("PM2.5 (µg/m³)", fontsize=9)
    ax.set_ylim(0, max([v for v in pm if v is not None] + [1]) * 1.25)
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title(f"Kualitas udara & asap karhutla — {name}", fontsize=13,
                 fontweight="bold", loc="left")
    ax.grid(True, axis="y", ls=":", alpha=0.3)

    ax = axes[1]
    av = [np.nan if v is None else v for v in aai]
    ax.plot(x, av, "o-", color="#8a4b08", lw=1.6, ms=3)
    ax.axhline(1.0, color="#8a4b08", ls=":", lw=1,
               label="AAI > 1 ≈ asap tebal")
    ax.set_ylabel("Indeks aerosol\n(Sentinel-5P)", fontsize=9)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, axis="y", ls=":", alpha=0.3)

    ax = axes[2]
    ax.bar(x, hot, color="#b30000")
    ax.set_ylabel("titik panas\n(FIRMS)", fontsize=9)
    ax.grid(True, axis="y", ls=":", alpha=0.3)
    step = max(len(days) // 22, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([d.strftime("%d %b") for d in days[::step]],
                       rotation=45, fontsize=8)
    fig.tight_layout()
    out = os.path.join(run_dir, "haze_timeline.png")
    fig.savefig(out, facecolor="#faf8f4"); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


def _render_smoke_map(aai_tif, fire_tif, bbox, run_dir, name, window):
    """Mean aerosol index over the episode, with active-fire pixels on top."""
    import numpy as np
    import rasterio
    plt = _plt()
    with rasterio.open(aai_tif) as ds:
        a = ds.read(1, masked=True).astype("float64").filled(np.nan)
        ab = ds.bounds
    w, s, e, n = ab.left, ab.bottom, ab.right, ab.top     # smoke frame, not AOI
    fig, ax = plt.subplots(figsize=(11, 10), dpi=150)
    # AAI is routinely negative over bright land; scale to the data, not to 0.
    finite = a[np.isfinite(a)]
    vmin, vmax = ((np.nanpercentile(finite, 2), np.nanpercentile(finite, 98))
                  if finite.size else (-1.0, 1.0))
    if vmax - vmin < 0.2:
        vmin, vmax = vmin - 0.1, vmax + 0.1
    im = ax.imshow(a, extent=[w, e, s, n], origin="upper", cmap="inferno",
                   vmin=vmin, vmax=vmax)
    plt.colorbar(im, ax=ax, shrink=0.7,
                 label="Indeks aerosol absorbing (asap)")
    if fire_tif and os.path.exists(fire_tif):
        with rasterio.open(fire_tif) as ds:
            f = ds.read(1).astype("float64")
        rows, cols = f.shape
        yy, xx = np.where(f > 0)
        lon = w + (xx + 0.5) * (e - w) / cols
        lat = n - (yy + 0.5) * (n - s) / rows
        ax.plot(lon, lat, ".", color="#39ff14", ms=2.5, alpha=0.9,
                label="titik panas FIRMS")
        ax.legend(loc="lower left", fontsize=9, framealpha=0.85)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    ax.set_title(f"Sebaran asap & titik api — {name}\n{window}",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.3)
    fig.tight_layout()
    out = os.path.join(run_dir, "haze_smoke_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


def _episode_days(dd, pm):
    """The current episode: the trailing run of days above the WHO guideline.

    A top-N-by-PM2.5 pick would scatter across the window and average the
    episode away; the trailing run is what people are breathing now.
    """
    have = [(d, v) for d, v in zip(dd, pm) if v is not None]
    episode = []
    for d, v in reversed(have):
        if v > WHO_24H:
            episode.append(d)
        elif episode:
            break
    return episode or [d for d, v in sorted(have, key=lambda t: -t[1])[:5]]


def _smoke_map(aoi, box, dd, pm, run_dir, name):
    """Aerosol index + hotspots over the current episode, on a regional frame."""
    import datetime as dt
    import ee
    from .gee_utils import download_geotiff
    peak_days = _episode_days(dd, pm)
    if not peak_days:
        return
    w0 = min(peak_days).isoformat()
    w1 = (max(peak_days) + dt.timedelta(days=1)).isoformat()
    coll = (ee.ImageCollection(S5P_AAI).select("absorbing_aerosol_index")
            .merge(ee.ImageCollection(S5P_AAI_NRT)
                   .select("absorbing_aerosol_index")))
    # Smoke is regional: a 7 km sensor over a city-sized box yields no pixels.
    smoke_aoi = aoi.buffer(SMOKE_BUFFER_M).bounds()
    aai_img = coll.filterDate(w0, w1).filterBounds(smoke_aoi).mean().clip(smoke_aoi)
    at = os.path.join(run_dir, "haze_aai.tif")
    ft = os.path.join(run_dir, "haze_fires.tif")
    fire_ic = (ee.ImageCollection(FIRMS_IC).select("T21")
               .filterDate(w0, w1).map(lambda i: i.gt(0)))
    fire_img = _safe_sum(fire_ic, "T21").unmask(0).clip(smoke_aoi)
    ok = download_geotiff(aai_img, smoke_aoi, at, scale=7000) is not None
    download_geotiff(fire_img.toByte(), smoke_aoi, ft, scale=2000)
    if ok:
        _render_smoke_map(at, ft, box, run_dir, name,
                          f"episode {w0} → {max(peak_days).isoformat()}")


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        days=45, start=None, end=None, admin=None, bbox=None):
    """Haze episode: PM2.5 + aerosol index + hotspots, plus a smoke map (GEE)."""
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"haze needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("haze currently needs --backend gee (CAMS + Sentinel-5P).")
    import datetime as dt
    import ee
    from .gee_utils import initialize_ee, download_geotiff
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)

    end = end or dt.date.today().isoformat()
    start = start or (dt.date.fromisoformat(end) -
                      dt.timedelta(days=int(days))).isoformat()
    dd = _days(start, end)
    if not dd:
        raise SystemExit("empty date range — check --start/--end.")

    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    box = [min(xs), min(ys), max(xs), max(ys)]
    print(f"  window {start} → {end} ({len(dd)} hari)")

    pm = _pm25_series(aoi, dd)
    aai = _aai_series(aoi, dd)
    hot = _hotspot_series(aoi, dd)
    _render_timeline(run_dir, name, dd, pm, aai, hot)

    _smoke_map(aoi, box, dd, pm, run_dir, name)

    valid = [v for v in pm if v is not None]
    cats = {}
    for v in valid:
        cats[_ispu(v)[0]] = cats.get(_ispu(v)[0], 0) + 1
    worst_i = max(range(len(pm)), key=lambda i: -1 if pm[i] is None else pm[i])
    latest = next(((d, v) for d, v in reversed(list(zip(dd, pm)))
                   if v is not None), (None, None))
    stats = {"run_id": run_id, "scenario": "haze", "name": name,
             "window": {"start": start, "end": end, "days": len(dd)},
             "sources": {"pm25": "ECMWF CAMS NRT (surface PM2.5)",
                         "aerosol_index": "Sentinel-5P TROPOMI (AAI)",
                         "hotspots": "FIRMS (MODIS)"},
             "pm25_ugm3_by_day": {d.isoformat(): v for d, v in zip(dd, pm)},
             "aerosol_index_by_day": {d.isoformat(): v for d, v in zip(dd, aai)},
             "hotspots_by_day": {d.isoformat(): v for d, v in zip(dd, hot)},
             "pm25_mean": round(sum(valid) / len(valid), 1) if valid else None,
             "pm25_max": max(valid) if valid else None,
             "pm25_max_date": dd[worst_i].isoformat() if valid else None,
             "latest": {"date": latest[0].isoformat() if latest[0] else None,
                        "pm25": latest[1],
                        "ispu": _ispu(latest[1])[0] if latest[1] else None},
             "days_by_ispu": cats,
             "days_above_who24h": sum(1 for v in valid if v > WHO_24H),
             "total_hotspots": sum(hot),
             "note": ("CAMS PM2.5 is a model reanalysis/forecast, not a ground "
                      "monitor; use it for episode timing and relative severity, "
                      "and compare with BMKG/KLHK station data where available")}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    if latest[1] is not None:
        print(f"\nUdara {name} — terakhir {latest[0]}: PM2.5 {latest[1]:.0f} µg/m³ "
              f"({_ispu(latest[1])[0]})")
    print(f"  puncak {stats['pm25_max']} µg/m³ pada {stats['pm25_max_date']} · "
          f"{stats['days_above_who24h']}/{len(valid)} hari di atas pedoman WHO · "
          f"{sum(hot):,} titik panas")
    return stats
