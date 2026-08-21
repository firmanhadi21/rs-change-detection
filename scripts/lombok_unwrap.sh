#!/bin/bash
# Unwrap the Lombok ALOS-2 interferogram with GMTSAR's snaphu.
#
# WHY THE FIRST ATTEMPT FAILED, because the failure was silent and the output
# looked like a product. GMTSAR at ~/GMTSAR was compiled but `make install` was
# never run, so $prefix/share/gmtsar did not exist. snaphu.csh calls
# gmtsar_sharedir.csh, gets a path that isn't there, and its `sed` of the
# template writes a ZERO-BYTE snaphu.conf.brief. snaphu then runs on pure
# defaults -- no DEFOMAX_CYCLE, C-band geometry, ERS orbit -- and exits 0. The
# grid that came out spanned 651 cm and had per-pixel islands flying to -300 cm
# across the whole eastern half of the island.
#
# Two fixes, both necessary:
#
#   1. A real config, with THIS satellite's geometry. The stock template is
#      ERS: LAMBDA 0.0565647 (C-band), ORBITRADIUS 7153 km, NEARRANGE 831 km.
#      ALOS-2 here is L-band 0.242452 m at 636 km with near range 714 km.
#   2. A coherence threshold that reflects the scene. Median coherence is
#      0.094; 0.12 asks snaphu to unwrap noise, and every isolated noisy pixel
#      becomes its own connected component with its own arbitrary 2-pi offset.
#      0.30 keeps the 22.5% of pixels that carry real fringes.
#
# Usage:  bash scripts/lombok_unwrap.sh [coherence_threshold] [defomax_cycles]
set -euo pipefail

export GMTSAR=${GMTSAR:-$HOME/GMTSAR}
export PATH=$GMTSAR/bin:$PATH

THRESH=${1:-0.30}
DEFOMAX=${2:-40}          # nonzero: this is a rupture, jumps are allowed
D=$HOME/Teaching/UNDIP/InSAR/EQ/Pair1/intf/2018132_2018216

# --- finish the GMTSAR install if it is still incomplete --------------------
SHARE=$(gmtsar_sharedir.csh)
if [ ! -f "$SHARE/snaphu/config/snaphu.conf.brief" ]; then
    echo "completing GMTSAR share install into $SHARE"
    mkdir -p "$SHARE/filters" "$SHARE/snaphu/config"
    cp "$GMTSAR"/gmtsar/filters/[bfgsxy]* "$SHARE/filters/"
    cp "$GMTSAR"/gmtsar/csh/snaphu.conf.* "$SHARE/snaphu/config/"
    cp "$GMTSAR"/gmtsar/*.grd "$SHARE/" 2>/dev/null || true
fi

cd "$D"

# --- SAR geometry, read from the PRM rather than assumed --------------------
PRM=$(ls -- *-180804-*.PRM | head -1)
get() { grep -E "^\s*$1\s*=" "$PRM" | tail -1 | awk -F= '{print $2}' | tr -d ' '; }
LAMBDA=$(get radar_wavelength)
NEAR=$(get near_range)
FS=$(get rng_samp_rate)
PRF=$(get PRF)
RE=$(get earth_radius)
HT=$(get SC_height)

# Multilook factors are recorded in the interferogram grid's own increments:
# GMTSAR writes x_inc / y_inc as the number of single-look pixels averaged.
RLOOKS=$(gmt grdinfo -C phasefilt.grd | cut -f8 | cut -d. -f1)
ALOOKS=$(gmt grdinfo -C phasefilt.grd | cut -f9 | cut -d. -f1)

read -r ORBRAD DR DA <<EOF
$(awk -v re="$RE" -v ht="$HT" -v fs="$FS" -v prf="$PRF" \
      -v rl="$RLOOKS" -v al="$ALOOKS" 'BEGIN{
  c = 299792458.0;
  orb = re + ht;
  # Ground velocity, not orbital velocity: the azimuth pixel walks along the
  # ground, which is slower than the satellite by the ratio of the radii.
  vsat = sqrt(3.986004418e14 / orb);
  vg   = vsat * re / orb;
  printf "%.1f %.4f %.4f", orb, (c/(2*fs))*rl, (vg/prf)*al;
}')
EOF

echo "geometry from $PRM"
echo "  wavelength   $LAMBDA m       (L-band; the ERS template says 0.0565647)"
echo "  near range   $NEAR m"
echo "  orbit radius $ORBRAD m"
echo "  looks        ${RLOOKS} rng x ${ALOOKS} azi"
echo "  pixel        $DR x $DA m on the ground"
echo "  threshold    $THRESH    defomax $DEFOMAX cycles"
echo

# --- write the config -------------------------------------------------------
sed -e "s/^LAMBDA.*/LAMBDA\t\t$LAMBDA/" \
    -e "s/^ORBITRADIUS.*/ORBITRADIUS\t\t$ORBRAD/" \
    -e "s/^EARTHRADIUS.*/EARTHRADIUS\t\t$RE/" \
    -e "s/^NEARRANGE.*/NEARRANGE\t$NEAR/" \
    -e "s/^DR\t.*/DR\t\t$DR/" \
    -e "s/^DA\t.*/DA\t\t$DA/" \
    -e "s/^NLOOKSRANGE.*/NLOOKSRANGE\t$RLOOKS/" \
    -e "s/^NLOOKSAZ.*/NLOOKSAZ\t$ALOOKS/" \
    -e "s/^DEFOMAX_CYCLE.*/DEFOMAX_CYCLE\t$DEFOMAX/" \
    "$SHARE/snaphu/config/snaphu.conf.brief" > snaphu.conf.alos2
grep -E "^(LAMBDA|ORBITRADIUS|EARTHRADIUS|NEARRANGE|DR|DA|NLOOKS|DEFOMAX)" \
     snaphu.conf.alos2 | sed 's/^/  /'
echo

# --- run --------------------------------------------------------------------
# Tag every product with the threshold it came from. The coherence cut is the
# single biggest lever on what this scene produces -- 0.30 keeps only Rinjani's
# flanks, which is exactly the ground you must NOT use to test phase against
# elevation -- so runs at different thresholds have to coexist and be compared,
# not silently overwrite each other.
TAG=$(printf 'c%02d' "$(awk -v t="$THRESH" 'BEGIN{printf "%d", t*100}')")
rm -f mask_patch.grd corr_patch.grd phase_patch.grd mask2_patch.grd \
      corr_tmp.grd phase.in corr.in tmp.grd conncomp.grd

gmt grdmath corr.grd "$THRESH" GE 0 NAN mask.grd MUL = mask2_patch.grd
gmt grdmath mask2_patch.grd corr.grd MUL = corr_tmp.grd
gmt grdmath phasefilt.grd mask2_patch.grd MUL = phase_patch.grd
gmt grd2xyz phase_patch.grd -ZTLf -do0 > phase.in
gmt grd2xyz corr_tmp.grd   -ZTLf -do0 > corr.in

WIDTH=$(gmt grdinfo -C phasefilt.grd | cut -f10)
echo "unwrapping ${WIDTH}-column grid ..."
snaphu phase.in "$WIDTH" -f snaphu.conf.alos2 -c corr.in \
       -o unwrap.out -v -d -g conncomp.out 2>&1 | tail -20

gmt xyz2grd unwrap.out -ZTLf -r $(gmt grdinfo -I- phasefilt.grd) \
    $(gmt grdinfo -I phasefilt.grd) -Gtmp.grd
gmt grdmath tmp.grd mask2_patch.grd MUL = unwrap_$TAG.grd

# The connected-component labels are what tell one island of coherent ground
# from another, so keep them. snaphu announces the width it used -- here
# "Writing connected components to file conncomp.out as 1-byte unsigned ints",
# which is -ZTLu. The default-config run wrote a wider type, and that is why
# snaphu.csh's fixed -ZTLu aborted there with "found half the expected
# records". Trust the line snaphu prints, not the script's assumption.
gmt xyz2grd conncomp.out -ZTLu -r $(gmt grdinfo -I- phasefilt.grd) \
    $(gmt grdinfo -I phasefilt.grd) -Gconncomp_$TAG.grd || \
  echo "conncomp conversion failed -- continuing without labels"

proj_ra2ll.csh trans.dat unwrap_$TAG.grd unwrap_${TAG}_ll.grd > /dev/null 2>&1
[ -f conncomp_$TAG.grd ] && \
  proj_ra2ll.csh trans.dat conncomp_$TAG.grd conncomp_${TAG}_ll.grd \
      > /dev/null 2>&1

echo
echo "products: unwrap_${TAG}_ll.grd  conncomp_${TAG}_ll.grd"
gmt grdinfo unwrap_${TAG}_ll.grd -L2 | grep -E "v_min|mean|NaN"
