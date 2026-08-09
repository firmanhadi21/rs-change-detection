#!/usr/bin/env python3
"""Fire-season accountability record — danger, hotspots and burned area by zone.

A danger forecast is ephemeral: it updates and the previous state is gone, so it
is weak material for anything retrospective. This produces the opposite -- a
reproducible, archived, per-zone record of what a fire season did, computed from
public data by code anyone can re-run:

  * the Drought Code trajectory through the season, sampled at checkpoints
  * FIRMS hotspots that occurred inside each zone, by month
  * MODIS burned area that followed
  * the dates each zone crossed the BMKG danger thresholds

The point is the ZONE. "Southern Kalimantan is red" has no addressee; "87% of
this Cagar Alam stood at Tinggi from 12 July, 9 hotspots followed, 340 ha burned"
does. Accountability needs a named party, a date and a number that survives being
checked a year later.

Everything is cross-tabulated locally on one grid, so the record can be
recomputed without Earth Engine once the rasters are downloaded.

Backend: needs --backend gee.
"""

import datetime as dt
import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from .fire_danger import (BMKG_BREAKS, ERA5_HOURLY, ERA5_SCALE, SPINUP_DAYS,
                          _accumulate, _classes, _day_factors, _label,
                          _noon_utc_hour, _read_zones)

FIRMS_IC = "FIRMS"
BURN_IC = "MODIS/061/MCD64A1"
FIRMS_SCALE, BURN_SCALE = 1000, 500
DEFAULT_STEP = 15          # days between Drought Code checkpoints
ZONE_GRID_M = 500.0


def _checkpoints(start, end, step):
    """Dates the record samples. Sparse on purpose: DC has a ~52-day time lag,
    so a fortnightly sample loses nothing and a daily one costs 25x more."""
    out, d = [], start
    while d <= end:
        out.append(d)
        d += dt.timedelta(days=step)
    if out[-1] != end:
        out.append(end)
    return out


def _dc_snapshots(aoi, season_start, season_end, spinup, step):
    """Drought Code at each checkpoint, from ONE continuous accumulation.

    Re-running the spinup per checkpoint would repeat the same arithmetic dozens
    of times; instead the daily chain runs once and the DC image is captured as
    it passes each checkpoint date.
    """
    import ee
    days = [season_start - dt.timedelta(days=spinup - i)
            for i in range(spinup)] + \
        [season_start + dt.timedelta(days=i)
         for i in range((season_end - season_start).days + 1)]
    cps = set(_checkpoints(season_start, season_end, step))
    want = [1 if d in cps else 0 for d in days]
    kept = [d for d in days if d in cps]

    cen = aoi.centroid(maxError=1000).coordinates().getInfo()
    noon_h = _noon_utc_hour(cen[0])
    le, lf, dl = _day_factors(cen[1], days)
    snaps = _accumulate_with_snapshots(aoi, days, noon_h, le, lf, want)
    return kept, snaps, dl, noon_h


def _accumulate_with_snapshots(aoi, days, noon_h, le, lf, want):
    """The fire_danger accumulation, keeping DC at flagged days."""
    import ee
    from .fire_danger import _dc, _dmc, _ffmc, _noon_weather
    from .fire_danger import DC_START, DMC_START, FFMC_START

    le_l, lf_l, want_l = ee.List(le), ee.List(lf), ee.List(want)
    day_l = ee.List([d.isoformat() for d in days])
    init = ee.Dictionary({
        "ffmc": ee.Image.constant(FFMC_START).rename("FFMC").clip(aoi).toFloat(),
        "dmc": ee.Image.constant(DMC_START).rename("DMC").clip(aoi).toFloat(),
        "dc": ee.Image.constant(DC_START).rename("DC").clip(aoi).toFloat(),
        "snaps": ee.List([]),
    })

    def step(i, prev):
        i = ee.Number(i)
        prev = ee.Dictionary(prev)
        t, h, w, r = _noon_weather(aoi, ee.String(day_l.get(i)), noon_h)
        dc = _dc(ee.Image(prev.get("dc")), t, r, ee.Number(lf_l.get(i)))
        snaps = ee.List(prev.get("snaps"))
        snaps = ee.List(ee.Algorithms.If(ee.Number(want_l.get(i)).eq(1),
                                         snaps.add(dc), snaps))
        return ee.Dictionary({
            "ffmc": _ffmc(ee.Image(prev.get("ffmc")), t, h, w, r),
            "dmc": _dmc(ee.Image(prev.get("dmc")), t, h, r,
                        ee.Number(le_l.get(i))),
            "dc": dc, "snaps": snaps})

    out = ee.Dictionary(ee.List.sequence(0, len(days) - 1).iterate(step, init))
    return ee.List(out.get("snaps"))


def _zone_on_grid(shapes, aoi_geom, out_shape, transform):
    """Zones burned onto a given grid, clipped to the AOI polygon.

    Clipping to the polygon matters: the AOI's bounding box includes chunks of
    neighbouring districts, and without this the record silently attributes
    their land -- and their fires -- to zones inside the area of interest.
    """
    import numpy as np
    from rasterio.features import rasterize

    zone = rasterize(shapes, out_shape=out_shape, transform=transform, fill=0,
                     dtype="int32", all_touched=False)
    inside = rasterize([(aoi_geom, 1)], out_shape=out_shape,
                       transform=transform, fill=0, dtype="uint8")
    zone[inside == 0] = 0
    return zone


def _grid_of(tif):
    """A raster's own grid, so a layer can be tabulated where it actually lives."""
    import rasterio
    with rasterio.open(tif) as src:
        return (src.height, src.width), src.transform


def _px_area_ha(shape, tr):
    """Latitude-corrected pixel area, one value per row."""
    import math
    import numpy as np
    h, _ = shape
    m_lat = (math.pi / 180) * 6_371_008.8
    lat = tr.f + (np.arange(h) + 0.5) * tr.e
    return (abs(tr.a) * m_lat * np.cos(np.radians(lat))) * (abs(tr.e) * m_lat) / 1e4


def _sample_mean(tif, zone, tr):
    """Area-weighted mean of a coarse field per zone.

    Sampling the coarse field onto the fine zone grid is right for a MEAN -- it
    approximates an area weighting. It would be wrong for a count, which is why
    counts go through _sum_native instead.
    """
    import numpy as np
    import rasterio

    from .gee_utils import read_band
    a, _ = read_band(tif, label=os.path.basename(tif))
    with rasterio.open(tif) as src:
        ct, H, W = src.transform, src.height, src.width
    h, w = zone.shape
    lon = tr.c + (np.arange(w) + 0.5) * tr.a
    lat = tr.f + (np.arange(h) + 0.5) * tr.e
    cols = np.clip(np.floor((lon - ct.c) / ct.a).astype("int64"), 0, W - 1)
    rows = np.clip(np.floor((lat - ct.f) / ct.e).astype("int64"), 0, H - 1)
    grid = a[np.ix_(rows, cols)]

    out = {}
    for z in np.unique(zone):
        if z == 0:
            continue
        vals = grid[zone == z]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            out[int(z)] = float(vals.mean())
    return out


def _sum_native(tif, shapes, aoi_geom):
    """Sum a count raster per zone, ON ITS OWN GRID.

    Resampling a count onto a finer grid multiplies it: a 1 km FIRMS pixel
    lands in four 500 m cells and gets added four times. Counts therefore have
    to be tabulated where they were measured.
    """
    import numpy as np
    import rasterio

    from .gee_utils import read_band
    shape, tr = _grid_of(tif)
    zone = _zone_on_grid(shapes, aoi_geom, shape, tr)
    a, _ = read_band(tif, label=os.path.basename(tif))
    a = np.nan_to_num(a, nan=0.0)
    out = {}
    for z in np.unique(zone):
        if z == 0:
            continue
        out[int(z)] = float(a[zone == z].sum())
    return out


def _burned_ha_native(tif, shapes, aoi_geom):
    """Burned hectares per zone, on the burn product's own grid."""
    import numpy as np
    import rasterio

    from .gee_utils import read_band
    shape, tr = _grid_of(tif)
    zone = _zone_on_grid(shapes, aoi_geom, shape, tr)
    # Burned area is the layer that shipped a confident zero for every zone, so
    # this one warns loudly rather than quietly returning nothing.
    a, _ = read_band(tif, label="burned area (MCD64A1)")
    a = np.nan_to_num(a, nan=0.0)
    px = _px_area_ha(shape, tr)
    burnt = a > 0
    out = {}
    for z in np.unique(zone):
        if z == 0:
            continue
        rows, _ = np.where(burnt & (zone == z))
        out[int(z)] = float(px[rows].sum()) if rows.size else 0.0
    return out


def _zone_area_ha(zone, tr):
    """Latitude-corrected area per zone, on the zone grid."""
    import numpy as np
    px = _px_area_ha(zone.shape, tr)
    out = {}
    for z in np.unique(zone):
        if z == 0:
            continue
        rows, _ = np.where(zone == z)
        out[int(z)] = float(px[rows].sum())
    return out


# ------------------------------------------------------- season layers
def _hotspots_monthly(aoi, start, end, run_dir):
    """FIRMS hotspot counts per month, as small rasters for local tabulation."""
    import ee
    from .gee_utils import download_geotiff
    out, m = {}, dt.date(start.year, start.month, 1)
    coords = aoi.bounds().getInfo()["coordinates"]
    while m <= end:
        nxt = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        a, b = max(m, start), min(nxt - dt.timedelta(days=1), end)
        img = (ee.ImageCollection(FIRMS_IC).select("T21")
               .filterDate(a.isoformat(), (b + dt.timedelta(days=1)).isoformat())
               .map(lambda i: i.gt(0).unmask(0)).sum().rename("n").clip(aoi))
        tif = os.path.join(run_dir, f"_hotspots_{m:%Y-%m}.tif")
        if download_geotiff(img.toFloat(), coords, tif, scale=FIRMS_SCALE):
            out[f"{m:%Y-%m}"] = tif
        m = nxt
    return out


def _burned_area(aoi, start, end, run_dir):
    """MODIS burned area over the season. Under-detects Indonesian peat fire,
    which smoulders below the surface -- a lower bound, and labelled as one."""
    import ee
    from .gee_utils import download_geotiff
    # Reduce first, THEN threshold and unmask. Unmasking inside the map did not
    # survive the collection reducer -- the downloaded raster came back every
    # pixel -inf, i.e. wholly masked, which reads identically to "nothing
    # burned" once a reader applies masked=True.
    img = (ee.ImageCollection(BURN_IC).select("BurnDate")
           .filterDate(start.isoformat(), (end + dt.timedelta(days=1)).isoformat())
           .max().gt(0).unmask(0).rename("burn").clip(aoi))
    tif = os.path.join(run_dir, "_burned.tif")
    coords = aoi.bounds().getInfo()["coordinates"]
    return download_geotiff(img.toFloat(), coords, tif, scale=BURN_SCALE)


def _build_records(zone, tr, names, dc_by_date, hs, burn, lang):
    """Assemble one record per zone from the tabulated layers."""
    import numpy as np
    labels = [_label(r, lang) for r in _classes("DC")]
    breaks = BMKG_BREAKS["DC"]
    areas = _zone_area_ha(zone, tr)

    recs = {}
    for i, nm in enumerate(names, start=1):
        if i not in areas:
            continue
        series = {d.isoformat(): round(v.get(i), 1)
                  for d, v in dc_by_date.items() if v.get(i) is not None}
        if not series:
            continue
        vals = list(series.values())
        peak = max(vals)
        # First date each threshold was crossed -- the date an obligation, if
        # one is attached to that class, would have started.
        #
        # A crossing dated to the FIRST snapshot is not a crossing: the zone was
        # already at that class when the window opened, and the real date is
        # earlier than anything this run can see. Recording it as a date would
        # turn the window's left edge into a finding, and every zone would
        # appear to have crossed on the same day.
        first_snap = next(iter(series))
        crossed, censored = {}, {}
        for lvl, br in zip(labels[1:], breaks):
            hit = next((d for d, v in series.items() if v >= br), None)
            crossed[lvl] = hit
            censored[lvl] = hit is not None and hit == first_snap
        months = {mo: int(round(v.get(i, 0))) for mo, v in hs.items()}
        recs[nm] = {
            "area_ha": round(areas[i], 1),
            "dc_series": series,
            "dc_peak": round(peak, 1),
            "dc_peak_date": max(series, key=series.get),
            "dc_class_at_peak": labels[int(np.digitize(peak, breaks))],
            "first_crossed": crossed,
            "first_crossed_censored": censored,
            "checkpoints_at_or_above_Tinggi": sum(1 for v in vals if v >= breaks[1]),
            "checkpoints_total": len(vals),
            "hotspots_by_month": months,
            "hotspots_total": sum(months.values()),
            "burned_ha": (round(burn[i], 1) if i in burn else None),
        }
    return recs


def _crossing_lines(r):
    """The threshold dates, with the ones the window cut off marked as such.

    A date equal to the first snapshot is the window's left edge showing
    through, not a finding. Left unmarked it reads as though every zone crossed
    on the same day -- which is exactly what a season starting after the build-up
    produces, and exactly the sort of tidy coincidence that gets quoted.
    """
    out, cens = [], r.get("first_crossed_censored", {})
    for lvl, d in r["first_crossed"].items():
        if not d:
            continue
        if cens.get(lvl):
            out.append(f"- Sudah pada kelas **{lvl}** saat jendela dibuka "
                       f"({d}) — tanggal sebenarnya lebih awal; mulai musim "
                       "lebih pagi untuk menemukannya")
        else:
            out.append(f"- Pertama mencapai **{lvl}**: {d}")
    return out


def _write_markdown(path, recs, meta, lang):
    """The citable document. One table per zone, sorted by exposure, with the
    provenance a reader needs to re-run or challenge it."""
    labels = [_label(r, lang) for r in _classes("DC")]
    hi = labels[2]
    order = sorted(recs.items(), key=lambda kv: -kv[1]["dc_peak"])
    L = []
    L.append(f"# Catatan musim kebakaran — {meta['name']}")
    L.append("")
    L.append(f"**Musim:** {meta['season'][0]} sampai {meta['season'][1]}  ")
    L.append(f"**Dikelompokkan menurut:** `{meta['zone_field']}` "
             f"({meta['zones_file']})  ")
    L.append(f"**Dihitung:** {dt.date.today().isoformat()} dengan "
             f"`earthchange -s fire-record`")
    L.append("")
    L.append("Catatan ini dapat dihitung ulang. Seluruh masukan bersifat publik "
             "dan metodenya terbuka, sehingga angka di bawah dapat diperiksa "
             "atau dibantah oleh siapa pun, bukan sekadar dipercaya.")
    L.append("")
    L.append("## Ringkasan")
    L.append("")
    L.append(f"| Kawasan | Luas (ha) | DC puncak | Kelas | Pertama ≥ {hi} | "
             f"Titik panas | Terbakar (ha) |")
    L.append("|---|---:|---:|---|---|---:|---:|")
    for nm, r in order:
        first = r["first_crossed"].get(hi) or "—"
        if r.get("first_crossed_censored", {}).get(hi):
            first = f"sebelum {first}"
        burned = f"{r['burned_ha']:,.0f}" if r["burned_ha"] is not None else "—"
        L.append(f"| {nm} | {r['area_ha']:,.0f} | {r['dc_peak']:,.0f} | "
                 f"{r['dc_class_at_peak']} | {first} | {r['hotspots_total']:,} | "
                 f"{burned} |")
    L.append("")
    for nm, r in order:
        L.append(f"## {nm}")
        L.append("")
        L.append(f"Luas {r['area_ha']:,.0f} ha. Drought Code memuncak pada "
                 f"**{r['dc_peak']:,.0f}** ({r['dc_class_at_peak']}) pada "
                 f"{r['dc_peak_date']}, dan berada pada kelas {hi} atau lebih "
                 f"tinggi pada {r['checkpoints_at_or_above_Tinggi']} dari "
                 f"{r['checkpoints_total']} titik pantau.")
        L.append("")
        L.extend(_crossing_lines(r))
        L.append("")
        if r["hotspots_total"]:
            L.append(f"Titik panas FIRMS di dalam kawasan: "
                     f"**{r['hotspots_total']:,}** "
                     + " · ".join(f"{mo} {n}" for mo, n in
                                  sorted(r["hotspots_by_month"].items()) if n))
        else:
            L.append("Tidak ada titik panas FIRMS terdeteksi di dalam kawasan.")
        if r["burned_ha"]:
            L.append("")
            L.append(f"Luas terbakar MODIS: **{r['burned_ha']:,.0f} ha** "
                     f"({r['burned_ha'] / r['area_ha'] * 100:.1f}% kawasan). "
                     f"Angka ini **batas bawah**: MCD64A1 pada 500 m meremehkan "
                     f"kebakaran gambut yang membara di bawah permukaan.")
        L.append("")
    L.append("## Sumber dan batasan")
    L.append("")
    L.append(f"- Drought Code: Sistem FWI Kanada (Van Wagner 1987) dari "
             f"ERA5-Land {ERA5_SCALE} m, akumulasi {meta['spinup']} hari sebelum "
             f"musim, faktor panjang hari {meta['daylength']}, dicuplik tiap "
             f"{meta['step']} hari")
    L.append(f"- Ambang kelas: BMKG SPARTAN — DC "
             f"{'/'.join(str(b) for b in BMKG_BREAKS['DC'])}")
    L.append("- Titik panas: NASA FIRMS (MODIS, ~1 km) — jumlah piksel-hari, "
             "bukan luas; awan menyembunyikan api")
    L.append("- Luas terbakar: MODIS MCD64A1 (500 m) — batas bawah untuk gambut")
    L.append(f"- Zona: `{meta['zones_file']}`, atribut `{meta['zone_field']}`, "
             f"ditabulasi pada grid {meta['grid_m']:.0f} m")
    L.append("- ERA5-Land meratakan cuaca lokal pada 11 km; kelas bahaya "
             "berasal dari bidang kasar itu, bukan dari pengamatan di kawasan")
    L.append("")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    return path


def _render(run_dir, name, recs, meta, lang):
    """DC trajectory per zone with hotspots beneath, on one time axis.

    The two panels share an x-axis because the claim the record makes is about
    sequence: the ground dried, and then it burned. Separate figures would let a
    reader assume the ordering instead of seeing it.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [_label(r, lang) for r in _classes("DC")]
    breaks = BMKG_BREAKS["DC"]
    order = sorted(recs.items(), key=lambda kv: -kv[1]["dc_peak"])[:8]
    if not order:
        return None
    fig, (ax, axh) = plt.subplots(2, 1, figsize=(13, 9), dpi=150,
                                  height_ratios=[2.1, 1], sharex=True)
    fig.patch.set_facecolor("#faf8f4")
    cmap = plt.get_cmap("turbo")
    for k, (nm, r) in enumerate(order):
        xs = [dt.date.fromisoformat(d) for d in sorted(r["dc_series"])]
        ys = [r["dc_series"][d.isoformat()] for d in xs]
        ax.plot(xs, ys, lw=1.9, color=cmap(k / max(len(order) - 1, 1)),
                label=f"{nm[:34]} ({r['area_ha']:,.0f} ha)")
    for br, lb in zip(breaks, labels[1:]):
        ax.axhline(br, ls="--", lw=.8, color="#888")
        ax.text(ax.get_xlim()[1], br, f" {lb}", va="center", fontsize=8,
                color="#666")
    ax.set_ylabel("Drought Code")
    ax.grid(ls=":", alpha=.4)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8, frameon=False, ncol=2, loc="upper left")
    ax.set_title(f"Catatan musim kebakaran — {name}\n"
                 f"{meta['season'][0]} → {meta['season'][1]} · Drought Code per "
                 f"{meta['zone_field']} · ambang BMKG",
                 fontsize=13, fontweight="bold", loc="left")

    months = sorted({m for _, r in order for m in r["hotspots_by_month"]})
    bottom = [0] * len(months)
    for k, (nm, r) in enumerate(order):
        vals = [r["hotspots_by_month"].get(m, 0) for m in months]
        axh.bar([dt.date.fromisoformat(m + "-15") for m in months], vals,
                width=22, bottom=bottom, color=cmap(k / max(len(order) - 1, 1)),
                edgecolor="none")
        bottom = [b + v for b, v in zip(bottom, vals)]
    axh.set_ylabel("titik panas FIRMS")
    axh.grid(axis="y", ls=":", alpha=.4)
    axh.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
        axh.spines[sp].set_visible(False)
    fig.text(.008, .012,
             "Drought Code: Sistem FWI Kanada dari ERA5-Land 11 km. Titik panas: "
             "FIRMS (MODIS ~1 km), jumlah piksel-hari. Ambang: BMKG SPARTAN. "
             "Dapat dihitung ulang dengan earthchange -s fire-record.",
             fontsize=7.5, color="#777")
    fig.tight_layout(rect=[0, .035, 1, 1])
    out = os.path.join(run_dir, f"{name}_fire_record.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _check_args(zones, zone_field, season):
    """Validate before any Earth Engine work. Returns the season dates."""
    if not zones or not zone_field:
        raise SystemExit("fire-record needs --zones FILE and --zone-field COLUMN "
                         "— the record is per zone, and without them there is no "
                         "party to attribute anything to.")
    if not os.path.exists(zones):
        from .gee_utils import missing_zones
        raise missing_zones(zones)
    if not season or ":" not in season:
        raise SystemExit("fire-record needs --season START:END, "
                         "e.g. --season 2019-06-01:2019-11-30")
    s0, s1 = (dt.date.fromisoformat(x) for x in season.split(":"))
    if s1 <= s0:
        raise SystemExit(f"--season end must follow start (got {season})")
    return s0, s1


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        season=None, admin=None, bbox=None, zones=None, zone_field=None,
        spinup=SPINUP_DAYS, step=DEFAULT_STEP, grid_m=ZONE_GRID_M, lang="id"):
    """Fire-season accountability record, by zone."""
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"fire-record needs {mod}: "
                             "pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("fire-record needs --backend gee (ERA5-Land + FIRMS).")
    s0, s1 = _check_args(zones, zone_field, season)

    from .gee_utils import initialize_ee, download_geotiff
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)
    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    bounds = (min(xs), min(ys), max(xs), max(ys))

    cps = _checkpoints(s0, s1, step)
    print(f"  {name}: {s0} → {s1} · {len(cps)} titik pantau tiap {step} hari · "
          f"akumulasi {spinup} hari sebelumnya")

    kept, snaps, dl, noon_h = _dc_snapshots(aoi, s0, s1, spinup, step)
    print(f"  menghitung Drought Code ({spinup + (s1 - s0).days + 1} hari) ...",
          flush=True)
    dc_tifs = {}
    for i, d in enumerate(kept):
        import ee
        tif = os.path.join(run_dir, f"_dc_{d.isoformat()}.tif")
        got = download_geotiff(ee.Image(snaps.get(i)).clip(aoi).toFloat(),
                               coords, tif, scale=ERA5_SCALE)
        if got:
            dc_tifs[d] = got
    print(f"  {len(dc_tifs)}/{len(kept)} titik pantau terunduh")

    hs_tifs = _hotspots_monthly(aoi, s0, s1, run_dir)
    burn_tif = _burned_area(aoi, s0, s1, run_dir)

    import rasterio
    from shapely.geometry import shape as shp_shape
    shapes, names = _read_zones(zones, zone_field, bounds)
    if not shapes:
        raise SystemExit("--zones has no features over this AOI.")
    aoi_geom = shp_shape(aoi.getInfo())
    deg = grid_m / 111_000.0
    zw = max(10, int(round((bounds[2] - bounds[0]) / deg)))
    zh = max(10, int(round((bounds[3] - bounds[1]) / deg)))
    tr = rasterio.transform.from_bounds(*bounds, zw, zh)
    zone = _zone_on_grid(shapes, aoi_geom, (zh, zw), tr)
    print(f"  {len(names)} kategori pada grid {grid_m:.0f} m, "
          f"dipotong ke poligon AOI")

    # Means on the fine zone grid; counts and areas on each layer's own grid,
    # because resampling a count multiplies it.
    dc_by_date = {d: _sample_mean(t, zone, tr) for d, t in dc_tifs.items()}
    hs = {mo: _sum_native(t, shapes, aoi_geom) for mo, t in hs_tifs.items()}
    burn = _burned_ha_native(burn_tif, shapes, aoi_geom) if burn_tif else {}
    recs = _build_records(zone, tr, names, dc_by_date, hs, burn, lang)

    meta = {"name": name, "season": [s0.isoformat(), s1.isoformat()],
            "zone_field": zone_field, "zones_file": os.path.basename(zones),
            "spinup": spinup, "step": step, "grid_m": grid_m, "daylength": dl}
    md = _write_markdown(os.path.join(run_dir, f"{name}_fire_record.md"),
                         recs, meta, lang)
    png = _render(run_dir, name, recs, meta, lang)
    stats = {"run_id": run_id, "scenario": "fire-record", "name": name,
             **meta, "class_breaks": BMKG_BREAKS,
             "class_source": "BMKG SPARTAN operational legend",
             "zones": recs,
             "outputs": {"record": os.path.basename(md),
                         "figure": os.path.basename(png) if png else None},
             "note": ("A record, not a forecast. Hotspot counts are pixel-days, "
                      "not area. MODIS burned area under-detects peat fire and "
                      "is a lower bound. The danger class comes from an 11 km "
                      "field, not from observations inside the zone.")}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    labels = [_label(r, lang) for r in _classes("DC")]
    print(f"\n{name} — {s0} → {s1}")
    print(f"  {'kawasan':34s} {'luas ha':>11s} {'DC puncak':>10s} "
          f"{'≥Tinggi':>8s} {'titik':>7s} {'terbakar ha':>12s}")
    for nm, r in sorted(recs.items(), key=lambda kv: -kv[1]["dc_peak"]):
        b = f"{r['burned_ha']:,.0f}" if r["burned_ha"] is not None else "—"
        print(f"  {nm[:34]:34s} {r['area_ha']:11,.0f} {r['dc_peak']:10,.0f} "
              f"{r['checkpoints_at_or_above_Tinggi']:4d}/{r['checkpoints_total']:<3d} "
              f"{r['hotspots_total']:7,} {b:>12s}")
    print(f"\n  catatan: {os.path.basename(md)}")
    return stats
