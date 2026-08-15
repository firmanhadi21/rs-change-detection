#!/bin/bash
# Collect both Flores InSAR stacks, detached, until they finish.
#
# Run this from a normal Terminal. It survives closing the window, and it
# restarts a collection that stops before reaching its target -- HyP3 downloads
# get interrupted, and a resumed run costs nothing because products are cached
# by job name and no job is resubmitted.
#
#   bash scripts/collect_flores.sh
#   tail -f ~/flores_desc.log        # watch either track
#   bash scripts/collect_flores.sh --status
#
# Nothing here spends credits: all 705 jobs are already paid for and finished.

set -u
cd "$(dirname "$0")/.." || exit 1
REPO="$PWD"

DESC_DIR="$REPO/output/insar_geom_desc"
ASC_DIR="$REPO/output/insar_geom_asc"
DESC_TARGET=354
ASC_TARGET=351

count() { ls "$1/hyp3" 2>/dev/null | wc -l | tr -d ' '; }

status() {
  printf '%-16s %s/%s\n' "descending" "$(count "$DESC_DIR")" "$DESC_TARGET"
  printf '%-16s %s/%s\n' "ascending"  "$(count "$ASC_DIR")"  "$ASC_TARGET"
  printf '%-16s %s\n' "disk free" "$(df -h "$HOME" | tail -1 | awk '{print $4}')"
}

if [ "${1:-}" = "--status" ]; then
  status
  exit 0
fi

# One worker per track. Loops because the download is long and can be cut off;
# each pass picks up where the last stopped.
worker() {
  local name="$1" dir="$2" target="$3" pass="$4" log="$5"
  local tries=0
  while [ "$(count "$dir")" -lt "$target" ] && [ "$tries" -lt 40 ]; do
    tries=$((tries + 1))
    echo "=== $name attempt $tries at $(date '+%H:%M') — $(count "$dir")/$target ===" >> "$log"
    python3 -m earthchange.detect -s insar-series \
      --lat -8.60 --lon 121.66 --radius 30 -n "$name" \
      --series-start 2022-08-13 --series-end 2026-08-13 \
      --orbit-pass "$pass" --confirm -o "$dir" >> "$log" 2>&1
    sleep 10
  done
  echo "=== $name finished at $(date '+%H:%M') — $(count "$dir")/$target ===" >> "$log"
}

echo "starting both collections, detached"
status
echo

nohup bash -c "$(declare -f count worker); \
  worker FloresDescGeom '$DESC_DIR' $DESC_TARGET descending '$HOME/flores_desc.log'" \
  > /dev/null 2>&1 &
echo "  descending -> ~/flores_desc.log   (pid $!)"

nohup bash -c "$(declare -f count worker); \
  worker FloresAscGeom '$ASC_DIR' $ASC_TARGET ascending '$HOME/flores_asc.log'" \
  > /dev/null 2>&1 &
echo "  ascending  -> ~/flores_asc.log    (pid $!)"

echo
echo "watch:    tail -f ~/flores_desc.log"
echo "check:    bash scripts/collect_flores.sh --status"
echo "stop:     pkill -f 'earthchange.detect -s insar-series'"
