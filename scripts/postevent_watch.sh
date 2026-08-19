#!/bin/bash
# Watch for post-event Sentinel-1 scenes on the Flores co-seismic stack.
#
# ASF has not yet mirrored ANY post-event acquisition -- path 112 ascending
# stops at 6 Aug, path 163 descending at 9 Aug, while the 18 Aug scene has been
# on Copernicus for a day. That lag is the thing being waited on, and it is
# measured in days, so a daily check is the right cadence: often enough not to
# lose an acquisition cycle, rare enough to be invisible.
#
# THIS DOES NOT SUBMIT ANYTHING. Submitting spends HyP3 credits -- ~220 for the
# current 22-pair network, more as scenes accumulate -- and a watcher that
# spends money while nobody is looking is the wrong shape for this. It reports;
# submission stays a decision.
#
# Install (survives Claude sessions, unlike a session cron):
#     crontab -e
#     17 21 * * *  /Users/firmanhadi/GitHub/rs-change-detection/scripts/postevent_watch.sh
#
# Read the log:
#     tail -40 ~/GitHub/rs-change-detection/output/coseismic/stack/watch.log
set -u

REPO="$HOME/GitHub/rs-change-detection"
OUT="$REPO/output/coseismic/stack"
LOG="$OUT/watch.log"
STATE="$OUT/.last_post_count"

mkdir -p "$OUT"

CONDA="$HOME/miniforge3/bin/conda"
[ -x "$CONDA" ] || CONDA=conda

ts=$(date "+%Y-%m-%d %H:%M")
report=$("$CONDA" run -n mintpy python "$REPO/scripts/postevent_stack.py" 2>&1)
rc=$?

# The number of post-event scenes is the only thing worth alerting on; the rest
# of the report is unchanged day to day and would bury the signal.
n_post=$(printf '%s\n' "$report" \
  | sed -n 's/.*(\([0-9]*\) pre-event, \([0-9]*\) post-event).*/\2/p' | head -1)
n_post=${n_post:-0}
prev=$(cat "$STATE" 2>/dev/null || echo 0)

{
  echo "=== $ts  (rc=$rc, post-event scenes: $n_post, was: $prev) ==="
  if [ "$n_post" -gt "$prev" ] 2>/dev/null; then
    echo ">>> NEW POST-EVENT SCENE(S) IN ASF — $prev -> $n_post"
    echo ">>> review the plan, then submit deliberately:"
    echo ">>>   conda run -n mintpy python scripts/postevent_stack.py --submit"
    printf '%s\n' "$report"
  elif [ "$rc" -ne 0 ]; then
    echo "check failed:"
    printf '%s\n' "$report" | tail -20
  else
    echo "no change; ASF still has no new post-event acquisition"
  fi
  echo
} >> "$LOG"

echo "$n_post" > "$STATE"

# macOS notification when something actually changed, so the log does not have
# to be watched by hand.
if [ "$n_post" -gt "$prev" ] 2>/dev/null && command -v osascript >/dev/null; then
  osascript -e "display notification \"ASF now has $n_post post-event scene(s) on path 112. Review before submitting.\" with title \"Flores co-seismic stack\"" 2>/dev/null || true
fi

exit 0
