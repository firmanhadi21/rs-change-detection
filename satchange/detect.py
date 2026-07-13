#!/usr/bin/env python3
"""Multipurpose satellite change detection.

Pick a SCENARIO and a LOCATION; the scenario selects the remote-sensing method
(NDVI/NDBI/NDWI/NBR change, SIRAD radar, or SAR flood water). Results download
straight to disk as a PNG quick-look, a georeferenced GeoTIFF, and a stats JSON.

Examples (installed CLI — after `pip install satchange`)
--------
    # List available scenarios
    satchange --list

    # Deforestation around a coordinate (radius 6 km)
    satchange -s deforestation --lat -3.333 --lon 122.25 -r 6

    # Same, coordinate as "lat,lon" (quote/`=` because lat is negative)
    satchange -s mining -l=-3.333,122.25

    # Flood: baseline window vs event window (both required)
    satchange -s flood --lat 24.9 --lon 67.9 \
        --pre 2022-06-01:2022-06-30 --post 2022-08-15:2022-09-05

    # Disturbance (flood/landslide impact in terrain, when flood shows nothing)
    satchange -s disturbance --lat 1.9983 --lon 99.4235 \
        --pre 2025-11-01:2025-11-11 --post 2025-11-26:2025-11-29

    # Urban history: built-up by decade since 1980 (GHSL + Landsat), a metro area
    satchange -s urban-history --lat -6.2 --lon 106.85 --radius 45 -n jabodetabek

    # Use a named preset from sites.py instead of a coordinate
    satchange -s mining --site konawe

    # From a source checkout (no install), swap `satchange` for `python3 detect.py`.

Outputs (per run):
    images/<scenario>_<product>_<name>.png     quick-look
    data/<scenario>_<product>_<name>.tif       full-resolution GeoTIFF
    data/<scenario>_<name>_stats.json          statistics
"""

import os
import sys
import json
import uuid
import argparse
from datetime import datetime

from .gee_utils import (
    download_png, download_geotiff, initialize_ee, square_aoi)
from .scenarios import SCENARIOS, run_optical_change
from .indices import (
    INDEX_FN, BUILTUP_METHODS, THERMAL_METHODS, METHOD_DEFAULTS)

# Outputs and credentials are resolved against the current working directory,
# so an installed package writes results where the user runs it (not site-packages).
OUTPUT_ROOT = os.path.join(os.getcwd(), "output")
CONFIG_KEY = os.path.join(os.getcwd(), "scripts", "config", "ee-geodetic.json")


def new_run_dir(scenario, name):
    """Create output/<timestamp>_<scenario>_<name>_<token>/ and return it."""
    run_id = (f"{datetime.now():%Y%m%d-%H%M%S}_{scenario}_{name}"
              f"_{uuid.uuid4().hex[:6]}")
    run_dir = os.path.join(OUTPUT_ROOT, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_id, run_dir


def list_outputs(run_dir):
    """Print the run folder and everything written to it."""
    print(f"\nAll outputs → output/{os.path.basename(run_dir)}/")
    for f in sorted(os.listdir(run_dir)):
        print(f"  {f}")


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
        from .sites import get_site
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

    if needs == "none":  # scenario uses fixed internal windows (e.g. urban-history)
        return p

    if needs in ("sirad", "epochs"):
        # Both take exactly 3 date windows (R/G/B). --epochs overrides the
        # scenario default; SIRAD stores them as sirad_periods, urban-trend as epochs.
        default = cfg["sirad_periods"] if needs == "sirad" else cfg["epochs"]
        windows = ([parse_period(w) for w in args.epochs.split(",")]
                   if args.epochs else default)
        if len(windows) != 3:
            raise SystemExit("--epochs needs exactly 3 windows: W1,W2,W3 "
                             "(each START:END, e.g. 2024-01-01:2024-12-31)")
        p["sirad_periods" if needs == "sirad" else "epochs"] = windows
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


def _write_gee_product(prod, aoi, run_dir, common, do_map, basemap,
                       do_drive=False, drive_folder="satchange"):
    """Download one GEE product (png + tif), write its meta, optionally its map."""
    base = f"{common['scenario']}_{prod['key']}_{common['name']}"
    png = os.path.join(run_dir, base + ".png")
    tif = os.path.join(run_dir, base + ".tif")
    print(f"Downloading {prod['key']} PNG...")
    download_png(prod["thumb"], aoi, png, vis=prod["thumb_vis"])
    print(f"Downloading {prod['key']} GeoTIFF...")
    tif_ok = download_geotiff(prod["tif"], aoi, tif, scale=prod.get("scale", 10))
    if do_drive:  # async full-resolution export to the user's Google Drive
        from .gee_utils import start_drive_export
        start_drive_export(prod["tif"], aoi, base, folder=drive_folder,
                           scale=prod.get("scale", 10))

    is_rgb = "bands" in prod["thumb_vis"]
    vis = dict(prod["thumb_vis"])
    if not is_rgb and "label" not in vis:
        k = prod["key"]
        vis["label"] = ("Δ" + k[1:].upper()) if k.startswith("d") else k.upper()
    meta = {"tif": tif, "product_key": prod["key"], "vis": vis, "is_rgb": is_rgb,
            "metric": vis.get("label"), **common}
    with open(os.path.join(run_dir, base + ".meta.json"), "w") as mf:
        json.dump(meta, mf, indent=2)

    if do_map and tif_ok:
        from .mapmaker import render_map
        render_map(meta, os.path.join(run_dir, base + "_map"), basemap=basemap)
    elif do_map:
        print("  (map skipped — GeoTIFF unavailable for this product)")


def run_gee(args, cfg, lat, lon, radius, name, params, run_dir, run_id, provider, window):
    """Run the Google Earth Engine backend and write outputs to run_dir."""
    try:
        import ee  # noqa: F401 — GEE backend only
    except ImportError:
        sys.exit("The GEE backend needs earthengine-api: "
                 "pip install 'satchange[gee]'  (or use --backend mpc)")
    if getattr(args, "drive", False):
        initialize_ee(prefer_user=True)  # Drive export needs personal auth
    else:
        initialize_ee(getattr(args, "ee_key", None) or CONFIG_KEY)
    aoi = square_aoi(lon, lat, radius)  # square clip (not a circle)

    if cfg.get("method") == "optical":
        result = run_optical_change(aoi, params, cfg["index"], cfg["direction"],
                                    cfg["thr"], cfg["severe"], cfg.get("vmax", 0.6))
    else:
        result = cfg["run"](aoi, params)

    common = {"scenario": args.scenario, "label": cfg["label"], "name": name,
              "run_id": run_id, "source": "Google Earth Engine", "provider": provider,
              "lat": lat, "lon": lon, "radius_km": radius, "window": window,
              "interpretation": result.get("interpretation",
                                           cfg.get("interpretation", "")),
              "stats": result["stats"]}
    for prod in result["products"]:
        _write_gee_product(prod, aoi, run_dir, common, args.map, args.basemap,
                           do_drive=getattr(args, "drive", False),
                           drive_folder=getattr(args, "drive_folder", "satchange"))

    stats = {"run_id": run_id, "scenario": args.scenario,
             "location": {"lat": lat, "lon": lon},
             "radius_km": radius, "results": result["stats"]}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("\n=== Results ===")
    print(json.dumps(result["stats"], indent=2))
    print(f"\n{result.get('interpretation', cfg.get('interpretation', ''))}")


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
    ap.add_argument("--epochs", help="three date windows W1,W2,W3 (each "
                    "START:END) for urban-trend epochs OR mining SIRAD periods "
                    "(R/G/B), e.g. 2024-01-01:2024-12-31,2025-...,2026-...")
    ap.add_argument("-n", "--name", help="output label (default from coords)")
    ap.add_argument("--map", action="store_true",
                    help="also render an A4 map layout (PDF + PNG) per product")
    ap.add_argument("--basemap", choices=["osm", "gray", "none"], default="osm",
                    help="map basemap (default osm)")
    ap.add_argument("--backend", choices=["gee", "mpc"], default="gee",
                    help="data backend: gee (Earth Engine) or mpc "
                         "(Microsoft Planetary Computer, no account needed)")
    ap.add_argument("--ee-key", help="path to a GEE service-account key JSON "
                    "(overrides $SATCHANGE_EE_KEY and the default locations)")
    ap.add_argument("--drive", action="store_true",
                    help="also export each full-resolution GeoTIFF to Google "
                         "Drive (async; needs PERSONAL google auth, not the "
                         "service-account key). Good for very large AOIs.")
    ap.add_argument("--drive-folder", default="satchange",
                    help="Drive folder for --drive exports (default: satchange)")
    ap.add_argument("--planet", action="store_true",
                    help="urban-history hybrid: auto-locate the most-changed hotspot "
                         "and add a PlanetScope ~3 m close-up (needs $PLANET_API_KEY). "
                         "Dry-run (search + quota) unless --planet-confirm.")
    ap.add_argument("--planet-confirm", action="store_true",
                    help="actually order & download the PlanetScope scenes (spends quota)")
    ap.add_argument("--planet-key", help="PlanetScope API key (else $PLANET_API_KEY)")
    ap.add_argument("--planet-pre", default="2018-07", help="Planet pre month YYYY-MM")
    ap.add_argument("--planet-post", default="2025-07", help="Planet post month YYYY-MM")
    ap.add_argument("--hotspot-km", type=float, default=6.0,
                    help="hotspot cell size in km (fits one PlanetScope scene; default 6)")
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

    run_id, run_dir = new_run_dir(args.scenario, name)
    print(f"Output folder: output/{run_id}/\n")

    if cfg.get("method") == "urban-history":
        from . import urban_history
        planet_opts = None
        if args.planet:
            planet_opts = {"key": args.planet_key, "pre": args.planet_pre,
                           "post": args.planet_post, "hotspot_km": args.hotspot_km,
                           "confirm": args.planet_confirm}
        urban_history.run(args.backend, lat, lon, radius, name, run_dir, run_id,
                          do_map=args.map, config_key=(args.ee_key or CONFIG_KEY),
                          do_drive=args.drive, drive_folder=args.drive_folder,
                          planet=planet_opts)
        list_outputs(run_dir)
        return

    if args.backend == "mpc":
        from .mpc_backend import run_mpc
        run_mpc(args.scenario, cfg, lat, lon, radius, name, params,
                run_dir, run_id, window, provider,
                do_map=args.map, basemap=args.basemap)
        list_outputs(run_dir)
        return

    run_gee(args, cfg, lat, lon, radius, name, params,
            run_dir, run_id, provider, window)
    list_outputs(run_dir)


if __name__ == "__main__":
    main()
