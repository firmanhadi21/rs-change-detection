#!/usr/bin/env python3
"""Drought: rainfall deficit (SPI), vegetation health (VCI/TCI/VHI), and ENSO state.

Three questions, three data sources, deliberately kept separate because they can
disagree and the disagreement is informative:

  1. Is rain missing?          CHIRPS 1981-      -> standardized rainfall anomaly
  2. Are plants suffering yet? MODIS NDVI + LST  -> VCI / TCI / VHI
  3. Is ENSO driving it?       NOAA OISST        -> Nino 3.4 anomaly

Which drought types this covers, in the Wilhite & Glantz (1985) sense:

  METEOROLOGICAL  rainfall_z, fully covered. Note this stays meteorological at
                  ANY --spi-months; the window changes what it is relevant to,
                  not what it measures.
  AGRICULTURAL    VCI/TCI/VHI, covered as an OBSERVED PROXY -- vegetation stress
                  is the symptom, not root-zone soil moisture itself.
  HYDROLOGICAL    only approximated, via --spi-months 6-12. There is no
                  streamflow, reservoir or groundwater data here. Do not report
                  a long-window rainfall index as a hydrological drought
                  assessment.
  SOCIOECONOMIC   not covered, and not derivable from satellites: it depends on
                  demand, allocation and infrastructure.

The types form a chain, each lagging the one before: rainfall deficit -> soil
and crops -> rivers and reservoirs -> people. So a large rainfall deficit with
a still-healthy VHI means the impact has not landed *yet*, not that it is
harmless -- and a recovered VHI does not mean reservoirs have refilled.

IMPORTANT on naming: the rainfall index here is a z-score of accumulated rainfall
against the same calendar window in each baseline year -- NOT a gamma-fitted SPI.
The two agree closely for 3-month and longer accumulations in the humid tropics
but diverge in the dry season, where rainfall is bounded at zero and strongly
skewed. Reported as `rainfall_z` and labelled as such everywhere.
"""

import json
import os
import datetime as dt

CHIRPS_IC = "UCSB-CHG/CHIRPS/DAILY"
NDVI_IC = "MODIS/061/MOD13A2"          # 1 km, 16-day, from 2000-02
LST_IC = "MODIS/061/MOD11A2"           # 1 km, 8-day, from 2000-02
SST_IC = "NOAA/CDR/OISST/V2_1"

CHIRPS_SCALE = 5566                    # native CHIRPS resolution, metres
MODIS_SCALE = 1000
SST_SCALE = 27830

CLIM_BASE = (1991, 2020)               # WMO normal, used for the SST climatology
MODIS_BASE = (2001, 2020)              # MODIS starts 2000; 2001 is the first full year

# Rainfall products, trading latency against archive depth and calibration.
# CHIRPS is gauge-blended and authoritative but lags ~5 weeks, which is useless
# for a season in progress; the others see the last few days.
#
# `factor` converts each product's native storage to MILLIMETRES:
#   CHIRPS/ERA5 store a per-image TOTAL (ERA5 in metres, hence 1000)
#   IMERG/GSMaP store a RATE in mm/hr, so each image counts for its own
#   duration -- 0.5 h for half-hourly IMERG, 1 h for hourly GSMaP.
#
# NEVER mix products inside one anomaly. Over Semarang, Apr-Jun 2026 totals were
# CHIRPS 500 mm, IMERG 403, GSMaP 363, ERA5 312 -- a real 60-100% spread between
# products. A current window from one and a climatology from another would turn
# that bias straight into a fake anomaly. Each source carries its own baseline.
RAIN_SOURCES = {
    "chirps": {"ic": CHIRPS_IC, "band": "precipitation", "factor": 1.0,
               "scale": CHIRPS_SCALE, "base": (1991, 2020), "archive": 1981,
               "label": "CHIRPS daily (UCSB-CHG), gauge+satellite",
               "lag": "~5 minggu"},
    "era5": {"ic": "ECMWF/ERA5_LAND/DAILY_AGGR", "band": "total_precipitation_sum",
             "factor": 1000.0, "scale": 11132, "base": (1991, 2020), "archive": 1950,
             "label": "ERA5-Land daily (ECMWF reanalysis)", "lag": "~8 hari"},
    "imerg": {"ic": "NASA/GPM_L3/IMERG_V07", "band": "precipitation",
              "factor": 0.5, "scale": 11132, "base": (2001, 2020), "archive": 1998,
              "label": "GPM IMERG V07 (satelit, near-real-time)", "lag": "~1 hari"},
    "gsmap": {"ic": "JAXA/GPM_L3/GSMaP/v8/operational", "band": "hourlyPrecipRate",
              "factor": 1.0, "scale": 11132, "base": (2001, 2020), "archive": 1998,
              "label": "GSMaP v8 operational (JAXA, satelit)", "lag": "~1 hari"},
}
DEFAULT_RAIN_SOURCE = "chirps"
NINO34_BOX = [-170, -5, -120, 5]       # standard Nino 3.4 region
# Indian Ocean Dipole poles (Saji et al. 1999). For Indonesia the IOD matters as
# much as ENSO: a positive dipole means cool water off Sumatra/Java, less
# convection, and suppressed rainfall -- and the two can compound.
IOD_WEST_BOX = [50, -10, 70, 10]
IOD_EAST_BOX = [90, -10, 110, 0]
IOD_EVENT_C = 0.4                      # conventional |DMI| event threshold

# McKee et al. (1993), the conventional SPI class boundaries.
SPI_CLASSES = [
    (2.0, "Sangat basah", "#0b5cad"),
    (1.5, "Basah", "#4a90d9"),
    (1.0, "Agak basah", "#9ecae1"),
    (-1.0, "Normal", "#d9d9d9"),
    (-1.5, "Kering sedang", "#fdae61"),
    (-2.0, "Kering parah", "#e34a33"),
    (-99.0, "Kering ekstrem", "#7f0000"),
]

# Kogan (1995) vegetation-health classes.
VHI_CLASSES = [
    (40.0, "Tidak kekeringan", "#1a9850"),
    (30.0, "Kekeringan ringan", "#fee08b"),
    (20.0, "Kekeringan sedang", "#fdae61"),
    (10.0, "Kekeringan parah", "#e34a33"),
    (-1.0, "Kekeringan ekstrem", "#7f0000"),
]

ENSO_CLASSES = [
    (2.0, "El Nino sangat kuat"), (1.5, "El Nino kuat"),
    (1.0, "El Nino sedang"), (0.5, "El Nino lemah"),
    (-0.5, "Netral"), (-1.0, "La Nina lemah"),
    (-1.5, "La Nina sedang"), (-99.0, "La Nina kuat"),
]

IOD_CLASSES = [
    (IOD_EVENT_C, "IOD positif"), (-IOD_EVENT_C, "Netral"),
    (-99.0, "IOD negatif"),
]


def _classify(value, table):
    """First label whose threshold the value clears (tables run high -> low)."""
    if value is None:
        return ("tidak diketahui", "#999999") if len(table[0]) == 3 else "tidak diketahui"
    for row in table:
        if value >= row[0]:
            return row[1:] if len(row) == 3 else row[1]
    return table[-1][1:] if len(table[0]) == 3 else table[-1][1]


def _spi_label(z):
    return _classify(z, SPI_CLASSES)


def _shift_months(d, n):
    """Date n months before d, snapped to the 1st (calendar-window arithmetic)."""
    m = d.month - n
    y = d.year + (m - 1) // 12
    return d.replace(year=y, month=(m - 1) % 12 + 1, day=1)


def _latest(ic_id, band):
    """Most recent acquisition date in a collection -- drought data always lags."""
    import ee
    img = ee.ImageCollection(ic_id).select(band).sort("system:time_start", False).first()
    ms = img.get("system:time_start").getInfo()
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).date()


def _mean_over(img, region, scale, band):
    import ee
    return ee.Number(img.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=region, scale=scale,
        maxPixels=int(1e10), bestEffort=True).get(band))


def _rain_total(aoi, start, end, src):
    """Accumulated rainfall in MILLIMETRES for one window, whatever the source."""
    import ee
    return (ee.ImageCollection(src["ic"]).select(src["band"])
            .filterDate(start.isoformat(), end.isoformat())
            .sum().multiply(src["factor"]))


def _same_window(start, end, year):
    """The same calendar window in another year, tolerating 29 February."""
    off = year - end.year
    try:
        return start.replace(year=start.year + off), end.replace(year=year)
    except ValueError:
        return start.replace(year=start.year + off), end.replace(year=year, day=28)


def _rain_window_totals(aoi, end, months, src):
    """Accumulated rainfall for the target window and the same window each
    baseline year. Returns (current_mm, [baseline_mm, ...]) as ee.Numbers."""
    import ee
    start = _shift_months(end, months)
    band, scale = src["band"], src["scale"]
    cur = _mean_over(_rain_total(aoi, start, end, src), aoi, scale, band)
    hist = []
    for y in range(src["base"][0], src["base"][1] + 1):
        a, b = _same_window(start, end, y)
        hist.append(_mean_over(_rain_total(aoi, a, b, src), aoi, scale, band))
    return cur, ee.List(hist)


def _rainfall_z(aoi, end, months, src):
    """Standardized rainfall anomaly. See the module docstring on why this is a
    z-score and not a gamma-fitted SPI."""
    import ee
    cur, hist = _rain_window_totals(aoi, end, months, src)
    mean = ee.Number(hist.reduce(ee.Reducer.mean()))
    sd = ee.Number(hist.reduce(ee.Reducer.stdDev()))
    out = ee.Dictionary({
        "current_mm": cur, "normal_mm": mean, "sd_mm": sd,
        "z": cur.subtract(mean).divide(sd),
        "pct_of_normal": cur.divide(mean).multiply(100),
    }).getInfo()
    return {k: (round(v, 2) if isinstance(v, (int, float)) else v)
            for k, v in out.items()}


def _rain_z_by_year(aoi, end, months, src, years):
    """Rainfall z for the same calendar window in each of `years`, so the current
    season can be ranked against the record rather than judged in isolation."""
    import ee
    _cur, hist = _rain_window_totals(aoi, end, months, src)
    mean = ee.Number(hist.reduce(ee.Reducer.mean()))
    sd = ee.Number(hist.reduce(ee.Reducer.stdDev()))
    start = _shift_months(end, months)
    per = []
    for y in years:
        a, b = _same_window(start, end, y)
        per.append(_mean_over(_rain_total(aoi, a, b, src), aoi,
                              src["scale"], src["band"]))
    zs = ee.List(per).map(
        lambda v: ee.Number(v).subtract(mean).divide(sd))
    return [None if v is None else round(v, 2) for v in zs.getInfo()]


def _baseline_stack(ic_id, band, start, end, base, scale_factor):
    """Same calendar window, one composite per baseline year.

    Skips years with no imagery: `.mean()` on an EMPTY ImageCollection returns a
    BANDLESS image, which then breaks any arithmetic downstream.
    """
    import ee
    ic = ee.ImageCollection(ic_id).select(band)
    imgs = []
    for y in range(base[0], base[1] + 1):
        try:
            a, b = start.replace(year=y), end.replace(year=y)
        except ValueError:
            a, b = start.replace(year=y, day=28), end.replace(year=y)
        sub = ic.filterDate(a.isoformat(), b.isoformat())
        if sub.size().getInfo() == 0:
            continue
        imgs.append(sub.mean().multiply(scale_factor))
    if not imgs:
        raise SystemExit(f"no baseline imagery for {ic_id} in {base[0]}-{base[1]}")
    return ee.ImageCollection(imgs)


def _condition_index(ic_id, band, end, window, base, scale_factor, invert=False):
    """VCI / TCI: where does today sit between the historical min and max?

    VCI = (NDVI - min) / (max - min) * 100          -- low means stressed
    TCI = (max - LST) / (max - min) * 100           -- low means hot

    Clamped to [0, 100]. The current period is NOT part of the baseline, so it can
    fall outside the historical min/max and drive the raw ratio past either end.
    Both indices are defined on 0-100, and "beyond anything in the baseline" is
    correctly represented by saturating rather than by 117.
    """
    import ee
    start = end - dt.timedelta(days=window)
    cur = (ee.ImageCollection(ic_id).select(band)
           .filterDate(start.isoformat(), end.isoformat())
           .mean().multiply(scale_factor))
    hist = _baseline_stack(ic_id, band, start, end, base, scale_factor)
    lo, hi = hist.min(), hist.max()
    rng = hi.subtract(lo)
    num = hi.subtract(cur) if invert else cur.subtract(lo)
    return num.divide(rng).multiply(100).clamp(0, 100).rename("ci")


def _vhi(aoi, end, window, base):
    """Vegetation Health Index = mean of VCI and TCI (Kogan 1995)."""
    vci = _condition_index(NDVI_IC, "NDVI", end, window, base, 0.0001)
    tci = _condition_index(LST_IC, "LST_Day_1km", end, window, base, 0.02, invert=True)
    vhi = vci.multiply(0.5).add(tci.multiply(0.5)).rename("vhi")
    vals = {
        "vci": _mean_over(vci, aoi, MODIS_SCALE, "ci").getInfo(),
        "tci": _mean_over(tci, aoi, MODIS_SCALE, "ci").getInfo(),
        "vhi": _mean_over(vhi, aoi, MODIS_SCALE, "vhi").getInfo(),
    }
    return vhi, {k: (round(v, 1) if v is not None else None) for k, v in vals.items()}


def _sst_mean(box, a, b):
    import ee
    sst = ee.ImageCollection(SST_IC).select("sst")
    return _mean_over(sst.filterDate(a.isoformat(), b.isoformat()).mean()
                      .multiply(0.01), ee.Geometry.Rectangle(box),
                      SST_SCALE, "sst")


def _sst_anomaly(box, m0, m1):
    """One month's SST anomaly for a box, against the 1991-2020 climatology."""
    import ee
    clim = ee.List([_sst_mean(box, m0.replace(year=y),
                              m1.replace(year=y + (m1.year - m0.year)))
                    for y in range(CLIM_BASE[0], CLIM_BASE[1] + 1)])
    return _sst_mean(box, m0, m1).subtract(ee.Number(clim.reduce(ee.Reducer.mean())))


def _months_back(end, months):
    """[(label, month_start, next_month_start), ...] oldest first."""
    out = []
    for i in range(months - 1, -1, -1):
        m0 = _shift_months(end.replace(day=1), i)
        out.append((m0.strftime("%Y-%m"), m0, _shift_months(m0, -1)))
    return out


def _climate_modes(end, months=24):
    """Monthly Nino 3.4 and IOD Dipole Mode Index, resolved in one round trip.

    DMI = western-pole anomaly minus eastern-pole anomaly (Saji et al. 1999).
    Both are computed from the same OISST collection and the same climatology,
    so they are directly comparable on one axis.
    """
    import ee
    wins = _months_back(end, months)
    nino = [_sst_anomaly(NINO34_BOX, m0, m1) for _, m0, m1 in wins]
    dmi = [_sst_anomaly(IOD_WEST_BOX, m0, m1).subtract(
           _sst_anomaly(IOD_EAST_BOX, m0, m1)) for _, m0, m1 in wins]
    both = ee.List([ee.List(nino), ee.List(dmi)]).getInfo()

    def clean(seq):
        return [round(v, 2) if v is not None else None for v in seq]

    return [w[0] for w in wins], clean(both[0]), clean(both[1])


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _panel_rain(ax, years, zs, cur_year):
    import numpy as np
    x = np.arange(len(years))
    cols = []
    for y, z in zip(years, zs):
        if z is None:
            cols.append("#cccccc")
        elif y == cur_year:
            cols.append("#7f0000")
        else:
            cols.append("#c46a1f" if z < 0 else "#4a90d9")
    ax.bar(x, [0 if z is None else z for z in zs], color=cols)
    ax.axhline(0, color="#333", lw=.8)
    for thr, style in ((-1.0, ":"), (-1.5, "--"), (-2.0, "-")):
        ax.axhline(thr, color="#7f0000", lw=.8, ls=style, alpha=.7)
    ax.set_xticks(x[::2])
    ax.set_xticklabels([str(y) for y in years][::2], rotation=45, fontsize=8)
    ax.set_ylabel("Anomali hujan (z)", fontsize=9)
    ax.set_title("Kekeringan meteorologis — anomali hujan terstandar per tahun",
                 fontsize=10, loc="left")


def _panel_health(ax, hv):
    labels = ["VCI\n(vegetasi)", "TCI\n(suhu)", "VHI\n(gabungan)"]
    vals = [hv["vci"], hv["tci"], hv["vhi"]]
    cols = [_classify(v, VHI_CLASSES)[1] if v is not None else "#cccccc" for v in vals]
    ax.bar(labels, [v or 0 for v in vals], color=cols, width=.55)
    for i, v in enumerate(vals):
        if v is not None:
            ax.text(i, v + 2, f"{v:.0f}", ha="center", fontsize=10, fontweight="bold")
    for thr in (10, 20, 30, 40):
        ax.axhline(thr, color="#999", lw=.6, ls=":")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Indeks (0–100)", fontsize=9)
    ax.set_title("Kesehatan vegetasi — di bawah 40 menandakan tekanan kekeringan",
                 fontsize=10, loc="left")


def _panel_enso(ax, labels, nino, dmi):
    """ENSO and IOD on one axis: for Indonesia the two compound, and reading
    either one alone is how forecasts get over-claimed."""
    import numpy as np
    x = np.arange(len(labels))
    nv = [0 if v is None else v for v in nino]
    dv = [0 if v is None else v for v in dmi]
    ax.plot(x, nv, color="#1a1a1a", lw=1.5, marker="o", ms=3, label="Nino 3.4 (ENSO)")
    ax.fill_between(x, 0, nv, where=[v > 0 for v in nv],
                    color="#e34a33", alpha=.35, interpolate=True)
    ax.fill_between(x, 0, nv, where=[v < 0 for v in nv],
                    color="#4a90d9", alpha=.35, interpolate=True)
    ax.plot(x, dv, color="#6a3d9a", lw=1.5, ls="--", marker="s", ms=3,
            label="DMI (IOD)")
    for thr, col in ((0.5, "#666"), (-0.5, "#666"),
                     (IOD_EVENT_C, "#6a3d9a"), (-IOD_EVENT_C, "#6a3d9a")):
        ax.axhline(thr, color=col, lw=.7, ls=":", alpha=.8)
    ax.axhline(0, color="#333", lw=.8)
    step = max(1, len(labels) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(labels[::step], rotation=45, fontsize=8)
    ax.set_ylabel("Anomali SST (°C)", fontsize=9)
    ax.legend(fontsize=8, frameon=False, ncol=2, loc="upper left")
    ax.set_title("Mode iklim — Nino 3.4 (>+0,5 °C = El Nino) & "
                 "IOD/DMI (>+0,4 °C = IOD positif)", fontsize=10, loc="left")


def _render_panel(run_dir, name, years, zs, hv, labels, nino, dmi, meta):
    plt = _plt()
    fig, axes = plt.subplots(3, 1, figsize=(11, 12), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    for ax in axes:
        ax.set_facecolor("#faf8f4")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    _panel_rain(axes[0], years, zs, meta["current_year"])
    _panel_health(axes[1], hv)
    _panel_enso(axes[2], labels, nino, dmi)
    fig.suptitle(f"Kekeringan — {name}", fontsize=15, fontweight="bold",
                 x=.02, ha="left", y=.985)
    fig.text(.02, .955,
             f"Jendela {meta['months']} bulan berakhir {meta['rain_end']} · "
             f"baseline hujan {meta['base'][0]}–{meta['base'][1]}, "
             f"vegetasi {MODIS_BASE[0]}–{MODIS_BASE[1]}",
             fontsize=9, color="#555")
    fig.text(.02, .012,
             f"Sumber: {meta['source']} (hujan) · MODIS MOD13A2/MOD11A2 (VCI/TCI) · "
             "NOAA OISST (Nino 3.4 & DMI/IOD). Anomali hujan = z-score, bukan SPI gamma.",
             fontsize=8, color="#777")
    fig.tight_layout(rect=[0, .025, 1, .945])
    out = os.path.join(run_dir, f"{name}_kekeringan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _rain_pct_image(aoi, end, months, src):
    """Per-pixel rainfall as % of the baseline normal for the same window.

    The area-mean z-score answers "how dry overall"; this answers "dry WHERE",
    which is the part that survives being screenshotted into a discussion.
    """
    start = _shift_months(end, months)
    import ee
    hist = []
    for y in range(src["base"][0], src["base"][1] + 1):
        a, b = _same_window(start, end, y)
        hist.append(_rain_total(aoi, a, b, src))
    normal = ee.ImageCollection(hist).mean()
    return (_rain_total(aoi, start, end, src).divide(normal).multiply(100)
            .clip(aoi).rename("pct"))


def _rings(geom):
    """Every coordinate ring in a GeoJSON geometry, whatever shape it takes
    (Polygon / MultiPolygon / GeometryCollection all occur in FAO GAUL)."""
    if not isinstance(geom, dict):
        return
    if geom.get("type") == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from _rings(g)
        return
    stack = [geom.get("coordinates") or []]
    while stack:
        node = stack.pop()
        if (isinstance(node, list) and node and isinstance(node[0], list)
                and node[0] and isinstance(node[0][0], (int, float))):
            yield node
        elif isinstance(node, list):
            stack.extend(n for n in node if isinstance(n, list))


def _draw_admin(ax, box):
    """Province outlines for context; silently skipped if the lookup fails."""
    import ee
    import numpy as np
    try:
        fc = (ee.FeatureCollection("FAO/GAUL/2015/level1")
              .filterBounds(ee.Geometry.Rectangle(box)))
        feats = fc.getInfo()["features"]
    except Exception:
        return
    for f in feats:
        for ring in _rings(f.get("geometry")):
            r = np.asarray(ring, dtype="float64")
            ax.plot(r[:, 0], r[:, 1], color="#333", lw=.55, alpha=.65)


def _render_rain_map(run_dir, name, tif, box, meta):
    """Map of rainfall as % of normal, from the GeoTIFF just downloaded."""
    import numpy as np
    import rasterio
    from matplotlib.colors import TwoSlopeNorm
    plt = _plt()

    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float32")
        b = src.bounds
    arr[arr <= 0] = np.nan
    if not np.isfinite(arr).any():
        return None

    # Shape the canvas to the AOI: a wide thin island like Java in a square
    # figure is mostly empty background.
    span_x, span_y = box[2] - box[0], box[3] - box[1]
    aspect = span_x / span_y if span_y else 1.0
    height = min(11.0, max(4.2, 11.0 / max(aspect, .35) + 2.0))
    fig, ax = plt.subplots(figsize=(11, height), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_facecolor("#faf8f4")
    im = ax.imshow(arr, cmap="BrBG", norm=TwoSlopeNorm(vmin=50, vcenter=100, vmax=150),
                   extent=[b.left, b.right, b.bottom, b.top])
    _draw_admin(ax, box)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(f"Curah hujan {name} — {meta['months']} bulan s/d {meta['rain_end']}\n"
                 f"% dari normal {meta['base'][0]}–{meta['base'][1]} ({meta['source']})",
                 fontsize=13, fontweight="bold", loc="left")
    cb = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=.046,
                      pad=.04, ticks=[50, 75, 100, 125, 150])
    cb.set_label("% dari normal  (coklat = lebih kering, hijau = lebih basah)",
                 fontsize=9.5)
    cb.ax.tick_params(labelsize=8.5)
    fig.text(.01, .015, "Sumber: CHIRPS harian (UCSB-CHG), batas provinsi FAO GAUL 2015. "
             "Dihitung dengan earthchange -s drought.", fontsize=8, color="#777")
    fig.tight_layout(rect=[0, .03, 1, 1])
    out = os.path.join(run_dir, f"{name}_peta_hujan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _rain_map(aoi, run_dir, name, end, months, src):
    """Download the % of normal field and render it. Best effort: the charts are
    the primary output, so a map failure must not sink the run."""
    from .gee_utils import download_geotiff
    tif = os.path.join(run_dir, f"{name}_hujan_pct.tif")
    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    box = [min(xs), min(ys), max(xs), max(ys)]
    # Rainfall pixels are 5-11 km depending on source. Below roughly 15 of them
    # across, the map is a blocky rectangle with no internal landmarks -- the
    # GeoTIFF is still valid data, but the PNG misleads more than it informs.
    span_km = (box[2] - box[0]) * 111.0
    if span_km < 15 * src["scale"] / 1000:
        print(f"  (AOI ~{span_km:.0f} km: terlalu kecil untuk peta "
              f"{src['scale'] / 1000:.0f} km — peta tetap dibuat tetapi sangat "
              f"kasar; pakai --radius >50 km atau --admin)")
    try:
        got = download_geotiff(_rain_pct_image(aoi, end, months, src).toFloat(),
                               coords, tif, scale=src["scale"])
        if not got:
            return None, None
        png = _render_rain_map(run_dir, name, got, box,
                               {"months": months, "rain_end": end.isoformat(),
                                "base": src["base"], "source": src["label"]})
        return png, got
    except Exception as exc:
        print(f"  (peta hujan dilewati: {str(exc)[:70]})")
        return None, None


def _vhi_class_image(vhi):
    """VHI -> 0..4 (ekstrem, parah, sedang, ringan, tidak kekeringan).

    Boundaries are the Kogan (1995) ones already used for the bar labels, so the
    map and the summary bar cannot drift apart.
    """
    return (vhi.gte(10).add(vhi.gte(20)).add(vhi.gte(30)).add(vhi.gte(40))
            .rename("cls").toByte())


def _vhi_class_areas(vhi, aoi):
    """Hectares in each drought class -- the answer to 'where', as a number.

    One grouped reduction rather than five, so this costs a single round trip.
    """
    import ee
    cls = _vhi_class_image(vhi)
    grouped = (ee.Image.pixelArea().divide(1e4).addBands(cls)
               .reduceRegion(reducer=ee.Reducer.sum().group(groupField=1,
                                                            groupName="cls"),
                             geometry=aoi, scale=MODIS_SCALE,
                             maxPixels=int(1e10), bestEffort=True).getInfo())
    labels = [r[1] for r in reversed(VHI_CLASSES)]      # index 0..4
    out = {lab: 0.0 for lab in labels}
    for g in grouped.get("groups", []):
        i = int(g["cls"])
        if 0 <= i < len(labels):
            out[labels[i]] = round(g["sum"], 1)
    total = sum(out.values()) or 1.0
    return out, {k: round(v / total * 100, 1) for k, v in out.items()}


def _render_vhi_map(run_dir, name, tif, box, meta, pct):
    """Classified drought map: which parts of the AOI are stressed, not just how
    stressed it is on average."""
    import numpy as np
    import rasterio
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    plt = _plt()

    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float32")
        b = src.bounds
    if not np.isfinite(arr).any():
        return None

    labels = [r[1] for r in VHI_CLASSES]                # ekstrem -> tidak
    colours = [r[2] for r in VHI_CLASSES]
    cmap = ListedColormap(list(reversed(colours)))
    norm = BoundaryNorm([0, 10, 20, 30, 40, 100], cmap.N)

    span_x, span_y = box[2] - box[0], box[3] - box[1]
    aspect = span_x / span_y if span_y else 1.0
    height = min(11.0, max(4.6, 11.0 / max(aspect, .35) + 2.2))
    fig, ax = plt.subplots(figsize=(11, height), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_facecolor("#faf8f4")
    ax.imshow(arr, cmap=cmap, norm=norm,
              extent=[b.left, b.right, b.bottom, b.top])
    _draw_admin(ax, box)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(f"Sebaran kekeringan vegetasi — {name}\n"
                 f"VHI (MODIS 1 km), {meta['vegetation_end']}",
                 fontsize=13, fontweight="bold", loc="left")
    # One decimal: a class holding tens of thousands of hectares still rounds to
    # "0%" of a large AOI, which reads as "nothing here" when it is not.
    handles = [Patch(facecolor=c, edgecolor="none",
                     label=f"{lab} — {pct.get(lab, 0):.1f}%")
               for lab, c in zip(labels, colours)]
    ax.legend(handles=handles, fontsize=9, frameon=False, ncol=3,
              loc="upper center", bbox_to_anchor=(.5, -.02))
    fig.text(.01, .015, "VHI = 0,5·VCI + 0,5·TCI (Kogan 1995); di bawah 40 = tekanan "
             "kekeringan. Sumber: MODIS MOD13A2 + MOD11A2.", fontsize=8, color="#777")
    fig.tight_layout(rect=[0, .05, 1, 1])
    out = os.path.join(run_dir, f"{name}_peta_kekeringan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _drought_extent(vhi, aoi, run_dir, name, veg_end):
    """GeoTIFF + classified map + area per drought class.

    Best effort: the charts are the primary output, so a failure here prints a
    note and the run still completes.
    """
    from .gee_utils import download_geotiff
    path = os.path.join(run_dir, f"{name}_vhi.tif")
    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    box = [min(xs), min(ys), max(xs), max(ys)]
    try:
        ha, pct = _vhi_class_areas(vhi, aoi)
        tif = download_geotiff(vhi.clip(aoi).toFloat(), coords, path,
                               scale=MODIS_SCALE)
        png = (_render_vhi_map(run_dir, name, tif, box,
                               {"vegetation_end": veg_end.isoformat()}, pct)
               if tif else None)
        return tif, png, ha, pct
    except Exception as exc:
        print(f"  (peta VHI dilewati: {str(exc)[:70]})")
        return None, None, {}, {}


def _print_extent(cls_ha, cls_pct):
    """Where the drought is, as a breakdown -- the average alone hides it."""
    if not cls_pct:
        return
    in_drought = sum(v for k, v in cls_pct.items() if k != "Tidak kekeringan")
    print(f"  luas terdampak: {in_drought:.0f}% dari AOI di bawah VHI 40")
    for row in VHI_CLASSES:
        lab = row[1]
        if cls_ha.get(lab):
            print(f"    {lab:22s} {cls_ha[lab]:>12,.0f} ha  ({cls_pct[lab]:5.1f}%)")


def _record_years(start_year, src, last_year):
    """Years to rank the current season against.

    Defaults to the product's OWN archive rather than a number inherited from
    another scenario: "driest of 27 years" and "driest of 36" are different
    claims, and that difference must not come from an unrelated flag's default.
    """
    first = max(start_year or src["archive"], src["archive"])
    return list(range(first, last_year + 1))


def _warn_if_stale(rain_source, rain_end):
    """A stale window reports "Normal" for a season that has already turned.

    Over Central Java in August 2026, CHIRPS (to 30 Jun) said 101% of normal
    while ERA5, IMERG and GSMaP -- all seeing into late July -- independently
    said 67-71%. The default must not hide that silently.
    """
    stale = (dt.date.today() - rain_end).days
    if rain_source == "chirps" and stale > 21:
        print(f"  ⚠ jendela hujan tertinggal {stale} hari dari hari ini. Untuk "
              f"musim yang sedang berjalan coba --rain-source era5 (lag ~8 hari) "
              f"atau imerg (~1 hari).")


def _resolve_source(name):
    if name not in RAIN_SOURCES:
        raise SystemExit(f"--rain-source harus salah satu dari "
                         f"{', '.join(RAIN_SOURCES)} (diberikan: {name})")
    return RAIN_SOURCES[name]


def _resolve_end(explicit, src):
    """Align to the freshest image of the chosen source unless the caller pinned
    a date. Each product has a different lag, so this cannot be a constant."""
    if explicit:
        return dt.date.fromisoformat(explicit)
    return _latest(src["ic"], src["band"])


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        months=3, end=None, admin=None, bbox=None, start_year=1991,
        vhi_window=48, rain_source=DEFAULT_RAIN_SOURCE):
    """Drought: rainfall deficit, vegetation health, and ENSO context."""
    for mod in ("numpy", "matplotlib"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"drought needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("drought currently needs --backend gee (CHIRPS + MODIS + OISST).")

    from .gee_utils import initialize_ee
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)

    src = _resolve_source(rain_source)
    rain_end = _resolve_end(end, src)
    ndvi_end = _latest(NDVI_IC, "NDVI")
    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)

    print(f"  hujan s/d {rain_end} ({rain_source}, lag {src['lag']}) · "
          f"vegetasi s/d {ndvi_end} (MODIS)")
    _warn_if_stale(rain_source, rain_end)
    print(f"  jendela {months} bulan · baseline hujan "
          f"{src['base'][0]}–{src['base'][1]}")

    rain = _rainfall_z(aoi, rain_end, months, src)
    years = _record_years(start_year, src, rain_end.year)
    zs = _rain_z_by_year(aoi, rain_end, months, src, years)

    vhi_img, hv = _vhi(aoi, ndvi_end, vhi_window, MODIS_BASE)
    # ENSO is anchored to the freshest SST, not to the rainfall window: OISST lags
    # only days while CHIRPS lags weeks, and "is it El Nino right now" is usually
    # the question being asked.
    sst_end = _latest(SST_IC, "sst")
    labels, nino, dmi = _climate_modes(sst_end)

    png = _render_panel(run_dir, name, years, zs, hv, labels, nino, dmi,
                        {"months": months, "rain_end": rain_end.isoformat(),
                         "current_year": rain_end.year, "base": src["base"],
                         "source": src["label"]})
    tif, vhi_png, cls_ha, cls_pct = _drought_extent(vhi_img, aoi, run_dir, name,
                                                    ndvi_end)
    map_png, map_tif = _rain_map(aoi, run_dir, name, rain_end, months, src)

    z = rain["z"]
    ranked = sorted((v for v in zs if v is not None))
    rank = ranked.index(z) + 1 if z in ranked else None
    enso_now = next((v for v in reversed(nino) if v is not None), None)
    iod_now = next((v for v in reversed(dmi) if v is not None), None)

    stats = {
        "run_id": run_id, "scenario": "drought", "name": name,
        "window": {"months": months, "rain_end": rain_end.isoformat(),
                   "vegetation_end": ndvi_end.isoformat(),
                   "enso_end": sst_end.isoformat(),
                   "rain_source": rain_source,
                   "rain_baseline": list(src["base"])},
        "sources": {
            "rainfall": (f"{src['label']} ({src['ic']}), baseline "
                         f"{src['base'][0]}-{src['base'][1]}, lag {src['lag']}"),
            "vegetation": f"MODIS {NDVI_IC} + {LST_IC}, baseline {MODIS_BASE[0]}-{MODIS_BASE[1]}",
            "enso": f"NOAA OISST ({SST_IC}), Nino 3.4 region {NINO34_BOX}",
            "iod": (f"NOAA OISST ({SST_IC}), DMI = west {IOD_WEST_BOX} minus "
                    f"east {IOD_EAST_BOX} (Saji et al. 1999)")},
        "rainfall": {**rain, "class": _spi_label(z)[0]},
        "rainfall_z_by_year": dict(zip([str(y) for y in years], zs)),
        "rank_driest_of_record": rank, "years_in_record": len(ranked),
        "vegetation": {**hv, "class": _classify(hv["vhi"], VHI_CLASSES)[0],
                       "area_ha_by_class": cls_ha, "area_pct_by_class": cls_pct,
                       "area_pct_in_drought": round(
                           sum(v for k, v in cls_pct.items()
                               if k != "Tidak kekeringan"), 1)},
        "enso": {"nino34_anomaly_c": enso_now,
                 "class": _classify(enso_now, ENSO_CLASSES),
                 "monthly": dict(zip(labels, nino))},
        "iod": {"dmi_c": iod_now, "class": _classify(iod_now, IOD_CLASSES),
                "event_threshold_c": IOD_EVENT_C,
                "monthly": dict(zip(labels, dmi))},
        "outputs": {"panel": os.path.basename(png),
                    "drought_map": os.path.basename(vhi_png) if vhi_png else None,
                    "rainfall_map": os.path.basename(map_png) if map_png else None,
                    "rainfall_geotiff": os.path.basename(map_tif) if map_tif else None,
                    "vhi_geotiff": os.path.basename(tif) if tif else None},
        "note": ("rainfall_z is a z-score of accumulated rainfall against the same "
                 "calendar window in each baseline year, NOT a gamma-fitted SPI; the "
                 "two agree for >=3-month windows in the humid tropics but diverge in "
                 "the dry season. Meteorological drought leads agricultural drought, "
                 "so a large deficit with healthy VHI means impact has not landed yet."),
    }
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nKekeringan {name} — {months} bulan s/d {rain_end}")
    print(f"  hujan {rain['current_mm']:.0f} mm ({rain['pct_of_normal']:.0f}% dari "
          f"normal {rain['normal_mm']:.0f} mm) · z {z:+.2f} → {_spi_label(z)[0]}")
    if rank:
        print(f"  peringkat terkering ke-{rank} dari {len(ranked)} tahun")
    print(f"  VHI {hv['vhi']:.0f} (VCI {hv['vci']:.0f} · TCI {hv['tci']:.0f}) → "
          f"{_classify(hv['vhi'], VHI_CLASSES)[0]}")
    _print_extent(cls_ha, cls_pct)
    if enso_now is not None:
        print(f"  Nino 3.4 {enso_now:+.2f} °C ({sst_end}) → "
              f"{_classify(enso_now, ENSO_CLASSES)}")
    if iod_now is not None:
        print(f"  IOD/DMI  {iod_now:+.2f} °C ({sst_end}) → "
              f"{_classify(iod_now, IOD_CLASSES)}")
    return stats
