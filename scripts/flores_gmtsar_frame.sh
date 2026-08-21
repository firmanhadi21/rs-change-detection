#!/bin/bash
# Flores co-seismic interferogram with GMTSAR TOPS, one ascending frame.
#
#   bash scripts/flores_gmtsar_frame.sh 1148
#   bash scripts/flores_gmtsar_frame.sh 1153
#
# Replaces the two near-identical per-frame scripts. They had already drifted
# apart -- 1153's was written before the ESD config existed -- and a difference
# in processing between two frames of the same pair is exactly what must not
# happen when the frames are going to be compared.
#
# WHICH FRAME TO USE, because it is not the obvious one. The epicentre at
# -8.3101 is OFFSHORE, north of the Flores coast:
#
#   1148  lat -10.17..-8.04   all of Flores. THE PRIMARY FRAME: it holds the
#                             land any deformation would be on.
#   1153  lat  -8.68..-6.55   the north coast and the sea beyond. Contains the
#                             epicentre, but 1.1% coherence and no coherent
#                             ground within 20 km, because most of it is water.
#
# Both contain the epicentre. Choosing on that alone is what sent the first run
# at 1153; the right question of a frame is whether it covers the deforming
# GROUND.
#
# ESD IS NOT OPTIONAL HERE. config.s1a.flores.txt sets spec_div = 1;
# pop_config's default is 0. Without it TOPS azimuth co-registration comes from
# the orbit alone, and these are RESTITUTED orbits (~10 cm), where orbit error
# dominates -- burst boundaries then carry phase discontinuities that look like
# real signal.
set -euo pipefail

FRAME="${1:-}"
case "$FRAME" in
  1148)
    REF="S1D_IW_SLC__1SDV_20260806T101603_20260806T101630_004003_00746B_959A"
    REP="S1D_IW_SLC__1SDV_20260818T101604_20260818T101631_004178_007A70_1384"
    DEM_NAME="dem_1148.grd"
    ;;
  1153)
    REF="S1D_IW_SLC__1SDV_20260806T101628_20260806T101655_004003_00746B_356A"
    REP="S1D_IW_SLC__1SDV_20260818T101628_20260818T101655_004178_007A70_D74C"
    DEM_NAME="dem.grd"
    ;;
  *)
    echo "usage: $0 {1148|1153}" >&2; exit 2 ;;
esac

export GMTSAR="${GMTSAR:-$HOME/GMTSAR}"
export PATH="$GMTSAR/bin:$PATH"

REPO="$HOME/GitHub/rs-change-detection"
WORK="${WORK:-$REPO/data/flores_gmtsar_$FRAME}"
SLC="$REPO/data/slc"
ORB="$REPO/data/orbits"
DEM="$REPO/data/dem/flores/$DEM_NAME"
CONFIG="${CONFIG:-$REPO/data/config.s1a.flores.txt}"
POL="${POL:-vv}"
PARALLEL="${PARALLEL:-1}"

REF_EOF="S1D_OPER_AUX_RESORB_OPOD_20260806T123722_V20260806T084013_20260806T121553.EOF"
REP_EOF="S1D_OPER_AUX_RESORB_OPOD_20260818T123612_V20260818T084014_20260818T121554.EOF"

for f in "$SLC/$REF.zip" "$SLC/$REP.zip" "$ORB/$REF_EOF" "$ORB/$REP_EOF" \
         "$DEM" "$CONFIG"; do
    [ -e "$f" ] || { echo "missing: $f" >&2; exit 2; }
done

avail=$(df -k "$REPO" | awk 'NR==2 {printf "%.0f", $4/1024/1024}')
echo "frame $FRAME   workspace $WORK   (${avail} GB free)"
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
copy_once "$CONFIG" config.s1a.txt
sd=$(grep -E "^spec_div" config.s1a.txt | tr -d ' ')
echo "  config: $CONFIG  ($sd)"
[ "$sd" = "spec_div=1" ] || echo "  WARNING: ESD is OFF" >&2

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
echo "frame $FRAME results in $WORK/merge:"
ls "$WORK/merge" 2>/dev/null | grep -E "_ll\.grd" | sed 's/^/  /' || true
