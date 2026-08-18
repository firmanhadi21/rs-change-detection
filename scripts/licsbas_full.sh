#!/bin/bash
# Launch the full 11-year LiCSBAS run detached.
#
# nohup inside a script rather than a backgrounded command: harness-tracked
# background jobs have been killed repeatedly in this session, and this run is
# hours long.
#
# The trial already downloaded 2026-01..2026-05; LiCSBAS01 skips what exists,
# so the full run only fetches what is missing.
cd "$HOME/GitHub/rs-change-detection" || exit 1

LOG="$HOME/licsbas_full.log"

nohup conda run --no-capture-output -n licsbas2 \
  bash scripts/run_licsbas.sh full > "$LOG" 2>&1 &

echo "started pid $! -> $LOG"
echo "watch:  tail -f $LOG"
echo "expect: ~3.5 GB download, then hours of inversion on 1188 interferograms"
