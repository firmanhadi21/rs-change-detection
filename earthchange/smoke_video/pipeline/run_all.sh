#!/bin/bash
# Full pipeline, in order. See README.md for prerequisites.
set -e
cd "$(dirname "$0")"

echo "== 1/5 downloading data (DEM, fires, smoke) =="
python3 download_dem.py
python3 download_fires.py
python3 download_aod.py

echo "== 2/5 rendering terrain with forge3d =="
python3 render_basemap.py

echo "== 3/5 grading basemap (land/sea/coastline) =="
python3 regrade.py

echo "== 4/5 compositing frames =="
python3 compose.py all

echo "== 5/5 encoding MP4 + GIF =="
bash encode.sh

echo "Done -> out/"
