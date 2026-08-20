#!/bin/bash
# Watch for the post-event DESCENDING scene on path 163, Flores M7.7.
#
# Path 163 runs a 12-day cycle from 2026-08-09, so it acquires 2026-08-21 and
# should mirror to ASF within a day or so -- the 18 Aug ascending scene took
# about that. The co-event pair will be 9 Aug -> 21 Aug, 12 days, matching the
# ascending baseline.
#
# Path 61 is not watched here. Its 14 Aug slot acquired at 21:36 UTC, twenty-two
# minutes BEFORE the 21:58 UTC rupture, so it is a pre-event scene; the next
# usable pass is 26 Aug.
#
# WHY THIS STILL MATTERS after the near-field fringe comparison showed the
# predicted 20-fringe bullseye is absent from coherent ground:
#
#   independent null   atmosphere on 21 Aug is uncorrelated with 18 Aug and the
#                      look geometry differs. A second geometry showing no
#                      concentric fringes puts the "model overpredicts onshore
#                      slip" conclusion on two observations rather than one.
#
#   the horizontal     the one way the finite fault could still be right is if
#   loophole           north-coast motion were nearly pure east-west, which
#                      ascending sees at -0.61 and descending sees with the
#                      opposite sign. The model says otherwise (+49 cm up
#                      against +4 cm east), but this tests the model on exactly
#                      the point in question instead of trusting it there.
#
# THIS DOES NOT SUBMIT. Credits are down to 105 after the frame-1153 baseline,
# and a watcher that spends the remainder unattended is the wrong shape. It
# reports and notifies; submission stays a decision.
#
# Install:
#     crontab -e
#     43 8,20 * * *  /Users/firmanhadi/GitHub/rs-change-detection/scripts/descending_watch.sh
set -u

REPO="$HOME/GitHub/rs-change-detection"
OUT="$REPO/output/coseismic"
LOG="$OUT/descending_watch.log"
STATE="$OUT/.desc_post_count"
mkdir -p "$OUT"

CONDA="$HOME/miniforge3/bin/conda"
[ -x "$CONDA" ] || CONDA=conda

ts=$(date "+%Y-%m-%d %H:%M")
report=$("$CONDA" run -n mintpy python \
  "$REPO/scripts/submit_coseismic.py" --track desc --frame 620 2>&1)
rc=$?

# The plan prints a pre-post line only once a post-event scene exists.
if printf '%s\n' "$report" | grep -q "spans the rupture"; then
  n_post=1
else
  n_post=0
fi
prev=$(cat "$STATE" 2>/dev/null || echo 0)

{
  echo "=== $ts  (rc=$rc, post-event pair available: $n_post, was: $prev) ==="
  if [ "$n_post" -gt "$prev" ] 2>/dev/null; then
    echo ">>> DESCENDING POST-EVENT SCENE IS IN ASF"
    echo ">>> review, then submit deliberately (~15 credits, 105 available):"
    echo ">>>   conda run -n mintpy python scripts/submit_coseismic.py \\"
    echo ">>>       --track desc --frame 620 --submit"
    printf '%s\n' "$report"
  elif [ "$rc" -ne 0 ]; then
    echo "check failed:"
    printf '%s\n' "$report" | tail -12
  else
    echo "no post-event descending scene yet (expected ~22-23 Aug)"
  fi
  echo
} >> "$LOG"

echo "$n_post" > "$STATE"

if [ "$n_post" -gt "$prev" ] 2>/dev/null && command -v osascript >/dev/null; then
  osascript -e "display notification \"Descending path 163 post-event scene is in ASF. Review before submitting.\" with title \"Flores co-seismic\"" 2>/dev/null || true
fi

exit 0
