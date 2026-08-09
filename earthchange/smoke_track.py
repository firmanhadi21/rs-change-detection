#!/usr/bin/env python3
"""Where the smoke went — indicative forward trajectories from the fires.

Seeds air parcels on FIRMS hotspots and carries them forward on the ERA5 100 m
wind field, producing a MovingPandas TrajectoryCollection drawn over the smoke
and the districts underneath.

THIS IS AN ILLUSTRATION, NOT AN ATTRIBUTION. Say it plainly, because a line
drawn from a fire to a city is the most persuasive object a map can contain,
and this one does not deserve that much trust:

  * 100 m wind is the best Earth Engine carries. Smoke that lofts into the
    boundary layer -- 500 to 1500 m by afternoon -- travels faster and on a
    different bearing than air near the surface.
  * No vertical motion, no plume rise, no mixing depth, no deposition. A parcel
    here stays at one level forever.
  * No dispersion. Real plumes spread; these threads do not.

For anything that has to survive a challenge -- who harmed whom, a legal or
compliance claim -- run HYSPLIT or FLEXPART against the receptor points that
smoke-exposure identifies. Those models exist because this problem is hard.
What this scenario is for is showing a general public which way the wind
carried the smoke, honestly labelled.

Backend: needs --backend gee.
"""

import datetime as dt
import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

ERA5_IC = "ECMWF/ERA5/HOURLY"        # 100 m wind lives here, not in ERA5-Land
U100, V100 = "u_component_of_wind_100m", "v_component_of_wind_100m"
ERA5_SCALE = 27830
FIRMS_IC = "FIRMS"
CAMS_IC = "ECMWF/CAMS/NRT"
CAMS_PM25 = "particulate_matter_d_less_than_25_um_surface"

DEFAULT_HOURS = 48
DEFAULT_PARCELS = 60


def _wind_stack(aoi, start, hours, run_dir):
    """Hourly u/v at 100 m as one multi-band GeoTIFF per component.

    Downloaded once and integrated locally. Stepping a parcel by querying Earth
    Engine per hour would be one round trip per parcel per step -- thousands of
    calls for a single figure.
    """
    import ee
    from .gee_utils import download_geotiff

    coll = ee.ImageCollection(ERA5_IC)
    ub, vb = [], []
    for h in range(hours + 1):
        t = ee.Date(start.isoformat()).advance(h, "hour")
        im = coll.filterDate(t, t.advance(1, "hour")).first()
        ub.append(ee.Image(im).select(U100).rename(f"h{h:03d}"))
        vb.append(ee.Image(im).select(V100).rename(f"h{h:03d}"))
    coords = aoi.bounds().getInfo()["coordinates"]
    up = download_geotiff(ee.Image.cat(ub).clip(aoi), coords,
                          os.path.join(run_dir, "_u100.tif"), scale=ERA5_SCALE)
    vp = download_geotiff(ee.Image.cat(vb).clip(aoi), coords,
                          os.path.join(run_dir, "_v100.tif"), scale=ERA5_SCALE)
    return up, vp


def _seeds(aoi, day, n):
    """Parcel start points: the strongest FIRMS detections that day."""
    import ee
    a = ee.Date(day.isoformat())
    ic = (ee.ImageCollection(FIRMS_IC).select("T21")
          .filterDate(a, a.advance(1, "day")))
    # reduceToVectors groups on the FIRST band and reduces the rest, so it needs
    # a label band and a value band. One band with Reducer.first fails with
    # "Need 1+1 bands" -- the same trap the Ketapang hotspot join hit.
    m = ic.max()
    img = m.gt(0).selfMask().rename("fire").addBands(m.rename("t21"))
    pts = (img.reduceToVectors(reducer=ee.Reducer.first(), geometry=aoi,
                               scale=1000, geometryType="centroid",
                               labelProperty="fire", maxPixels=int(1e10),
                               bestEffort=True)
           .sort("first", False).limit(n).getInfo()["features"])
    return [(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1])
            for f in pts]


def _advect(seeds, up, vp, start, hours, step_min=20):
    """Carry each parcel forward on the wind field.

    Midpoint (RK2) rather than Euler: over two days of curving monsoon flow,
    Euler cuts every corner and drifts noticeably inside the turn.
    """
    import numpy as np
    import rasterio
    from .gee_utils import read_band

    with rasterio.open(up) as s:
        nb, tr = s.count, s.transform
        H, W = s.height, s.width
    U = np.stack([read_band(up, b + 1, label=f"u100 h{b}")[0]
                  for b in range(nb)])
    V = np.stack([read_band(vp, b + 1, label=f"v100 h{b}")[0]
                  for b in range(nb)])
    U = np.nan_to_num(U)
    V = np.nan_to_num(V)

    def sample(arr, h, lon, lat):
        """Nearest-cell wind, with linear interpolation between the two hours."""
        c = int(np.clip((lon - tr.c) / tr.a, 0, W - 1))
        r = int(np.clip((lat - tr.f) / tr.e, 0, H - 1))
        h0 = int(np.clip(np.floor(h), 0, nb - 1))
        h1 = min(h0 + 1, nb - 1)
        f = h - h0
        return arr[h0, r, c] * (1 - f) + arr[h1, r, c] * f

    dt_s = step_min * 60
    nstep = int(hours * 60 / step_min)
    out = []
    for lon0, lat0 in seeds:
        lon, lat = lon0, lat0
        path = [(start, lon, lat)]
        for k in range(nstep):
            h = k * step_min / 60.0
            u1 = sample(U, h, lon, lat)
            v1 = sample(V, h, lon, lat)
            # midpoint
            mlat = lat + (v1 * dt_s / 2) / 111_320.0
            mlon = lon + (u1 * dt_s / 2) / (111_320.0 *
                                            max(np.cos(np.radians(lat)), .2))
            u2 = sample(U, h + step_min / 120.0, mlon, mlat)
            v2 = sample(V, h + step_min / 120.0, mlon, mlat)
            lat += (v2 * dt_s) / 111_320.0
            lon += (u2 * dt_s) / (111_320.0 *
                                  max(np.cos(np.radians(lat)), .2))
            path.append((start + dt.timedelta(seconds=(k + 1) * dt_s), lon, lat))
        out.append(path)
    return out


def _trajectories(paths):
    """Wrap the paths as a MovingPandas TrajectoryCollection.

    MovingPandas contributes no physics -- the advection above is the physics.
    What it gives is the right object: time-indexed paths that can be measured,
    clipped against district polygons and plotted without hand-rolling any of
    it. An air-parcel ensemble is exactly its data model.
    """
    import geopandas as gpd
    import movingpandas as mpd
    import pandas as pd
    from shapely.geometry import Point

    rows = []
    for i, path in enumerate(paths):
        for t, lon, lat in path:
            rows.append({"traj_id": i, "t": t, "geometry": Point(lon, lat)})
    if not rows:
        return None
    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry="geometry",
                           crs="EPSG:4326").set_index("t")
    return mpd.TrajectoryCollection(gdf, "traj_id")


def _crossed(tc, shapes, field="ADM2_NAME"):
    """Which districts the parcels passed over, and how many crossed each.

    This is the sentence the figure is for -- 'most of these threads passed over
    X' -- and it is also where the honesty has to hold: crossing is not the same
    as depositing smoke there.
    """
    import geopandas as gpd
    from shapely.geometry import shape as shp_shape

    polys, names = [], []
    for f in shapes:
        g = f.get("geometry")
        nm = (f.get("properties") or {}).get(field)
        if g and nm:
            try:
                polys.append(shp_shape(g))
                names.append(nm)
            except Exception:                                      # noqa: BLE001
                continue
    if not polys:
        return {}
    gdf = gpd.GeoDataFrame({"name": names}, geometry=polys, crs="EPSG:4326")
    counts = {}
    for traj in tc.trajectories:
        line = traj.to_linestring()
        hit = gdf[gdf.intersects(line)]["name"].tolist()
        for nm in set(hit):
            counts[nm] = counts.get(nm, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _render(run_dir, name, tc, seeds, smoke_tif, box, day, hours, crossed):
    """The trajectories over the smoke field they are meant to explain.

    A fan of threads, not one bold arrow. The spread IS the message: these are
    plausible paths, and their disagreement is the honest width of the answer.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(13.5, 11), dpi=160)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])

    if smoke_tif and os.path.exists(smoke_tif):
        import rasterio
        from .gee_utils import read_band
        a, _ = read_band(smoke_tif, label="CAMS PM2.5")
        with rasterio.open(smoke_tif) as src:
            b = src.bounds
        smoke = LinearSegmentedColormap.from_list(
            "smoke", ["#00000000", "#d9a15c60", "#c25b2a90", "#7d1d0fc0"])
        im = ax.imshow(np.ma.masked_invalid(a), cmap=smoke, vmin=10, vmax=180,
                       extent=[b.left, b.right, b.bottom, b.top],
                       interpolation="bilinear", zorder=3)
        # Without a scale the backdrop is decoration. With one it is the reason
        # the trajectories matter.
        cax = ax.inset_axes([.62, .045, .34, .016])
        cb = fig.colorbar(im, cax=cax, orientation="horizontal",
                          extend="max")
        cb.set_label("PM2.5 CAMS (µg/m³)", fontsize=7.5, color="#eee",
                     labelpad=2)
        cb.ax.tick_params(labelsize=7, colors="#eee", length=2)
        cb.outline.set_visible(False)
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326",
                       source=cx.providers.CartoDB.DarkMatter,
                       attribution_size=5, zorder=1)
    except Exception as exc:                                       # noqa: BLE001
        print(f"  (basemap skipped: {exc.__class__.__name__})")

    cmap = plt.get_cmap("YlOrRd")
    for traj in tc.trajectories:
        xy = np.array(traj.to_linestring().coords)
        n = len(xy)
        for i in range(0, n - 1, 3):
            ax.plot(xy[i:i + 4, 0], xy[i:i + 4, 1], lw=1.1,
                    color=cmap(0.25 + 0.7 * i / max(n - 1, 1)),
                    alpha=.75, solid_capstyle="round", zorder=4)
        # An arrowhead at the far end. Without it the fan is a tangle: a reader
        # cannot tell a plume blowing northwest from one blowing southeast, and
        # that direction is the entire content of the figure.
        if n > 4:
            ax.annotate("", xy=xy[-1], xytext=xy[-4],
                        arrowprops=dict(arrowstyle="-|>", lw=0,
                                        color="#ffe9b0", mutation_scale=9,
                                        shrinkA=0, shrinkB=0), zorder=5)
    if seeds:
        s = np.array(seeds)
        ax.scatter(s[:, 0], s[:, 1], s=13, marker="^", c="#ff3b1f",
                   edgecolor="#4a0d05", linewidth=.4, zorder=6)

    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal", adjustable="box")
    for sp in ax.spines.values():
        sp.set_visible(False)
    leg = ax.legend(handles=[
        Line2D([], [], ls="", marker="^", color="#ff3b1f",
               label=f"titik api FIRMS {day} — awal parsel ({len(seeds)})"),
        Line2D([], [], color=cmap(.3), lw=2, label="jam ke-0"),
        Line2D([], [], color=cmap(.95), lw=2, marker=">",
               markerfacecolor="#ffe9b0", markeredgecolor="#ffe9b0",
               label=f"jam ke-{hours} (ujung panah)"),
    ], fontsize=9, frameon=False, loc="lower left", labelcolor="#e8e4dc")
    leg.set_zorder(7)

    top = list(crossed.items())[:4]
    sub = ("melintasi " + ", ".join(f"{k} ({v})" for k, v in top)
           if top else "")
    ax.set_title(
        f"Ke mana asap terbawa — {name}\n"
        f"parsel udara dari titik api {day}, {hours} jam ke depan · {sub}",
        fontsize=12.5, fontweight="bold", loc="left")
    fig.text(.008, .022,
             "ILUSTRASI, BUKAN ATRIBUSI. Parsel dibawa angin ERA5 100 m — "
             "level terbaik yang tersedia, tetapi asap yang terangkat ke "
             "lapisan batas (500–1500 m) bergerak lebih cepat dan ke arah "
             "berbeda. Tanpa gerak vertikal, tanpa dispersi, tanpa deposisi. "
             "Untuk klaim yang harus tahan uji, gunakan HYSPLIT/FLEXPART. "
             "Latar: PM2.5 CAMS. Peta dasar © CartoDB/OpenStreetMap.",
             fontsize=7.5, color="#777", wrap=True)
    fig.tight_layout(rect=[0, .055, 1, 1])
    out = os.path.join(run_dir, f"{name}_smoke_track.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        day=None, hours=DEFAULT_HOURS, parcels=DEFAULT_PARCELS,
        admin=None, bbox=None, lang="id"):
    """Indicative forward trajectories from a day's fires."""
    if backend == "mpc":
        raise SystemExit("smoke-track needs --backend gee (ERA5 + FIRMS).")
    try:
        import movingpandas                                       # noqa: F401
    except ImportError:
        raise SystemExit("smoke-track needs movingpandas: "
                         "pip install 'earthchange[track]'")
    if not day:
        raise SystemExit("smoke-track needs --date YYYY-MM-DD — the day whose "
                         "fires to follow")
    d0 = dt.date.fromisoformat(day)
    start = dt.datetime(d0.year, d0.month, d0.day, tzinfo=dt.UTC)

    import ee
    from .gee_utils import download_geotiff, initialize_ee
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)
    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    box = [min(xs), min(ys), max(xs), max(ys)]

    print(f"  {name}: fires of {d0}, carried {hours} h on ERA5 100 m wind")
    seeds = _seeds(aoi, d0, parcels)
    if not seeds:
        raise SystemExit(f"No FIRMS detections in this area on {d0}. "
                         "Try a day during an active episode.")
    print(f"  {len(seeds)} parcels seeded")

    up, vp = _wind_stack(aoi, start, hours, run_dir)
    if not (up and vp):
        raise SystemExit("Could not download the ERA5 wind stack.")
    paths = _advect(seeds, up, vp, start, hours)
    tc = _trajectories(paths)
    if tc is None:
        raise SystemExit("No trajectories produced.")

    # Mean smoke over the window, as the backdrop the threads should explain.
    smoke = os.path.join(run_dir, "_pm25.tif")
    img = (ee.ImageCollection(CAMS_IC).select(CAMS_PM25)
           .filterDate(start.isoformat(),
                       (start + dt.timedelta(hours=hours)).isoformat())
           .mean().multiply(1e9).clip(aoi))
    smoke = download_geotiff(img, coords, smoke, scale=44453)

    from .exposure import _district_shapes, _districts
    shapes = _district_shapes(_districts(aoi))
    crossed = _crossed(tc, shapes)
    png = _render(run_dir, name, tc, seeds, smoke, box, d0, hours, crossed)

    lens = [t.get_length() / 1000.0 for t in tc.trajectories]
    stats = {"run_id": run_id, "scenario": "smoke-track", "name": name,
             "day": d0.isoformat(), "hours": hours, "parcels": len(seeds),
             "median_path_km": round(sorted(lens)[len(lens) // 2], 1),
             "districts_crossed": crossed,
             "sources": {"wind": f"ERA5 100 m ({ERA5_IC})",
                         "seeds": f"FIRMS ({FIRMS_IC}) detections on {d0}",
                         "smoke": f"CAMS ({CAMS_IC}) mean over the window"},
             "outputs": {"figure": os.path.basename(png) if png else None},
             "note": ("ILLUSTRATION, NOT ATTRIBUTION. 100 m wind is the best "
                      "Earth Engine carries, but lofted smoke travels faster "
                      "and on a different bearing. No vertical motion, no "
                      "dispersion, no deposition. For a claim that must "
                      "survive challenge, run HYSPLIT or FLEXPART against the "
                      "receptors smoke-exposure identifies.")}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n{name} — parsel dari {d0}, {hours} jam")
    print(f"  panjang lintasan median: {stats['median_path_km']:,.0f} km")
    print("  kabupaten/kota terlintasi (jumlah parsel):")
    for k, v in list(crossed.items())[:10]:
        print(f"    {k[:30]:30s} {v:4d}")
    print("\n  ILUSTRASI, bukan atribusi — lihat catatan di stats.json")
    return stats
