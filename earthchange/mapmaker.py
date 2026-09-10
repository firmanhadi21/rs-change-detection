#!/usr/bin/env python3
"""Compose a value-added cartographic map from a change-detection GeoTIFF.

Produces an A4-landscape map sheet (PDF + PNG) with:
  * the change layer on its own, opaque -- no tiles under it: it already
    covers the AOI, and anything underneath only muddies the data
  * title / subtitle
  * legend (colorbar or SIRAD RGB key)
  * statistics panel (from the stats dict)
  * location overview inset (Esri Light Gray Canvas, wide)
  * ESRI Satellite inset (same AOI as the main map, no overlay)
  * coordinate grid, scale bar, north arrow
  * data-source / date footer

Used by detect.py (--map) and by make_map.py (re-render an existing result).
Dependencies: matplotlib, rasterio, contextily (inset tiles need internet).
"""

import os
import textwrap
from datetime import datetime

# Remove a stale external PROJ override (e.g. an OTB install exporting PROJ_LIB)
# so rasterio and pyproj each use their OWN bundled PROJ. Do NOT set a shared
# PROJ_DATA — rasterio's PROJ (v6+) can't read pyproj's older database layout.
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle, FancyArrow
import matplotlib.font_manager as fm  # noqa: F401  (ensures fonts load)
import rasterio

from . import LIGHT_BASEMAP

try:
    import contextily as cx
    from . import identify_to_tile_servers
    identify_to_tile_servers(cx)
    _HAS_CX = True
except Exception:  # noqa: BLE001
    _HAS_CX = False

A4_LANDSCAPE = (11.69, 8.27)  # inches
OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def _cmap(palette):
    cols = ["#" + c.lstrip("#") for c in palette]
    if len(cols) == 1:  # a single-colour palette (e.g. flood) must span 0->1
        cols = cols * 2
    return LinearSegmentedColormap.from_list("scenario", cols)


def _fmt_lon(x, _=None):
    return f"{abs(x):.2f}°{'E' if x >= 0 else 'W'}"


def _fmt_lat(y, _=None):
    return f"{abs(y):.2f}°{'N' if y >= 0 else 'S'}"


def _nice_km(width_km):
    """Largest 'nice' scale-bar length <= ~40% of map width."""
    target = width_km * 0.4
    for v in (0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200):
        if v > target:
            break
        nice = v
    return locals().get("nice", 0.5)


_CX_WARNED = False


def _tiles(ax, source, what, fallback=True):
    """Draw basemap tiles, and say plainly when it cannot be done.

    Silence is expensive here. A missing contextily or a blocked tile host
    leaves a blank white box, which reads as a rendering bug rather than as a
    missing dependency — and the insets use different tile hosts from the main
    map, so one can go dark while the other still works.

    Returns the name of what was actually drawn, or None.
    """
    global _CX_WARNED
    if not _HAS_CX:
        if not _CX_WARNED:
            print("  NOTE: contextily is not installed, so no basemap tiles can "
                  "be drawn — the main map and both insets get blank\n"
                  "        backgrounds. Fix: pip install 'earthchange[maps]'")
            _CX_WARNED = True
        return None
    tried = [(source, None)]
    if fallback and source is not OSM:
        tried.append((OSM, "OpenStreetMap"))
    last = None
    for src, label in tried:
        try:
            cx.add_basemap(ax, crs="EPSG:4326", source=src, attribution=False)
            if label:
                print(f"  ({what}: usual provider unavailable, used {label})")
            return label or "provider"
        except Exception as e:  # noqa: BLE001 — try the fallback, then report
            last = e
    print(f"  ({what}: no basemap — {last.__class__.__name__}: {str(last)[:70]})")
    return None


def _add_basemap(ax, source=OSM):
    return _tiles(ax, source, "main map")


def _read_raster(tif):
    with rasterio.open(tif) as src:
        arr = src.read(masked=True)
        b = src.bounds
    extent = [b.left, b.right, b.bottom, b.top]
    return arr, extent


def _draw_scalebar(ax, extent, lat):
    minlon, maxlon, minlat, maxlat = extent
    km_per_deg = 111.320 * np.cos(np.radians(lat))
    width_km = (maxlon - minlon) * km_per_deg
    bar_km = _nice_km(width_km)
    bar_deg = bar_km / km_per_deg
    x0 = minlon + (maxlon - minlon) * 0.05
    y0 = minlat + (maxlat - minlat) * 0.05
    h = (maxlat - minlat) * 0.012
    ax.add_patch(Rectangle((x0, y0), bar_deg, h, facecolor="black",
                           edgecolor="black", zorder=6))
    ax.add_patch(Rectangle((x0 + bar_deg / 2, y0), bar_deg / 2, h,
                           facecolor="white", edgecolor="black", zorder=6))
    ax.text(x0, y0 + h * 1.6, "0", ha="center", va="bottom", fontsize=7, zorder=6)
    ax.text(x0 + bar_deg, y0 + h * 1.6, f"{bar_km:g} km", ha="center",
            va="bottom", fontsize=7, zorder=6)


def _draw_north(ax):
    ax.annotate("N", xy=(0.94, 0.93), xytext=(0.94, 0.82),
                xycoords="axes fraction", textcoords="axes fraction",
                ha="center", va="center", fontsize=12, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", facecolor="black", lw=1.8),
                zorder=7)


def _location_inset(fig, rect, lon, lat, span=7.0, tiles=True):
    """Returns what _tiles drew ("provider", a fallback name, or None)."""
    ax = fig.add_axes(rect)
    ax.set_xlim(lon - span, lon + span)
    ax.set_ylim(lat - span, lat + span)
    ax.set_xticks([]); ax.set_yticks([])
    drawn = _tiles(ax, LIGHT_BASEMAP, "location inset") if tiles else None
    ax.plot(lon, lat, marker="*", markersize=15, color="red",
            markeredgecolor="white", markeredgewidth=0.8, zorder=8)
    ax.set_title("Lokasi", fontsize=8)
    for s in ax.spines.values():
        s.set_edgecolor("#888")
    return drawn


def _satellite_inset(fig, rect, extent, tiles=True):
    """ESRI Satellite close-up of the same AOI as the main map.

    `extent` is [minlon, maxlon, minlat, maxlat] (matches the main map).
    No change layer, no AOI rectangle — just the satellite basemap underneath.
    Returns what _tiles drew ("provider", a fallback name, or None).
    """
    ax = fig.add_axes(rect)
    minlon, maxlon, minlat, maxlat = extent
    ax.set_xlim(minlon, maxlon)
    ax.set_ylim(minlat, maxlat)
    ax.set_xticks([]); ax.set_yticks([])
    drawn = (_tiles(ax, cx.providers.Esri.WorldImagery if _HAS_CX else OSM,
                    "satellite inset") if tiles else None)
    # Title what was actually drawn: an OSM fallback here is better than a
    # blank box, but labelling street tiles "Satelit (ESRI)" would be a lie.
    ax.set_title("Satelit (ESRI)" if drawn == "provider"
                 else ("Peta dasar (OSM)" if drawn else "Basemap tidak tersedia"),
                 fontsize=8)
    for s in ax.spines.values():
        s.set_edgecolor("#888")
    return drawn


def _stats_lines(meta, both=False):
    """Human-readable statistics lines from meta['stats'].

    A mining run's stats hold both legs, SIRAD and NDVI. A single-product sheet
    lists only its own leg -- the SIRAD sheet used to show the NDVI metric,
    mean and affected area, as if they were the radar's. `both` is for the
    side-by-side sheet, which shows the two products and so both legs.
    """
    s = meta.get("stats", {})
    lines = []

    def opt(res):
        d = res.get("direction", "")
        m = res.get("metric", "")
        out = [f"Metrik: {m} (arah: {d})"]
        if res.get("mean") is not None:
            out.append(f"Rerata Δ: {res['mean']:+.3f}")
        if "pct_affected" in res:
            out.append(f"Area terdampak: {res['pct_affected']:.1f}%")
        for k in ("pct_severe", "pct_strong"):
            if k in res:
                out.append(f"  ({'berat' if k=='pct_severe' else 'kuat'}): {res[k]:.1f}%")
        if "scenes_pre" in res:
            out.append(f"Scene pre/post: {res['scenes_pre']}/{res['scenes_post']}")
        return out

    if "pct_new_builtup" in s:  # urban-trend
        lines += [f"Metode: {s.get('method', 'NDBI trend')}",
                  f"Built-up epoch-1: {s['pct_builtup_first']:.1f}%",
                  f"Built-up epoch-3: {s['pct_builtup_last']:.1f}%",
                  f"Built-up baru: {s['pct_new_builtup']:.1f}%",
                  f"Scene/epoch: {s.get('scenes_per_epoch', '-')}"]
    elif "pct_flooded" in s:  # flood
        masked = s.get("pct_permanent_water", s.get("pct_water_masked", 0))
        lines += [f"Metode: {s.get('method','SAR')}",
                  f"Tergenang: {s['pct_flooded']:.1f}%",
                  f"Air/laut di-mask: {masked:.1f}%",
                  f"Orbit: {s.get('orbit','-')} (track {s.get('relative_orbit','-')})"]
        if s.get("date_pre"):
            lines.append(f"Citra pra/pasca: {s['date_pre']} → {s['date_post']}")
        else:
            lines.append(f"Scene pre/post: {s.get('scenes_pre','-')}/{s.get('scenes_post','-')}")
    elif "pct_disturbed" in s:  # disturbance (SAR VH change)
        lines += [f"Metode: {s.get('method','SAR VH')}",
                  f"Terganggu: {s['pct_disturbed']:.1f}%",
                  f"  (berat): {s.get('pct_severe', 0):.1f}%"]
        if s.get("pct_landslide_like") is not None:
            lines += [f"Mirip longsor (lereng): {s['pct_landslide_like']:.1f}%",
                      f"Mirip endapan (datar): {s['pct_sediment_flat']:.1f}%"]
        lines.append(f"Orbit: {s.get('orbit','-')} (track {s.get('relative_orbit','-')})")
        if s.get("date_pre"):
            lines.append(f"Citra pra/pasca: {s['date_pre']} → {s['date_post']}")
    elif "sirad" in s and "ndvi" in s:  # mining (2 products)
        if both or meta.get("is_rgb"):
            lines += [f"SIRAD orbit: {s['sirad'].get('orbit','-')}",
                      f"Citra/periode: {s['sirad'].get('images_per_period','-')}"]
        if both or not meta.get("is_rgb"):
            lines += opt(s["ndvi"])
    elif "metric" in s:  # single optical
        lines += opt(s)
    else:  # sirad-only
        lines += [f"Metode: {s.get('method','-')}",
                  f"Orbit: {s.get('orbit','-')}",
                  f"Citra/periode: {s.get('images_per_period','-')}"]
    return lines


def render_map(meta, out_base, basemap="osm"):
    """Render the map sheet. meta describes one product; writes PDF + PNG.

    `basemap` no longer puts tiles under the main map -- the product is a GEE
    raster covering the whole AOI, so tiles there were never seen except as
    noise through a semi-transparent layer. "none" still means no tiles at all,
    so the insets stay blank and nothing is fetched (e.g. offline).
    """
    lat, lon = meta["lat"], meta["lon"]

    fig = plt.figure(figsize=A4_LANDSCAPE, dpi=150)
    fig.patch.set_facecolor("white")

    # --- main map ---
    ax = fig.add_axes([0.045, 0.09, 0.60, 0.80])
    im, extent = _draw_product(ax, meta)
    is_rgb = meta.get("is_rgb")

    # --- title / subtitle ---
    fig.text(0.045, 0.955, meta["label"], fontsize=16, fontweight="bold")
    fig.text(0.045, 0.925, _subtitle(meta), fontsize=9, color="#333")

    # --- legend (colorbar or RGB key) ---
    lg = fig.add_axes([0.68, 0.72, 0.29, 0.16])
    lg.axis("off")
    lg.text(0, 1.0, "Legenda", fontsize=11, fontweight="bold", va="top")
    if is_rgb:
        for i, (c, txt) in enumerate(SIRAD_KEYS):
            lg.add_patch(Rectangle((0.02, 0.6 - i * 0.22), 0.06, 0.12,
                                   facecolor=c, transform=lg.transAxes))
            lg.text(0.11, 0.66 - i * 0.22, txt, fontsize=8, va="center",
                    transform=lg.transAxes)
    else:
        # At 0.70 the ticks and label ran into the "Statistik" heading (top
        # 0.68); 0.79 sits in the legend box, clear of both.
        cax = fig.add_axes([0.68, 0.79, 0.27, 0.025])
        cb = fig.colorbar(im, cax=cax, orientation="horizontal")
        cb.set_label(meta["vis"].get("label", meta.get("metric", "Δ")), fontsize=8)
        cb.ax.tick_params(labelsize=7)

    # --- statistics panel ---
    st = fig.add_axes([0.68, 0.42, 0.29, 0.26])
    st.axis("off")
    st.text(0, 1.0, "Statistik", fontsize=11, fontweight="bold", va="top")
    body = "\n".join(_stats_lines(meta))
    st.text(0, 0.88, body, fontsize=8, va="top", family="monospace", linespacing=1.4)
    interp = meta.get("interpretation", "")
    if interp:
        st.text(0, 0.06, interp, fontsize=7.5, va="bottom", style="italic",
                wrap=True, color="#444")

    # --- location overview inset (wide, Esri Light Gray Canvas) ---
    tiles = basemap != "none"
    drawn = [_location_inset(fig, [0.68, 0.18, 0.135, 0.16], lon, lat, tiles=tiles)]

    # --- ESRI Satellite inset (same AOI as the main map) ---
    drawn.append(_satellite_inset(fig, [0.835, 0.18, 0.135, 0.16], extent,
                                  tiles=tiles))

    _footer(fig, meta, drawn, y=0.03)
    _save(fig, out_base)


# The SIRAD composite is three periods mapped to R, G, B.
SIRAD_KEYS = [("#ff0000", "Periode 1"), ("#00ff00", "Periode 2"),
              ("#0000ff", "Periode 3 (biru = aktivitas baru)")]


def _draw_product(ax, meta):
    """Draw one product on `ax`: raster, grid, scale bar, north arrow.

    Opaque. The raster covers the AOI (99.7%+ valid on a typical run), so there
    is nothing under it worth seeing through; no-data cells stay transparent
    and show the white axes ground. Returns (image, extent).
    """
    arr, extent = _read_raster(meta["tif"])
    minlon, maxlon, minlat, maxlat = extent
    ax.set_xlim(minlon, maxlon)
    ax.set_ylim(minlat, maxlat)

    if meta.get("is_rgb"):
        rgb = np.dstack([arr[0], arr[1], arr[2]]).astype(float)
        if rgb.max() > 1:
            rgb /= 255.0
        alpha = (~np.ma.getmaskarray(arr[0])).astype(float)
        im = ax.imshow(rgb, extent=extent, origin="upper", zorder=3, alpha=alpha)
    else:
        vis = meta["vis"]
        cmap = _cmap(vis["palette"])
        cmap.set_bad(alpha=0.0)
        band = np.ma.filled(arr[0].astype(float), np.nan)
        im = ax.imshow(band, extent=extent, origin="upper", cmap=cmap,
                       norm=Normalize(vis["min"], vis["max"]), zorder=3)

    # coordinate grid
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_fmt_lon))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_fmt_lat))
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle=":", color="#555", alpha=0.5, zorder=4)
    for s in ax.spines.values():
        s.set_linewidth(1.2)

    _draw_scalebar(ax, extent, meta["lat"])
    _draw_north(ax)
    return im, extent


def _subtitle(meta):
    sub = (f"{meta['name']}  |  {meta['lat']:.4f}, {meta['lon']:.4f}  |  "
           f"radius {meta['radius_km']} km")
    if meta.get("window"):
        sub += f"  |  {meta['window']}"
    return sub


def _footer(fig, meta, drawn, y):
    # Credit what the insets actually drew: each falls back to OSM if Esri is
    # down, and the main map has no tiles at all.
    credit = sorted({"Esri" if d == "provider" else d for d in drawn if d})
    date = datetime.now().strftime("%Y-%m-%d")
    source = meta.get("source", "Google Earth Engine")
    provider = meta.get("provider", "Copernicus Sentinel (ESA)")
    fig.text(0.045, y,
             f"Data: {provider} via {source}  ·  "
             + (f"Peta inset © {', '.join(credit)}  ·  " if credit else "")
             + f"CRS EPSG:4326  ·  Dibuat {date}",
             fontsize=7, color="#555")


def _save(fig, out_base):
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    pdf, png = out_base + ".pdf", out_base + ".png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=150)
    plt.close(fig)
    print(f"Map: {os.path.normpath(pdf)}")
    print(f"Map: {os.path.normpath(png)}")


def find_pair(metas):
    """(radar RGB meta, change meta) when a run has exactly one of each, else None.

    That is the mining scenario: a SIRAD composite and an NDVI change over the
    same AOI. Checked on content, not on the scenario name, so another radar +
    optical run gets the same sheet.
    """
    rgb = [m for m in metas if m.get("is_rgb")]
    change = [m for m in metas if not m.get("is_rgb")]
    if len(rgb) != 1 or len(change) != 1:
        return None
    a, b = rgb[0], change[0]
    if (a.get("run_id"), a.get("name")) != (b.get("run_id"), b.get("name")):
        return None
    return a, b


def render_pair_map(rgb_meta, change_meta, out_base, basemap="osm"):
    """Radar and optical change side by side, on one A4 sheet.

    Same extent, same grid, so a patch that is blue in SIRAD (new activity) can
    be checked against the same patch in ΔNDVI (vegetation lost) by eye, without
    flipping between two sheets. Writes PDF + PNG.
    """
    fig = plt.figure(figsize=A4_LANDSCAPE, dpi=150)
    fig.patch.set_facecolor("white")
    fig.text(0.045, 0.955, rgb_meta["label"], fontsize=16, fontweight="bold")
    fig.text(0.045, 0.925, _subtitle(rgb_meta), fontsize=9, color="#333")

    # Two square panels; the right one shares the left's latitude labels.
    ax_l = fig.add_axes([0.065, 0.30, 0.42, 0.58])
    ax_r = fig.add_axes([0.515, 0.30, 0.42, 0.58])
    _, extent = _draw_product(ax_l, rgb_meta)
    im, _ = _draw_product(ax_r, change_meta)
    ax_r.tick_params(labelleft=False)
    change_label = change_meta["vis"].get("label", change_meta.get("metric", "Δ"))
    ax_l.set_title("SIRAD — komposit radar tiga periode", fontsize=11,
                   fontweight="bold", loc="left", pad=6)
    ax_r.set_title(f"{change_label} — perubahan vegetasi (optik)", fontsize=11,
                   fontweight="bold", loc="left", pad=6)

    # Legends directly under the panel they explain.
    lg = fig.add_axes([0.065, 0.225, 0.42, 0.04])
    lg.axis("off")
    for i, (c, txt) in enumerate(SIRAD_KEYS):
        x = 0.0 + i * 0.30
        lg.add_patch(Rectangle((x, 0.25), 0.035, 0.5, facecolor=c,
                               transform=lg.transAxes))
        lg.text(x + 0.05, 0.5, txt, fontsize=7.5, va="center",
                transform=lg.transAxes)
    cax = fig.add_axes([0.53, 0.255, 0.30, 0.018])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label(change_label, fontsize=8)
    cb.ax.tick_params(labelsize=7)

    # Bottom band: statistics, how to read it, where it is.
    fig.text(0.065, 0.165, "Statistik", fontsize=10, fontweight="bold")
    fig.text(0.065, 0.150, "\n".join(_stats_lines(rgb_meta, both=True)), fontsize=7,
             va="top", family="monospace", linespacing=1.35)
    interp = rgb_meta.get("interpretation", "")
    if interp:
        # Wrapped by hand: matplotlib's wrap=True wraps at the FIGURE edge,
        # which runs the line under the insets.
        fig.text(0.30, 0.165, "Cara membaca", fontsize=10, fontweight="bold")
        fig.text(0.30, 0.150, textwrap.fill(interp, 58), fontsize=7.5,
                 va="top", style="italic", color="#444", linespacing=1.4)
    tiles = basemap != "none"
    drawn = [_location_inset(fig, [0.64, 0.045, 0.13, 0.125],
                             rgb_meta["lon"], rgb_meta["lat"], tiles=tiles),
             _satellite_inset(fig, [0.80, 0.045, 0.13, 0.125], extent,
                              tiles=tiles)]
    _footer(fig, rgb_meta, drawn, y=0.012)
    _save(fig, out_base)


def render_pair_if_any(metas, out_dir, basemap="osm"):
    """Render the side-by-side sheet into out_dir, if the run has a pair.

    out_dir is explicit rather than taken from meta["tif"]: a run folder that
    was moved or copied still records its old GeoTIFF path.
    """
    pair = find_pair(metas)
    if not pair:
        return None
    rgb, change = pair
    out_base = os.path.join(out_dir,
                            f"{rgb['scenario']}_{rgb['product_key']}_"
                            f"{change['product_key']}_{rgb['name']}_map")
    render_pair_map(rgb, change, out_base, basemap=basemap)
    return out_base
    return pdf, png
