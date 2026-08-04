#!/usr/bin/env python3
"""Drought: rainfall deficit (SPI), vegetation health (VCI/TCI/VHI), and ENSO state.

Three questions, three data sources, deliberately kept separate because they can
disagree and the disagreement is informative:

  1. Is rain missing?          CHIRPS 1981-      -> standardized rainfall anomaly
  2. Are plants suffering yet? MODIS NDVI + LST  -> VCI / TCI / VHI
  3. Is ENSO driving it?       NOAA OISST        -> Nino 3.4 anomaly

Meteorological drought leads agricultural drought by weeks to months, so a large
rainfall deficit with still-healthy VHI means the impact has not landed *yet*.

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

CHIRPS_BASE = (1991, 2020)             # WMO 30-year climate normal
MODIS_BASE = (2001, 2020)              # MODIS starts 2000; 2001 is the first full year
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


def _rain_total(aoi, start, end):
    import ee
    return (ee.ImageCollection(CHIRPS_IC).select("precipitation")
            .filterDate(start.isoformat(), end.isoformat()).sum())


def _rain_window_totals(aoi, end, months, base):
    """Accumulated rainfall for the target window and the same window each
    baseline year. Returns (current_mm, [baseline_mm, ...]) as ee.Numbers."""
    import ee
    start = _shift_months(end, months)
    cur = _mean_over(_rain_total(aoi, start, end), aoi, CHIRPS_SCALE, "precipitation")
    hist = []
    for y in range(base[0], base[1] + 1):
        off = y - end.year
        try:
            a, b = start.replace(year=start.year + off), end.replace(year=y)
        except ValueError:                      # 29 Feb in a non-leap baseline year
            a, b = start.replace(year=start.year + off), end.replace(year=y, day=28)
        hist.append(_mean_over(_rain_total(aoi, a, b), aoi,
                               CHIRPS_SCALE, "precipitation"))
    return cur, ee.List(hist)


def _rainfall_z(aoi, end, months, base):
    """Standardized rainfall anomaly. See the module docstring on why this is a
    z-score and not a gamma-fitted SPI."""
    import ee
    cur, hist = _rain_window_totals(aoi, end, months, base)
    mean = ee.Number(hist.reduce(ee.Reducer.mean()))
    sd = ee.Number(hist.reduce(ee.Reducer.stdDev()))
    out = ee.Dictionary({
        "current_mm": cur, "normal_mm": mean, "sd_mm": sd,
        "z": cur.subtract(mean).divide(sd),
        "pct_of_normal": cur.divide(mean).multiply(100),
    }).getInfo()
    return {k: (round(v, 2) if isinstance(v, (int, float)) else v)
            for k, v in out.items()}


def _rain_z_by_year(aoi, end, months, base, years):
    """Rainfall z for the same calendar window in each of `years`, so the current
    season can be ranked against the record rather than judged in isolation."""
    import ee
    _cur, hist = _rain_window_totals(aoi, end, months, base)
    mean = ee.Number(hist.reduce(ee.Reducer.mean()))
    sd = ee.Number(hist.reduce(ee.Reducer.stdDev()))
    start = _shift_months(end, months)
    per = []
    for y in years:
        off = y - end.year
        try:
            a, b = start.replace(year=start.year + off), end.replace(year=y)
        except ValueError:
            a, b = start.replace(year=start.year + off), end.replace(year=y, day=28)
        per.append(_mean_over(_rain_total(aoi, a, b), aoi,
                              CHIRPS_SCALE, "precipitation"))
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
                    for y in range(CHIRPS_BASE[0], CHIRPS_BASE[1] + 1)])
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
             f"baseline hujan {CHIRPS_BASE[0]}–{CHIRPS_BASE[1]}, "
             f"vegetasi {MODIS_BASE[0]}–{MODIS_BASE[1]}",
             fontsize=9, color="#555")
    fig.text(.02, .012,
             "Sumber: CHIRPS (hujan) · MODIS MOD13A2/MOD11A2 (VCI/TCI) · "
             "NOAA OISST (Nino 3.4 & DMI/IOD). Anomali hujan = z-score, bukan SPI gamma.",
             fontsize=8, color="#777")
    fig.tight_layout(rect=[0, .025, 1, .945])
    out = os.path.join(run_dir, f"{name}_kekeringan.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _export_vhi(vhi, aoi, run_dir, name):
    """Best-effort GeoTIFF of the VHI field; the panel is the primary output."""
    from .gee_utils import download_geotiff
    path = os.path.join(run_dir, f"{name}_vhi.tif")
    try:
        return download_geotiff(vhi.clip(aoi).toFloat(),
                                aoi.bounds().getInfo()["coordinates"],
                                path, scale=MODIS_SCALE)
    except Exception as exc:
        print(f"  (peta VHI dilewati: {str(exc)[:70]})")
        return None


def _resolve_end(explicit):
    """Align to the latest CHIRPS image unless the caller pinned a date."""
    if explicit:
        return dt.date.fromisoformat(explicit)
    return _latest(CHIRPS_IC, "precipitation")


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        months=3, end=None, admin=None, bbox=None, start_year=1991,
        vhi_window=48):
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

    rain_end = _resolve_end(end)
    ndvi_end = _latest(NDVI_IC, "NDVI")
    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)

    print(f"  hujan s/d {rain_end} (CHIRPS) · vegetasi s/d {ndvi_end} (MODIS)")
    print(f"  jendela {months} bulan · baseline {CHIRPS_BASE[0]}–{CHIRPS_BASE[1]}")

    rain = _rainfall_z(aoi, rain_end, months, CHIRPS_BASE)
    years = list(range(max(start_year, 1981), rain_end.year + 1))
    zs = _rain_z_by_year(aoi, rain_end, months, CHIRPS_BASE, years)

    vhi_img, hv = _vhi(aoi, ndvi_end, vhi_window, MODIS_BASE)
    # ENSO is anchored to the freshest SST, not to the rainfall window: OISST lags
    # only days while CHIRPS lags weeks, and "is it El Nino right now" is usually
    # the question being asked.
    sst_end = _latest(SST_IC, "sst")
    labels, nino, dmi = _climate_modes(sst_end)

    png = _render_panel(run_dir, name, years, zs, hv, labels, nino, dmi,
                        {"months": months, "rain_end": rain_end.isoformat(),
                         "current_year": rain_end.year})
    tif = _export_vhi(vhi_img, aoi, run_dir, name)

    z = rain["z"]
    ranked = sorted((v for v in zs if v is not None))
    rank = ranked.index(z) + 1 if z in ranked else None
    enso_now = next((v for v in reversed(nino) if v is not None), None)
    iod_now = next((v for v in reversed(dmi) if v is not None), None)

    stats = {
        "run_id": run_id, "scenario": "drought", "name": name,
        "window": {"months": months, "rain_end": rain_end.isoformat(),
                   "vegetation_end": ndvi_end.isoformat(),
                   "enso_end": sst_end.isoformat()},
        "sources": {
            "rainfall": f"CHIRPS daily ({CHIRPS_IC}), baseline {CHIRPS_BASE[0]}-{CHIRPS_BASE[1]}",
            "vegetation": f"MODIS {NDVI_IC} + {LST_IC}, baseline {MODIS_BASE[0]}-{MODIS_BASE[1]}",
            "enso": f"NOAA OISST ({SST_IC}), Nino 3.4 region {NINO34_BOX}",
            "iod": (f"NOAA OISST ({SST_IC}), DMI = west {IOD_WEST_BOX} minus "
                    f"east {IOD_EAST_BOX} (Saji et al. 1999)")},
        "rainfall": {**rain, "class": _spi_label(z)[0]},
        "rainfall_z_by_year": dict(zip([str(y) for y in years], zs)),
        "rank_driest_of_record": rank, "years_in_record": len(ranked),
        "vegetation": {**hv, "class": _classify(hv["vhi"], VHI_CLASSES)[0]},
        "enso": {"nino34_anomaly_c": enso_now,
                 "class": _classify(enso_now, ENSO_CLASSES),
                 "monthly": dict(zip(labels, nino))},
        "iod": {"dmi_c": iod_now, "class": _classify(iod_now, IOD_CLASSES),
                "event_threshold_c": IOD_EVENT_C,
                "monthly": dict(zip(labels, dmi))},
        "outputs": {"panel": os.path.basename(png),
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
    if enso_now is not None:
        print(f"  Nino 3.4 {enso_now:+.2f} °C ({sst_end}) → "
              f"{_classify(enso_now, ENSO_CLASSES)}")
    if iod_now is not None:
        print(f"  IOD/DMI  {iod_now:+.2f} °C ({sst_end}) → "
              f"{_classify(iod_now, IOD_CLASSES)}")
    return stats
