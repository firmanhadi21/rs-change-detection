#!/usr/bin/env python3
"""Compose a value-added cartographic map from a change-detection GeoTIFF.

Produces an A4-landscape map sheet (PDF + PNG) with:
  * OSM basemap + the change layer overlaid
  * title / subtitle
  * legend (colorbar or SIRAD RGB key)
  * statistics panel (from the stats dict)
  * location inset, coordinate grid, scale bar, north arrow
  * data-source / date footer

Used by detect.py (--map) and by make_map.py (re-render an existing result).
Dependencies: matplotlib, rasterio, contextily (OSM tiles need internet).
"""

import os
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

try:
    import contextily as cx
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


def _add_basemap(ax, source=OSM):
    if not _HAS_CX:
        return
    try:
        cx.add_basemap(ax, crs="EPSG:4326", source=source, attribution=False)
    except Exception as e:  # noqa: BLE001
        print(f"  (basemap skipped: {e})")


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


def _location_inset(fig, rect, lon, lat):
    ax = fig.add_axes(rect)
    span = 7.0
    ax.set_xlim(lon - span, lon + span)
    ax.set_ylim(lat - span, lat + span)
    ax.set_xticks([]); ax.set_yticks([])
    _add_basemap(ax, source=cx.providers.CartoDB.Positron if _HAS_CX else OSM)
    ax.plot(lon, lat, marker="*", markersize=15, color="red",
            markeredgecolor="white", markeredgewidth=0.8, zorder=8)
    ax.set_title("Lokasi", fontsize=8)
    for s in ax.spines.values():
        s.set_edgecolor("#888")
    return ax


def _stats_lines(meta):
    """Human-readable statistics lines from meta['stats']."""
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
                  f"Orbit: {s.get('orbit','-')}",
                  f"Scene pre/post: {s.get('scenes_pre','-')}/{s.get('scenes_post','-')}"]
    elif "sirad" in s and "ndvi" in s:  # mining (2 products)
        lines += [f"SIRAD orbit: {s['sirad'].get('orbit','-')}",
                  f"Citra/periode: {s['sirad'].get('images_per_period','-')}"]
        lines += opt(s["ndvi"])
    elif "metric" in s:  # single optical
        lines += opt(s)
    else:  # sirad-only
        lines += [f"Metode: {s.get('method','-')}",
                  f"Orbit: {s.get('orbit','-')}",
                  f"Citra/periode: {s.get('images_per_period','-')}"]
    return lines


def render_map(meta, out_base, basemap="osm"):
    """Render the map sheet. meta describes one product; writes PDF + PNG."""
    arr, extent = _read_raster(meta["tif"])
    minlon, maxlon, minlat, maxlat = extent
    lat, lon = meta["lat"], meta["lon"]

    fig = plt.figure(figsize=A4_LANDSCAPE, dpi=150)
    fig.patch.set_facecolor("white")

    # --- main map ---
    ax = fig.add_axes([0.045, 0.09, 0.60, 0.80])
    ax.set_xlim(minlon, maxlon)
    ax.set_ylim(minlat, maxlat)

    if basemap != "none":
        src = cx.providers.CartoDB.Positron if (basemap == "gray" and _HAS_CX) else OSM
        _add_basemap(ax, source=src)

    is_rgb = meta.get("is_rgb")
    if is_rgb:
        rgb = np.dstack([arr[0], arr[1], arr[2]]).astype(float)
        if rgb.max() > 1:
            rgb /= 255.0
        alpha = (~arr[0].mask).astype(float) * 0.90 if np.ma.isMaskedArray(arr) else 0.90
        ax.imshow(rgb, extent=extent, origin="upper", zorder=3,
                  alpha=alpha if np.ndim(alpha) else 0.9)
    else:
        vis = meta["vis"]
        cmap = _cmap(vis["palette"])
        cmap.set_bad(alpha=0.0)
        band = np.ma.filled(arr[0].astype(float), np.nan)
        im = ax.imshow(band, extent=extent, origin="upper", cmap=cmap,
                       norm=Normalize(vis["min"], vis["max"]), alpha=0.78, zorder=3)

    # coordinate grid
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_fmt_lon))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_fmt_lat))
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle=":", color="#555", alpha=0.5, zorder=4)
    for s in ax.spines.values():
        s.set_linewidth(1.2)

    _draw_scalebar(ax, extent, lat)
    _draw_north(ax)

    # --- title / subtitle ---
    fig.text(0.045, 0.955, meta["label"], fontsize=16, fontweight="bold")
    sub = f"{meta['name']}  |  {lat:.4f}, {lon:.4f}  |  radius {meta['radius_km']} km"
    win = meta.get("window")
    if win:
        sub += f"  |  {win}"
    fig.text(0.045, 0.925, sub, fontsize=9, color="#333")

    # --- legend (colorbar or RGB key) ---
    lg = fig.add_axes([0.68, 0.72, 0.29, 0.16])
    lg.axis("off")
    lg.text(0, 1.0, "Legenda", fontsize=11, fontweight="bold", va="top")
    if is_rgb:
        keys = [("#ff0000", "Periode 1"), ("#00ff00", "Periode 2"),
                ("#0000ff", "Periode 3 (biru = aktivitas baru)")]
        for i, (c, txt) in enumerate(keys):
            lg.add_patch(Rectangle((0.02, 0.6 - i * 0.22), 0.06, 0.12,
                                   facecolor=c, transform=lg.transAxes))
            lg.text(0.11, 0.66 - i * 0.22, txt, fontsize=8, va="center",
                    transform=lg.transAxes)
    else:
        cax = fig.add_axes([0.68, 0.70, 0.27, 0.025])
        cb = fig.colorbar(im, cax=cax, orientation="horizontal")
        cb.set_label(meta["vis"].get("label", meta.get("metric", "Δ")), fontsize=8)
        cb.ax.tick_params(labelsize=7)

    # --- statistics panel ---
    st = fig.add_axes([0.68, 0.30, 0.29, 0.34])
    st.axis("off")
    st.text(0, 1.0, "Statistik", fontsize=11, fontweight="bold", va="top")
    body = "\n".join(_stats_lines(meta))
    st.text(0, 0.90, body, fontsize=8.5, va="top", family="monospace", linespacing=1.5)
    interp = meta.get("interpretation", "")
    if interp:
        st.text(0, 0.06, interp, fontsize=8, va="bottom", style="italic",
                wrap=True, color="#444")

    # --- location inset ---
    _location_inset(fig, [0.68, 0.09, 0.18, 0.19], lon, lat)

    # --- footer ---
    date = datetime.now().strftime("%Y-%m-%d")
    source = meta.get("source", "Google Earth Engine")
    provider = meta.get("provider", "Copernicus Sentinel (ESA)")
    fig.text(0.045, 0.03,
             f"Data: {provider} via {source}  ·  "
             f"Basemap: {'OpenStreetMap' if basemap!='none' else 'none'}  ·  "
             f"CRS EPSG:4326  ·  Dibuat {date}",
             fontsize=7, color="#555")

    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    pdf, png = out_base + ".pdf", out_base + ".png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=150)
    plt.close(fig)
    print(f"Map: {os.path.normpath(pdf)}")
    print(f"Map: {os.path.normpath(png)}")
    return pdf, png
