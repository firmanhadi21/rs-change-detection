#!/usr/bin/env python3
"""Transit accessibility scenario — SDG 11.2.1 "access to public transport".

Answers: *what share of the population can reach a public-transport stop on foot?*
following UN SDG indicator 11.2.1 (the metric behind figures like "public
transport now reaches 60% of the world's urban population").

Method (network-based, not naive circular buffers):
  1. Build the pedestrian street network from OpenStreetMap (Overpass) over the AOI.
  2. Load transit stops — from your GeoJSON (--transit-file) or, if omitted, fetched
     from OSM (bus stops, stations, BRT/tram platforms).
  3. Snap every stop to the nearest network node; run a multi-source Dijkstra so each
     node gets its shortest *walking distance along streets* to the nearest stop.
  4. Pull the WorldPop 100 m population grid (GEE) for the AOI. Snap each populated
     cell to the nearest network node; a cell has access if that node is within the
     walking-distance threshold (default 500 m; SDG 11.2.1 uses 500 m for buses and
     ~1 km for high-capacity rail).
  5. Report the population-weighted share with access, write a service-area polygon
     and the stops used, and render a map.

Because access is measured along the real street graph, a river or a limited-access
road with no crossing correctly blocks access even if a stop is close as the crow flies.

Backends: needs --backend gee (WorldPop lives in Earth Engine).
"""

import json
import math
import os

# Clear a stale external PROJ override (e.g. an OTB install exporting PROJ_LIB)
# before rasterio/pyproj load, or GeoTIFF CRS handling picks the wrong proj.db.
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Highway classes a pedestrian can use (mirrors osmnx 'walk' network filter).
WALK_HIGHWAY = {
    "footway", "path", "pedestrian", "living_street", "residential", "service",
    "unclassified", "tertiary", "tertiary_link", "secondary", "secondary_link",
    "primary", "primary_link", "trunk_link", "road", "track", "steps",
    "cycleway", "bridleway", "corridor",
}

DEFAULT_WALK_DIST = "500"          # metres, SDG 11.2.1 bus threshold
DEFAULT_POP_YEAR = 2020            # WorldPop GP 100 m global coverage 2000–2020
MAX_SNAP_M = 400.0                 # a cell/stop farther than this from any street is unsnapped


# ----------------------------- geometry helpers -----------------------------
def _proj(bbox):
    """Local equirectangular projection to metres (accurate over a city AOI)."""
    lon0, lat0 = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110570.0
    return (lambda lon, lat: ((lon - lon0) * kx, (lat - lat0) * ky),
            lambda x, y: (lon0 + x / kx, lat0 + y / ky))


def _haversine(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


# ----------------------------- OSM / Overpass -----------------------------
def _overpass(query, timeout=180):
    last = None
    for url in OVERPASS_URLS:
        try:
            r = requests.post(url, data={"data": query}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — try the next mirror
            last = e
            print(f"  Overpass {url.split('/')[2]} failed ({e.__class__.__name__}); trying next…")
    raise SystemExit(f"All Overpass mirrors failed: {last}")


def _walk_graph(bbox):
    """Build a walking network graph from OSM over bbox=(w,s,e,n).

    Returns (G, node_lonlat) where G is a networkx.Graph with edge 'length' in
    metres and node_lonlat maps node id -> (lon, lat).
    """
    import networkx as nx
    w, s, e, n = bbox
    hw = "|".join(sorted(WALK_HIGHWAY))
    q = (f"[out:json][timeout:150];"
         f'way["highway"~"^({hw})$"]["foot"!~"^(no|private)$"]'
         f'["access"!~"^(private|no)$"]({s},{w},{n},{e});'
         f"(._;>;);out body;")
    print("  fetching walking network from OpenStreetMap…")
    data = _overpass(q)
    coords = {el["id"]: (el["lon"], el["lat"])
              for el in data["elements"] if el["type"] == "node"}
    G = nx.Graph()
    for el in data["elements"]:
        if el["type"] != "way":
            continue
        nds = el.get("nodes", [])
        for a, b in zip(nds[:-1], nds[1:]):
            if a not in coords or b not in coords:
                continue
            la, lb = coords[a], coords[b]
            d = _haversine(la[0], la[1], lb[0], lb[1])
            if G.has_edge(a, b):
                if d < G[a][b]["length"]:
                    G[a][b]["length"] = d
            else:
                G.add_edge(a, b, length=d)
    node_lonlat = {nid: coords[nid] for nid in G.nodes if nid in coords}
    print(f"  network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G, node_lonlat


def _stops_from_osm(bbox):
    w, s, e, n = bbox
    q = (f"[out:json][timeout:120];("
         f'node["highway"="bus_stop"]({s},{w},{n},{e});'
         f'node["public_transport"="platform"]({s},{w},{n},{e});'
         f'node["public_transport"="stop_position"]({s},{w},{n},{e});'
         f'node["railway"~"^(station|halt|tram_stop)$"]({s},{w},{n},{e});'
         f'node["amenity"="bus_station"]({s},{w},{n},{e});'
         f'way["amenity"="bus_station"]({s},{w},{n},{e});'
         f");out center;")
    print("  fetching transit stops from OpenStreetMap…")
    data = _overpass(q)
    pts = []
    for el in data["elements"]:
        if el["type"] == "node":
            pts.append((el["lon"], el["lat"]))
        elif "center" in el:
            pts.append((el["center"]["lon"], el["center"]["lat"]))
    return pts


def _sample_line(coords, step_m=250.0):
    """Sample points every ~step_m along a LineString given as [(lon,lat),...]."""
    out = [tuple(coords[0])]
    acc = 0.0
    for a, b in zip(coords[:-1], coords[1:]):
        seg = _haversine(a[0], a[1], b[0], b[1])
        acc += seg
        if acc >= step_m:
            out.append((b[0], b[1]))
            acc = 0.0
    out.append(tuple(coords[-1]))
    return out


def _stops_from_file(path):
    """Load stops from a GeoJSON of Points and/or LineStrings (routes)."""
    with open(path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    pts = []
    for ft in feats:
        g = ft.get("geometry", ft)
        t, c = g.get("type"), g.get("coordinates")
        if t == "Point":
            pts.append((c[0], c[1]))
        elif t == "MultiPoint":
            pts += [(p[0], p[1]) for p in c]
        elif t == "LineString":
            pts += _sample_line(c)
        elif t == "MultiLineString":
            for line in c:
                pts += _sample_line(line)
    return pts


# ----------------------------- accessibility core -----------------------------
def _node_arrays(node_lonlat, to_m):
    import numpy as np
    ids = list(node_lonlat)
    xy = np.array([to_m(*node_lonlat[i]) for i in ids])
    return ids, xy


def _snap(pts, node_ids, node_xy, tree, to_m):
    """Snap lon/lat points to nearest network node id (within MAX_SNAP_M)."""
    import numpy as np
    if not pts:
        return []
    q = np.array([to_m(p[0], p[1]) for p in pts])
    dist, idx = tree.query(q, k=1)
    out = []
    for d, i in zip(np.atleast_1d(dist), np.atleast_1d(idx)):
        if d <= MAX_SNAP_M:
            out.append(node_ids[int(i)])
    return sorted(set(out))


def _dijkstra_node_dist(G, sources, cutoff):
    import networkx as nx
    src = [s for s in sources if s in G]
    if not src:
        raise SystemExit("No transit stop could be snapped to the walking network.")
    return nx.multi_source_dijkstra_path_length(G, src, cutoff=cutoff, weight="length")


def _service_polygon(G, node_lonlat, served_nodes, to_m, to_ll, buffer_m):
    """Union of served street segments, buffered, as a lon/lat shapely polygon."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union, transform
    served = set(served_nodes)
    segs = []
    for a, b in G.edges():
        if a in served and b in served and a in node_lonlat and b in node_lonlat:
            (xa, ya), (xb, yb) = to_m(*node_lonlat[a]), to_m(*node_lonlat[b])
            segs.append(LineString([(xa, ya), (xb, yb)]))
    if not segs:
        return None
    poly_m = unary_union(segs).buffer(buffer_m)
    return transform(lambda xs, ys, z=None: to_ll(xs, ys), poly_m)


# ----------------------------- WorldPop -----------------------------
def _worldpop_tif(aoi, region, year, run_dir):
    import ee
    from .gee_utils import download_geotiff
    coll = (ee.ImageCollection("WorldPop/GP/100m/pop")
            .filter(ee.Filter.eq("year", year)).filterBounds(aoi))
    if coll.size().getInfo() == 0:  # fall back to nearest available year
        yrs = (ee.ImageCollection("WorldPop/GP/100m/pop").filterBounds(aoi)
               .aggregate_array("year").getInfo())
        if not yrs:
            raise SystemExit("WorldPop has no coverage over this AOI.")
        year = min(yrs, key=lambda y: abs(y - year))
        coll = (ee.ImageCollection("WorldPop/GP/100m/pop")
                .filter(ee.Filter.eq("year", year)).filterBounds(aoi))
        print(f"  WorldPop: requested year unavailable, using {year}")
    img = coll.mosaic().select("population").clip(aoi)
    path = os.path.join(run_dir, "worldpop.tif")
    out = download_geotiff(img, region, path, scale=100)
    if out is None:
        raise SystemExit("WorldPop download failed — try a smaller --radius.")
    return out, year


def _population_access(pop_path, G, node_lonlat, node_dist, thresholds,
                       to_m, tree, node_ids):
    """Return (stats-per-threshold, primary_served_nodes, grid dict for the map)."""
    import numpy as np
    import rasterio
    with rasterio.open(pop_path) as ds:
        pop = ds.read(1).astype("float64")
        if ds.nodata is not None:
            pop[pop == ds.nodata] = 0.0
        pop[~np.isfinite(pop)] = 0.0
        pop[pop < 0] = 0.0
        T = ds.transform
        H, W = pop.shape
    lon = T.c + T.a * (np.arange(W) + 0.5)
    lat = T.f + T.e * (np.arange(H) + 0.5)
    lon2d, lat2d = np.meshgrid(lon, lat)

    popf = pop.ravel()
    sel = popf > 0
    total_pop = float(popf.sum())
    # Snap each populated cell to its nearest network node (metric coords via to_m).
    plon = lon2d.ravel()[sel]; plat = lat2d.ravel()[sel]
    qx = np.empty(plon.size); qy = np.empty(plon.size)
    for k in range(plon.size):
        qx[k], qy[k] = to_m(plon[k], plat[k])
    dist, idx = tree.query(np.column_stack([qx, qy]), k=1)
    # Per-cell nearest-node walking-distance-to-stop (inf if node unreachable).
    near_nodes = [node_ids[int(i)] for i in idx]
    cell_node_dist = np.array([node_dist.get(nid, np.inf) for nid in near_nodes])
    snap_ok = dist <= MAX_SNAP_M
    cell_pop = popf[sel]

    stats = []
    primary_served_nodes = None
    for j, thr in enumerate(thresholds):
        served = snap_ok & (cell_node_dist <= thr)
        served_pop = float(cell_pop[served].sum())
        stats.append({
            "walk_dist_m": thr,
            "pop_total": round(total_pop),
            "pop_with_access": round(served_pop),
            "pct_with_access": round(100.0 * served_pop / total_pop, 1) if total_pop else 0.0,
        })
        if j == 0:
            primary_served_nodes = {nid for nid, d in node_dist.items() if d <= thr}
    grid = {"lon": lon, "lat": lat, "pop": pop}
    return stats, primary_served_nodes, grid


# ----------------------------- rendering -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _add_basemap(ax):
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.CartoDB.Positron,
                       attribution_size=5)
    except Exception as e:  # noqa: BLE001 — basemap is optional
        print(f"  (basemap skipped: {e.__class__.__name__})")


def _render_map(run_dir, name, bbox, grid, service_poly, stops, primary_stats):
    plt = _plt()
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    w, s, e, n = bbox
    pop = grid["pop"].copy()
    pop[pop <= 0] = np.nan
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    # Population density (log-ish via percentile clip).
    finite = pop[np.isfinite(pop)]
    vmax = float(np.nanpercentile(finite, 97)) if finite.size else 1.0
    cmap = LinearSegmentedColormap.from_list("pop", ["#ffffcc", "#fd8d3c", "#800026"])
    im = ax.imshow(pop, extent=[w, e, s, n], origin="upper", cmap=cmap,
                   vmin=0, vmax=max(vmax, 1.0), alpha=0.75, zorder=2)
    if service_poly is not None and not service_poly.is_empty:
        geoms = getattr(service_poly, "geoms", [service_poly])
        first = True
        for g in geoms:
            xs, ys = g.exterior.xy
            ax.fill(xs, ys, facecolor="#2c7fb8", edgecolor="#08519c", lw=0.6,
                    alpha=0.28, zorder=4, label="Area terlayani" if first else None)
            first = False
    if stops:
        ax.scatter([p[0] for p in stops], [p[1] for p in stops], s=9,
                   c="#08306b", edgecolors="white", linewidths=0.3, zorder=6,
                   label="Halte/stasiun")
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="Populasi / sel 100 m (WorldPop)")
    pct = primary_stats["pct_with_access"]
    d = primary_stats["walk_dist_m"]
    ax.set_title(f"Akses transportasi publik — {name}\n"
                 f"{pct:.0f}% populasi dalam {d:.0f} m jalan kaki ke halte "
                 f"(SDG 11.2.1)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "transit_access_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        transit_file=None, walk_dist=DEFAULT_WALK_DIST, pop_year=DEFAULT_POP_YEAR,
        access_buffer=100.0):
    """Compute SDG 11.2.1 transit accessibility for a city AOI (GEE backend)."""
    for mod in ("networkx", "shapely", "rasterio", "numpy", "scipy"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(f"transit-access needs {mod}: pip install 'satchange[transit]'")
    if backend == "mpc":
        raise SystemExit("transit-access currently needs --backend gee (WorldPop).")

    import numpy as np
    from scipy.spatial import cKDTree
    from .gee_utils import initialize_ee, square_aoi

    thresholds = sorted({float(x) for x in str(walk_dist).split(",") if x.strip()})
    if not thresholds:
        thresholds = [500.0]
    cutoff = max(thresholds)

    initialize_ee(config_key)
    aoi = square_aoi(lon, lat, radius)
    b = aoi.bounds().coordinates().getInfo()[0]
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    to_m, to_ll = _proj(bbox)

    # 1. Walking network.
    G, node_lonlat = _walk_graph(bbox)
    if G.number_of_nodes() == 0:
        raise SystemExit("OpenStreetMap returned no walkable streets for this AOI.")
    node_ids, node_xy = _node_arrays(node_lonlat, to_m)
    tree = cKDTree(node_xy)

    # 2. Stops.
    if transit_file:
        stops = _stops_from_file(transit_file)
        src = f"file ({len(stops)})"
    else:
        stops = _stops_from_osm(bbox)
        src = f"OSM ({len(stops)})"
    if not stops:
        raise SystemExit("No transit stops found — pass --transit-file with your stops.")
    with open(os.path.join(run_dir, "stops.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry":
             {"type": "Point", "coordinates": [p[0], p[1]]}} for p in stops]}, f)
    print(f"Stops: {src}")

    # 3. Snap stops → multi-source Dijkstra (walking distance to nearest stop per node).
    src_nodes = _snap(stops, node_ids, node_xy, tree, to_m)
    print(f"  snapped {len(src_nodes)} stop nodes; routing (cutoff {cutoff:.0f} m)…")
    node_dist = _dijkstra_node_dist(G, src_nodes, cutoff)

    # 4. WorldPop + population-weighted access.
    pop_path, used_year = _worldpop_tif(aoi, aoi, pop_year, run_dir)
    per_thr, served_nodes, grid = _population_access(
        pop_path, G, node_lonlat, node_dist, thresholds, to_m, tree, node_ids)

    # 5. Service-area polygon + map.
    service_poly = _service_polygon(G, node_lonlat, served_nodes, to_m, to_ll, access_buffer)
    if service_poly is not None:
        from shapely.geometry import mapping
        with open(os.path.join(run_dir, "service_area.geojson"), "w") as f:
            json.dump({"type": "Feature",
                       "properties": {"walk_dist_m": thresholds[0]},
                       "geometry": mapping(service_poly)}, f)
    _render_map(run_dir, name, bbox, grid, service_poly, stops, per_thr[0])

    primary = per_thr[0]
    for t in per_thr:
        print(f"  ≤ {t['walk_dist_m']:.0f} m: {t['pct_with_access']:.1f}% "
              f"({t['pop_with_access']:,} / {t['pop_total']:,})")
    stats = {"run_id": run_id, "scenario": "transit-access",
             "method": "SDG 11.2.1 network walking distance to nearest stop",
             "worldpop_year": used_year, "stops_source": src,
             "n_stops": len(stops), "n_stops_snapped": len(src_nodes),
             "network_nodes": G.number_of_nodes(), "network_edges": G.number_of_edges(),
             "access_buffer_m": access_buffer,
             "thresholds": per_thr,
             "pct_with_access": primary["pct_with_access"],
             "pop_total": primary["pop_total"],
             "pop_with_access": primary["pop_with_access"]}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nSDG 11.2.1: {primary['pct_with_access']:.0f}% of {primary['pop_total']:,} "
          f"people are within {thresholds[0]:.0f} m walk of a stop.")
    return stats
