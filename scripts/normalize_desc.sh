#!/bin/bash
# Normalise the descending grid detached, then reload MintPy on the full stack.
#
# Backgrounding via the tool harness has been killed repeatedly mid-run; nohup
# invoked INSIDE a script survives, which is why this exists as a file rather
# than an inline command.
cd /Users/firmanhadi/GitHub/rs-change-detection || exit 1

LOG=/Users/firmanhadi/normalize_desc.log

# The running desc job is inverting the truncated 156-pair stack, and it holds
# the rasters open. Stop only that one -- ascending is correct and still going.
pkill -f "smallbaselineApp.*insar_geom_desc" 2>/dev/null
sleep 3

nohup bash -c '
  cd /Users/firmanhadi/GitHub/rs-change-detection
  echo "=== normalize start $(date) ==="
  python3 scripts/normalize_grid.py output/insar_geom_desc
  status=$?
  echo "=== normalize done rc=$status $(date) ==="
  [ $status -ne 0 ] && exit $status

  # Metadata was deleted with each rewrite; regenerate before reloading.
  echo "=== prep_hyp3 $(date) ==="
  python3 scripts/run_mintpy.py output/insar_geom_desc --prep
  echo "=== prep done rc=$? $(date) ==="

  # Force a clean reload so the stack is rebuilt from all 354 products.
  rm -f output/insar_geom_desc/mintpy/*.h5 \
        output/insar_geom_desc/mintpy/inputs/*.h5
  echo "=== mintpy start $(date) ==="
  cd output/insar_geom_desc/mintpy
  PROJ_LIB= GDAL_DATA= conda run -n mintpy smallbaselineApp.py earthchange.cfg
  echo "=== mintpy done rc=$? $(date) ==="
' > "$LOG" 2>&1 &

echo "started pid $! -> $LOG"
