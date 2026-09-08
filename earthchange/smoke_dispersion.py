#!/usr/bin/env python3
"""Where the smoke actually goes, and how much of it — HYSPLIT dispersion.

smoke-track draws trajectories and says, correctly, that a line crossing a
town is not the same as smoke landing on it: a trajectory has no width, no
settling and no concentration. This scenario runs the model that does. HYSPLIT
releases mass over a duration, disperses it, and reports a concentration field
averaged through a layer -- which is the quantity anyone downwind is actually
asking about.

WHAT THE NUMBERS MEAN, AND WHAT THEY DO NOT.

By default the release is one unit of mass per hour of an inert tracer with no
deposition. That makes the field RELATIVE: it says where the plume goes and
how sharply it thins, not how many micrograms are in the air. This is
deliberate. Turning a fire into an emission rate needs burned area, fuel load,
combustion completeness and an emission factor, each carrying its own factor
of two, and a plot labelled ug/m3 built on four guesses is worse than one
labelled "relative concentration" built on none. Pass --emission-rate when a
real inventory exists, and the axis relabels itself.

Three limits worth stating on the figure rather than in a footnote:

  GDAS1 is 1 degree and 3-hourly. A sea breeze, a valley channel and a
  convective downdraft are all below that. Over Sumatra and Kalimantan this
  smooths the diurnal reversal that decides whether smoke sits on a city
  overnight or leaves.

  Plume rise is not modelled. Release heights are prescribed. A hot flaming
  front lofts far higher than a smouldering peat fire, and the difference
  changes the direction of travel, not just the height.

  The vertical average is exactly what is asked for. A layer of 0-10000 m
  dilutes a shallow nocturnal plume across ten kilometres of mostly clean air.
  For surface exposure use a shallow top -- --layer-top 500 is closer to what
  a person breathes.

Backend: none. HYSPLIT and GDAS1 are fetched independently of GEE/MPC.
"""

import datetime as dt
import json
import math
import os

from . import hysplit

# Log-decade classes, the convention every HYSPLIT concentration plot uses:
# half-decade steps so a plume spanning four orders of magnitude stays legible.
# Colours run cool-to-hot in the same order NOAA's do, because people read
# these against published plots and a reversed ramp is a real misreading risk.
CLASS_COLOURS = ["#cfc4de", "#00c000", "#0000ff", "#ffff00", "#ff8000",
                 "#ff0000"]

DEFAULT_LEVELS = (0, 10000)
DEFAULT_HOURS = 24
DEFAULT_DURATION = 1.0


def _decades(vmax, n=6):
    """Half-decade thresholds below the maximum, largest last.

    Anchored on the data rather than fixed: a run whose peak is 1e-10 and one
    whose peak is 1e-3 both want six readable classes, and hardcoded bounds
    give one of them an empty legend.
    """
    if not (vmax > 0) or not math.isfinite(vmax):
        return []
    top = math.floor(math.log10(vmax) * 2) / 2.0     # snap to half a decade
    return [10.0 ** (top - 0.5 * i) for i in range(n - 1, -1, -1)]


def average_layer(grids, meta, level_top, pollutant=None):
    """Time-integrated mean concentration in one layer, as a 2-D list.

    HYSPLIT emits one plane per sampling interval; the published plots show
    the average across the whole run, which is what "Integrated from ... to
    ..." in their title block means. Level 0 is skipped: it is the deposition
    accumulation surface, not a height, and averaging it into a concentration
    would mix two different quantities with different units.
    """
    keep = [g for g in grids
            if g["level"] == level_top and g["level"] != 0
            and (pollutant is None or g["pollutant"] == pollutant)]
    if not keep:
        have = sorted({g["level"] for g in grids})
        raise SystemExit(
            f"no concentration planes at level {level_top} m; the run wrote "
            f"levels {have}. Pass --layer-top with one of those.")
    nlat, nlon = meta["nlat"], meta["nlon"]
    acc = [[0.0] * nlon for _ in range(nlat)]
    for g in keep:
        for j in range(nlat):
            row, out = g["data"][j], acc[j]
            for i in range(nlon):
                out[i] += row[i]
    n = float(len(keep))
    for j in range(nlat):
        acc[j] = [v / n for v in acc[j]]
    return acc, len(keep)


def crop_to_plume(field, meta, pad_deg=2.0, floor_frac=1e-6):
    """Trim the grid to where there is anything, plus a margin.

    A 601x601 grid spanning 30 degrees around a source produces a figure that
    is almost entirely empty, and the plume becomes a speck. Cropping to the
    non-zero extent is what makes the map readable -- and doing it from the
    data rather than a fixed box means a run that goes 800 km still fits.
    """
    nlat, nlon = meta["nlat"], meta["nlon"]
    vmax = max((v for row in field for v in row), default=0.0)
    if vmax <= 0:
        return None
    thr = vmax * floor_frac
    js = [j for j in range(nlat) if any(v > thr for v in field[j])]
    is_ = [i for i in range(nlon)
           if any(field[j][i] > thr for j in range(nlat))]
    if not js or not is_:
        return None
    padj = int(round(pad_deg / meta["dlat"]))
    padi = int(round(pad_deg / meta["dlon"]))
    j0, j1 = max(0, min(js) - padj), min(nlat - 1, max(js) + padj)
    i0, i1 = max(0, min(is_) - padi), min(nlon - 1, max(is_) + padi)
    return (i0, i1, j0, j1)


def run(backend, lat, lon, radius_km, name, run_dir, run_id, *,
        day=None, hours=DEFAULT_HOURS, heights=(10.0,),
        duration=DEFAULT_DURATION, rate=1.0, rate_units=None,
        layer_top=10000, sample_hours=1, spacing=0.05, span=None,
        hysplit_bin=None, met_cache=None, met_product="gdas1",
        lang="id", **_ignored):
    """Run a HYSPLIT dispersion and write the concentration map.

    backend is accepted and ignored: this scenario touches neither GEE nor
    MPC. It is in the signature so detect.py can dispatch it like every other
    scenario rather than special-casing it.
    """
    binary = hysplit.find_binary(hysplit_bin, kind="concentration")
    if not binary:
        raise SystemExit(hysplit.INSTALL_HELP.replace(
            "hyts_std", "hycs_std").replace("smoke-track --engine hysplit",
                                            "smoke-dispersion"))

    start = dt.datetime.combine(
        dt.date.fromisoformat(str(day)) if day else dt.date.today(),
        dt.time(0), tzinfo=dt.UTC)
    hours = int(hours)

    spec = hysplit.MET_PRODUCTS.get(met_product)
    if spec is None:
        raise SystemExit(f"unknown --met-product {met_product!r}; have "
                         f"{', '.join(sorted(hysplit.MET_PRODUCTS))}")
    if spec["forecast"]:
        # Say it before the download, not after the model refuses: the public
        # HYSPLIT build is licensed for dispersion on ANALYSIS meteorology
        # only, and this is the one place that restriction can bite.
        print(f"  note: {met_product} is a forecast product. The unregistered "
              f"HYSPLIT build may refuse dispersion on it; if it does, "
              f"register at ready.noaa.gov or use --met-product gdas1 once "
              f"ARL publishes the week.")

    cache = met_cache or os.path.join(run_dir, "met")
    keys = hysplit.met_keys(start, hours, "forward", product=met_product)
    print(f"  meteorology: {met_product} ({spec['res']}), "
          f"{len(keys)} file(s), ~{len(keys) * spec['size_mib'] / 1024:.1f} "
          f"GiB if uncached")
    met_paths = hysplit.fetch_met(keys, cache, hours=hours,
                                  direction="forward")

    if span is None:
        # Wide enough that a 24 h plume at 10 m/s (about 8 degrees) stays
        # inside, without making the grid so large the run crawls.
        deg = max(6.0, min(30.0, 0.35 * hours))
        span = (deg, deg)

    points = [(lat, lon, float(h)) for h in heights]
    work = os.path.join(run_dir, "hysplit_conc")
    grids, meta = hysplit.run_concentration(
        binary, start, points, hours, met_paths, work,
        rate=rate, duration=duration, pollutant="SMOK",
        spacing=(spacing, spacing), span=span,
        levels=(0, int(layer_top)), sample_hours=sample_hours)

    # The grid is centred on the source by construction, so this is a free
    # check that the header was read with the right cell convention. Half a
    # cell of error is invisible on a 30-degree map and moves a plume 3 km,
    # which is the sort of thing that survives review.
    cx = meta["lon0"] + (meta["nlon"] - 1) / 2.0 * meta["dlon"]
    cy = meta["lat0"] + (meta["nlat"] - 1) / 2.0 * meta["dlat"]
    if max(abs(cx - lon), abs(cy - lat)) > 0.51 * max(meta["dlon"],
                                                     meta["dlat"]):
        print(f"  WARNING: grid centre ({cx:.4f}, {cy:.4f}) is not the source "
              f"({lon:.4f}, {lat:.4f}). The cdump georeference is not what "
              f"this code assumes; treat positions with suspicion.")

    field, nsamp = average_layer(grids, meta, int(layer_top))
    vmax = max((v for row in field for v in row), default=0.0)
    nz = [v for row in field for v in row if v > 0]
    vmin = min(nz) if nz else 0.0
    if vmax <= 0:
        raise SystemExit(
            "The dispersion produced no non-zero concentration anywhere. "
            "Usually this means the sampling window missed the release: "
            "check --date against the meteorology span.")

    fig_path = os.path.join(run_dir, f"{run_id}_dispersion.png")
    _plot(field, meta, lat, lon, start, hours, layer_top, vmax, vmin,
          nsamp, heights, duration, rate, rate_units, fig_path, name, lang,
          met_product, spec)

    stats = {"source": {"lat": lat, "lon": lon,
                        "heights_m_agl": list(heights)},
             "start_utc": start.isoformat(), "run_hours": hours,
             "release_hours": duration,
             "emission_rate": rate,
             "emission_units": rate_units or "unit mass/hour (relative)",
             "layer_m": [0, int(layer_top)],
             "samples_averaged": nsamp,
             "grid": {"nlat": meta["nlat"], "nlon": meta["nlon"],
                      "d_deg": meta["dlat"],
                      "lat0": meta["lat0"], "lon0": meta["lon0"]},
             "max": vmax, "min_nonzero": vmin,
             "meteorology": f"{met_product} — {spec['res']} (NOAA ARL)",
             "met_is_forecast": spec["forecast"],
             "met_files": [os.path.basename(p) for p in met_paths],
             "model": os.path.basename(binary)}
    with open(os.path.join(run_dir, f"{run_id}_dispersion.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"  wrote {fig_path}")
    return {"figure": fig_path, "stats": stats}


def _plot(field, meta, slat, slon, start, hours, layer_top, vmax, vmin,
          nsamp, heights, duration, rate, rate_units, out, name, lang,
          met_product="gdas1", met_spec=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import BoundaryNorm, ListedColormap

    arr = np.asarray(field, dtype="float64")
    box = crop_to_plume(field, meta)
    if box:
        i0, i1, j0, j1 = box
        arr = arr[j0:j1 + 1, i0:i1 + 1]
    else:
        i0, j0 = 0, 0
    # meta lat0/lon0 are the CENTRE of the lower-left cell, not the grid edge.
    # HYSPLIT proves it: it centres the grid on the source, and
    #     lon0 + (nlon-1)/2 * dlon  ==  source longitude, exactly.
    # imshow's extent wants the outer EDGES, so half a cell comes off each
    # side. Treating the centre as an edge drew the whole field 0.025 deg
    # (~2.8 km) northeast of the truth while the source star, plotted from its
    # own coordinates, stayed put -- so the plume appeared detached from the
    # vent that produced it.
    half_x, half_y = meta["dlon"] / 2.0, meta["dlat"] / 2.0
    left = meta["lon0"] - half_x + i0 * meta["dlon"]
    bottom = meta["lat0"] - half_y + j0 * meta["dlat"]
    extent = [left, left + arr.shape[1] * meta["dlon"],
              bottom, bottom + arr.shape[0] * meta["dlat"]]

    bounds = _decades(vmax)
    cmap = ListedColormap(CLASS_COLOURS[:len(bounds) - 1])
    cmap.set_under((0, 0, 0, 0))                    # below the lowest class
    norm = BoundaryNorm(bounds, cmap.N)

    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        proj = ccrs.PlateCarree()
        fig = plt.figure(figsize=(11, 8.2))
        ax = fig.add_axes([0.06, 0.09, 0.64, 0.79], projection=proj)
        ax.set_extent(extent, crs=proj)
        # Coastline detail from the domain, not fixed. At 50 m the Krakatau
        # island group is not drawn at all, so a source sitting on it appeared
        # to float in open water beside Sumatra -- the map made a correct
        # position look wrong. Small volcanic islands are exactly the sources
        # this scenario is pointed at, so a regional domain gets 10 m.
        span_deg = max(extent[1] - extent[0], extent[3] - extent[2])
        scale = "10m" if span_deg <= 15 else "50m"
        ax.add_feature(cfeature.LAND.with_scale(scale), fc="#f4f2ee",
                       zorder=0)
        ax.add_feature(cfeature.OCEAN.with_scale(scale), fc="#dce8f0",
                       zorder=0)
        ax.add_feature(cfeature.COASTLINE.with_scale(scale), lw=.7,
                       ec="#4a5560", zorder=3)
        ax.add_feature(cfeature.BORDERS.with_scale(scale), lw=.5,
                       ec="#8a949e", ls=":", zorder=3)
        gl = ax.gridlines(draw_labels=True, lw=.5, color="#9fb3c8",
                          alpha=.6, ls=":")
        gl.top_labels = gl.right_labels = False
        kw = {"transform": proj}
    except Exception:                                    # noqa: BLE001
        # cartopy is optional; a bare axes still carries the science, it just
        # loses the coastline. Better than refusing to draw.
        fig = plt.figure(figsize=(11, 8.2))
        ax = fig.add_axes([0.06, 0.09, 0.64, 0.79])
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.grid(alpha=.3, ls=":")
        kw = {}

    # origin="lower": HYSPLIT's lat0 is the LOWER-LEFT corner, so row 0 is the
    # southernmost. Rendering upper-origin flips the plume across the source.
    ax.imshow(arr, origin="lower", extent=extent, cmap=cmap, norm=norm,
              interpolation="nearest", zorder=2, **kw)
    ax.plot(slon, slat, "*", ms=17, mfc="#111", mec="white", mew=1.2,
            zorder=5, **kw)

    stop = start + dt.timedelta(hours=hours)
    unit = rate_units or "unit mass"
    conc_unit = f"{unit}/m3" if rate_units else "relative"

    # fig.text, not ax.set_title: on cartopy 0.25 with matplotlib 3.11 a
    # GeoAxes title silently does not render -- the artist is created and
    # carries the text, and nothing appears. Reproduced in six lines, so it is
    # the pairing rather than anything here. Figure coordinates also place the
    # header better against a fixed add_axes rect.
    fig.text(0.06, 0.965, f"{name} — HYSPLIT dispersion", fontsize=14,
             weight="bold", va="top")
    fig.text(0.06, 0.925,
             f"Concentration averaged 0–{int(layer_top)} m AGL, integrated "
             f"{start:%d %b %Y %H:%M} → {stop:%d %b %H:%M} UTC",
             fontsize=10.5, color="#42505e", va="top")

    # Legend panel, laid out like the published plots people compare against.
    lax = fig.add_axes([0.72, 0.09, 0.26, 0.79])
    lax.axis("off")
    y = 0.97
    lax.text(0, y, "Concentration", fontsize=10.5, weight="bold", va="top")
    y -= 0.05
    lax.text(0, y, f"({conc_unit})", fontsize=9, color="#5c6674", va="top")
    y -= 0.06
    for k in range(len(bounds) - 2, -1, -1):
        lax.add_patch(plt.Rectangle((0, y - 0.038), 0.16, 0.038,
                                    fc=CLASS_COLOURS[k], ec="#333", lw=.5,
                                    transform=lax.transAxes))
        lax.text(0.20, y - 0.019, f"> {bounds[k]:.1E}", fontsize=9,
                 va="center", family="monospace")
        y -= 0.046

    y -= 0.03
    for label, val in (("Maximum", vmax), ("Minimum", vmin)):
        lax.text(0, y, f"{label}: {val:.1E}", fontsize=8.5, va="top",
                 family="monospace")
        y -= 0.035

    y -= 0.02
    hs = ", ".join(f"{h:g}" for h in heights)
    res = (met_spec or {}).get("res", "")
    for line in (f"Release: {duration:g} h at {hs} m AGL",
                 f"Rate: {rate:g} {unit}/h",
                 f"Averaged over {nsamp} sampling steps",
                 f"Meteorology: {met_product} {res}"):
        lax.text(0, y, line, fontsize=8, color="#5c6674", va="top")
        y -= 0.032

    caveat = (
        f"{met_product} {res}: angin darat-laut dan aliran lembah mungkin tidak "
        "terselesaikan. "
        "Tanpa plume rise — ketinggian pelepasan ditentukan, bukan dihitung. "
        "Rata-rata 0–{top} m mengencerkan asap dangkal; untuk paparan permukaan "
        "gunakan lapisan lebih tipis."
        if lang == "id" else
        f"{met_product} {res}: sea breeze and valley flow may be unresolved. "
        "No plume rise — release heights are prescribed, not computed. A "
        "0–{top} m mean dilutes a shallow plume; for surface exposure use a "
        "thinner layer.")
    if (met_spec or {}).get("forecast"):
        caveat += (" Meteorologi prakiraan, bukan analisis."
                   if lang == "id" else
                   " Forecast meteorology, not analysis.")
    if not rate_units:
        caveat += (" Laju emisi = 1 satuan massa/jam: medan ini RELATIF, bukan "
                   "µg/m³." if lang == "id" else
                   " Emission is 1 unit mass/h: this field is RELATIVE, not "
                   "µg/m³.")
    fig.text(0.06, 0.045, caveat.format(top=int(layer_top)), fontsize=7.6,
             color="#5c6674", wrap=True, va="top")

    fig.savefig(out, dpi=140, facecolor="white")
    plt.close(fig)
