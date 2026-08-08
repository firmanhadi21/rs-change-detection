#!/usr/bin/env python3
"""Fire danger rating — the Canadian Forest Fire Weather Index (FWI) System.

Six components, computed per pixel from daily noon weather (ERA5-Land):

  FFMC  fine fuel moisture   temp, RH, wind, rain   litter -> ease of ignition
  DMC   duff moisture        temp, RH, rain         loose organic layers
  DC    drought code         temp, rain             DEEP compact organic matter
  ISI   initial spread       FFMC + wind            rate of spread
  BUI   buildup              DMC + DC               fuel available to burn
  FWI   fire weather index   ISI + BUI              overall intensity

Equations: Van Wagner & Pickett (1985), Van Wagner (1987), CFS Forestry Tech.
Report 35. Implemented server-side; every conditional becomes .where().

WHY DC LEADS HERE. The headline FWI weights wind-driven spread through ISI,
which is what matters in Canadian boreal forest. Indonesian peat fires are
driven by deep drying and smoulder below the surface, so DC -- and BUI, which
is built from it -- are the operative variables. This module reports all six
but leads with DC/BUI, and says so in its output.

DAY-LENGTH FACTORS. DMC and DC carry month-by-month day-length constants
tabulated for 46 degrees N. At the equator day length barely varies, so the
Canadian table is simply wrong there. The equatorial convention (Field et al.'s
Indonesian FDRS work, and GFWED) uses flat Le = 9.0 and Lf = 1.4. Chosen by
AOI latitude, and recorded in the output so the choice is auditable.

Backend: needs --backend gee.
"""

import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

ERA5_HOURLY = "ECMWF/ERA5_LAND/HOURLY"
ERA5_SCALE = 11132

# Van Wagner start-of-season defaults: fully-cured fine fuel, damp deeper layers.
FFMC_START, DMC_START, DC_START = 85.0, 6.0, 15.0
# DC has a ~52-day time lag, so it is meaningless until it has been accumulating
# for at least that long. Anything shorter reports the starting value, not the site.
SPINUP_DAYS = 60

# Canadian day-length tables (46 N), for AOIs outside the tropics.
DMC_LE_N = [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0]
DC_LF_N = [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6]
DMC_LE_EQ, DC_LF_EQ = 9.0, 1.4        # equatorial convention
TROPIC = 15.0                          # |lat| below this -> equatorial factors

# FWI danger classes as adapted for Indonesia (BMKG SPBK / ASEAN). These are far
# lower than the Canadian thresholds; quoting Canadian classes over Sumatra or
# Kalimantan would call a dangerous day "low".
FWI_CLASSES = [
    (1.0, {"id": "Rendah", "en": "Low"}, "#2e9e4f"),
    (6.0, {"id": "Sedang", "en": "Moderate"}, "#2f7fd1"),
    (13.0, {"id": "Tinggi", "en": "High"}, "#e8a33d"),
    (float("inf"), {"id": "Ekstrem", "en": "Extreme"}, "#d1372f"),
]
NODATA = 255


def _label(row, lang):
    return row[1].get(lang, row[1]["id"])


# --------------------------------------------------------------- weather
def _noon_utc_hour(lon):
    """UTC hour closest to local solar noon. FWI is defined at noon local
    standard time; taking a daily mean instead would understate the peak."""
    h = round(12.0 - lon / 15.0)
    return int(h % 24)


def _noon_weather(aoi, day, noon_h):
    """Noon temp (C), RH (%), wind (km/h) and the 24 h rain (mm) to noon."""
    import ee
    start = ee.Date(day)
    noon = start.advance(noon_h, "hour")
    hourly = ee.ImageCollection(ERA5_HOURLY)

    at_noon = hourly.filterDate(noon, noon.advance(1, "hour")).first()
    t = at_noon.select("temperature_2m").subtract(273.15)
    td = at_noon.select("dewpoint_temperature_2m").subtract(273.15)
    # Magnus: RH from temperature and dewpoint.
    def sat(x):
        return x.multiply(17.625).divide(x.add(243.04)).exp()
    rh = sat(td).divide(sat(t)).multiply(100).clamp(0, 100)
    u = at_noon.select("u_component_of_wind_10m")
    v = at_noon.select("v_component_of_wind_10m")
    wind = u.hypot(v).multiply(3.6)                       # m/s -> km/h

    # 24 h to noon, metres -> mm. The FWI rain window ends at noon, not midnight.
    rain = (hourly.filterDate(noon.advance(-24, "hour"), noon)
            .select("total_precipitation_hourly").sum().multiply(1000))
    return (t.rename("t"), rh.rename("h"), wind.rename("w"), rain.rename("r"))


# ------------------------------------------------------- the six codes
def _ffmc(ffmc0, t, h, w, r):
    """Fine Fuel Moisture Code. Responds within hours; drives ignition."""
    import ee
    mo = ffmc0.multiply(-1).add(101).multiply(147.2).divide(ffmc0.add(59.5))

    rf = r.subtract(0.5).max(0)
    # Wetting, with the >150 correction for already-wet fuel.
    base = (rf.multiply(42.5)
            .multiply(mo.multiply(-1).add(251).pow(-1).multiply(-100).exp())
            .multiply(rf.pow(-1).multiply(-6.93).exp().multiply(-1).add(1)))
    extra = mo.subtract(150).pow(2).multiply(0.0015).multiply(rf.sqrt())
    mw = mo.add(base).add(extra.multiply(mo.gt(150)))
    mo = mo.where(r.gt(0.5), mw.min(250))

    hh = h.divide(100)
    ed = (h.pow(0.679).multiply(0.942)
          .add(h.subtract(100).divide(10).exp().multiply(11))
          .add(t.multiply(-1).add(21.1).multiply(0.18)
               .multiply(h.multiply(-0.115).exp().multiply(-1).add(1))))
    ew = (h.pow(0.753).multiply(0.618)
          .add(h.subtract(100).divide(10).exp().multiply(10))
          .add(t.multiply(-1).add(21.1).multiply(0.18)
               .multiply(h.multiply(-0.115).exp().multiply(-1).add(1))))

    ko = (hh.pow(1.7).multiply(-1).add(1).multiply(0.424)
          .add(w.sqrt().multiply(0.0694).multiply(hh.pow(8).multiply(-1).add(1))))
    kd = ko.multiply(t.multiply(0.0365).exp()).multiply(0.581)
    m_dry = ed.add(mo.subtract(ed).multiply(ee.Image(10).pow(kd.multiply(-1))))

    h2 = h.multiply(-1).add(100).divide(100)
    kl = (h2.pow(1.7).multiply(-1).add(1).multiply(0.424)
          .add(w.sqrt().multiply(0.0694).multiply(h2.pow(8).multiply(-1).add(1))))
    kw = kl.multiply(t.multiply(0.0365).exp()).multiply(0.581)
    m_wet = ew.subtract(ew.subtract(mo).multiply(ee.Image(10).pow(kw.multiply(-1))))

    m = mo.where(mo.gt(ed), m_dry).where(mo.lt(ed).And(mo.lt(ew)), m_wet)
    return m.multiply(-1).add(250).multiply(59.5).divide(m.add(147.2)) \
        .clamp(0, 101).rename("FFMC")


def _dmc(dmc0, t, h, r, le):
    """Duff Moisture Code. Loosely-compacted organic layers, weeks-scale."""
    re = r.multiply(0.92).subtract(1.27).max(0)
    mo = dmc0.divide(-43.43).add(5.6348).exp().add(20)
    b = (dmc0.multiply(0.3).add(0.5).pow(-1).multiply(100)
         .where(dmc0.gt(33), dmc0.log().multiply(-1.3).add(14))
         .where(dmc0.gt(65), dmc0.log().multiply(6.2).subtract(17.2)))
    mr = mo.add(re.multiply(1000).divide(b.multiply(re).add(48.77)))
    pr = mr.subtract(20).log().multiply(-43.43).add(244.72).max(0)
    p0 = dmc0.where(r.gt(1.5), pr)

    tt = t.max(-1.1)
    k = tt.add(1.1).multiply(h.multiply(-1).add(100)).multiply(le).multiply(1e-4) \
        .multiply(1.894)
    return p0.add(k).max(0).rename("DMC")


def _dc(dc0, t, r, lf):
    """Drought Code. Deep compact organic matter, ~52-day time lag.

    This is the peat-relevant component: it tracks the slow drying that lets
    fire get below the surface, which is what makes Indonesian fires persistent
    and hard to extinguish.
    """
    rd = r.multiply(0.83).subtract(1.27).max(0)
    qo = dc0.divide(-400).exp().multiply(800)
    qr = qo.add(rd.multiply(3.937))
    dr = qr.pow(-1).multiply(800).log().multiply(400).max(0)
    d0 = dc0.where(r.gt(2.8), dr)

    v = t.max(-2.8).add(2.8).multiply(0.36).add(lf).max(0)
    return d0.add(v.multiply(0.5)).max(0).rename("DC")


def _isi(ffmc, w):
    """Initial Spread Index — how fast fire would run, given wind."""
    mo = ffmc.multiply(-1).add(101).multiply(147.2).divide(ffmc.add(59.5))
    ff = (mo.multiply(-0.1386).exp().multiply(91.9)
          .multiply(mo.pow(5.31).divide(4.93e7).add(1)))
    return w.multiply(0.05039).exp().multiply(0.208).multiply(ff).rename("ISI")


def _bui(dmc, dc):
    """Buildup Index — total fuel available, from the two moisture codes."""
    low = dmc.multiply(dc).multiply(0.8).divide(dmc.add(dc.multiply(0.4)))
    hi = dmc.subtract(
        dc.multiply(0.8).divide(dmc.add(dc.multiply(0.4))).multiply(-1).add(1)
        .multiply(dmc.multiply(0.0114).pow(1.7).add(0.92)))
    return low.where(dmc.gt(dc.multiply(0.4)), hi).max(0).rename("BUI")


def _fwi_final(isi, bui):
    """Fire Weather Index — the headline number."""
    fd = (bui.pow(0.809).multiply(0.626).add(2)
          .where(bui.gt(80),
                 bui.multiply(-0.023).exp().multiply(108.64).add(25)
                 .pow(-1).multiply(1000)))
    b = isi.multiply(fd).multiply(0.1)
    s = b.log().multiply(0.434).pow(0.647).multiply(2.72).exp()
    return b.where(b.gt(1), s).max(0).rename("FWI")


# ------------------------------------------------------- accumulation
def _day_factors(lat, days):
    """Per-day (Le, Lf) day-length factors, chosen by latitude.

    Decided once, client-side, so the choice can be reported in the output
    rather than buried in the server-side graph.
    """
    if abs(lat) < TROPIC:
        return ([DMC_LE_EQ] * len(days), [DC_LF_EQ] * len(days), "equatorial")
    return ([DMC_LE_N[d.month - 1] for d in days],
            [DC_LF_N[d.month - 1] for d in days], "Canadian 46N table")


def _accumulate(aoi, days, noon_h, le, lf):
    """Walk the days forward, carrying FFMC, DMC and DC.

    The codes are cumulative by definition, so this cannot be vectorised: each
    day is a function of the day before. ee.List.iterate keeps the whole chain
    server-side; doing it client-side would be one round trip per day.
    """
    import ee
    le_l, lf_l = ee.List(le), ee.List(lf)
    day_l = ee.List([d.isoformat() for d in days])

    init = ee.Dictionary({
        "ffmc": ee.Image.constant(FFMC_START).rename("FFMC").clip(aoi).toFloat(),
        "dmc": ee.Image.constant(DMC_START).rename("DMC").clip(aoi).toFloat(),
        "dc": ee.Image.constant(DC_START).rename("DC").clip(aoi).toFloat(),
    })

    def step(i, prev):
        i = ee.Number(i)
        prev = ee.Dictionary(prev)
        t, h, w, r = _noon_weather(aoi, ee.String(day_l.get(i)), noon_h)
        return ee.Dictionary({
            "ffmc": _ffmc(ee.Image(prev.get("ffmc")), t, h, w, r),
            "dmc": _dmc(ee.Image(prev.get("dmc")), t, h, r,
                        ee.Number(le_l.get(i))),
            "dc": _dc(ee.Image(prev.get("dc")), t, r, ee.Number(lf_l.get(i))),
            "w": w, "t": t, "h": h, "r": r})

    out = ee.Dictionary(ee.List.sequence(0, len(days) - 1).iterate(step, init))
    ffmc = ee.Image(out.get("ffmc"))
    dmc = ee.Image(out.get("dmc"))
    dc = ee.Image(out.get("dc"))
    isi = _isi(ffmc, ee.Image(out.get("w")))
    bui = _bui(dmc, dc)
    return {"FFMC": ffmc, "DMC": dmc, "DC": dc, "ISI": isi, "BUI": bui,
            "FWI": _fwi_final(isi, bui),
            "_wx": {"t": ee.Image(out.get("t")), "h": ee.Image(out.get("h")),
                    "w": ee.Image(out.get("w")), "r": ee.Image(out.get("r"))}}


def _mean(img, aoi, scale=ERA5_SCALE):
    import ee
    v = img.reduceRegion(ee.Reducer.mean(), aoi, scale, maxPixels=int(1e10),
                         bestEffort=True).values().get(0).getInfo()
    return round(v, 2) if v is not None else None


# A field this skewed is not described by its average. Calibrated on Ketapang,
# 20 October 2019: district DC 51 and "99% low danger", while fire concentrated
# in a pocket at DC 240 -- 4.7x the mean. Reporting the mean alone would have
# told a fire agency the district was safe on the most dangerous week tested.
SKEW_ALERT = 2.0


def _spread(img, aoi, scale=ERA5_SCALE):
    """Mean AND the upper tail. An area mean hides a dry pocket, and the pocket
    is where the fire goes."""
    import ee
    red = (ee.Reducer.mean()
           .combine(ee.Reducer.percentile([50, 90]), None, True)
           .combine(ee.Reducer.max(), None, True))
    got = img.reduceRegion(red, aoi, scale, maxPixels=int(1e10),
                           bestEffort=True).getInfo()
    out = {}
    for key, name in (("mean", "mean"), ("p50", "p50"), ("p90", "p90"),
                      ("max", "max")):
        v = next((v for k, v in got.items() if k.endswith(name)), None)
        out[key] = round(v, 2) if v is not None else None
    m, p90 = out["mean"], out["p90"]
    out["skew"] = round(p90 / m, 2) if m and p90 and m > 0 else None
    return out


def _pocket(img, aoi, p90, scale=ERA5_SCALE):
    """Where the driest tenth of the AOI actually is.

    A number the reader cannot locate is not actionable; this returns the
    centroid and extent of the area above the 90th percentile.
    """
    import ee
    if p90 is None:
        return None
    hot = img.gte(p90).selfMask()
    try:
        area = hot.multiply(ee.Image.pixelArea()).divide(1e4).reduceRegion(
            ee.Reducer.sum(), aoi, scale, maxPixels=int(1e10),
            bestEffort=True).values().get(0)
        cen = (hot.toInt().reduceToVectors(
            geometry=aoi, scale=scale, geometryType="polygon",
            maxPixels=int(1e10), bestEffort=True)
            .geometry().centroid(maxError=1000).coordinates())
        area, cen = ee.List([area, cen]).getInfo()
        if not cen:
            return None
        return {"threshold": p90, "area_ha": round(area or 0, 1),
                "centroid_lon": round(cen[0], 3), "centroid_lat": round(cen[1], 3)}
    except Exception:                                              # noqa: BLE001
        return None


def _class_image(fwi):
    """FWI as a 0-3 class code, on the Indonesia-adapted thresholds.

    Masked to where FWI actually exists. ERA5-Land is land-only, so starting
    from an unmasked constant silently files every sea pixel under the lowest
    class -- which reads as "half the area is at low danger" when in truth half
    the area is water.
    """
    import ee
    out = ee.Image(0)
    for i, (hi, _, _) in enumerate(FWI_CLASSES[:-1]):
        out = out.where(fwi.gte(hi), i + 1)
    return out.updateMask(fwi.mask()).rename("class").toByte()


def _class_areas(cls, aoi, lang):
    import ee
    labels = [_label(r, lang) for r in FWI_CLASSES]
    area = ee.Image.pixelArea().divide(1e4).addBands(cls)
    got = area.reduceRegion(
        ee.Reducer.sum().group(groupField=1, groupName="c"),
        aoi, ERA5_SCALE, maxPixels=int(1e10), bestEffort=True).getInfo()
    ha = {lb: 0.0 for lb in labels}
    for g in got.get("groups", []):
        i = int(g["c"])
        if 0 <= i < len(labels):
            ha[labels[i]] = round(g["sum"], 1)
    tot = sum(ha.values()) or 1.0
    return ha, {k: round(v / tot * 100, 1) for k, v in ha.items()}


# ------------------------------------------------------------- rendering
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


# Fixed display ranges, so two runs are comparable. Auto-scaling to each run's
# own data range made a harmless week render exactly as dramatically as a
# dangerous one -- fatal for a monitoring product, where the whole point is
# noticing that this week looks worse than last week. Upper bounds sit above
# the highest values measured over Indonesian conditions (DC 378, BUI 109,
# FWI 27); anything beyond is clamped and the map says so.
RAMPS = {
    "DC": ("Drought Code — kekeringan lapisan organik dalam (gambut)",
           ["#f7fcf5", "#e5f5e0", "#fee391", "#fe9929", "#d95f0e", "#7f2704"],
           (0, 400)),
    "BUI": ("Buildup Index — bahan bakar tersedia",
            ["#f7fbff", "#deebf7", "#fdd0a2", "#fd8d3c", "#d94801", "#7f2704"],
            (0, 120)),
    "FWI": ("Fire Weather Index — intensitas keseluruhan",
            ["#f7fcf5", "#c7e9c0", "#ffffb2", "#fd8d3c", "#e31a1c", "#800026"],
            (0, 40)),
}


def _overlays(ax, a, b, box, kind, vmin, spread, pocket):
    """Admin outlines and the dry pocket. Returns legend handles."""
    import numpy as np
    from matplotlib.lines import Line2D

    handles = []
    try:
        from .drought import _draw_admin
        _draw_admin(ax, list(box))
        handles.append(Line2D([], [], color="#333", lw=.55,
                              label="batas provinsi (FAO GAUL)"))
    except Exception as exc:                                       # noqa: BLE001
        print(f"  (admin boundaries skipped: {exc.__class__.__name__})")

    p90 = (spread or {}).get("p90")
    if p90 is not None and np.nanmax(a) > p90:
        ny, nx = a.shape
        xs = np.linspace(b.left, b.right, nx)
        ys = np.linspace(b.top, b.bottom, ny)
        ax.contour(xs, ys, np.nan_to_num(a, nan=vmin), levels=[p90],
                   colors="#0b3d91", linewidths=1.4, zorder=4)
        handles.append(Line2D([], [], color="#0b3d91", lw=1.4,
                              label=f"sepersepuluh terkering ({kind} ≥ {p90:g})"))
    if pocket:
        ax.plot(pocket["centroid_lon"], pocket["centroid_lat"], marker="x",
                ms=11, mew=2.2, color="#0b3d91", zorder=5)
        handles.append(Line2D([], [], ls="", marker="x", color="#0b3d91",
                              ms=9, mew=2,
                              label=f"pusat kantong kering "
                                    f"({pocket['area_ha']:,.0f} ha)"))
    return handles


def _render(run_dir, name, tif, box, meta, kind, lang, spread=None, pocket=None):
    """One code as a map: tiles, admin outlines, and the dry pocket marked.

    The pocket is drawn because it is what the run now leads with. Computing a
    p90 threshold, printing an alert about it and then shipping a map that does
    not show it leaves the one actionable thing in the text only.
    """
    import numpy as np
    import rasterio
    plt = _plt()
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.lines import Line2D

    with rasterio.open(tif) as src:
        a = src.read(1, masked=True).astype("float64").filled(np.nan)
        b = src.bounds
    if not np.isfinite(a).any():
        return None
    title, cols, (vmin, vmax) = RAMPS[kind]
    cmap = LinearSegmentedColormap.from_list(kind, cols)
    span_x, span_y = box[2] - box[0], box[3] - box[1]
    aspect = span_x / span_y if span_y else 1.0
    h = min(11.0, max(5.0, 10.0 / max(aspect, .4) + 2.2))
    fig, ax = plt.subplots(figsize=(10.5, h), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326",
                       source=cx.providers.CartoDB.Positron,
                       attribution_size=5, zorder=1)
    except Exception as exc:                                       # noqa: BLE001
        print(f"  (basemap skipped: {exc.__class__.__name__})")
    im = ax.imshow(np.ma.masked_invalid(a), cmap=cmap, vmin=vmin, vmax=vmax,
                   extent=[b.left, b.right, b.bottom, b.top],
                   interpolation="nearest", alpha=.78, zorder=2)
    cb = plt.colorbar(im, ax=ax, shrink=.72, extend="max")
    cb.set_label(f"{kind}  (skala tetap {vmin}–{vmax}, agar antar-pekan "
                 f"bisa dibandingkan)", fontsize=8.5)

    handles = _overlays(ax, a, b, box, kind, vmin, spread, pocket)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal", adjustable="box")
    for s in ax.spines.values():
        s.set_visible(False)
    if handles:
        ax.legend(handles=handles, fontsize=8, frameon=False,
                  loc="upper center", bbox_to_anchor=(.5, -.01), ncol=3)
    sub = f"{name} — {meta['date']} · akumulasi {meta['spinup']} hari · ERA5-Land 11 km"
    if spread and spread.get("skew"):
        sub += (f" · rerata {spread['mean']} · p90 {spread['p90']} "
                f"(timpang {spread['skew']:.1f}×)")
    ax.set_title(f"{title}\n{sub}", fontsize=11.5, fontweight="bold", loc="left")
    fig.text(.01, .015,
             "Sistem Fire Weather Index Kanada (Van Wagner 1987), dihitung dari "
             "ERA5-Land. Faktor panjang hari: " + meta["daylength"] + ". "
             "Ambang kelas FWI mengikuti adaptasi Indonesia (BMKG/ASEAN), bukan "
             "ambang boreal. Perlu kalibrasi lokal sebelum dipakai operasional. "
             "Peta dasar © CartoDB/OpenStreetMap.",
             fontsize=7.5, color="#777", wrap=True)
    fig.tight_layout(rect=[0, .09, 1, 1])
    out = os.path.join(run_dir, f"{name}_{kind.lower()}.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        end=None, admin=None, bbox=None, spinup=SPINUP_DAYS, lang="id"):
    """Fire danger rating (Canadian FWI System) from ERA5-Land weather."""
    import datetime as dt
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"fire-danger needs {mod}: "
                             "pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("fire-danger currently needs --backend gee (ERA5-Land).")
    if spinup < 30:
        raise SystemExit(
            f"--spinup {spinup} is too short. DC has a ~52-day time lag, so a "
            "shorter run reports the starting constant, not the site. Use 60+.")

    import ee
    from .gee_utils import initialize_ee, download_geotiff
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)

    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    cen = aoi.centroid(maxError=1000).coordinates().getInfo()
    clon, clat = cen[0], cen[1]

    # ERA5-Land lags ~6 days; default to its freshest complete day.
    if end:
        end_d = dt.date.fromisoformat(end)
    else:
        last = (ee.ImageCollection(ERA5_HOURLY).limit(1, "system:time_start", False)
                .first().get("system:time_start").getInfo())
        end_d = dt.datetime.fromtimestamp(last / 1000, dt.UTC).date() - dt.timedelta(days=1)
    days = [end_d - dt.timedelta(days=spinup - 1 - i) for i in range(spinup)]
    noon_h = _noon_utc_hour(clon)
    le, lf, dl_name = _day_factors(clat, days)

    print(f"  {name}: FWI to {end_d} · {spinup} days accumulation "
          f"(from {days[0]})")
    print(f"  noon = {noon_h:02d}:00 UTC at {clon:.2f}E · "
          f"day-length factors: {dl_name}")

    codes = _accumulate(aoi, days, noon_h, le, lf)
    idx = {k: _mean(codes[k], aoi) for k in ("FFMC", "DMC", "ISI")}
    spread = {k: _spread(codes[k], aoi) for k in ("DC", "BUI", "FWI")}
    idx.update({k: v["mean"] for k, v in spread.items()})
    pocket = _pocket(codes["DC"], aoi, spread["DC"]["p90"])
    cls = _class_image(codes["FWI"]).clip(aoi)
    ha, pct = _class_areas(cls, aoi, lang)

    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    box = [min(xs), min(ys), max(xs), max(ys)]
    meta = {"date": end_d.isoformat(), "spinup": spinup, "daylength": dl_name}

    maps = {}
    for kind in ("DC", "BUI", "FWI"):
        tif = os.path.join(run_dir, f"{name}_{kind.lower()}.tif")
        got = download_geotiff(codes[kind].clip(aoi).toFloat(), coords, tif,
                               scale=ERA5_SCALE)
        if got:
            png = _render(run_dir, name, got, box, meta, kind, lang,
                          spread=spread[kind],
                          pocket=pocket if kind == "DC" else None)
            maps[kind] = {"map": os.path.basename(png) if png else None,
                          "geotiff": os.path.basename(got)}

    stats = {
        "run_id": run_id, "scenario": "fire-danger", "name": name,
        "date": end_d.isoformat(), "spinup_days": spinup,
        "accumulated_from": days[0].isoformat(),
        "noon_utc_hour": noon_h, "daylength_factors": dl_name,
        "indices": idx, "spread": spread, "dry_pocket": pocket,
        "skewed": bool(spread["DC"]["skew"] and
                       spread["DC"]["skew"] >= SKEW_ALERT),
        "fwi_class_ha": ha, "fwi_class_pct": pct,
        "sources": {"weather": f"ERA5-Land hourly ({ERA5_HOURLY}), {ERA5_SCALE} m",
                    "system": "Canadian Forest Fire Weather Index, "
                              "Van Wagner (1987) / Van Wagner & Pickett (1985)"},
        "outputs": maps,
        "note": ("DC and BUI lead here, not FWI. FWI weights wind-driven spread "
                 "(via ISI), which is what matters in boreal forest; Indonesian "
                 "peat fire is driven by deep drying, which is what DC tracks. "
                 "FWI class thresholds follow the Indonesian adaptation "
                 "(BMKG/ASEAN), not the Canadian ones. Validate locally before "
                 "operational use: ERA5-Land is 11 km and smooths local weather, "
                 "and it lags ~6 days -- which barely affects DC (52-day time "
                 "lag) but does affect FFMC and ISI."),
    }
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    _print_summary(name, end_d, idx, spread, pocket, pct)
    return stats


def _print_summary(name, end_d, idx, spread, pocket, pct):
    """Report the upper tail beside the mean, always.

    An area mean is the wrong summary for a skewed field, and this one is
    routinely skewed. Ketapang on 20 October 2019 read DC 51 and "99% low
    danger" while fire concentrated in a pocket at DC 240; the mean alone would
    have called the most dangerous week of the three tested safe.
    """
    print(f"\n{name} — {end_d}")
    print(f"  {'':4s} {'rerata':>9s} {'p90':>9s} {'maks':>9s}   ")
    for code, note in (("DC", "lapisan dalam / gambut"),
                       ("BUI", "bahan bakar tersedia"),
                       ("FWI", "indeks keseluruhan")):
        s = spread[code]
        print(f"  {code:4s} {s['mean']:>9} {s['p90']:>9} {s['max']:>9}   {note}")
    print(f"  FFMC {idx['FFMC']:>7}  ISI {idx['ISI']:>7}  DMC {idx['DMC']:>7}")
    print("  kelas FWI: " + " · ".join(
        f"{k} {v:.0f}%" for k, v in pct.items() if v > 0))

    skew = spread["DC"]["skew"]
    if skew and skew >= SKEW_ALERT:
        print(f"\n  PERHATIAN: sebaran DC sangat timpang (p90 {skew:.1f}x rerata).")
        print(f"  Rerata wilayah TIDAK mewakili kondisi: sepersepuluh terkering "
              f"berada di DC >= {spread['DC']['p90']}, sementara rerata "
              f"{spread['DC']['mean']}.")
        if pocket:
            print(f"  Kantong kering: {pocket['area_ha']:,.0f} ha, pusat di "
                  f"{pocket['centroid_lat']:.3f}, {pocket['centroid_lon']:.3f}")
        print("  Justru pekan seperti ini yang paling menipu: ringkasan wilayah "
              "terlihat aman.")
    elif pocket:
        print(f"\n  Sepersepuluh terkering: DC >= {spread['DC']['p90']}, "
              f"{pocket['area_ha']:,.0f} ha, pusat di "
              f"{pocket['centroid_lat']:.3f}, {pocket['centroid_lon']:.3f}")
