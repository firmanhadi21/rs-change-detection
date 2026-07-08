#!/usr/bin/env python3
"""Render a value-added map from an already-produced change-detection result.

Works fully offline (no Earth Engine) — reads the GeoTIFF and its `.meta.json`
sidecar that detect.py writes next to every product.

    # By product base name (as in data/ and images/)
    python3 make_map.py deforestation_dndvi_m3p333_122p25

    # Or point at the .tif / .meta.json directly
    python3 make_map.py data/mining_sirad_konawe.tif --basemap gray
"""

import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mapmaker import render_map  # noqa: E402

DATA_DIR = os.path.join(HERE, "data")
MAPS_DIR = os.path.join(HERE, "maps")


def resolve_meta(target):
    """Find the .meta.json for a base name, a .tif, or a .meta.json path."""
    if target.endswith(".meta.json"):
        return target
    if target.endswith(".tif"):
        cand = target[:-4] + ".meta.json"
    else:  # bare base name
        cand = os.path.join(DATA_DIR, target + ".meta.json")
    if not os.path.exists(cand):
        sys.exit(f"Sidecar not found: {cand}\n"
                 "Run detect.py first, or pass the correct base name / .tif.")
    return cand


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="product base name, .tif, or .meta.json")
    ap.add_argument("--basemap", choices=["osm", "gray", "none"], default="osm")
    ap.add_argument("-o", "--out", help="output base path (no extension)")
    args = ap.parse_args()

    meta_path = resolve_meta(args.target)
    with open(meta_path) as f:
        meta = json.load(f)

    # Make the tif path absolute relative to the meta file if needed
    if not os.path.isabs(meta["tif"]) or not os.path.exists(meta["tif"]):
        alt = os.path.join(os.path.dirname(meta_path), os.path.basename(meta["tif"]))
        meta["tif"] = alt if os.path.exists(alt) else meta["tif"]

    base = os.path.splitext(os.path.basename(meta_path))[0].replace(".meta", "")
    out_base = args.out or os.path.join(MAPS_DIR, base + "_map")
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    render_map(meta, out_base, basemap=args.basemap)


if __name__ == "__main__":
    main()
