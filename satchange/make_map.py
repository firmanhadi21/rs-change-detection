#!/usr/bin/env python3
"""Render value-added map(s) from an already-produced change-detection run.

Works fully offline (no Earth Engine) — reads each product's GeoTIFF and its
`.meta.json` sidecar that detect.py writes into output/<run-id>/.

    # A whole run folder (renders every product in it)
    python3 make_map.py output/20260708-2210_deforestation_x_ab12cd

    # A single product (.tif or .meta.json)
    python3 make_map.py output/<run>/deforestation_dndvi_x.tif --basemap gray

    # A run-id or product base name (searched under output/)
    python3 make_map.py 20260708-2210_deforestation_x_ab12cd
"""

import os
import sys
import json
import argparse
from glob import glob

from .mapmaker import render_map

OUTPUT_ROOT = os.path.join(os.getcwd(), "output")


def metas_for(target):
    """Resolve a target into a list of .meta.json paths."""
    if os.path.isdir(target):
        return sorted(glob(os.path.join(target, "*.meta.json")))
    if target.endswith(".meta.json"):
        return [target]
    if target.endswith(".tif"):
        return [target[:-4] + ".meta.json"]
    # bare name: a run-id folder under output/, or a product base anywhere
    run_dir = os.path.join(OUTPUT_ROOT, target)
    if os.path.isdir(run_dir):
        return sorted(glob(os.path.join(run_dir, "*.meta.json")))
    return sorted(glob(os.path.join(OUTPUT_ROOT, "*", target + ".meta.json")))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="run folder, .tif, .meta.json, or a base/run-id")
    ap.add_argument("--basemap", choices=["osm", "gray", "none"], default="osm")
    ap.add_argument("-o", "--out", help="output base path (single product only)")
    args = ap.parse_args()

    metas = [m for m in metas_for(args.target) if os.path.exists(m)]
    if not metas:
        sys.exit(f"No .meta.json found for '{args.target}'. Run detect.py first, "
                 "or pass a run folder / .tif / .meta.json path.")
    if args.out and len(metas) > 1:
        sys.exit("--out only works with a single product; pass a specific .tif.")

    for meta_path in metas:
        with open(meta_path) as f:
            meta = json.load(f)
        # Resolve the tif relative to the sidecar if the stored path moved
        if not os.path.exists(meta.get("tif", "")):
            meta["tif"] = os.path.join(os.path.dirname(meta_path),
                                       os.path.basename(meta["tif"]))
        base = os.path.basename(meta_path)[:-len(".meta.json")]
        out_base = args.out or os.path.join(os.path.dirname(meta_path), base + "_map")
        render_map(meta, out_base, basemap=args.basemap)


if __name__ == "__main__":
    main()
