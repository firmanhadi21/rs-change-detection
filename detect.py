#!/usr/bin/env python3
"""Multipurpose satellite change detection.

Pick a SCENARIO and a LOCATION; the scenario selects the remote-sensing method
(NDVI/NDBI/NDWI/NBR change, SIRAD radar, or SAR flood water). Results download
straight to disk as a PNG quick-look, a georeferenced GeoTIFF, and a stats JSON.

Examples
--------
    # List available scenarios
    python3 detect.py --list

    # Deforestation around a coordinate (radius 6 km)
    python3 detect.py -s deforestation --lat -3.333 --lon 122.25 -r 6

    # Same, coordinate as "lat,lon" (quote/`=` because lat is negative)
    python3 detect.py -s mining -l=-3.333,122.25

    # Flood: baseline window vs event window (both required)
    python3 detect.py -s flood --lat 24.9 --lon 67.9 \
        --pre 2022-06-01:2022-06-30 --post 2022-08-15:2022-09-05

    # Use a named preset from sites.py instead of a coordinate
    python3 detect.py -s mining --site konawe

Outputs (per run):
    images/<scenario>_<product>_<name>.png     quick-look
    data/<scenario>_<product>_<name>.tif       full-resolution GeoTIFF
    data/<scenario>_<name>_stats.json          statistics
"""

import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gee_utils import (  # noqa: E402
    download_png, download_geotiff, initialize_ee, square_aoi)
from scenarios import SCENARIOS, run_optical_change  # noqa: E402
from indices import (  # noqa: E402
    INDEX_FN, BUILTUP_METHODS, THERMAL_METHODS, METHOD_DEFAULTS)

try:
    import ee
except ImportError:
    sys.exit("Install earthengine-api: pip install earthengine-api")

IMAGES_DIR = os.path.join(HERE, "images")
DATA_DIR = os.path.join(HERE, "data")
MAPS_DIR = os.path.join(HERE, "maps")
CONFIG_KEY = os.path.join(HERE, "scripts", "config", "ee-geodetic.json")


def parse_period(text):
    """'YYYY-MM-DD:YYYY-MM-DD' -> (start, end)."""
    try:
        start, end = text.split(":")
        return start.strip(), end.strip()
    except ValueError:
        raise SystemExit(f"Bad date window '{text}'. Use START:END "
                         "(e.g. 2023-01-01:2023-12-31).")


def parse_location(text):
    """'lat,lon' -> (lat, lon)."""
    try:
        lat, lon = (float(x) for x in text.split(","))
        return lat, lon
    except ValueError:
        raise SystemExit(f"Bad location '{text}'. Use 'lat,lon' "
                         "(e.g. -3.333,122.25).")


def safe_name(text):
    return (text.replace(" ", "_").replace(",", "_")
                .replace(".", "p").replace("-", "m"))


def print_scenarios():
    print("Available scenarios (-s):\n")
    for key, cfg in SCENARIOS.items():
        print(f"  {key:<14} {cfg['label']}")
    print(f"\nBuilt-up methods (--method) · Sentinel-2: {', '.join(BUILTUP_METHODS)}")
    print(f"                            · Landsat (thermal, auto): {', '.join(THERMAL_METHODS)}")
    print("\nLocation: --lat LAT --lon LON  |  -l 'lat,lon'  |  --site NAME")


def resolve_location(args):
    """Return (lat, lon, radius_km, name)."""
    if args.site:
        sys.path.insert(0, HERE)
        from sites import get_site
        site = get_site(["--site", args.site])
        return site["lat"], site["lon"], site["radius_km"], args.site
    if args.location:
        lat, lon = parse_location(args.location)
    elif args.lat is not None and args.lon is not None:
        lat, lon = args.lat, args.lon
    else:
        raise SystemExit("Provide a location: --lat/--lon, -l 'lat,lon', "
                         "or --site NAME. See --help.")
    name = args.name or safe_name(f"{lat}_{lon}")
    return lat, lon, None, name


def build_params(scenario, args):
    """Assemble the params dict a scenario's run() expects."""
    cfg = SCENARIOS[scenario]
    needs = cfg.get("needs")
    p = {}

    if needs == "sirad":
        p["sirad_periods"] = cfg["sirad_periods"]
        return p

    if needs == "epochs":
        if args.epochs:
            windows = [parse_period(w) for w in args.epochs.split(",")]
        else:
            windows = cfg["epochs"]
        if len(windows) != 3:
            raise SystemExit("--epochs needs exactly 3 windows: W1,W2,W3 "
                             "(each START:END, e.g. 2010-01-01:2010-12-31)")
        p["epochs"] = windows
        return p

    # pre/post windows (optical + flood)
    pre = parse_period(args.pre) if args.pre else cfg.get("pre")
    post = parse_period(args.post) if args.post else cfg.get("post")
    if needs == "pre_post_required" and (not pre or not post):
        raise SystemExit(
            f"Scenario '{scenario}' needs explicit windows: "
            "--pre START:END --post START:END")
    p["pre"], p["post"] = pre, post
    return p


def apply_overrides(cfg, args):
    """Return a cfg copy with --method/--thr/--severe applied (optical only)."""
    cfg = dict(cfg)
    if cfg.get("method") != "optical":
        if args.method:
            print(f"(--method ignored — '{args.scenario}' is not index-based)")
        return cfg
    if args.method:
        m = args.method.upper()
        if m not in INDEX_FN:
            raise SystemExit(f"Unknown --method '{args.method}'. "
                             f"Options: {', '.join(sorted(INDEX_FN))}")
        direction, thr, severe, vmax = METHOD_DEFAULTS[m]
        sensor = "Landsat" if m in THERMAL_METHODS else "Sentinel-2"
        cfg.update(index=m, direction=direction, thr=thr, severe=severe, vmax=vmax,
                   label=f"{args.scenario.capitalize()} — {m} change ({sensor})")
    cfg.setdefault("vmax", METHOD_DEFAULTS.get(cfg["index"], (None, 0, 0, 0.6))[3])
    if args.thr is not None:
        cfg["thr"] = args.thr
    if args.severe is not None:
        cfg["severe"] = args.severe
    return cfg


def main():
    ap = argparse.ArgumentParser(
        description="Multipurpose satellite change detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("-s", "--scenario", choices=list(SCENARIOS))
    ap.add_argument("-l", "--location", help="'lat,lon' (use -l=-3.3,122.2 if lat<0)")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--site", help="named preset from sites.py")
    ap.add_argument("-r", "--radius", type=float, help="AOI radius in km")
    ap.add_argument("--pre", help="baseline window START:END")
    ap.add_argument("--post", help="recent/event window START:END")
    ap.add_argument("--epochs", help="urban-trend: three windows W1,W2,W3 "
                    "(each START:END), e.g. 2010-01-01:2010-12-31,...")
    ap.add_argument("-n", "--name", help="output label (default from coords)")
    ap.add_argument("--map", action="store_true",
                    help="also render an A4 map layout (PDF + PNG) per product")
    ap.add_argument("--basemap", choices=["osm", "gray", "none"], default="osm",
                    help="map basemap (default osm)")
    ap.add_argument("--backend", choices=["gee", "mpc"], default="gee",
                    help="data backend: gee (Earth Engine) or mpc "
                         "(Microsoft Planetary Computer, no account needed)")
    ap.add_argument("--method", help="override the index for optical scenarios "
                    "(e.g. urbanization: NDBI|UI|BU|IBI; also NDVI/NDWI/NBR)")
    ap.add_argument("--thr", type=float, help="override the 'affected' threshold")
    ap.add_argument("--severe", type=float, help="override the 'severe' threshold")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = ap.parse_args()

    if args.list or not args.scenario:
        print_scenarios()
        return

    cfg = SCENARIOS[args.scenario]
    lat, lon, site_radius, name = resolve_location(args)
    radius = args.radius or site_radius or cfg["radius"]
    params = build_params(args.scenario, args)

    cfg = apply_overrides(cfg, args)

    print(f"=== Change detection: {args.scenario} ===")
    print(f"{cfg['label']}")
    print(f"Location: {lat}, {lon}  radius {radius} km  [{name}]\n")

    # temporal window label for the map subtitle (both backends)
    if params.get("pre"):
        window = f"{params['pre'][0]} → {params['post'][1]}"
    elif params.get("sirad_periods"):
        sp = params["sirad_periods"]
        window = f"{sp[0][0]} → {sp[-1][1]}"
    elif params.get("epochs"):
        ep = params["epochs"]
        window = " · ".join(w[0][:4] for w in ep)
    else:
        window = None

    landsat = cfg.get("method") == "trend" or cfg.get("index") in THERMAL_METHODS
    provider = "Landsat C2-L2 (USGS/NASA)" if landsat else "Copernicus Sentinel (ESA)"

    if args.backend == "mpc":
        from mpc_backend import run_mpc
        run_mpc(args.scenario, cfg, lat, lon, radius, name, params,
                IMAGES_DIR, DATA_DIR, MAPS_DIR, window,
                do_map=args.map, basemap=args.basemap)
        return

    initialize_ee(CONFIG_KEY)
    aoi = square_aoi(lon, lat, radius)  # square clip (not a circle)

    if cfg.get("method") == "optical":
        result = run_optical_change(aoi, params, cfg["index"], cfg["direction"],
                                    cfg["thr"], cfg["severe"], cfg.get("vmax", 0.6))
    else:
        result = cfg["run"](aoi, params)

    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    for prod in result["products"]:
        base = f"{args.scenario}_{prod['key']}_{name}"
        png = os.path.join(IMAGES_DIR, base + ".png")
        tif = os.path.join(DATA_DIR, base + ".tif")
        print(f"Downloading {prod['key']} PNG...")
        download_png(prod["thumb"], aoi, png, vis=prod["thumb_vis"])
        print(f"Downloading {prod['key']} GeoTIFF...")
        download_geotiff(prod["tif"], aoi, tif, scale=prod.get("scale", 10))

        # sidecar meta so make_map.py can re-render offline (no GEE needed)
        is_rgb = "bands" in prod["thumb_vis"]
        vis = dict(prod["thumb_vis"])
        if not is_rgb and "label" not in vis:
            k = prod["key"]
            vis["label"] = ("Δ" + k[1:].upper()) if k.startswith("d") else k.upper()
        meta = {"tif": tif, "scenario": args.scenario, "label": cfg["label"],
                "product_key": prod["key"], "name": name,
                "source": "Google Earth Engine", "provider": provider,
                "lat": lat, "lon": lon, "radius_km": radius,
                "vis": vis, "is_rgb": is_rgb, "metric": vis.get("label"),
                "interpretation": result.get("interpretation",
                                             cfg.get("interpretation", "")),
                "stats": result["stats"], "window": window}
        with open(os.path.join(DATA_DIR, base + ".meta.json"), "w") as mf:
            json.dump(meta, mf, indent=2)

        if args.map:
            os.makedirs(MAPS_DIR, exist_ok=True)
            from mapmaker import render_map
            render_map(meta, os.path.join(MAPS_DIR, base + "_map"),
                       basemap=args.basemap)

    stats = {"scenario": args.scenario, "location": {"lat": lat, "lon": lon},
             "radius_km": radius, "results": result["stats"]}
    stats_path = os.path.join(DATA_DIR, f"{args.scenario}_{name}_stats.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    print("\n=== Results ===")
    print(json.dumps(result["stats"], indent=2))
    print(f"\n{result.get('interpretation', cfg.get('interpretation', ''))}")
    print(f"Stats: {os.path.normpath(stats_path)}")


if __name__ == "__main__":
    main()
