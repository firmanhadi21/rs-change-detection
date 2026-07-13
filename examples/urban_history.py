#!/usr/bin/env python3
"""Standalone runner for the decadal urban-history analysis (Jakarta default).

This is a thin wrapper around satchange.urban_history — the SAME analysis is a
first-class scenario in the CLI:

    satchange -s urban-history --lat -6.2 --lon 106.85 --radius 45 -n jabodetabek

Combines GHSL GHS-BUILT-S (authoritative built-up 1980-2025, GEE) with Landsat
NDBI/NDVI (built-up + vegetation loss). Produces a first-built-decade map, a
decadal built-up panel, trend charts, and stats. Use --backend mpc for a
Landsat-only run without an Earth Engine account (GHSL is GEE-only).
"""

import os
import sys
import uuid
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from satchange import urban_history


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, default=-6.2)
    ap.add_argument("--lon", type=float, default=106.85)
    ap.add_argument("--radius", type=float, default=45.0)
    ap.add_argument("-n", "--name", default="jabodetabek")
    ap.add_argument("--backend", choices=["gee", "mpc"], default="gee")
    args = ap.parse_args()

    run_id = (f"{datetime.now():%Y%m%d-%H%M%S}_urbanhistory_{args.name}"
              f"_{uuid.uuid4().hex[:6]}")
    run_dir = os.path.join(os.getcwd(), "output", run_id)
    os.makedirs(run_dir, exist_ok=True)
    config_key = os.path.join(os.getcwd(), "scripts", "config", "ee-geodetic.json")
    print(f"Output folder: output/{run_id}/\n")

    urban_history.run(args.backend, args.lat, args.lon, args.radius, args.name,
                      run_dir, run_id, config_key=config_key)


if __name__ == "__main__":
    main()
