#!/bin/bash
# Independent cross-check of the Flores interseismic result using LiCSBAS2.
#
# Frame 112A_09831_050508 is the same relative orbit as our ascending HyP3
# stack, but everything else differs: LiCSAR interferograms produced at COMET
# rather than HyP3, a different unwrapper, GACOS rather than ERA5, and a
# different inversion. Agreement between two chains that share only the raw SAR
# is far stronger evidence than two runs of the same software.
#
# It is also a BETTER test of the question. LiCSAR holds 1,188 interferograms
# over 298 epochs from 2015-07 to 2026-05 -- eleven years against our four. A
# 5 mm/yr signal accumulates ~55 mm over that span versus ~20 mm over ours,
# which against a ~25 mm/yr noise floor is the difference between undetectable
# and marginal.
#
#   bash run_licsbas.sh trial     # 6 months, verify the chain works
#   bash run_licsbas.sh full      # all 11 years
set -u

FRAME=112A_09831_050508
WORK="$HOME/GitHub/rs-change-detection/output/licsbas"
LICSBAS="$HOME/GitHub/LiCSBAS2"
MODE="${1:-trial}"

# Sets PATH and PYTHONPATH; LiCSBAS_check_install fails without it even when
# every Python dependency is present.
source "$LICSBAS/bashrc_LiCSBAS.sh"

mkdir -p "$WORK"
cd "$WORK" || exit 1

if [ "$MODE" = "trial" ]; then
  START=20260101; END=20260531
  echo "TRIAL: $START..$END — verifying the chain before committing to 11 years"
else
  START=20150101; END=20260531
  echo "FULL: $START..$END"
fi

echo "=== 01: download LiCSAR geotiffs ==="
LiCSBAS01_get_geotiff.py -f "$FRAME" -s "$START" -e "$END" || exit 1
du -sh GEOC 2>/dev/null

echo
echo "=== 02: multilook and prepare ==="
# 10 looks: the frame is large and this is a velocity question, not a mapping
# one. Keeps the inversion tractable without touching the temporal sampling.
LiCSBAS02_ml_prep.py -i GEOC -o GEOCml10 -n 10 || exit 1

echo
echo "=== 11: check unwrapping ==="
LiCSBAS11_check_unw.py -d GEOCml10 -t TS_GEOCml10 || exit 1

echo
echo "=== 12: loop closure ==="
LiCSBAS12_loop_closure.py -d GEOCml10 -t TS_GEOCml10 || exit 1

echo
echo "=== 13: small-baseline inversion ==="
LiCSBAS13_sb_inv.py -d GEOCml10 -t TS_GEOCml10 || exit 1

echo
echo "=== 14-16: velocity, mask, filter ==="
LiCSBAS14_vel_std.py -t TS_GEOCml10
LiCSBAS15_mask_ts.py -t TS_GEOCml10
LiCSBAS16_filt_ts.py -t TS_GEOCml10

echo
echo "=== done ==="
ls -la TS_GEOCml10/results/ 2>/dev/null | head
echo
echo "velocity field: $WORK/TS_GEOCml10/results/vel.filt.mskd"
echo "compare against HyP3 asc: output/insar_geom_asc/mintpy/velocityERA5.h5"
