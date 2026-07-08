#!/usr/bin/env python3
"""Run the full remote-sensing pipeline end-to-end for one site.

Runs, in order:
    1. Sentinel-2 true-color download          (data-collection/01_...)
    2. SIRAD radar change composite            (data-collection/02_...)
    3. Sentinel-2 NDVI change detection        (data-collection/03_ndvi_change_gee.py)
    4. PlanetScope NDVI change detection        (optional — only if data present)

All flags are passed through to each step, so `--site` and `--drive` work:

    python3 run_all.py --site konawe
    python3 run_all.py --site konawe --drive
    python3 run_all.py                 # defaults to --site capkala

The Capkala documentary video (TTS + assembly) is Capkala-specific content and
is NOT part of this generic pipeline — build it separately with:
    python3 scripts/01_generate_tts.py && python3 scripts/02_assemble_video.py
"""

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASSTHROUGH = sys.argv[1:]  # e.g. --site konawe --drive

# (script, required?) — optional steps that fail are reported but don't abort.
STEPS = [
    ("data-collection/01_sentinel2_download.py", True),
    ("data-collection/02_sirad_gee.py", True),
    ("data-collection/03_ndvi_change_gee.py", True),
    ("data-collection/03_planetscope_ndvi.py", False),  # needs commercial .tif
]


def main():
    site = "capkala"
    for i, a in enumerate(PASSTHROUGH):
        if a == "--site" and i + 1 < len(PASSTHROUGH):
            site = PASSTHROUGH[i + 1]
        elif a.startswith("--site="):
            site = a.split("=", 1)[1]

    print(f"\n{'=' * 60}\nEND-TO-END PIPELINE — site: {site}\n{'=' * 60}")
    results = []
    for script, required in STEPS:
        name = os.path.basename(script)
        print(f"\n>>> {name}")
        cmd = [PY, os.path.join(HERE, script)] + PASSTHROUGH
        proc = subprocess.run(cmd)
        ok = proc.returncode == 0
        results.append((name, ok, required))
        if not ok and required:
            print(f"!!! {name} failed (required). Stopping.")
            break
        if not ok:
            print(f"--- {name} skipped/failed (optional). Continuing.")

    print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
    for name, ok, required in results:
        tag = "OK " if ok else ("FAIL" if required else "skip")
        print(f"  [{tag}] {name}")
    print(f"\nResults: images/*_{site}.png  ·  data/*_{site}.tif  ·  "
          f"data/ndvi_{site}_stats.json")


if __name__ == "__main__":
    main()
