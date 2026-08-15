#!/bin/bash
# Run MintPy's small-baseline workflow on both Flores tracks, detached.
#
# smallbaselineApp.py loads 354 (or 351) interferograms, inverts the network,
# repairs unwrapping errors, removes a ramp, estimates topographic residual and
# fetches ERA5 for the tropospheric correction. That is hours, and it must not
# die with the shell.
#
#   bash scripts/mintpy_both.sh
#   tail -f ~/mintpy_desc.log
#
# PROJ_LIB from an OTB install points at a PROJ 1.2 database and breaks every
# CRS lookup GDAL makes; MintPy is little else.

set -u
cd "$(dirname "$0")/.." || exit 1
REPO="$PWD"
BIN=/Users/firmanhadi/miniforge3/envs/mintpy/bin

unset PROJ_LIB GDAL_DATA

launch() {
  local dir="$1" log="$2"
  local cfg="$REPO/$dir/mintpy/earthchange.cfg"
  if [ ! -f "$cfg" ]; then
    echo "  no config for $dir — skipping"
    return
  fi
  nohup env -u PROJ_LIB -u GDAL_DATA \
    "$BIN/smallbaselineApp.py" "$cfg" \
    > "$log" 2>&1 &
  echo "  $dir -> $log   (pid $!)"
}

echo "starting MintPy on both tracks"
cd "$REPO/output/insar_geom_desc/mintpy" && launch output/insar_geom_desc "$HOME/mintpy_desc.log"
cd "$REPO/output/insar_geom_asc/mintpy"  && launch output/insar_geom_asc  "$HOME/mintpy_asc.log"

echo
echo "watch:  tail -f ~/mintpy_desc.log"
echo "stop:   pkill -f smallbaselineApp"
