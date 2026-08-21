#!/bin/bash
# Flores co-seismic interferogram, GMTSAR TOPS, ASCENDING PATH 112 FRAME 1148.
#
# WHY A SECOND FRAME. The first run used frame 1153, chosen because it contains
# the epicentre. That was the wrong criterion: the epicentre at -8.3101 is
# OFFSHORE, north of the Flores coast, and 1153 extends north into the Flores
# Sea. The result was 1.1% coherence overall and ZERO coherent pixels within
# 20 km -- there is no ground there to measure.
#
# Frame 1148 spans lat -10.17 to -8.04 and covers all of Flores. It also
# contains the epicentre, but that is incidental; what matters is that it
# contains the LAND the deformation would be on. A deformation field spans
# tens of kilometres, so the right question of a frame is "does it cover the
# deforming ground", not "does it contain the hypocentre".
#
# Separate workspace from the 1153 run so both results survive for comparison.
#
#   bash scripts/flores_gmtsar_1148.sh
set -euo pipefail

export GMTSAR="${GMTSAR:-$HOME/GMTSAR}"
export PATH="$GMTSAR/bin:$PATH"

REPO="$HOME/GitHub/rs-change-detection"
WORK="${WORK:-$REPO/data/flores_gmtsar_1148}"
SLC="$REPO/data/slc"
ORB="$REPO/data/orbits"
DEM="$REPO/data/dem/flores/dem_1148.grd"
POL="${POL:-vv}"
PARALLEL="${PARALLEL:-1}"

REF="S1D_IW_SLC__1SDV_20260806T101603_20260806T101630_004003_00746B_959A"
REP="S1D_IW_SLC__1SDV_20260818T101604_20260818T101631_004178_007A70_1384"
REF_EOF="S1D_OPER_AUX_RESORB_OPOD_20260806T123722_V20260806T084013_20260806T121553.EOF"
REP_EOF="S1D_OPER_AUX_RESORB_OPOD_20260818T123612_V20260818T084014_20260818T121554.EOF"

for f in "$SLC/$REF.zip" "$SLC/$REP.zip" "$ORB/$REF_EOF" "$ORB/$REP_EOF" "$DEM"; do
    [ -e "$f" ] || { echo "missing: $f" >&2; exit 2; }
done

avail=$(df -k "$REPO" | awk 'NR==2 {printf "%.0f", $4/1024/1024}')
echo "workspace $WORK   (${avail} GB free)"
if [ "$avail" -lt 30 ]; then
    echo "need ~30 GB free for a 3-swath run" >&2
    exit 2
fi

# Not `cp -n`: BSD cp exits 1 when it skips an existing target, so under
# `set -e` the script works on a fresh workspace and dies on every rerun.
copy_once() { [ -e "$2" ] || cp "$1" "$2"; }

mkdir -p "$WORK/raw" "$WORK/topo"
copy_once "$DEM" "$WORK/topo/dem.grd"

cd "$WORK/raw"
for g in "$REF" "$REP"; do
    if [ -d "$g.SAFE" ]; then
        echo "  have $g.SAFE"
    else
        echo "  unzipping $g"
        unzip -q -o "$SLC/$g.zip"
    fi
done
copy_once "$ORB/$REF_EOF" "./$REF_EOF"
copy_once "$ORB/$REP_EOF" "./$REP_EOF"

cd "$WORK"
if [ ! -f config.s1a.txt ]; then
    pop_config.csh S1_TOPS > config.s1a.txt
    sed -i '' 's/^threshold_snaphu = .*/threshold_snaphu = 0.10/' config.s1a.txt || true
    sed -i '' 's/^threshold_geocode = .*/threshold_geocode = 0.10/' config.s1a.txt || true
fi

echo
echo "running p2p_S1_TOPS_Frame.csh  ($POL, parallel=$PARALLEL)"
echo "  reference $REF"
echo "  repeat    $REP"
echo
# Bare names: the script does `cd raw/$1` itself, so a path gives raw/raw/...
time p2p_S1_TOPS_Frame.csh \
    "$REF.SAFE" "$REF_EOF" \
    "$REP.SAFE" "$REP_EOF" \
    config.s1a.txt "$POL" "$PARALLEL"

echo
echo "results in $WORK/merge:"
ls "$WORK/merge" 2>/dev/null | grep -E "_ll\.grd" | sed 's/^/  /' || true
