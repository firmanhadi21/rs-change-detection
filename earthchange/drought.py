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
               "label": {"id": "CHIRPS harian (UCSB-CHG), penakar+satelit",
                         "en": "CHIRPS daily (UCSB-CHG), gauge+satellite"},
               "lag": {"id": "~5 minggu", "en": "~5 weeks"}},
    "era5": {"ic": "ECMWF/ERA5_LAND/DAILY_AGGR", "band": "total_precipitation_sum",
             "factor": 1000.0, "scale": 11132, "base": (1991, 2020), "archive": 1950,
             "label": {"id": "ERA5-Land harian (reanalisis ECMWF)",
                       "en": "ERA5-Land daily (ECMWF reanalysis)"},
             "lag": {"id": "~8 hari", "en": "~8 days"}},
    "imerg": {"ic": "NASA/GPM_L3/IMERG_V07", "band": "precipitation",
              "factor": 0.5, "scale": 11132, "base": (2001, 2020), "archive": 1998,
              "label": {"id": "GPM IMERG V07 (satelit, near-real-time)",
                        "en": "GPM IMERG V07 (satellite, near-real-time)"},
              "lag": {"id": "~1 hari", "en": "~1 day"}},
    "gsmap": {"ic": "JAXA/GPM_L3/GSMaP/v8/operational", "band": "hourlyPrecipRate",
              "factor": 1.0, "scale": 11132, "base": (2001, 2020), "archive": 1998,
              "label": {"id": "GSMaP v8 operational (JAXA, satelit)",
                        "en": "GSMaP v8 operational (JAXA, satellite)"},
              "lag": {"id": "~1 hari", "en": "~1 day"}},
}
DEFAULT_RAIN_SOURCE = "chirps"
NINO34_BOX = [-170, -5, -120, 5]       # standard Nino 3.4 region
# Indian Ocean Dipole poles (Saji et al. 1999). For Indonesia the IOD matters as
# much as ENSO: a positive dipole means cool water off Sumatra/Java, less
# convection, and suppressed rainfall -- and the two can compound.
IOD_WEST_BOX = [50, -10, 70, 10]
IOD_EAST_BOX = [90, -10, 110, 0]
IOD_EVENT_C = 0.4                      # conventional |DMI| event threshold

# Class tables carry BOTH labels so a language switch can never desynchronise a
# chart legend from the value written to stats.json.
# McKee et al. (1993), the conventional SPI class boundaries.
SPI_CLASSES = [
    (2.0, {"id": "Sangat basah", "en": "Extremely wet"}, "#0b5cad"),
    (1.5, {"id": "Basah", "en": "Very wet"}, "#4a90d9"),
    (1.0, {"id": "Agak basah", "en": "Moderately wet"}, "#9ecae1"),
    (-1.0, {"id": "Normal", "en": "Near normal"}, "#d9d9d9"),
    (-1.5, {"id": "Kering sedang", "en": "Moderately dry"}, "#fdae61"),
    (-2.0, {"id": "Kering parah", "en": "Severely dry"}, "#e34a33"),
    (-99.0, {"id": "Kering ekstrem", "en": "Extremely dry"}, "#7f0000"),
]

# Kogan (1995) vegetation-health classes.
VHI_CLASSES = [
    (40.0, {"id": "Tidak kekeringan", "en": "No drought"}, "#1a9850"),
    (30.0, {"id": "Kekeringan ringan", "en": "Mild drought"}, "#fee08b"),
    (20.0, {"id": "Kekeringan sedang", "en": "Moderate drought"}, "#fdae61"),
    (10.0, {"id": "Kekeringan parah", "en": "Severe drought"}, "#e34a33"),
    (-1.0, {"id": "Kekeringan ekstrem", "en": "Extreme drought"}, "#7f0000"),
]

ENSO_CLASSES = [
    (2.0, {"id": "El Nino sangat kuat", "en": "Very strong El Nino"}),
    (1.5, {"id": "El Nino kuat", "en": "Strong El Nino"}),
    (1.0, {"id": "El Nino sedang", "en": "Moderate El Nino"}),
    (0.5, {"id": "El Nino lemah", "en": "Weak El Nino"}),
    (-0.5, {"id": "Netral", "en": "Neutral"}),
    (-1.0, {"id": "La Nina lemah", "en": "Weak La Nina"}),
    (-1.5, {"id": "La Nina sedang", "en": "Moderate La Nina"}),
    (-99.0, {"id": "La Nina kuat", "en": "Strong La Nina"}),
]

IOD_CLASSES = [
    (IOD_EVENT_C, {"id": "IOD positif", "en": "Positive IOD"}),
    (-IOD_EVENT_C, {"id": "Netral", "en": "Neutral"}),
    (-99.0, {"id": "IOD negatif", "en": "Negative IOD"}),
]

UNKNOWN = {"id": "tidak diketahui", "en": "unknown"}

TEXT = {
    "id": {
        "title": "Kekeringan — {name}",
        "sub": ("Jendela {months} bulan berakhir {end} · baseline hujan "
                "{b0}–{b1}, vegetasi {m0}–{m1}"),
        "src": ("Sumber: {src} (hujan) · MODIS MOD13A2/MOD11A2 (VCI/TCI) · "
                "NOAA OISST (Nino 3.4 & DMI/IOD). Anomali hujan = z-score, "
                "bukan SPI gamma."),
        "rain_ax": "Anomali hujan (z)",
        "rain_title": "Kekeringan meteorologis — anomali hujan terstandar per tahun",
        "health_ax": "Indeks (0–100)",
        "health_title": "Kesehatan vegetasi — di bawah 40 menandakan tekanan kekeringan",
        "vci": "VCI\n(vegetasi)", "tci": "TCI\n(suhu)", "vhi": "VHI\n(gabungan)",
        "modes_ax": "Anomali SST (°C)",
        "modes_title": ("Mode iklim — Nino 3.4 (>+0,5 °C = El Nino) & "
                        "IOD/DMI (>+0,4 °C = IOD positif)"),
        "nino_lbl": "Nino 3.4 (ENSO)", "dmi_lbl": "DMI (IOD)",
        "map_rain_title": "Curah hujan {name} — {months} bulan s/d {end}",
        "map_rain_sub": "% dari normal {b0}–{b1} ({src})",
        "map_rain_cb": "% dari normal  (coklat = lebih kering, hijau = lebih basah)",
        "map_rain_src": ("Sumber: {src}, batas provinsi FAO GAUL 2015. "
                         "Dihitung dengan earthchange -s drought."),
        "map_vhi_title": "Sebaran kekeringan vegetasi — {name}",
        "map_vhi_sub": "VHI (MODIS 1 km), {end}",
        "map_vhi_src": ("VHI = 0,5·VCI + 0,5·TCI (Kogan 1995); di bawah 40 = "
                        "tekanan kekeringan. Sumber: MODIS MOD13A2 + MOD11A2."),
        "resampled": ("Sel asli {native:.0f} km, ditampilkan pada {shown:.0f} km "
                      "(interpolasi bilinear — hanya untuk keterbacaan, tidak "
                      "menambah informasi). Hanya daratan."),
        "met_title": "Kekeringan meteorologis — {name}",
        "met_sub": "anomali hujan terstandar, {months} bulan s/d {rain_end}",
        "met_src": ("Defisit hujan terhadap jendela kalender yang sama pada tiap "
                    "tahun baseline. Kelas mengikuti batas SPI (McKee dkk. 1993). "
                    "Ini pemicu rantai kekeringan, bukan dampaknya."),
        "agri_title": "Kekeringan pertanian — {name}",
        "agri_sub": "anomali lengas tanah zona akar (7–28 cm), s/d {era5_end}",
        "agri_src": ("Lengas tanah ERA5-Land, bukan kesehatan vegetasi: tanah "
                     "adalah mekanismenya, vegetasi hanya gejala yang muncul "
                     "beberapa minggu kemudian. Keluaran model, bukan pengukuran "
                     "lapangan."),
        "hydro_title": "Kekeringan hidrologis — {name}",
        "hydro_sub": ("anomali simpanan dalam (100–289 cm) + limpasan, "
                      "3 bulan s/d {era5_end}"),
        "hydro_src": ("PENDEKATAN. Tidak ada data debit sungai, muka air waduk, "
                      "atau sumur pantau di sini — hanya proksi simpanan "
                      "ERA5-Land. Untuk pernyataan resmi soal pasokan air, angka "
                      "PJT/BBWS jauh lebih berwenang."),
        "cdi_title": "Indikator Kekeringan Gabungan — {name}",
        "cdi_sub": ("hujan s/d {rain} · lengas tanah s/d {era5} · "
                    "vegetasi s/d {veg}"),
        "cdi_src": ("Klasifikasi mengikuti logika Combined Drought Indicator (EDO): "
                    "hujan (IMERG/CHIRPS) → lengas tanah zona akar (ERA5-Land) → "
                    "vegetasi (MODIS VHI). Hidrologis dilaporkan terpisah karena "
                    "berjalan pada skala musim, bukan minggu."),
        "cdi_extent": "kekeringan gabungan: {pct:.0f}% dari AOI di atas Normal",
        "sum_title": "Kekeringan {name} — {months} bulan s/d {end}",
        "sum_rain": ("hujan {mm:.0f} mm ({pct:.0f}% dari normal {normal:.0f} mm)"
                     " · z {z:+.2f} → {cls}"),
        "sum_rank": "peringkat terkering ke-{rank} dari {n} tahun",
        "sum_vhi": "VHI {vhi:.0f} (VCI {vci:.0f} · TCI {tci:.0f}) → {cls}",
        "extent": "luas terdampak: {pct:.0f}% dari AOI di bawah VHI 40",
    },
    "en": {
        "title": "Drought — {name}",
        "sub": ("{months}-month window ending {end} · rainfall baseline "
                "{b0}–{b1}, vegetation {m0}–{m1}"),
        "src": ("Source: {src} (rainfall) · MODIS MOD13A2/MOD11A2 (VCI/TCI) · "
                "NOAA OISST (Nino 3.4 & DMI/IOD). Rainfall anomaly is a "
                "z-score, not a gamma-fitted SPI."),
        "rain_ax": "Rainfall anomaly (z)",
        "rain_title": "Meteorological drought — standardized rainfall anomaly by year",
        "health_ax": "Index (0–100)",
        "health_title": "Vegetation health — below 40 indicates drought stress",
        "vci": "VCI\n(vegetation)", "tci": "TCI\n(thermal)", "vhi": "VHI\n(combined)",
        "modes_ax": "SST anomaly (°C)",
        "modes_title": ("Climate modes — Nino 3.4 (>+0.5 °C = El Nino) & "
                        "IOD/DMI (>+0.4 °C = positive IOD)"),
        "nino_lbl": "Nino 3.4 (ENSO)", "dmi_lbl": "DMI (IOD)",
        "map_rain_title": "Rainfall {name} — {months} months to {end}",
        "map_rain_sub": "% of the {b0}–{b1} normal ({src})",
        "map_rain_cb": "% of normal  (brown = drier, green = wetter)",
        "map_rain_src": ("Source: {src}, province boundaries FAO GAUL 2015. "
                         "Computed with earthchange -s drought."),
        "map_vhi_title": "Vegetation drought extent — {name}",
        "map_vhi_sub": "VHI (MODIS 1 km), {end}",
        "map_vhi_src": ("VHI = 0.5·VCI + 0.5·TCI (Kogan 1995); below 40 = "
                        "drought stress. Source: MODIS MOD13A2 + MOD11A2."),
        "resampled": ("Native cell {native:.0f} km, displayed at {shown:.0f} km "
                      "(bilinear interpolation — for legibility only, it adds no "
                      "information). Land only."),
        "met_title": "Meteorological drought — {name}",
        "met_sub": "standardized rainfall anomaly, {months} months to {rain_end}",
        "met_src": ("Rainfall deficit against the same calendar window in each "
                    "baseline year. Classes follow the SPI boundaries (McKee et "
                    "al. 1993). This is the trigger of the drought chain, not its "
                    "impact."),
        "agri_title": "Agricultural drought — {name}",
        "agri_sub": "root-zone soil moisture anomaly (7–28 cm), to {era5_end}",
        "agri_src": ("ERA5-Land soil moisture, not vegetation health: soil is the "
                     "mechanism, vegetation only the symptom that appears weeks "
                     "later. Model output, not field measurement."),
        "hydro_title": "Hydrological drought — {name}",
        "hydro_sub": ("deep storage (100–289 cm) + runoff anomaly, "
                      "3 months to {era5_end}"),
        "hydro_src": ("APPROXIMATION. No river discharge, reservoir level or "
                      "monitoring-well data is involved here — only ERA5-Land "
                      "storage proxies. For official statements about water "
                      "supply, PJT/BBWS figures are far more authoritative."),
        "cdi_title": "Combined Drought Indicator — {name}",
        "cdi_sub": ("rainfall to {rain} · soil moisture to {era5} · "
                    "vegetation to {veg}"),
        "cdi_src": ("Classification follows the EDO Combined Drought Indicator "
                    "logic: rainfall (IMERG/CHIRPS) → root-zone soil moisture "
                    "(ERA5-Land) → vegetation (MODIS VHI). Hydrological is "
                    "reported separately because it runs on seasons, not weeks."),
        "cdi_extent": "combined drought: {pct:.0f}% of AOI beyond Normal",
        "sum_title": "Drought {name} — {months} months to {end}",
        "sum_rain": ("rainfall {mm:.0f} mm ({pct:.0f}% of normal {normal:.0f} mm)"
                     " · z {z:+.2f} → {cls}"),
        "sum_rank": "{rank}th driest of {n} years",
        "sum_vhi": "VHI {vhi:.0f} (VCI {vci:.0f} · TCI {tci:.0f}) → {cls}",
        "extent": "area affected: {pct:.0f}% of AOI below VHI 40",
    },
}


def _label(row, lang):
    return row[1].get(lang, row[1]["id"])


def _classify(value, table, lang="id"):
    """First label whose threshold the value clears (tables run high -> low).

    Returns (label, colour) for tables that carry a colour, else just the label.
    """
    has_colour = len(table[0]) == 3
    if value is None:
        return (UNKNOWN[lang], "#999999") if has_colour else UNKNOWN[lang]
    row = next((r for r in table if value >= r[0]), table[-1])
    return (_label(row, lang), row[2]) if has_colour else _label(row, lang)


def _spi_label(z, lang="id"):
    return _classify(z, SPI_CLASSES, lang)


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


def _panel_rain(ax, years, zs, cur_year, T):
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
    ax.set_ylabel(T["rain_ax"], fontsize=9)
    ax.set_title(T["rain_title"], fontsize=10, loc="left")


def _panel_health(ax, hv, T, lang):
    labels = [T["vci"], T["tci"], T["vhi"]]
    vals = [hv["vci"], hv["tci"], hv["vhi"]]
    cols = [_classify(v, VHI_CLASSES, lang)[1] if v is not None else "#cccccc"
            for v in vals]
    ax.bar(labels, [v or 0 for v in vals], color=cols, width=.55)
    for i, v in enumerate(vals):
        if v is not None:
            ax.text(i, v + 2, f"{v:.0f}", ha="center", fontsize=10, fontweight="bold")
    for thr in (10, 20, 30, 40):
        ax.axhline(thr, color="#999", lw=.6, ls=":")
    ax.set_ylim(0, 105)
    ax.set_ylabel(T["health_ax"], fontsize=9)
    ax.set_title(T["health_title"], fontsize=10, loc="left")


def _panel_enso(ax, labels, nino, dmi, T):
    """ENSO and IOD on one axis: for Indonesia the two compound, and reading
    either one alone is how forecasts get over-claimed."""
    import numpy as np
    x = np.arange(len(labels))
    nv = [0 if v is None else v for v in nino]
    dv = [0 if v is None else v for v in dmi]
    ax.plot(x, nv, color="#1a1a1a", lw=1.5, marker="o", ms=3, label=T["nino_lbl"])
    ax.fill_between(x, 0, nv, where=[v > 0 for v in nv],
                    color="#e34a33", alpha=.35, interpolate=True)
    ax.fill_between(x, 0, nv, where=[v < 0 for v in nv],
                    color="#4a90d9", alpha=.35, interpolate=True)
    ax.plot(x, dv, color="#6a3d9a", lw=1.5, ls="--", marker="s", ms=3,
            label=T["dmi_lbl"])
    for thr, col in ((0.5, "#666"), (-0.5, "#666"),
                     (IOD_EVENT_C, "#6a3d9a"), (-IOD_EVENT_C, "#6a3d9a")):
        ax.axhline(thr, color=col, lw=.7, ls=":", alpha=.8)
    ax.axhline(0, color="#333", lw=.8)
    step = max(1, len(labels) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(labels[::step], rotation=45, fontsize=8)
    ax.set_ylabel(T["modes_ax"], fontsize=9)
    ax.legend(fontsize=8, frameon=False, ncol=2, loc="upper left")
    ax.set_title(T["modes_title"], fontsize=10, loc="left")


def _render_panel(run_dir, name, years, zs, hv, labels, nino, dmi, meta,
                  lang="id"):
    plt = _plt()
    fig, axes = plt.subplots(3, 1, figsize=(11, 12), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    for ax in axes:
        ax.set_facecolor("#faf8f4")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    T = TEXT.get(lang, TEXT["id"])
    _panel_rain(axes[0], years, zs, meta["current_year"], T)
    _panel_health(axes[1], hv, T, lang)
    _panel_enso(axes[2], labels, nino, dmi, T)
    fig.suptitle(T["title"].format(name=name), fontsize=15, fontweight="bold",
                 x=.02, ha="left", y=.985)
    fig.text(.02, .955,
             T["sub"].format(months=meta["months"], end=meta["rain_end"],
                             b0=meta["base"][0], b1=meta["base"][1],
                             m0=MODIS_BASE[0], m1=MODIS_BASE[1]),
             fontsize=9, color="#555")
    fig.text(.02, .012, T["src"].format(src=meta["source"]),
             fontsize=8, color="#777")
    fig.tight_layout(rect=[0, .025, 1, .945])
    out = os.path.join(run_dir, f"{name}_drought_{lang}.png"
                       if lang != "id" else f"{name}_kekeringan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _rain_pct_image(aoi, end, months, src, downscale_m=None):
    """Per-pixel rainfall as % of the baseline normal for the same window.

    The area-mean z-score answers "how dry overall"; this answers "dry WHERE",
    which is the part that survives being screenshotted into a discussion.

    Two display decisions, both mattering most for the satellite products:

    LAND ONLY. IMERG and GSMaP cover the ocean; CHIRPS does not. On a map of a
    long thin island the sea then fills most of the frame, and because the ocean
    ratio is computed over a different rainfall regime it can render as a solid
    dark block that swamps the land signal. Masked with SRTM, which is void over
    open sea (the same trick `flood` uses).

    RESAMPLED. IMERG cells are ~11 km; over Java that is a coarse mosaic. The
    ratio field is far smoother than raw rainfall, so bilinear resampling to a
    finer grid is the conventional delta-method display. It adds NO information
    -- it only stops the blocks hiding the pattern -- and the caption says so.
    """
    start = _shift_months(end, months)
    import ee
    hist = []
    for y in range(src["base"][0], src["base"][1] + 1):
        a, b = _same_window(start, end, y)
        hist.append(_rain_total(aoi, a, b, src))
    normal = ee.ImageCollection(hist).mean()
    pct = _rain_total(aoi, start, end, src).divide(normal).multiply(100)
    if downscale_m:
        pct = pct.resample("bilinear").reproject(crs="EPSG:4326",
                                                 scale=downscale_m)
    # Land mask from GAUL country polygons, NOT from SRTM. SRTM's mask is 30 m;
    # reprojected to a kilometre grid it neither survives cleanly nor lines up,
    # and it punches holes wherever a tile is absent. Vector land gives a crisp
    # coastline at any display scale.
    return pct.updateMask(_land_mask(aoi)).clip(aoi).rename("pct")


def _land_mask(aoi):
    """Land from GAUL country polygons.

    NOT from SRTM: that mask is 30 m, does not survive reprojection to a
    kilometre grid, and punches holes wherever a tile is absent. Vector land
    gives a crisp coastline at any display scale.
    """
    import ee
    return ee.Image.constant(1).clip(
        ee.FeatureCollection("FAO/GAUL/2015/level0").filterBounds(aoi)).mask()


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


def _render_rain_map(run_dir, name, tif, box, meta, lang="id"):
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
    # A fixed 50-150 scale saturates when a whole region is far from normal: at
    # 47% of normal every land pixel renders the same dark brown and the internal
    # pattern disappears. Stretch to the data (5th-95th percentile) while keeping
    # 100% as the neutral midpoint, so colour still means the same thing.
    lo = float(np.nanpercentile(arr, 5))
    hi = float(np.nanpercentile(arr, 95))
    vmin = max(0.0, min(lo, 90.0))
    vmax = max(hi, 110.0)
    ticks = [round(v) for v in np.linspace(vmin, vmax, 5)]
    im = ax.imshow(arr, cmap="BrBG",
                   norm=TwoSlopeNorm(vmin=vmin, vcenter=100.0, vmax=vmax),
                   extent=[b.left, b.right, b.bottom, b.top])
    _draw_admin(ax, box)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    T = TEXT.get(lang, TEXT["id"])
    ax.set_title(T["map_rain_title"].format(name=name, months=meta["months"],
                                            end=meta["rain_end"]) + "\n"
                 + T["map_rain_sub"].format(b0=meta["base"][0], b1=meta["base"][1],
                                            src=meta["source"]),
                 fontsize=13, fontweight="bold", loc="left")
    cb = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=.046,
                      pad=.04, ticks=ticks)
    cb.set_label(T["map_rain_cb"], fontsize=9.5)
    cb.ax.tick_params(labelsize=8.5)
    note = T["map_rain_src"].format(src=meta["source"])
    if meta.get("shown_km") and meta["shown_km"] < meta.get("native_km", 0):
        note += " " + T["resampled"].format(native=meta["native_km"],
                                            shown=meta["shown_km"])
    fig.text(.01, .015, note, fontsize=8, color="#777", wrap=True)
    fig.tight_layout(rect=[0, .03, 1, 1])
    out = os.path.join(run_dir, f"{name}_rainfall_map_{lang}.png"
                       if lang != "id" else f"{name}_peta_hujan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _rain_map(aoi, run_dir, name, end, months, src, lang="id"):
    """Download the % of normal field and render it. Best effort: the charts are
    the primary output, so a map failure must not sink the run."""
    from .gee_utils import download_geotiff
    tif = os.path.join(run_dir, f"{name}_rainfall_pct.tif"
                       if lang != "id" else f"{name}_hujan_pct.tif")
    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    box = [min(xs), min(ys), max(xs), max(ys)]
    # Rainfall pixels are 5-11 km depending on source. Below roughly 15 of them
    # across, the map is a blocky rectangle with no internal landmarks -- the
    # GeoTIFF is still valid data, but the PNG misleads more than it informs.
    # Resample for display only when the native cell is coarse (IMERG/GSMaP/
     # ERA5 at 11 km); CHIRPS at 5.5 km already reads acceptably.
    # Half the native cell: enough to soften the mosaic without blurring the
    # pattern away, which a quarter-cell bilinear does.
    ds = max(4000, src["scale"] // 2) if src["scale"] >= 10000 else None
    span_km = (box[2] - box[0]) * 111.0
    if span_km < 15 * src["scale"] / 1000:
        print(f"  (AOI ~{span_km:.0f} km: terlalu kecil untuk peta "
              f"{src['scale'] / 1000:.0f} km — peta tetap dibuat tetapi sangat "
              f"kasar; pakai --radius >50 km atau --admin)")
    try:
        got = download_geotiff(
            _rain_pct_image(aoi, end, months, src, ds).toFloat(),
            coords, tif, scale=ds or src["scale"])
        if not got:
            return None, None
        png = _render_rain_map(run_dir, name, got, box,
                               {"months": months, "rain_end": end.isoformat(),
                                "base": src["base"],
                                "source": src["label"].get(lang, src["label"]["id"]),
                                "native_km": src["scale"] / 1000,
                                "shown_km": (ds or src["scale"]) / 1000},
                               lang)
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


def _vhi_class_areas(vhi, aoi, lang="id"):
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
    labels = [_label(r, lang) for r in reversed(VHI_CLASSES)]   # index 0..4
    out = {lab: 0.0 for lab in labels}
    for g in grouped.get("groups", []):
        i = int(g["cls"])
        if 0 <= i < len(labels):
            out[labels[i]] = round(g["sum"], 1)
    total = sum(out.values()) or 1.0
    return out, {k: round(v / total * 100, 1) for k, v in out.items()}


def _render_vhi_map(run_dir, name, tif, box, meta, pct, lang="id"):
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

    T = TEXT.get(lang, TEXT["id"])
    labels = [_label(r, lang) for r in VHI_CLASSES]     # extreme -> none
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
    ax.set_title(T["map_vhi_title"].format(name=name) + "\n"
                 + T["map_vhi_sub"].format(end=meta["vegetation_end"]),
                 fontsize=13, fontweight="bold", loc="left")
    # One decimal: a class holding tens of thousands of hectares still rounds to
    # "0%" of a large AOI, which reads as "nothing here" when it is not.
    handles = [Patch(facecolor=c, edgecolor="none",
                     label=f"{lab} — {pct.get(lab, 0):.1f}%")
               for lab, c in zip(labels, colours)]
    ax.legend(handles=handles, fontsize=9, frameon=False, ncol=3,
              loc="upper center", bbox_to_anchor=(.5, -.02))
    fig.text(.01, .015, T["map_vhi_src"], fontsize=8, color="#777")
    fig.tight_layout(rect=[0, .05, 1, 1])
    out = os.path.join(run_dir, f"{name}_drought_map_{lang}.png"
                       if lang != "id" else f"{name}_peta_kekeringan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _drought_extent(vhi, aoi, run_dir, name, veg_end, lang="id"):
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
        ha, pct = _vhi_class_areas(vhi, aoi, lang)
        tif = download_geotiff(vhi.clip(aoi).toFloat(), coords, path,
                               scale=MODIS_SCALE)
        png = (_render_vhi_map(run_dir, name, tif, box,
                               {"vegetation_end": veg_end.isoformat()}, pct, lang)
               if tif else None)
        return tif, png, ha, pct
    except Exception as exc:
        print(f"  (peta VHI dilewati: {str(exc)[:70]})")
        return None, None, {}, {}


def _print_extent(cls_ha, cls_pct, lang="id"):
    """Where the drought is, as a breakdown -- the average alone hides it."""
    if not cls_pct:
        return
    none_lab = _label(VHI_CLASSES[0], lang)
    in_drought = sum(v for k, v in cls_pct.items() if k != none_lab)
    print("  " + TEXT.get(lang, TEXT["id"])["extent"].format(pct=in_drought))
    for row in VHI_CLASSES:
        lab = _label(row, lang)
        if cls_ha.get(lab):
            print(f"    {lab:22s} {cls_ha[lab]:>12,.0f} ha  ({cls_pct[lab]:5.1f}%)")


def _print_summary(name, months, rain_end, rain, z, rank, n_years, hv,
                   cls_ha, cls_pct, enso_now, iod_now, sst_end, lang):
    """Console summary in the requested language."""
    T = TEXT.get(lang, TEXT["id"])
    print("\n" + T["sum_title"].format(name=name, months=months,
                                       end=rain_end))
    print("  " + T["sum_rain"].format(
        mm=rain["current_mm"], pct=rain["pct_of_normal"],
        normal=rain["normal_mm"], z=z, cls=_spi_label(z, lang)[0]))
    if rank:
        print("  " + T["sum_rank"].format(rank=rank, n=n_years))
    print("  " + T["sum_vhi"].format(
        vhi=hv["vhi"], vci=hv["vci"], tci=hv["tci"],
        cls=_classify(hv["vhi"], VHI_CLASSES, lang)[0]))
    _print_extent(cls_ha, cls_pct, lang)
    if enso_now is not None:
        print(f"  Nino 3.4 {enso_now:+.2f} °C ({sst_end}) → "
              f"{_classify(enso_now, ENSO_CLASSES, lang)}")
    if iod_now is not None:
        print(f"  IOD/DMI  {iod_now:+.2f} °C ({sst_end}) → "
              f"{_classify(iod_now, IOD_CLASSES, lang)}")


def _print_cdi(cdi_out, lang):
    """Console breakdown of the combined indicator."""
    if not cdi_out:
        return
    T = TEXT.get(lang, TEXT["id"])
    pct, ha = cdi_out["area_pct_by_class"], cdi_out["area_ha_by_class"]
    normal = _label(CDI_CLASSES[0], lang)
    beyond = sum(v for k, v in pct.items() if k != normal)
    print("  " + T["cdi_extent"].format(pct=beyond))
    for row in CDI_CLASSES[1:] + [CDI_CLASSES[0]]:
        lab = _label(row, lang)
        if ha.get(lab):
            print(f"    {lab:44s} {ha[lab]:>12,.0f} ha  ({pct[lab]:5.1f}%)")
    idx = cdi_out["indices"]
    print(f"    z: met {idx['meteorological_z']:+.2f} · "
          f"agri {idx['agricultural_z']:+.2f} · "
          f"hydro {idx['hydrological_z']:+.2f}")


def _record_years(start_year, src, last_year):
    """Years to rank the current season against.

    Defaults to the product's OWN archive rather than a number inherited from
    another scenario: "driest of 27 years" and "driest of 36" are different
    claims, and that difference must not come from an unrelated flag's default.
    """
    first = max(start_year or src["archive"], src["archive"])
    return list(range(first, last_year + 1))


NOTE = {
    "en": ("rainfall_z is a z-score of accumulated rainfall against the same "
           "calendar window in each baseline year, NOT a gamma-fitted SPI; the "
           "two agree for >=3-month windows in the humid tropics but diverge in "
           "the dry season. Meteorological drought leads agricultural drought, "
           "so a large deficit with healthy VHI means impact has not landed yet."),
    "id": ("rainfall_z adalah z-score curah hujan terakumulasi terhadap jendela "
           "kalender yang sama pada tiap tahun baseline, BUKAN SPI gamma; "
           "keduanya sepakat untuk jendela >=3 bulan di tropis basah tetapi "
           "berbeda pada musim kemarau. Kekeringan meteorologis mendahului "
           "kekeringan pertanian, jadi defisit besar dengan VHI sehat berarti "
           "dampaknya belum tiba."),
}

STALE_WARN = {
    "id": ("  ⚠ jendela hujan tertinggal {n} hari dari hari ini. Untuk musim "
           "yang sedang berjalan coba --rain-source era5 (lag ~8 hari) atau "
           "imerg (~1 hari)."),
    "en": ("  ⚠ the rainfall window is {n} days behind today. For a season "
           "still in progress try --rain-source era5 (~8 day lag) or imerg "
           "(~1 day)."),
}


def _warn_if_stale(rain_source, rain_end, lang="id"):
    """A stale window reports "Normal" for a season that has already turned.

    Over Central Java in August 2026, CHIRPS (to 30 Jun) said 101% of normal
    while ERA5, IMERG and GSMaP -- all seeing into late July -- independently
    said 67-71%. The default must not hide that silently.
    """
    stale = (dt.date.today() - rain_end).days
    if rain_source == "chirps" and stale > 21:
        print(STALE_WARN.get(lang, STALE_WARN["id"]).format(n=stale))


# ---------------------------------------------------------------------------
# Combined Drought Indicator
#
# Classifies rather than averages. Averaging the three types destroys the very
# thing worth reporting: a region can be meteorologically dry, agriculturally
# marginal and hydrologically fine at the same time, and the mean of those is a
# middling number that says nothing. The EDO scheme instead reads the chain --
# rain fails, then soil dries, then plants show it -- and reports how far it got.
#
# Hydrological is computed and reported but deliberately NOT folded into the
# class: it runs on seasons rather than weeks, so mixing it in would blur two
# different questions.
# ---------------------------------------------------------------------------
ERA5_IC = "ECMWF/ERA5_LAND/DAILY_AGGR"
ERA5_SCALE = 11132
SOIL_ROOT = "volumetric_soil_water_layer_2"        # 7-28 cm, the crop root zone
SOIL_DEEP = "volumetric_soil_water_layer_4"        # 100-289 cm, storage proxy
RUNOFF = "runoff_sum"

CDI_CLASSES = [
    (0, {"id": "Normal", "en": "Normal"}, "#c8dcc0"),
    (1, {"id": "Waspada — defisit hujan saja",
         "en": "Watch — rainfall deficit only"}, "#fee08b"),
    (2, {"id": "Peringatan — hujan + tanah",
         "en": "Warning — rainfall + soil"}, "#fdae61"),
    (3, {"id": "Awas — hujan + tanah + vegetasi",
         "en": "Alert — rainfall + soil + vegetation"}, "#7f0000"),
    (4, {"id": "Defisit tanah saja, tanpa pemicu hujan",
         "en": "Soil deficit only, no rainfall trigger"}, "#9ecae1"),
]
CDI_NODATA = 255


def _pixel_z(ic_id, band, aoi, end, months, reducer="mean", factor=1.0,
             base=CLIM_BASE):
    """Per-pixel z of a window statistic against the same window each baseline
    year. `sum` for a flux (rainfall, runoff), `mean` for a state (soil water)."""
    import ee
    start = _shift_months(end, months)

    def stat(a, b):
        ic = ee.ImageCollection(ic_id).select(band).filterDate(
            a.isoformat(), b.isoformat())
        return (ic.sum() if reducer == "sum" else ic.mean()).multiply(factor)

    hist = ee.ImageCollection([stat(*_same_window(start, end, y))
                               for y in range(base[0], base[1] + 1)])
    return (stat(start, end).subtract(hist.mean())
            .divide(hist.reduce(ee.Reducer.stdDev())).rename("z"))


def _cdi_floor(src):
    """Finest pixel the CDI can honestly be drawn at.

    The indicator is only as sharp as its coarsest input, and that input is soil
    moisture. Measured native scales: CHIRPS 5,566 m, IMERG/GSMaP 11,132 m,
    ERA5-Land 11,132 m, SMAP 10,593 m, GLDAS 27,830 m, MODIS vegetation 927 m.

    So the floor is set by ERA5-Land, not by the rainfall product. Drawing below
    it does not add information -- and for a CLASSIFIED raster it is worse than
    merely cosmetic, because interpolated class boundaries are boundaries the
    classification never produced.

    Genuinely finer would need a finer soil-moisture field. None exists globally;
    it would have to be downscaled with terrain and land-cover covariates, which
    is a modelling exercise, not a resampling option.
    """
    return max(src["scale"], ERA5_SCALE)


def _resolve_cdi_scale(requested, src, lang):
    floor = _cdi_floor(src)
    if not requested:
        return floor
    if requested < floor:
        msg = {
            "id": (f"  ⚠ --cdi-scale {requested} m di bawah batas data "
                   f"({floor} m, ditentukan lengas tanah ERA5-Land). Peta akan "
                   f"terlihat lebih halus tetapi TIDAK menambah informasi; batas "
                   f"kelas hasil interpolasi tidak pernah dihitung."),
            "en": (f"  ⚠ --cdi-scale {requested} m is below the data floor "
                   f"({floor} m, set by ERA5-Land soil moisture). The map will "
                   f"look smoother but carries NO extra information; interpolated "
                   f"class boundaries were never computed."),
        }
        print(msg.get(lang, msg["id"]))
    return requested


def _cdi_layers(aoi, rain_end, era5_end, months, src):
    """The three per-pixel fields the indicator is built from, plus hydrological."""
    met = _pixel_z(src["ic"], src["band"], aoi, rain_end, months, "sum",
                   src["factor"], src["base"])
    agri = _pixel_z(ERA5_IC, SOIL_ROOT, aoi, era5_end, 1)
    deep = _pixel_z(ERA5_IC, SOIL_DEEP, aoi, era5_end, 3)
    runoff = _pixel_z(ERA5_IC, RUNOFF, aoi, era5_end, 3, "sum", 1000.0)
    return met, agri, deep.add(runoff).divide(2).rename("z")


def _cdi_classify(met, agri, vhi):
    """0 normal · 1 watch · 2 warning · 3 alert · 4 soil-only."""
    import ee
    dry_rain, dry_soil, stressed = met.lt(-1), agri.lt(-1), vhi.lt(40)
    return (ee.Image(0)
            .where(dry_rain, 1)
            .where(dry_rain.And(dry_soil), 2)
            .where(dry_rain.And(dry_soil).And(stressed), 3)
            .where(dry_rain.Not().And(dry_soil.Or(stressed)), 4)
            .rename("cdi").toByte())


def _cdi_areas(cdi, aoi, lang):
    """Hectares per class, in one grouped reduction.

    Measured at MODIS_SCALE (1 km), not at the 11 km grid the classes are
    computed on. At 11 km a coastal cell that is half sea is counted whole, and
    over a long thin island like Java that inflated the total by more than 20%
    (16.0 Mha against a true land area near 13.1 Mha). The classification stays
    at its native resolution; only the area integration is finer.
    """
    import ee
    grouped = (ee.Image.pixelArea().divide(1e4).addBands(cdi)
               .reduceRegion(reducer=ee.Reducer.sum().group(groupField=1,
                                                            groupName="cdi"),
                             geometry=aoi, scale=MODIS_SCALE,
                             maxPixels=int(1e10), bestEffort=True).getInfo())
    ha = {_label(r, lang): 0.0 for r in CDI_CLASSES}
    for g in grouped.get("groups", []):
        i = int(g["cdi"])
        if 0 <= i < len(CDI_CLASSES):
            ha[_label(CDI_CLASSES[i], lang)] = round(g["sum"], 1)
    total = sum(ha.values()) or 1.0
    return ha, {k: round(v / total * 100, 1) for k, v in ha.items()}


def _z_class_image(z):
    """z -> 0..6 using the McKee SPI boundaries, driest first.

    0 extremely dry · 1 severely dry · 2 moderately dry · 3 near normal
    4 moderately wet · 5 very wet · 6 extremely wet
    """
    return (z.gte(-2).add(z.gte(-1.5)).add(z.gte(-1))
            .add(z.gte(1)).add(z.gte(1.5)).add(z.gte(2))
            .rename("cls").toByte())


def _z_class_areas(cls, aoi, lang):
    """Hectares per SPI class. Integrated at 1 km for the same reason as the
    CDI: an 11 km coastal cell that is half sea would otherwise count whole."""
    import ee
    grouped = (ee.Image.pixelArea().divide(1e4).addBands(cls)
               .reduceRegion(reducer=ee.Reducer.sum().group(groupField=1,
                                                            groupName="cls"),
                             geometry=aoi, scale=MODIS_SCALE,
                             maxPixels=int(1e10), bestEffort=True).getInfo())
    labels = [_label(r, lang) for r in reversed(SPI_CLASSES)]   # index 0..6
    ha = {lab: 0.0 for lab in labels}
    for g in grouped.get("groups", []):
        i = int(g["cls"])
        if 0 <= i < len(labels):
            ha[labels[i]] = round(g["sum"], 1)
    total = sum(ha.values()) or 1.0
    return ha, {k: round(v / total * 100, 1) for k, v in ha.items()}


def _render_z_map(run_dir, name, tif, box, meta, pct, lang, kind):
    """One drought type as a classified map.

    All three types share the McKee SPI class boundaries and one colour ramp, so
    the maps can be read side by side: the same colour means the same standard
    deviation everywhere. Only the underlying variable differs.
    """
    import numpy as np
    import rasterio
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    plt = _plt()

    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float32")
        b = src.bounds
    arr[arr == CDI_NODATA] = np.nan
    if not np.isfinite(arr).any():
        return None

    T = TEXT.get(lang, TEXT["id"])
    rows = list(reversed(SPI_CLASSES))                 # driest -> wettest
    cmap = ListedColormap([r[2] for r in rows])
    span_x, span_y = box[2] - box[0], box[3] - box[1]
    aspect = span_x / span_y if span_y else 1.0
    height = min(11.0, max(4.8, 11.0 / max(aspect, .35) + 2.4))
    fig, ax = plt.subplots(figsize=(11, height), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_facecolor("#faf8f4")
    ax.imshow(np.ma.masked_invalid(arr), cmap=cmap,
              norm=BoundaryNorm(np.arange(-.5, 7.5), 7),
              extent=[b.left, b.right, b.bottom, b.top], interpolation="nearest")
    _draw_admin(ax, box)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(T[f"{kind}_title"].format(name=name) + "\n"
                 + T[f"{kind}_sub"].format(**meta),
                 fontsize=13, fontweight="bold", loc="left")
    # legend driest-first, and only classes that actually occur
    handles = [Patch(facecolor=r[2], label=f"{_label(r, lang)} — "
                                          f"{pct.get(_label(r, lang), 0):.1f}%")
               for r in rows if pct.get(_label(r, lang), 0) > 0]
    ax.legend(handles=handles, fontsize=8.5, frameon=False, ncol=4,
              loc="upper center", bbox_to_anchor=(.5, -.02))
    fig.text(.01, .015, T[f"{kind}_src"], fontsize=8, color="#777", wrap=True)
    fig.tight_layout(rect=[0, .10, 1, 1])
    out = os.path.join(run_dir, f"{name}_{kind}_{lang}.png"
                       if lang != "id" else f"{name}_{kind}.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _layer_map(z_img, aoi, run_dir, name, meta, lang, kind, px, coords, box):
    """Classify one drought type, export it, and draw it. Best effort."""
    from .gee_utils import download_geotiff
    try:
        cls = _z_class_image(z_img).updateMask(_land_mask(aoi))
        ha, pct = _z_class_areas(cls, aoi, lang)
        tif = os.path.join(run_dir, f"{name}_{kind}.tif")
        got = download_geotiff(cls.clip(aoi).reproject(crs="EPSG:4326", scale=px)
                               .toFloat(), coords, tif, scale=px)
        png = None
        if got:
            _style_class_tif(got, lang, SPI_CLASSES, reverse=True)
            png = _render_z_map(run_dir, name, got, box, meta, pct, lang, kind)
        return {"area_ha_by_class": ha, "area_pct_by_class": pct,
                "map": os.path.basename(png) if png else None,
                "geotiff": os.path.basename(got) if got else None}
    except Exception as exc:
        print(f"  ({kind} map skipped: {str(exc)[:60]})")
        return None


def _render_cdi_map(run_dir, name, tif, box, meta, pct, lang):
    """Classified CDI map. Only the class raster is drawn, at native resolution:
    a categorical field must never be interpolated."""
    import numpy as np
    import rasterio
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    plt = _plt()

    with rasterio.open(tif) as src:
        arr = src.read(1).astype("float32")
        b = src.bounds
    arr[arr == CDI_NODATA] = np.nan
    if not np.isfinite(arr).any():
        return None

    T = TEXT.get(lang, TEXT["id"])
    cmap = ListedColormap([r[2] for r in CDI_CLASSES])
    span_x, span_y = box[2] - box[0], box[3] - box[1]
    aspect = span_x / span_y if span_y else 1.0
    height = min(11.0, max(4.8, 11.0 / max(aspect, .35) + 2.4))
    fig, ax = plt.subplots(figsize=(11, height), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_facecolor("#faf8f4")
    ax.imshow(np.ma.masked_invalid(arr), cmap=cmap,
              norm=BoundaryNorm([-.5, .5, 1.5, 2.5, 3.5, 4.5], 5),
              extent=[b.left, b.right, b.bottom, b.top], interpolation="nearest")
    _draw_admin(ax, box)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(T["cdi_title"].format(name=name) + "\n"
                 + T["cdi_sub"].format(rain=meta["rain_end"], era5=meta["era5_end"],
                                       veg=meta["veg_end"]),
                 fontsize=13, fontweight="bold", loc="left")
    order = [1, 2, 3, 4, 0]                       # severity first, Normal last
    ax.legend(handles=[Patch(facecolor=CDI_CLASSES[i][2],
                             label=f"{_label(CDI_CLASSES[i], lang)} — "
                                   f"{pct.get(_label(CDI_CLASSES[i], lang), 0):.1f}%")
                       for i in order],
              fontsize=8.5, frameon=False, ncol=2, loc="upper center",
              bbox_to_anchor=(.5, -.02))
    fig.text(.01, .015, T["cdi_src"], fontsize=8, color="#777", wrap=True)
    fig.tight_layout(rect=[0, .10, 1, 1])
    out = os.path.join(run_dir, f"{name}_cdi_{lang}.png"
                       if lang != "id" else f"{name}_cdi.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _style_class_tif(path, lang, table=None, reverse=False):
    """Re-write the downloaded class raster as styled uint8: colour table, class
    names, and a warning that it must not be interpolated."""
    import numpy as np
    import rasterio
    from rasterio.enums import ColorInterp

    with rasterio.open(path) as src:
        arr = src.read(1)
        prof = src.profile
    bad = ~np.isfinite(arr)
    out = np.where(bad, CDI_NODATA, np.rint(arr)).astype("uint8")
    prof.update(dtype="uint8", nodata=CDI_NODATA, compress="deflate",
                tiled=True, blockxsize=256, blockysize=256)
    rows = list(reversed(table)) if reverse else (table or CDI_CLASSES)
    codes = (list(range(len(rows))) if table is not None
             else [r[0] for r in rows])
    tags = {f"CLASS_{c}": _label(r, lang) for c, r in zip(codes, rows)}
    tags["NODATA"] = str(CDI_NODATA)
    tags["WARNING"] = ("Categorical raster - resample with NEAREST NEIGHBOUR "
                       "only. Interpolating class codes invents classes that "
                       "were never computed.")
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(out, 1)
        dst.write_colormap(1, {c: tuple(int(r[2][i:i + 2], 16)
                                        for i in (1, 3, 5))
                               for c, r in zip(codes, rows)}
                           | {CDI_NODATA: (0, 0, 0)})
        dst.set_band_description(1, "drought class")
        dst.update_tags(**tags)
        dst.colorinterp = [ColorInterp.palette]
    return path


def _run_cdi(aoi, run_dir, name, rain_end, era5_end, veg_end, months, src,
             vhi_img, lang, scale=None):
    """Compute, map and export the Combined Drought Indicator. Best effort."""
    from .gee_utils import download_geotiff
    try:
        px = _resolve_cdi_scale(scale, src, lang)
        met, agri, hydro = _cdi_layers(aoi, rain_end, era5_end, months, src)
        cdi = _cdi_classify(met, agri, vhi_img)
        land = _land_mask(aoi)
        ha, pct = _cdi_areas(cdi.updateMask(land), aoi, lang)

        coords = aoi.bounds().getInfo()["coordinates"]
        xs = [p[0] for p in coords[0]]
        ys = [p[1] for p in coords[0]]
        box = [min(xs), min(ys), max(xs), max(ys)]
        tif = os.path.join(run_dir, f"{name}_cdi.tif")
        # Nearest-neighbour reprojection only: a class raster must never be
        # interpolated, whatever pixel size is asked for.
        out = cdi.updateMask(land).clip(aoi)
        if px != _cdi_floor(src):
            out = out.reproject(crs="EPSG:4326", scale=px)
        got = download_geotiff(out.toFloat(), coords, tif, scale=px)
        png = None
        if got:
            _style_class_tif(got, lang)
            png = _render_cdi_map(run_dir, name, got, box,
                                  {"rain_end": rain_end.isoformat(),
                                   "era5_end": era5_end.isoformat(),
                                   "veg_end": veg_end.isoformat()}, pct, lang)
        idx = {
            "meteorological_z": _round(_mean_over(met, aoi, src["scale"], "z")),
            "agricultural_z": _round(_mean_over(agri, aoi, ERA5_SCALE, "z")),
            "hydrological_z": _round(_mean_over(hydro, aoi, ERA5_SCALE, "z")),
        }
        lmeta = {"months": months, "rain_end": rain_end.isoformat(),
                 "era5_end": era5_end.isoformat()}
        layers = {
            kind: _layer_map(img, aoi, run_dir, name, lmeta, lang, kind,
                             px, coords, box)
            for kind, img in (("met", met), ("agri", agri), ("hydro", hydro))
        }
        return {"layers": layers,
                "area_ha_by_class": ha, "area_pct_by_class": pct,
                "indices": idx, "scale_m": px, "data_floor_m": _cdi_floor(src),
                "map": os.path.basename(png) if png else None,
                "geotiff": os.path.basename(got) if got else None}
    except Exception as exc:
        print(f"  (CDI dilewati / skipped: {str(exc)[:70]})")
        return None


def _round(num):
    v = num.getInfo()
    return round(v, 2) if v is not None else None


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
        vhi_window=48, rain_source=DEFAULT_RAIN_SOURCE, lang="id",
        cdi=False, cdi_scale=None):
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

    prim = "id" if lang in ("id", "both") else lang
    src_label = src["label"].get(prim, src["label"]["id"])
    src_lag = src["lag"].get(prim, src["lag"]["id"])
    print(f"  {'rainfall to' if prim == 'en' else 'hujan s/d'} {rain_end} "
          f"({rain_source}, lag {src_lag}) · "
          f"{'vegetation to' if prim == 'en' else 'vegetasi s/d'} "
          f"{ndvi_end} (MODIS)")
    _warn_if_stale(rain_source, rain_end)
    print(f"  {'window' if prim == 'en' else 'jendela'} {months} "
          f"{'months' if prim == 'en' else 'bulan'} · "
          f"{'rainfall baseline' if prim == 'en' else 'baseline hujan'} "
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

    panels = {}
    for lg in (["id", "en"] if lang == "both" else [lang]):
        panels[lg] = _render_panel(
            run_dir, name, years, zs, hv, labels, nino, dmi,
            {"months": months, "rain_end": rain_end.isoformat(),
             "current_year": rain_end.year, "base": src["base"],
             "source": src["label"].get(lg, src["label"]["id"])}, lg)
    png = panels[list(panels)[0]]
    tif, vhi_png, cls_ha, cls_pct = _drought_extent(vhi_img, aoi, run_dir, name,
                                                    ndvi_end, prim)
    map_png, map_tif = _rain_map(aoi, run_dir, name, rain_end, months, src, prim)

    cdi_out = None
    if cdi:
        era5_end = _latest(ERA5_IC, SOIL_ROOT)
        print(f"  CDI: ERA5-Land {'to' if prim == 'en' else 's/d'} {era5_end}")
        cdi_out = _run_cdi(aoi, run_dir, name, rain_end, era5_end, ndvi_end,
                           months, src, vhi_img, prim, cdi_scale)
    if lang == "both":
        _drought_extent(vhi_img, aoi, run_dir, name, ndvi_end, "en")
        _rain_map(aoi, run_dir, name, rain_end, months, src, "en")

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
                   "rain_source": rain_source, "lang": lang,
                   "rain_baseline": list(src["base"])},
        "sources": {
            "rainfall": (f"{src_label} ({src['ic']}), baseline "
                         f"{src['base'][0]}-{src['base'][1]}, lag {src_lag}"),
            "vegetation": f"MODIS {NDVI_IC} + {LST_IC}, baseline {MODIS_BASE[0]}-{MODIS_BASE[1]}",
            "enso": f"NOAA OISST ({SST_IC}), Nino 3.4 region {NINO34_BOX}",
            "iod": (f"NOAA OISST ({SST_IC}), DMI = west {IOD_WEST_BOX} minus "
                    f"east {IOD_EAST_BOX} (Saji et al. 1999)")},
        "rainfall": {**rain, "class": _spi_label(z, prim)[0]},
        "rainfall_z_by_year": dict(zip([str(y) for y in years], zs)),
        "rank_driest_of_record": rank, "years_in_record": len(ranked),
        "vegetation": {**hv, "class": _classify(hv["vhi"], VHI_CLASSES, prim)[0],
                       "area_ha_by_class": cls_ha, "area_pct_by_class": cls_pct,
                       "area_pct_in_drought": round(
                           sum(v for k, v in cls_pct.items()
                               if k != "Tidak kekeringan"), 1)},
        "enso": {"nino34_anomaly_c": enso_now,
                 "class": _classify(enso_now, ENSO_CLASSES, prim),
                 "monthly": dict(zip(labels, nino))},
        "iod": {"dmi_c": iod_now, "class": _classify(iod_now, IOD_CLASSES, prim),
                "event_threshold_c": IOD_EVENT_C,
                "monthly": dict(zip(labels, dmi))},
        "cdi": cdi_out,
        "outputs": {"panel": os.path.basename(png),
                    "cdi_map": cdi_out["map"] if cdi_out else None,
                    "cdi_geotiff": cdi_out["geotiff"] if cdi_out else None,
                    "panels_by_lang": {k: os.path.basename(v)
                                       for k, v in panels.items()},
                    "drought_map": os.path.basename(vhi_png) if vhi_png else None,
                    "rainfall_map": os.path.basename(map_png) if map_png else None,
                    "rainfall_geotiff": os.path.basename(map_tif) if map_tif else None,
                    "vhi_geotiff": os.path.basename(tif) if tif else None},
        "note": NOTE.get(prim, NOTE["id"]),
    }
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    _print_summary(name, months, rain_end, rain, z, rank, len(ranked), hv,
                   cls_ha, cls_pct, enso_now, iod_now, sst_end, prim)
    _print_cdi(cdi_out, prim)
    return stats
