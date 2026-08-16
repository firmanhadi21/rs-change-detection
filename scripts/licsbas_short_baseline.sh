#!/bin/bash
# Rerun LiCSBAS on short temporal baselines only.
#
# Loop closure rejected 1,026 of 1,183 interferograms. Coherence explains some
# of that but cannot fix it: even keeping only coh >= 0.15, two thirds still
# fail, and that gate discards 95% of the network. Temporal baseline separates
# the groups better -- survivors median 24 days against 36 for failures.
#
# That fits savanna. Grass and soil scatter consistently across 12 days and
# change substantially across 48, so the phase is unwrappable short-term and
# not long-term. If that is the mechanism, a network built only from 12- and
# 24-day pairs should close where the full network could not.
#
# Symlinks into a new directory rather than copies: the interferograms are
# 6 GB and unchanged.
set -u

WORK="$HOME/GitHub/rs-change-detection/output/licsbas"
SRC="$WORK/GEOCml10"
DST="$WORK/GEOCml10short"
MAXDT="${1:-24}"        # days

source "$HOME/GitHub/LiCSBAS2/bashrc_LiCSBAS.sh"
cd "$WORK" || exit 1

rm -rf "$DST"
mkdir -p "$DST"

# Geometry and parameter files the later steps need, alongside the pairs.
for f in "$SRC"/*; do
  [ -d "$f" ] || ln -s "$f" "$DST/" 2>/dev/null
done

kept=0; skipped=0
for d in "$SRC"/[0-9]*_[0-9]*; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  d1=${n%_*}; d2=${n#*_}
  s1=$(date -j -f "%Y%m%d" "$d1" "+%s" 2>/dev/null) || continue
  s2=$(date -j -f "%Y%m%d" "$d2" "+%s" 2>/dev/null) || continue
  dt=$(( (s2 - s1) / 86400 ))
  if [ "$dt" -le "$MAXDT" ]; then
    ln -s "$d" "$DST/$n"
    kept=$((kept+1))
  else
    skipped=$((skipped+1))
  fi
done

echo "short-baseline network (<= ${MAXDT} d): kept $kept, excluded $skipped"
[ "$kept" -lt 50 ] && { echo "too few pairs to invert"; exit 1; }

echo
echo "=== 11: check unwrapping ==="
LiCSBAS11_check_unw.py -d GEOCml10short -t TS_short || exit 1
echo
echo "=== 12: loop closure ==="
LiCSBAS12_loop_closure.py -d GEOCml10short -t TS_short || exit 1
echo
echo "=== 13: inversion ==="
LiCSBAS13_sb_inv.py -d GEOCml10short -t TS_short || exit 1
echo
echo "=== 14-16 ==="
LiCSBAS14_vel_std.py -t TS_short
LiCSBAS15_mask_ts.py -t TS_short
LiCSBAS16_filt_ts.py -t TS_short

echo
echo "=== compare ==="
echo "full network:"
grep -E "^n_ifg:|^n_ifg_all:|^n_im:" TS_GEOCml10/info/13parameters.txt 2>/dev/null
echo "short-baseline network:"
grep -E "^n_ifg:|^n_ifg_all:|^n_im:" TS_short/info/13parameters.txt 2>/dev/null
