#!/bin/bash
# Wait for the frame-1148 run, then reprocess 1153 with the SAME config.
#
# Both frames must be processed identically before their results can be
# compared or mosaicked. 1153 was first run with pop_config's defaults, which
# leave spec_div = 0 -- no enhanced spectral diversity -- so its azimuth
# co-registration came from restituted orbits alone. Reprocessing it with
# config.s1a.flores.txt removes that as a difference between the frames.
#
# The old 1153 merge is MOVED ASIDE rather than deleted, so the ESD and
# non-ESD results can be compared directly. If ESD makes no difference on this
# pair that is worth knowing; if it does, the difference is the evidence.
#
#   nohup bash scripts/flores_gmtsar_chain.sh > chain.log 2>&1 &
set -euo pipefail

REPO="$HOME/GitHub/rs-change-detection"
W1148="$REPO/data/flores_gmtsar_1148"
W1153="$REPO/data/flores_gmtsar"          # the original 1153 workspace

echo "waiting for the frame-1148 run to finish..."
while pgrep -f "flores_gmtsar_(1148|frame\.sh 1148)" > /dev/null; do
    sleep 60
done

if [ -f "$W1148/merge/los_ll.grd" ]; then
    echo "frame 1148 completed: $(ls "$W1148"/merge/*_ll.grd | wc -l | tr -d ' ') geocoded grids"
else
    echo "frame 1148 did NOT produce los_ll.grd — stopping rather than" >&2
    echo "starting 1153 on top of a failure that has not been read." >&2
    exit 1
fi

# Reclaim the extracted SAFEs. They are ~14 GB and re-extract from the zips in
# data/slc, which stay. Everything the result depends on -- merge/, F1..F3 --
# is untouched.
echo
echo "reclaiming frame-1148 SAFEs (re-extractable from data/slc):"
du -sh "$W1148"/raw/*.SAFE 2>/dev/null || true
rm -rf "$W1148"/raw/*.SAFE
echo "  free now: $(df -k "$REPO" | awk 'NR==2{printf "%.0f", $4/1024/1024}') GB"

# Preserve the non-ESD 1153 result for comparison, then clear the workspace so
# alignment genuinely redoes rather than reusing the old SLCs.
STAMP=$(date +%Y%m%d-%H%M%S)
if [ -d "$W1153/merge" ]; then
    echo
    echo "preserving the non-ESD 1153 result as merge_noesd_$STAMP"
    mv "$W1153/merge" "$W1153/merge_noesd_$STAMP"
fi
rm -rf "$W1153"/F1 "$W1153"/F2 "$W1153"/F3 "$W1153"/config.s1a.txt
rm -rf "$W1153"/raw/*.SAFE 2>/dev/null || true

echo
echo "=== reprocessing frame 1153 with the ESD config ==="
WORK="$W1153" bash "$REPO/scripts/flores_gmtsar_frame.sh" 1153

echo
echo "=== both frames done ==="
for w in "$W1148" "$W1153"; do
    printf "%-40s " "$(basename "$w")"
    ls "$w"/merge/*_ll.grd 2>/dev/null | wc -l | tr -d ' '
done
