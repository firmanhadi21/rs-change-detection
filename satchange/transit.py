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
def _overpass(query, timeout=180, rounds=4):
    """POST a query to Overpass, cycling mirrors and retrying with backoff.

    Public Overpass servers routinely return 429/504 under load, so a single
    pass over the mirrors is not enough for a reliable city-scale fetch. Each
    round tries every mirror; between rounds we wait (20 s, 40 s, 60 s…) to let
    a busy server recover.
    """
    import time
    last = None
    for attempt in range(rounds):
        for url in OVERPASS_URLS:
            try:
                return _overpass_try(url, query, timeout)
            except Exception as e:  # noqa: BLE001 — try the next mirror
                last = e
                print(f"  Overpass {url.split('/')[2]} failed ({e.__class__.__name__}); trying next…")
        if attempt < rounds - 1:
            wait = 20 * (attempt + 1)
            print(f"  all mirrors busy; waiting {wait}s before retry "
                  f"{attempt + 2}/{rounds}…")
            time.sleep(wait)
    raise SystemExit(f"All Overpass mirrors failed after {rounds} rounds: {last}")


def _overpass_try(url, query, timeout):
    """One Overpass POST; raises on a transient status so the caller can fail over."""
    r = requests.post(url, data={"data": query}, timeout=timeout)
    if r.status_code in (429, 502, 503, 504):
        raise requests.HTTPError(f"HTTP {r.status_code}")
    r.raise_for_status()
    return r.json()


def _walk_graph(bbox):
    """Build a walking network graph from OSM over bbox=(w,s,e,n).

    Returns (G, node_lonlat) where G is a networkx.Graph with edge 'length' in
    metres and node_lonlat maps node id -> (lon, lat).
    """
    import math
    import networkx as nx
    w, s, e, n = bbox
    hw = "|".join(sorted(WALK_HIGHWAY))

    def query(ts, tw, tn, te):
        return (f"[out:json][timeout:300];"
                f'way["highway"~"^({hw})$"]["foot"!~"^(no|private)$"]'
                f'["access"!~"^(private|no)$"]({ts},{tw},{tn},{te});'
                f"(._;>;);out body;")

    # A single Overpass query for a whole big-city bbox 504s; split into tiles of
    # at most ~MAXSPAN degrees per side so each sub-request is small enough to serve.
    MAXSPAN = 0.11
    ncol = max(1, math.ceil((e - w) / MAXSPAN))
    nrow = max(1, math.ceil((n - s) / MAXSPAN))
    if ncol * nrow > 1:
        print(f"  fetching walking network from OpenStreetMap ({ncol}×{nrow} tiles)…")
    else:
        print("  fetching walking network from OpenStreetMap…")

    coords, ways = {}, []
    for r in range(nrow):
        for c in range(ncol):
            tw = w + (e - w) * c / ncol; te = w + (e - w) * (c + 1) / ncol
            ts = s + (n - s) * r / nrow; tn = s + (n - s) * (r + 1) / nrow
            data = _overpass(query(ts, tw, tn, te), timeout=330)
            for el in data["elements"]:
                if el["type"] == "node":
                    coords[el["id"]] = (el["lon"], el["lat"])
                elif el["type"] == "way":
                    ways.append(el.get("nodes", []))
            if ncol * nrow > 1:
                print(f"    tile {r * ncol + c + 1}/{ncol * nrow}: "
                      f"{len(coords)} nodes so far")

    G = _graph_from_ways(ways, coords)
    node_lonlat = {nid: coords[nid] for nid in G.nodes if nid in coords}
    print(f"  network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G, node_lonlat


def _graph_from_ways(ways, coords):
    """Build an undirected networkx graph (edge 'length' m) from OSM way node-lists."""
    import networkx as nx
    G = nx.Graph()
    for nds in ways:
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
    return G


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


# ----------------------------- admin boundary -----------------------------
def _boundary_from_geojson(gj):
    """First Polygon/MultiPolygon in a GeoJSON as a shapely geometry (lon/lat)."""
    from shapely.geometry import shape
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    for ft in feats:
        g = ft.get("geometry", ft)
        if g.get("type") in ("Polygon", "MultiPolygon"):
            return shape(g)
    raise SystemExit("boundary file has no Polygon/MultiPolygon geometry.")


def _load_boundary_file(path):
    return _boundary_from_geojson(json.load(open(path)))


def _fetch_boundary(name):
    """Fetch an administrative boundary polygon by name from OSM Nominatim."""
    from shapely.geometry import shape
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": name, "format": "jsonv2",
                             "polygon_geojson": 1, "limit": 8},
                     headers={"User-Agent": "satchange transit-access (boundary lookup)"},
                     timeout=60)
    r.raise_for_status()
    results = r.json()
    polys = [x for x in results
             if x.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")]
    if not polys:
        raise SystemExit(f"Nominatim found no polygon boundary for {name!r}. "
                         "Try a more specific name or pass --aoi-file.")
    # Prefer an administrative boundary / city over a point-of-interest polygon.
    def rank(x):
        return (x.get("category") == "boundary",
                x.get("addresstype") in ("city", "administrative", "county"))
    best = sorted(polys, key=rank, reverse=True)[0]
    print(f"  boundary: {best.get('display_name', name)[:70]}  "
          f"[{best.get('category')}/{best.get('type')}]")
    return shape(best["geojson"])


# ----------------------------- accessibility core -----------------------------
def _node_arrays(node_lonlat, to_m):
    import numpy as np
    ids = list(node_lonlat)
    xy = np.array([to_m(*node_lonlat[i]) for i in ids])
    return ids, xy
def _node_arrays(node_lonlat, to_m):
    import numpy as np
    ids = list(node_lonlat)
    xy = np.array([to_m(*node_lonlat[i]) for i in ids])
    return ids, xy


def _snap(pts, tree, to_m, snap_m=MAX_SNAP_M):
    """Snap lon/lat points to their nearest network-node INDEX (within snap_m)."""
    import numpy as np
    if not pts:
        return []
    q = np.array([to_m(p[0], p[1]) for p in pts])
    dist, idx = tree.query(q, k=1)
    d = np.atleast_1d(dist); i = np.atleast_1d(idx)
    return sorted({int(j) for dj, j in zip(d, i) if dj <= snap_m})


def _route_min_dist(G, node_ids, id_to_idx, source_idx, cutoff):
    """Min walking distance from ANY source node to every node (scipy csgraph).

    Returns a float array aligned to the node_ids index; entries beyond `cutoff`
    are inf. Uses scipy's C-level Dijkstra with min_only=True (a single pass over
    the graph from all sources at once) — orders of magnitude faster than a
    pure-Python multi-source Dijkstra on a city-sized network (~300k nodes).
    """
    import numpy as np
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    if not source_idx:
        raise SystemExit("No transit stop could be snapped to the walking network.")
    n = len(node_ids)
    m = G.number_of_edges()
    rows = np.empty(2 * m, dtype=np.int64)
    cols = np.empty(2 * m, dtype=np.int64)
    data = np.empty(2 * m, dtype=np.float64)
    k = 0
    for a, b, w in G.edges(data="length"):
        ia, ib = id_to_idx[a], id_to_idx[b]
        rows[k] = ia; cols[k] = ib; data[k] = w; k += 1
        rows[k] = ib; cols[k] = ia; data[k] = w; k += 1
    csr = csr_matrix((data, (rows, cols)), shape=(n, n))
    return dijkstra(csr, directed=False, indices=list(source_idx),
                    limit=cutoff, min_only=True)


def _service_polygon(G, node_lonlat, served_nodes, to_m, to_ll, buffer_m):
    """Buffered union of served street segments, as a lon/lat shapely polygon.

    Buffering a single MultiLineString dissolves the segments inside GEOS (C),
    which is far faster than a Python-level unary_union of many LineStrings on a
    city-sized served network.
    """
    from shapely.geometry import MultiLineString
    from shapely.ops import transform
    served = set(served_nodes)
    segs = []
    for a, b in G.edges():
        if a in served and b in served and a in node_lonlat and b in node_lonlat:
            segs.append((to_m(*node_lonlat[a]), to_m(*node_lonlat[b])))
    if not segs:
        return None
    poly_m = MultiLineString(segs).buffer(buffer_m, quad_segs=2)
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


def _population_access(pop_path, dist_arr, thresholds, to_m, tree, boundary_geom=None,
                       snap_m=MAX_SNAP_M):
    """Return (stats-per-threshold, primary_served_node_indices, grid dict).

    `dist_arr` is the per-node walking distance to the nearest stop, aligned to
    the KDTree's node index. Each populated WorldPop cell is snapped to its
    nearest network node and inherits that node's distance-to-stop. When
    `boundary_geom` is given, only cells inside it are *counted* (the reported
    share is over that administrative area) — but the full population raster is
    still returned for display, so the map is not blanked outside the boundary.
    """
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
    inside = np.ones(popf.size, dtype=bool)
    if boundary_geom is not None:
        from rasterio.features import rasterize
        mask = rasterize([(boundary_geom, 1)], out_shape=(H, W), transform=T,
                         fill=0, dtype="uint8")
        inside = mask.ravel().astype(bool)
        print(f"  counting population within boundary ({int(inside.sum()):,} cells inside)")
    sel = (popf > 0) & inside                        # cells that count toward the %
    total_pop = float(popf[sel].sum())
    # Snap every counted cell to its nearest network node (vectorised projection).
    plon = lon2d.ravel()[sel]; plat = lat2d.ravel()[sel]
    qx, qy = to_m(plon, plat)                         # to_m is pure arithmetic → vectorises
    dist, idx = tree.query(np.column_stack([qx, qy]), k=1)
    cell_node_dist = np.where(dist <= snap_m, dist_arr[idx], np.inf)
    cell_pop = popf[sel]

    stats = []
    for thr in thresholds:
        served = cell_node_dist <= thr
        served_pop = float(cell_pop[served].sum())
        stats.append({
            "walk_dist_m": thr,
            "pop_total": round(total_pop),
            "pop_with_access": round(served_pop),
            "pct_with_access": round(100.0 * served_pop / total_pop, 1) if total_pop else 0.0,
        })
    primary_served_idx = np.where(dist_arr <= thresholds[0])[0]
    grid = {"lon": lon, "lat": lat, "pop": pop}       # full raster for display (not blanked)
    return stats, primary_served_idx, grid


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


def _network_segments(G, node_lonlat, served_nodes):
    """Split walking-network edges into (served, other) lon/lat segment lists."""
    served = set(served_nodes or [])
    seg_served, seg_other = [], []
    for a, b in G.edges():
        if a not in node_lonlat or b not in node_lonlat:
            continue
        seg = (node_lonlat[a], node_lonlat[b])
        (seg_served if (a in served and b in served) else seg_other).append(seg)
    return seg_served, seg_other


def _render_map(run_dir, name, bbox, grid, service_poly, stops, primary_stats,
                G=None, node_lonlat=None, served_nodes=None, boundary_geom=None):
    plt = _plt()
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    w, s, e, n = bbox
    pop = grid["pop"].copy()
    pop[pop <= 0] = np.nan
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    _add_basemap(ax)
    # Population density (percentile-clipped).
    finite = pop[np.isfinite(pop)]
    vmax = float(np.nanpercentile(finite, 97)) if finite.size else 1.0
    cmap = LinearSegmentedColormap.from_list("pop", ["#ffffcc", "#fd8d3c", "#800026"])
    im = ax.imshow(pop, extent=[w, e, s, n], origin="upper", cmap=cmap,
                   vmin=0, vmax=max(vmax, 1.0), alpha=0.65, zorder=2)
    handles = [Patch(facecolor="#800026", edgecolor="none", label="Populasi (WorldPop)")]

    # OSM walking network: streets beyond reach in grey, within reach in green.
    if G is not None and node_lonlat is not None:
        seg_served, seg_other = _network_segments(G, node_lonlat, served_nodes)
        if seg_other:
            ax.add_collection(LineCollection(seg_other, colors="#6b7280",
                                             linewidths=0.25, alpha=0.5, zorder=3,
                                             rasterized=True, antialiaseds=False))
            handles.append(Line2D([0], [0], color="#6b7280", lw=1.0,
                                  label="Jaringan jalan OSM"))
        if seg_served:
            ax.add_collection(LineCollection(seg_served, colors="#1a9850",
                                             linewidths=0.6, alpha=0.9, zorder=5,
                                             rasterized=True))
            handles.append(Line2D([0], [0], color="#1a9850", lw=1.4,
                                  label="Jalan dalam jangkauan"))

    if service_poly is not None and not service_poly.is_empty:
        for g in getattr(service_poly, "geoms", [service_poly]):
            xs, ys = g.exterior.xy
            ax.fill(xs, ys, facecolor="#2c7fb8", edgecolor="none", alpha=0.18, zorder=4)
        handles.append(Patch(facecolor="#2c7fb8", alpha=0.35, label="Area terlayani"))
    if stops:
        ax.scatter([p[0] for p in stops], [p[1] for p in stops], s=11,
                   c="#08306b", edgecolors="white", linewidths=0.3, zorder=6)
        handles.append(Line2D([0], [0], marker="o", color="none",
                              markerfacecolor="#08306b", markeredgecolor="white",
                              markersize=6, label="Halte BRT / stasiun"))
    if boundary_geom is not None:
        for g in getattr(boundary_geom, "geoms", [boundary_geom]):
            xs, ys = g.exterior.xy
            ax.plot(xs, ys, color="#111", lw=1.6, zorder=7)
        handles.append(Line2D([0], [0], color="#111", lw=1.6, label="Batas wilayah"))
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="Populasi / sel 100 m (WorldPop)")
    pct = primary_stats["pct_with_access"]
    d = primary_stats["walk_dist_m"]
    ax.set_title(f"Akses transportasi publik — {name}\n"
                 f"{pct:.0f}% populasi dalam {d:.0f} m jalan kaki ke halte "
                 f"(SDG 11.2.1)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
    ax.grid(True, ls=":", color="#888", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(run_dir, "transit_access_map.png")
    fig.savefig(out); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def _resolve_boundary(boundary, aoi_file, lat, lon, radius):
    """Resolve an optional admin boundary and auto-size the AOI to it.

    Leaves ~1.5 km margin so stops just outside the line still serve edge cells.
    Returns (boundary_geom_or_None, lat, lon, radius).
    """
    import math
    geom = None
    if aoi_file:
        geom = _load_boundary_file(aoi_file)
        print(f"Boundary: file {aoi_file}")
    elif boundary:
        print(f"Boundary: fetching '{boundary}' from OpenStreetMap…")
        geom = _fetch_boundary(boundary)
    if geom is None:
        return None, lat, lon, radius
    minx, miny, maxx, maxy = geom.bounds
    lon, lat = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    half_lon_km = (maxx - minx) / 2.0 * 111.32 * math.cos(math.radians(lat))
    half_lat_km = (maxy - miny) / 2.0 * 110.57
    radius = max(half_lon_km, half_lat_km) + 1.5
    print(f"  AOI auto-sized to boundary: centre ({lat:.4f}, {lon:.4f}), radius {radius:.1f} km")
    return geom, lat, lon, radius


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        transit_file=None, walk_dist=DEFAULT_WALK_DIST, pop_year=DEFAULT_POP_YEAR,
        access_buffer=100.0, boundary=None, aoi_file=None, snap_dist=MAX_SNAP_M):
    """Compute SDG 11.2.1 transit accessibility for a city AOI (GEE backend).

    If `boundary` (a place name, fetched from OSM) or `aoi_file` (a local GeoJSON
    polygon) is given, the AOI is auto-sized to that boundary and the reported
    population share is computed over it — not the square AOI box.
    """
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

    boundary_geom, lat, lon, radius = _resolve_boundary(boundary, aoi_file, lat, lon, radius)

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
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
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

    # 3. Snap stops → scipy multi-source Dijkstra (walking distance to nearest stop).
    src_idx = _snap(stops, tree, to_m, snap_m=snap_dist)
    print(f"  snapped {len(src_idx)} stop nodes; routing (cutoff {cutoff:.0f} m, "
          f"snap {snap_dist:.0f} m)…")
    dist_arr = _route_min_dist(G, node_ids, id_to_idx, src_idx, cutoff)

    # 4. WorldPop + population-weighted access (counted within boundary if given).
    pop_path, used_year = _worldpop_tif(aoi, aoi, pop_year, run_dir)
    per_thr, served_idx, grid = _population_access(pop_path, dist_arr, thresholds, to_m, tree,
                                                   boundary_geom=boundary_geom, snap_m=snap_dist)
    served_nodes = {node_ids[i] for i in served_idx}

    # 5. Service-area polygon + boundary + map.
    from shapely.geometry import mapping
    service_poly = _service_polygon(G, node_lonlat, served_nodes, to_m, to_ll, access_buffer)
    if service_poly is not None:
        with open(os.path.join(run_dir, "service_area.geojson"), "w") as f:
            json.dump({"type": "Feature",
                       "properties": {"walk_dist_m": thresholds[0]},
                       "geometry": mapping(service_poly)}, f)
    if boundary_geom is not None:
        with open(os.path.join(run_dir, "boundary.geojson"), "w") as f:
            json.dump({"type": "Feature", "properties": {"name": boundary or aoi_file},
                       "geometry": mapping(boundary_geom)}, f)
    _render_map(run_dir, name, bbox, grid, service_poly, stops, per_thr[0],
                G=G, node_lonlat=node_lonlat, served_nodes=served_nodes,
                boundary_geom=boundary_geom)

    primary = per_thr[0]
    area = boundary or aoi_file or "AOI (kotak)"
    for t in per_thr:
        print(f"  ≤ {t['walk_dist_m']:.0f} m: {t['pct_with_access']:.1f}% "
              f"({t['pop_with_access']:,} / {t['pop_total']:,})")
    stats = {"run_id": run_id, "scenario": "transit-access",
             "method": "SDG 11.2.1 network walking distance to nearest stop",
             "population_area": area, "boundary_clipped": boundary_geom is not None,
             "worldpop_year": used_year, "stops_source": src,
             "n_stops": len(stops), "n_stops_snapped": len(src_idx),
             "network_nodes": G.number_of_nodes(), "network_edges": G.number_of_edges(),
             "access_buffer_m": access_buffer, "snap_dist_m": snap_dist,
             "thresholds": per_thr,
             "pct_with_access": primary["pct_with_access"],
             "pop_total": primary["pop_total"],
             "pop_with_access": primary["pop_with_access"]}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nSDG 11.2.1 [{area}]: {primary['pct_with_access']:.0f}% of "
          f"{primary['pop_total']:,} people are within {thresholds[0]:.0f} m walk of a stop.")
    return stats
