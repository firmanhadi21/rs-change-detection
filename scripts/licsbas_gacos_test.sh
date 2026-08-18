#!/bin/bash
# Does GACOS change anything over Flores?
#
# The cleanest experiment available: run the SAME interferograms twice,
# differing only in whether the GACOS tropospheric correction was applied.
# Everything else -- multilook, thresholds, network, reference -- is identical,
# so any difference is attributable to the correction alone. Our ERA5
# comparison on the HyP3 side could never say that, because the correction
# arrived bundled with solid Earth tides, look vectors and a new reference
# point.
#
# Prediction, stated before running so it cannot be adjusted afterwards:
# GACOS should NOT rescue loop closure. Loop closure sums phase around a
# triplet, where any per-epoch delay cancels exactly, so a tropospheric
# correction is invisible to it by construction. If loop-closure rejection
# falls sharply, my reasoning about that is wrong and worth knowing.
#
# Where GACOS SHOULD show up is in residual RMS and velocity scatter, which
# do see per-epoch delay.
set -u

BASE="$HOME/GitHub/rs-change-detection/output/licsbas"

# bashrc_LiCSBAS.sh appends to PYTHONPATH without a default, so it trips
# `set -u` when the variable is unset. Relax it for that one line only.
set +u
source "$HOME/GitHub/LiCSBAS2/bashrc_LiCSBAS.sh"
set -u

cd "$BASE" || exit 1

echo "=== 03: apply GACOS ==="
# -g for the GACOS directory (not -z), and step 03 takes no -t.
LiCSBAS03op_GACOS.py -i GEOCml4 -o GEOCml4GACOS -g GACOS || exit 1

n_gacos=$(ls -d GEOCml4GACOS/[0-9]*_[0-9]* 2>/dev/null | wc -l | tr -d ' ')
echo "corrected interferograms: $n_gacos"
[ "$n_gacos" -lt 30 ] && { echo "too few to compare"; exit 1; }

# --- control: the SAME pairs, uncorrected -----------------------------
echo
echo "=== building matched control (same pairs, no GACOS) ==="
rm -rf GEOCml4ctrl
mkdir -p GEOCml4ctrl
for f in GEOCml4/*; do
  [ -d "$f" ] || ln -s "../$f" "GEOCml4ctrl/" 2>/dev/null
done
kept=0
for d in GEOCml4GACOS/[0-9]*_[0-9]*; do
  n=$(basename "$d")
  if [ -d "GEOCml4/$n" ]; then
    ln -s "../GEOCml4/$n" "GEOCml4ctrl/$n"
    kept=$((kept+1))
  fi
done
echo "control pairs: $kept"

# --- identical processing on both -------------------------------------
# Default loop threshold on purpose: a tight gate makes any improvement
# from the correction easier to see than a loose one would.
for dir in GEOCml4ctrl GEOCml4GACOS; do
  ts="TS_${dir}"
  echo
  echo "=== $dir ==="
  LiCSBAS11_check_unw.py    -d "$dir" -t "$ts" -u 0.5 -c 0.02 || continue
  LiCSBAS12_loop_closure.py -d "$dir" -t "$ts" -l 1.5 --multi_prime || continue
  LiCSBAS13_sb_inv.py       -d "$dir" -t "$ts" --mem_size 2000 || continue
  LiCSBAS14_vel_std.py -t "$ts"
  LiCSBAS15_mask_ts.py -t "$ts"
  LiCSBAS16_filt_ts.py -t "$ts"
done

echo
echo "=== COMPARISON ==="
for ts in TS_GEOCml4ctrl TS_GEOCml4GACOS; do
  echo "--- $ts ---"
  grep -E "^n_ifg:|^n_ifg_all:|^n_im:" "$ts/info/13parameters.txt" 2>/dev/null
  echo -n "  rejected by loop closure: "
  wc -l < "$ts/info/12bad_ifg.txt" 2>/dev/null | tr -d ' '
done
