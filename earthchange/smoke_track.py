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
DEFAULT_HEIGHTS = (100.0, 500.0, 1500.0)     # m AGL, HYSPLIT release levels
# Longest subtitle line that fits the figure at 12.5 pt bold on 13.5 in.
# Measured, not guessed: 144 characters clipped, 123 fitted.
SUBTITLE_CHARS = 125

DEFAULT_CAVEAT = (
    "ILUSTRASI, BUKAN ATRIBUSI. Parsel dibawa angin ERA5 100 m — level terbaik "
    "yang tersedia, tetapi asap yang terangkat ke lapisan batas (500–1500 m) "
    "bergerak lebih cepat dan ke arah berbeda. Tanpa gerak vertikal, tanpa "
    "dispersi, tanpa deposisi. Untuk klaim yang harus tahan uji, gunakan "
    "HYSPLIT (--engine hysplit) atau FLEXPART. Latar: PM2.5 CAMS. "
    "Peta dasar © CartoDB/OpenStreetMap.")

# The HYSPLIT footer is shorter because it has less to apologise for. It still
# states the configuration, because a trajectory without its met resolution and
# release height is not reproducible.
HYSPLIT_CAVEAT = (
    "Lintasan HYSPLIT (NOAA ARL) dengan meteorologi GDAS1 1° 3-jam; gerak "
    "vertikal mengikuti medan (opsi 0). Dilepas pada {levels} m di atas "
    "permukaan — sebaran antar-ketinggian adalah geseran angin yang nyata, "
    "bukan ketidakpastian. Ini lintasan, bukan dispersi: garis tidak "
    "menyebar dan tidak mengendap, sehingga melintas ≠ menurunkan asap. "
    "Latar: PM2.5 CAMS. Peta dasar © CartoDB/OpenStreetMap.")


def _as_date(day):
    return day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))


def _fmt_when(t):
    """A date, or a date and time when the run does not land on midnight."""
    return t.strftime("%Y-%m-%d" if (t.hour, t.minute) == (0, 0)
                      else "%Y-%m-%d %H:%M")


def span_dates(day, hours, direction):
    """Both ends of the run, as dates rather than a duration.

    "48 jam ke depan" makes the reader do arithmetic against a date they have to
    hold in their head. The two dates are what they actually want, and they are
    always given oldest first so the text reads in the same direction the
    arrows on the map point.

    A run that is not a whole number of days lands mid-day, and saying so beats
    rounding to a date that is off by twelve hours.
    """
    start = dt.datetime.combine(_as_date(day), dt.time(), tzinfo=dt.UTC)
    delta = dt.timedelta(hours=abs(hours))
    other = start - delta if direction == "backward" else start + delta
    lo, hi = sorted([start, other])
    return _fmt_when(lo), _fmt_when(hi)


def _captions(name, day, hours, crossed, direction, seeds, seed_label, hours_lbl):
    """Title, subtitle and legend labels, which differ only by direction.

    Backward is not forward with a minus sign: the seeds are receptors, the
    question is 'where did this air come from', and every label has to say so or
    the figure quietly asserts the opposite of what it computed.
    """
    back = direction == "backward"
    lo, hi = span_dates(day, hours_lbl, direction)
    when = (f"parsel udara yang tiba pada {hi}, berasal dari {lo}" if back
            else f"parsel udara dari titik api {lo}, sampai {hi}")
    head = "Dari mana asap datang" if back else "Ke mana asap terbawa"

    # Budget the whole rendered line, not just the district list. Counting
    # districts overflows the moment one is called "Kota Pontianak"; budgeting
    # the list alone still overflows, because the prefix ahead of it is another
    # seventy characters and its length changes with direction.
    prefix = f"{when} · melintasi "
    parts, budget = [], SUBTITLE_CHARS - len(prefix)
    for k, v in crossed.items():
        piece = f"{k} ({v})"
        if len(piece) + 2 > budget:
            break
        parts.append(piece)
        budget -= len(piece) + 2
    sub = ("melintasi " + ", ".join(parts)) if parts else ""
    return {
        "title": f"{head} — {name}\n{when} · {sub}",
        "seed": seed_label or f"titik api FIRMS {day} — awal parsel ({len(seeds)})",
        "start": "paling awal" if back else "jam ke-0",
        "end": ("tiba di reseptor (ujung panah)" if back
                else f"jam ke-{hours_lbl} (ujung panah)"),
    }


FIG_ASPECT = 13.5 / 11.0        # the figsize _render draws into


def display_box(aoi_box, xs, ys, pad=0.10, q=2.0, aspect=FIG_ASPECT):
    """Frame the trajectories, not just the area the seeds came from.

    Seeding on one district is the natural way to ask "where does Ketapang's
    smoke go", but the AOI is then district-sized while the parcels travel
    hundreds of kilometres, so every path leaves the frame and the figure
    answers nothing.

    Two refinements, both from looking at the result:

      * A percentile rather than min/max. One parcel that runs 900 km north
        while the other twenty-four stay together should not decide the frame;
        it is drawn to the edge and clipped, which is the honest treatment of an
        outlier in a fan whose spread is the point.
      * Aspect balancing. An equal-aspect axis with a tall thin extent renders
        as a sliver down the middle of the page with the title running off it.
    """
    import numpy as np

    lo_x = min(aoi_box[0], float(np.percentile(xs, q)))
    hi_x = max(aoi_box[2], float(np.percentile(xs, 100 - q)))
    lo_y = min(aoi_box[1], float(np.percentile(ys, q)))
    hi_y = max(aoi_box[3], float(np.percentile(ys, 100 - q)))

    mx = max(hi_x - lo_x, 0.1) * pad
    my = max(hi_y - lo_y, 0.1) * pad
    lo_x, hi_x, lo_y, hi_y = lo_x - mx, hi_x + mx, lo_y - my, hi_y + my

    # Grow the short side only -- never crop what was just fitted.
    w, h = hi_x - lo_x, hi_y - lo_y
    if w / h < aspect:
        grow = (h * aspect - w) / 2
        lo_x, hi_x = lo_x - grow, hi_x + grow
    else:
        grow = (w / aspect - h) / 2
        lo_y, hi_y = lo_y - grow, hi_y + grow

    return [max(lo_x, -180.0), max(lo_y, -90.0),
            min(hi_x, 180.0), min(hi_y, 90.0)]


def _wind_stack(aoi, start, hours, run_dir):
    """Hourly u/v at 100 m as one multi-band GeoTIFF per component.

    Downloaded once and integrated locally. Stepping a parcel by querying Earth
    Engine per hour would be one round trip per parcel per step -- thousands of
    calls for a single figure.
    """
    import ee
    from .gee_utils import download_geotiff

    # ERA5 lags real time by about six days, so a run whose seeds exist in FIRMS
    # can still have no wind for its second day. Count the hours rather than
    # check the range: the trailing day arrives piecemeal, so a window ending
    # inside it passes a min/max test and then hits a null image mid-loop,
    # surfacing as "Image.select: Parameter 'input' ... may not be null".
    from .gee_utils import require_hours
    require_hours(ERA5_IC, start, start + dt.timedelta(hours=hours + 1),
                  "ERA5 100 m wind")

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


LATE_HINT = {
    FIRMS_IC: ("FIRMS reaches Earth Engine a few days behind real time, so the "
               "most recent days are never there. Pick an earlier day — or use "
               "smoke-video, which reads the NASA FIRMS live feed directly "
               "(last 7 days) and needs no Earth Engine account."),
    CAMS_IC: ("CAMS is a near-real-time forecast archive and lags by a day or "
              "two. Pick an earlier day."),
}


def coverage_message(what, day, lo, hi, late_hint=""):
    """The message for a day the archive does not hold.

    Separate from the Earth Engine call so the wording can be tested, and worth
    getting right: the default failure here is a bare 'Image.gt: ... Got 0 and
    1', which says nothing about dates at all.
    """
    msg = (f"{what} has no data for {day}. Earth Engine carries "
           f"{lo} to {hi}.")
    if late_hint and str(day) > hi:
        msg += "\n\n" + late_hint
    elif str(day) < lo:
        msg += f"\n\nThe archive begins {lo}; earlier days cannot be computed."
    return msg


def window_message(what, need_lo, need_hi, have_lo, have_hi, hours, direction):
    """A run window the archive cannot cover, said usefully.

    Partial coverage is the trap: a 48 h run can seed from FIRMS, find wind for
    its first day and none for its second. Reporting only the archive's end date
    leaves the user to do the arithmetic, so do it for them and name the dates
    that would actually work.
    """
    span = dt.timedelta(hours=abs(hours))
    if direction == "backward":
        earliest, latest = have_lo + span, have_hi
    else:
        earliest, latest = have_lo, have_hi - span
    return "\n".join([
        f"{what} does not cover the whole run window.",
        f"  needed:    {need_lo:%Y-%m-%d %H:%M} to {need_hi:%Y-%m-%d %H:%M}",
        f"  available: {have_lo:%Y-%m-%d %H:%M} to {have_hi:%Y-%m-%d %H:%M}",
        "",
        f"With --track-hours {abs(hours)}, --date has to fall between "
        f"{earliest:%Y-%m-%d} and {latest:%Y-%m-%d}.",
        "Reanalysis runs several days behind real time. For the last few days "
        "use smoke-video, which reads live feeds and needs no Earth Engine.",
    ])


def _require_window(collection_id, lo, hi, what, hours, direction="forward"):
    """Refuse a run the archive cannot cover end to end."""
    import ee

    full = ee.ImageCollection(collection_id)
    span = ee.Dictionary({
        "lo": ee.Date(full.aggregate_min("system:time_start")).format(
            "yyyy-MM-dd HH:mm"),
        "hi": ee.Date(full.aggregate_max("system:time_start")).format(
            "yyyy-MM-dd HH:mm"),
    }).getInfo()
    fmt = "%Y-%m-%d %H:%M"
    have_lo = dt.datetime.strptime(span["lo"], fmt).replace(tzinfo=dt.UTC)
    have_hi = dt.datetime.strptime(span["hi"], fmt).replace(tzinfo=dt.UTC)
    if have_lo <= lo and hi <= have_hi:
        return
    raise SystemExit(window_message(what, lo, hi, have_lo, have_hi, hours,
                                    direction))


def _require_day(ic, collection_id, day, what):
    """Refuse early when a collection holds nothing for this day.

    An empty ImageCollection reduces to an image with no bands, and every
    arithmetic op after that fails with a message about band counts rather than
    about the date -- which is the actual problem and is easy to fix.
    """
    import ee

    if ic.size().getInfo():
        return
    full = ee.ImageCollection(collection_id)
    span = ee.Dictionary({
        "lo": ee.Date(full.aggregate_min("system:time_start")).format("YYYY-MM-dd"),
        "hi": ee.Date(full.aggregate_max("system:time_start")).format("YYYY-MM-dd"),
    }).getInfo()
    raise SystemExit(coverage_message(what, day, span["lo"], span["hi"],
                                      LATE_HINT.get(collection_id, "")))


def _seeds(aoi, day, n):
    """Parcel start points: the strongest FIRMS detections that day."""
    import ee
    a = ee.Date(day.isoformat())
    ic = (ee.ImageCollection(FIRMS_IC).select("T21")
          .filterDate(a, a.advance(1, "day")))
    # FIRMS is a daily global image, so inside the archive there is always one,
    # masked wherever nothing burned -- a fireless day still yields an image and
    # simply produces no seeds. Zero IMAGES means the day itself is missing.
    _require_day(ic, FIRMS_IC, day, "FIRMS")
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


def parse_receptors(spec):
    """Parse --receptors 'Nama,lon,lat; Nama,lon,lat' into points.

    Explicit rather than geocoded, for the same reason smoke-video takes
    --video-cities that way: a name lookup cannot tell you which places matter
    for this question, and silently geocoding to the wrong Pontianak would be
    worse than asking.
    """
    out = []
    for i, chunk in enumerate(spec.split(";"), 1):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) != 3:
            raise SystemExit(
                f"--receptors entry {i} is {chunk!r}; expected "
                "'Name,lon,lat' separated by semicolons, e.g. "
                "'Pontianak,109.33,-0.02; Palangkaraya,113.92,-2.21'")
        name, lon_s, lat_s = parts
        try:
            lon, lat = float(lon_s), float(lat_s)
        except ValueError:
            raise SystemExit(f"--receptors entry {i}: {lon_s!r},{lat_s!r} are "
                             "not numbers. The order is Name,lon,lat.")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise SystemExit(
                f"--receptors entry {i}: lon={lon}, lat={lat} is out of range. "
                "The order is Name,lon,lat -- longitude first.")
        out.append((lon, lat, name or f"receptor {i}"))
    if not out:
        raise SystemExit("--receptors was empty.")
    return out


def _sample_pm25(day, points):
    """CAMS PM2.5 at each named point, so explicit receptors report like ranked
    ones and stats.json has the same shape either way."""
    import ee

    a = ee.Date(day.isoformat())
    pm = (ee.ImageCollection(CAMS_IC).select(CAMS_PM25)
          .filterDate(a, a.advance(1, "day")).mean().multiply(1e9))
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lon, lat]))
                               for lon, lat, _ in points])
    vals = pm.reduceRegions(fc, ee.Reducer.first(), 44453).getInfo()["features"]
    out = []
    for (lon, lat, nm), f in zip(points, vals):
        v = f["properties"].get("first")
        out.append((lon, lat, nm, round(v, 1) if v is not None else None))
    return out


def _receptors(aoi, day, n, named=None):
    """Backward-run start points: where the smoke actually was, worst first.

    A backward trajectory is only worth running from somewhere people were
    breathing. With no --receptors, take the districts with the highest CAMS
    PM2.5 that day and start at their centroids -- the same ranking
    smoke-exposure reports, so the two scenarios line up. With --receptors, use
    exactly the places named, in the order given.

    Returns [(lon, lat, name, pm25), ...].
    """
    import ee
    from .exposure import _districts
    from shapely.geometry import shape as shp_shape

    if named:
        return _sample_pm25(day, named)

    a = ee.Date(day.isoformat())
    day_ic = (ee.ImageCollection(CAMS_IC).select(CAMS_PM25)
              .filterDate(a, a.advance(1, "day")))
    # Ranking receptors by PM2.5 is impossible without PM2.5, so this one is
    # fatal rather than cosmetic.
    _require_day(day_ic, CAMS_IC, day, "CAMS PM2.5")
    pm = day_ic.mean().multiply(1e9).rename("pm25")
    fc = _districts(aoi)
    stats = pm.reduceRegions(fc, ee.Reducer.mean(), 44453).getInfo()["features"]
    ranked = sorted(
        (f for f in stats if f["properties"].get("mean") is not None),
        key=lambda f: -f["properties"]["mean"])[:n]

    out = []
    for f in ranked:
        try:
            c = shp_shape(f["geometry"]).representative_point()
        except Exception:                                          # noqa: BLE001
            continue
        nm = f["properties"].get("ADM2_NAME") or "?"
        out.append((c.x, c.y, nm, round(f["properties"]["mean"], 1)))
    return out


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


def _render(run_dir, name, tc, seeds, smoke_tif, box, day, hours, crossed,
            engine="kinematic", direction="forward", caveat=None,
            seed_label=None):
    """The trajectories over the smoke field they are meant to explain.

    A fan of threads, not one bold arrow. The spread IS the message: these are
    plausible paths, and their disagreement is the honest width of the answer.

    Both engines render through here, and that is the point: swapping in HYSPLIT
    changes the physics and the footnote, not the picture. A reader who has seen
    one can read the other.
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
    # Even running backward the threads are drawn oldest-first, so the arrow
    # always points the way the air actually travelled. What changes is which
    # end was chosen: forward starts at fires, backward starts at receptors.
    cap = _captions(name, day, hours, crossed, direction, seeds, seed_label,
                    abs(hours))
    leg = ax.legend(handles=[
        Line2D([], [], ls="", marker="^", color="#ff3b1f", label=cap["seed"]),
        Line2D([], [], color=cmap(.3), lw=2, label=cap["start"]),
        Line2D([], [], color=cmap(.95), lw=2, marker=">",
               markerfacecolor="#ffe9b0", markeredgecolor="#ffe9b0",
               label=cap["end"]),
    ], fontsize=9, frameon=False, loc="lower left", labelcolor="#e8e4dc")
    leg.set_zorder(7)
    ax.set_title(cap["title"], fontsize=12.5, fontweight="bold", loc="left")
    fig.text(.008, .022, caveat or DEFAULT_CAVEAT,
             fontsize=7.5, color="#777", wrap=True)
    fig.tight_layout(rect=[0, .055, 1, 1])
    out = os.path.join(run_dir, f"{name}_smoke_track.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _engine_kinematic(aoi, seeds, start, hours, run_dir):
    """The no-dependency engine: ERA5 100 m wind, integrated here."""
    up, vp = _wind_stack(aoi, start, hours, run_dir)
    if not (up and vp):
        raise SystemExit("Could not download the ERA5 wind stack.")
    return _advect([(s[0], s[1]) for s in seeds], up, vp, start, hours)


def _engine_hysplit(seeds, start, hours, run_dir, heights, direction,
                    exe, met_cache=None):
    """The real engine: NOAA ARL HYSPLIT on GDAS1.

    Every seed is released at several heights, because that is the thing the
    kinematic engine cannot do and the reason to bother: the spread between
    release levels is genuine wind shear, not model uncertainty.
    """
    from . import hysplit as hy

    print(f"  HYSPLIT: {exe}")
    signed = -abs(hours) if direction == "backward" else abs(hours)
    cache = met_cache or os.path.expanduser("~/.cache/earthchange/arl")
    met = hy.fetch_met(hy.met_keys(start, hours, direction), cache,
                       hours=hours, direction=direction)

    pts = [(lat, lon, h) for lon, lat, *_ in seeds for h in heights]
    if len(pts) > 500:
        raise SystemExit(
            f"{len(pts)} start points ({len(seeds)} seeds x {len(heights)} "
            "heights) is more than HYSPLIT will take in one run. Lower "
            "--track-parcels or pass fewer --track-heights.")

    paths, got_dir = hy.run_trajectories(exe, start, pts, signed, met,
                                         os.path.join(run_dir, "_hysplit"))
    print(f"  {len(paths)} trajectories ({got_dir.lower()}), "
          f"released at {', '.join(f'{h:g}' for h in heights)} m AGL")
    # Drop the height column: the rest of the pipeline is 2-D, and carrying a
    # third coordinate into MovingPandas would silently change get_length()
    # from ground distance to slant distance.
    return [[(t, lon, lat) for t, lon, lat, _h in p] for p in paths]


HYSPLIT_NOTE = (
    "Trajectories, not dispersion. HYSPLIT resolves vertical motion, mixing "
    "depth and terrain, so these are defensible paths -- but a trajectory line "
    "does not spread or deposit, so crossing a district is still not the same "
    "as depositing smoke on it. For concentration attribution run HYSPLIT in "
    "dispersion mode or FLEXPART. GDAS1 is 1 degree; local terrain flow is not "
    "resolved.")

KINEMATIC_NOTE = (
    "ILLUSTRATION, NOT ATTRIBUTION. 100 m wind is the best Earth Engine "
    "carries, but lofted smoke travels faster and on a different bearing. No "
    "vertical motion, no dispersion, no deposition. For a claim that must "
    "survive challenge, re-run with --engine hysplit, or use FLEXPART.")


def _stats(run_id, name, d0, hours, engine, direction, heights, seeds, recept,
           tc, crossed, png):
    """The machine-readable record, including what the figure cannot carry."""
    lens = sorted(t.get_length() / 1000.0 for t in tc.trajectories)
    hy = engine == "hysplit"
    seed_src = (f"CAMS PM2.5 district ranking on {d0}"
                if direction == "backward"
                else f"FIRMS ({FIRMS_IC}) detections on {d0}")
    out = {"run_id": run_id, "scenario": "smoke-track", "name": name,
           "day": d0.isoformat(), "hours": hours, "engine": engine,
           "direction": direction, "seeds": len(seeds),
           "trajectories": len(tc.trajectories),
           "median_path_km": round(lens[len(lens) // 2], 1),
           "districts_crossed": crossed,
           "outputs": {"figure": os.path.basename(png) if png else None},
           "note": HYSPLIT_NOTE if hy else KINEMATIC_NOTE,
           "sources": {
               "model": ("NOAA ARL HYSPLIT (hyts_std), vertical motion = data"
                         if hy else "kinematic integration (RK2 midpoint)"),
               "meteorology": ("GDAS1 1 deg 3-hourly (ARL public S3)" if hy
                               else f"ERA5 100 m ({ERA5_IC})"),
               "seeds": seed_src,
               "smoke": f"CAMS ({CAMS_IC}) mean over the window"}}
    if hy:
        out["release_heights_m_agl"] = list(heights)
    if recept:
        out["receptors"] = [{"name": r[2], "lon": round(r[0], 3),
                             "lat": round(r[1], 3), "pm25": r[3]}
                            for r in recept]
    return out


def _check_opts(backend, day, engine, direction, receptors, hysplit_bin):
    """Everything that can be refused before spending a second on data.

    All of it runs ahead of Earth Engine and ahead of the met download, because
    being told to install a binary after sitting through a FIRMS query is a
    waste of the user's time.
    """
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

    named = parse_receptors(receptors) if receptors else None
    if named and direction != "backward":
        raise SystemExit(
            "--receptors names places for air to arrive AT, so it only means "
            "something with --direction backward. Going forward the start "
            "points are the fires.")
    if direction == "backward" and engine != "hysplit":
        raise SystemExit(
            "--direction backward needs --engine hysplit. Running the "
            "kinematic integrator in reverse would look like a source "
            "attribution while being no more defensible than the forward fan, "
            "which is exactly the confusion this scenario exists to avoid.")

    exe = None
    if engine == "hysplit":
        from . import hysplit as hy
        exe = hy.find_binary(hysplit_bin)
        if not exe:
            raise SystemExit(hy.INSTALL_HELP)
    return named, exe


def _seed_points(aoi, d0, parcels, direction, name, hours, engine, named=None):
    """Where the parcels start — fires going forward, receptors going back."""
    if direction == "backward":
        recept = _receptors(aoi, d0, parcels, named=named)
        if not recept:
            raise SystemExit(f"No CAMS PM2.5 over any district on {d0}.")
        print(f"  {name}: air arriving {d0}, traced back {hours} h (hysplit)")
        for _lon, _lat, nm, pm in recept[:8]:
            shown = f"{pm:6.1f} µg/m³" if pm is not None else "   no CAMS value"
            print(f"    {nm[:28]:28s} PM2.5 {shown}")
        label = (f"reseptor — {len(recept)} lokasi yang disebutkan" if named
                 else f"reseptor — {len(recept)} kabupaten PM2.5 tertinggi {d0}")
        return [(r[0], r[1]) for r in recept], recept, label

    seeds = _seeds(aoi, d0, parcels)
    if not seeds:
        raise SystemExit(f"No FIRMS detections in this area on {d0}. "
                         "Try a day during an active episode.")
    print(f"  {name}: fires of {d0}, carried {hours} h ({engine})")
    print(f"  {len(seeds)} parcels seeded")
    return seeds, None, None


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        day=None, hours=DEFAULT_HOURS, parcels=DEFAULT_PARCELS,
        admin=None, bbox=None, lang="id", engine="kinematic",
        direction="forward", heights=None, hysplit_bin=None, met_cache=None,
        receptors=None):
    """Forward or backward smoke trajectories, kinematic or HYSPLIT."""
    named, exe = _check_opts(backend, day, engine, direction, receptors,
                             hysplit_bin)
    heights = tuple(heights or DEFAULT_HEIGHTS)
    d0 = dt.date.fromisoformat(day)
    start = dt.datetime(d0.year, d0.month, d0.day, tzinfo=dt.UTC)

    import ee
    import numpy as np
    from .gee_utils import download_geotiff, initialize_ee
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)
    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    coords = aoi.bounds().getInfo()["coordinates"]
    xs = [p[0] for p in coords[0]]
    ys = [p[1] for p in coords[0]]
    box = [min(xs), min(ys), max(xs), max(ys)]

    seeds, recept, seed_label = _seed_points(aoi, d0, parcels, direction,
                                             name, hours, engine, named=named)
    if engine == "hysplit":
        paths = _engine_hysplit(seeds, start, hours, run_dir, heights,
                                direction, exe, met_cache)
    else:
        paths = _engine_kinematic(aoi, seeds, start, hours, run_dir)
    tc = _trajectories(paths)
    if tc is None:
        raise SystemExit("No trajectories produced.")

    # Mean smoke over the window the parcels actually occupy. Backward runs
    # look at the hours BEFORE the start time; averaging the following two days
    # would put the backdrop in the wrong place entirely.
    span = dt.timedelta(hours=abs(hours))
    lo, hi = ((start - span, start) if direction == "backward"
              else (start, start + span))
    # Frame the paths. Done before the backdrop is fetched so the smoke field
    # covers the whole figure rather than a rectangle in the middle of it.
    pts = [np.array(t.to_linestring().coords) for t in tc.trajectories]
    box = display_box(box, np.concatenate([p[:, 0] for p in pts]),
                      np.concatenate([p[:, 1] for p in pts]))
    region = ee.Geometry.Rectangle(box)

    smoke = os.path.join(run_dir, "_pm25.tif")
    window = (ee.ImageCollection(CAMS_IC).select(CAMS_PM25)
              .filterDate(lo.isoformat(), hi.isoformat()))
    # Unlike the receptor ranking, the backdrop is decorative: CAMS starts in
    # mid-2016, and refusing to draw 2015 trajectories over a blank background
    # would withhold the part that still works.
    if window.size().getInfo():
        img = window.mean().multiply(1e9).clip(region)
        smoke = download_geotiff(img, region.bounds().getInfo()["coordinates"],
                                 smoke, scale=44453)
    else:
        print("  (no CAMS PM2.5 for this window — trajectories only)")
        smoke = None

    from .exposure import _district_shapes, _districts
    shapes = _district_shapes(_districts(aoi))
    crossed = _crossed(tc, shapes)
    caveat = (HYSPLIT_CAVEAT.format(levels="/".join(f"{h:g}" for h in heights))
              if engine == "hysplit" else DEFAULT_CAVEAT)
    png = _render(run_dir, name, tc, seeds, smoke, box, d0, hours, crossed,
                  engine=engine, direction=direction, caveat=caveat,
                  seed_label=seed_label)

    stats = _stats(run_id, name, d0, hours, engine, direction, heights,
                   seeds, recept, tc, crossed, png)
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    verb = "menuju" if direction == "backward" else "dari"
    print(f"\n{name} — parsel {verb} {d0}, {abs(hours)} jam ({engine})")
    print(f"  panjang lintasan median: {stats['median_path_km']:,.0f} km")
    print("  kabupaten/kota terlintasi (jumlah lintasan):")
    for k, v in list(crossed.items())[:10]:
        print(f"    {k[:30]:30s} {v:4d}")
    print("\n  " + ("Lintasan HYSPLIT — bukan dispersi"
                    if engine == "hysplit" else "ILUSTRASI, bukan atribusi")
          + " — lihat catatan di stats.json")
    return stats
