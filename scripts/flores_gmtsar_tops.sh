#!/bin/bash
# Flores co-seismic interferogram with GMTSAR TOPS, as an independent check.
#
# WHY BOTHER, given the question has already been answered three ways. The
# standing result is a null: the USGS finite-fault model predicts a 20-fringe
# concentric bullseye over the north coast and it is absent from coherent
# ground. That rests on SNAP, on ASF HyP3, and on PyGMTSAR -- and PyGMTSAR
# shares its lineage with GMTSAR, so it is not fully independent. A native
# GMTSAR run is a genuinely separate chain, and a null that survives four
# unrelated implementations is worth much more than one that survives three.
#
# THE FRAME MATTERS AND IT IS EASY TO GET WRONG. Path 112 frame 1153 contains
# the epicentre at 121.3517, -8.3101. The adjacent slice on the same orbit,
# 25 seconds earlier, does NOT -- its northern edge falls about 7 km south of
# it. Both are called "the 6 August scene" and differ only in the seconds
# field of the granule name. Check the footprint, not the date.
#
# ORBITS ARE RESTITUTED, NOT PRECISE. Precise orbits are published about 20
# days after acquisition, so for these two scenes they arrive around 7
# September. RESORB is accurate to roughly 10 cm against POEORB's few cm.
# Enhanced spectral diversity re-estimates the azimuth alignment from the data,
# so the residue is mostly a long-wavelength ramp -- which is precisely the
# thing not to trust when asking whether a broad fringe pattern exists. Repeat
# on POEORB before drawing any conclusion that depends on long wavelengths.
#
#   bash scripts/flores_gmtsar_tops.sh
set -euo pipefail

export GMTSAR="${GMTSAR:-$HOME/GMTSAR}"
export PATH="$GMTSAR/bin:$PATH"

REPO="$HOME/GitHub/rs-change-detection"
WORK="${WORK:-$REPO/data/flores_gmtsar}"
SLC="$REPO/data/slc"
ORB="$REPO/data/orbits"
DEM="$REPO/data/dem/flores/dem.grd"
POL="${POL:-vv}"
PARALLEL="${PARALLEL:-1}"

REF="S1D_IW_SLC__1SDV_20260806T101628_20260806T101655_004003_00746B_356A"
REP="S1D_IW_SLC__1SDV_20260818T101628_20260818T101655_004178_007A70_D74C"
REF_EOF="S1D_OPER_AUX_RESORB_OPOD_20260806T123722_V20260806T084013_20260806T121553.EOF"
REP_EOF="S1D_OPER_AUX_RESORB_OPOD_20260818T123612_V20260818T084014_20260818T121554.EOF"

for f in "$SLC/$REF.zip" "$SLC/$REP.zip" "$ORB/$REF_EOF" "$ORB/$REP_EOF" "$DEM"; do
    [ -e "$f" ] || { echo "missing: $f" >&2; exit 2; }
done

avail=$(df -k "$REPO" | awk 'NR==2 {printf "%.0f", $4/1024/1024}')
echo "workspace $WORK   (${avail} GB free)"
# `if`, not `[ ] && { }`: the AND-list returns 1 whenever the condition is
# false, which is the normal case, and reads as a failure to anything
# inspecting $?.
if [ "$avail" -lt 25 ]; then
    echo "need ~25 GB free for a 3-swath run" >&2
    exit 2
fi

# copy_once, not `cp -n`: BSD cp exits 1 when it skips an existing target, so
# under `set -e` the script succeeds on a fresh workspace and dies on every
# rerun -- the exact opposite of idempotent, and it looks like a disk error.
copy_once() { [ -e "$2" ] || cp "$1" "$2"; }

mkdir -p "$WORK/raw" "$WORK/topo"
copy_once "$DEM" "$WORK/topo/dem.grd"

# Unzip once. The SAFE directories are what p2p_S1_TOPS_Frame.csh wants; the
# zips stay put so a failed run can be restarted without re-downloading.
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

# GMTSAR's own defaults, then the few that matter here.
cd "$WORK"
if [ ! -f config.s1a.txt ]; then
    pop_config.csh S1_TOPS > config.s1a.txt
    # proc_stage 1 = start from the beginning (align, then interferogram).
    # The filter and looks below are GMTSAR's Sentinel-1 defaults; leaving
    # them alone keeps this comparable to a stock run rather than tuned to
    # produce a particular answer.
    sed -i '' 's/^threshold_snaphu = .*/threshold_snaphu = 0.10/' config.s1a.txt || true
    sed -i '' 's/^threshold_geocode = .*/threshold_geocode = 0.10/' config.s1a.txt || true
    echo "  wrote config.s1a.txt (snaphu and geocode thresholds 0.10 --"
    echo "   coherence over Flores is low and 0.15+ erases the near field)"
fi

echo
echo "running p2p_S1_TOPS_Frame.csh  ($POL, parallel=$PARALLEL)"
echo "  reference $REF"
echo "  repeat    $REP"
echo
# BARE NAMES, NOT PATHS. p2p_S1_TOPS_Frame.csh does `cd raw/$1` internally and
# builds its symlinks as ../../raw/$1/..., so it prepends raw/ itself. Passing
# "raw/NAME.SAFE" produces "raw/raw/NAME.SAFE: No such file or directory" --
# which reads like a missing download and is a doubled prefix.
time p2p_S1_TOPS_Frame.csh \
    "$REF.SAFE" "$REF_EOF" \
    "$REP.SAFE" "$REP_EOF" \
    config.s1a.txt "$POL" "$PARALLEL"

echo
echo "results in $WORK/merge:"
ls -la "$WORK/merge" 2>/dev/null | grep -E "\.grd|\.png" | awk '{print "  " $9}' || true
