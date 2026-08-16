#!/bin/bash
# Run LiCSBAS via its OWN batch script, configured from the official sample.
#
# My first attempt called the steps directly and skipped 04 (coherence mask)
# and 05 (clip), both of which the published Campi Flegrei example enables.
# Over Flores that mattered: only 15.6% of the frame has any coherence, so loop
# closure, reference selection and masking were all working across open sea.
#
# Whether that explains the 92% loop-closure rejection is the point of this
# run. It may not -- loop closure detects unwrapping errors, and those are
# baked into the LiCSAR products before LiCSBAS sees them -- but it is the one
# difference from a known-good configuration that has not been tested.
set -u

WORK="$HOME/GitHub/rs-change-detection/output/licsbas"
source "$HOME/GitHub/LiCSBAS2/bashrc_LiCSBAS.sh"
cd "$WORK" || exit 1

nohup bash batch_flores.sh > "$HOME/licsbas_batch.log" 2>&1 &
echo "started pid $! -> $HOME/licsbas_batch.log"
echo
echo "settings taken from the official sample:"
grep -E '^(start_step|end_step|nlook|do0[345]op|p04_mask_coh_thre|p05_clip_range_geo|p12_multi_prime)=' batch_flores.sh
echo
echo "compare afterwards:"
echo "  full frame, no mask/clip : TS_GEOCml10/info/13parameters.txt  (89 of 1183)"
echo "  masked + clipped         : TS_GEOCml4clip/info/13parameters.txt"
