#!/bin/bash
# Co-seismic interferogram over the WHOLE scene: all three IW subswaths.
#
# The IW2-only run found no fringes, but IW2 spans 121.34-122.31 E and its land
# starts ~10 km from the rupture. IW1 reaches to 120.58 E -- west of the
# epicentre's meridian -- and IW3 to 123.06 E. Together they cover every part of
# Flores the ascending pass sees, so a null here is a null for the whole island
# rather than for one subswath.
#
# Burst indices are NOT comparable across subswaths: IW3 is offset ~0.3 deg
# north of IW1 in azimuth, so the same index sits at a different latitude. These
# ranges come from snap_find_burst.py and each covers the AOI in its own swath:
#
#     IW1  bursts 6-9    lat -9.232 .. -8.372   lon 120.580 .. 121.508
#     IW2  bursts 6-9    lat -9.174 .. -8.304   lon 121.339 .. 122.313   <- epicentre
#     IW3  bursts 4-9    lat -9.271 .. -8.090   lon 122.109 .. 123.061
#
# TWO STAGES, on purpose. One graph with three coregistration chains feeding a
# single TOPSAR-Merge pulls all three through the heap at once, which is what
# exhausts it. Staging bounds memory to one swath, and makes the run
# restartable: a failure in IW3 does not throw away IW1 and IW2.
#
#   stage 1   per swath: Split -> Orbit -> Back-Geocoding -> ESD -> Ifg -> Deburst
#   stage 2   TOPSAR-Merge -> TopoPhaseRemoval -> Multilook -> Terrain-Correction
#
# Stage 1 products are large (~2 GB per swath per pair) and are kept, not
# deleted, so stage 2 can be re-run with different multilook or geocoding
# without redoing the expensive coregistration.
#
#   bash scripts/snap_coseismic_full.sh prepre
#   bash scripts/snap_coseismic_full.sh prepost
#
# Resume a partial run -- completed swaths are skipped automatically.
set -u

GPT=/Applications/esa-snap/bin/gpt
DL="$HOME/Downloads"
OUT="$HOME/GitHub/rs-change-detection/output/coseismic/snap"
STAGE1="$OUT/swaths"

# swath:firstBurst:lastBurst
SWATHS=("IW1:6:9" "IW2:6:9" "IW3:4:9")

PAIR="${1:?usage: snap_coseismic_full.sh prepre|prepost}"

# Mbay (18 km from the rupture, the closest town to it), Riung and Larantuka
# came back with ZERO observed pixels -- not low coherence, no data at all.
# Terrain-Correction's nodataValueAtSea uses the DEM's sea mask, and these
# towns sit on low-lying coastal delta that SRTM flags as sea. The damage
# analysis was therefore blind exactly where damage would be largest.
#
#   NOSEA=1 bash scripts/snap_coseismic_full.sh prepost
#
# writes ${PAIR}_fullsea alongside, so the two are comparable rather than one
# silently replacing the other. Stage 1 is untouched and reused.
NOSEA="${NOSEA:-0}"
if [ "$NOSEA" = "1" ]; then
  SEA_FLAG=false
  STAGE2_SUFFIX=fullsea
else
  SEA_FLAG=true
  STAGE2_SUFFIX=full
fi
case "$PAIR" in
  prepre)  M=20260725T101603; S=20260806T101603 ;;
  prepost) M=20260806T101603; S=20260818T101604 ;;
  *) echo "pair must be prepre or prepost"; exit 1 ;;
esac

find_zip () { ls "$DL"/S1D_IW_SLC__1SDV_"$1"*.zip 2>/dev/null | head -1; }
MASTER=$(find_zip "$M"); SLAVE=$(find_zip "$S")
[ -f "$MASTER" ] || { echo "missing master $M"; exit 1; }
[ -f "$SLAVE" ]  || { echo "missing slave  $S"; exit 1; }

mkdir -p "$STAGE1"

echo "pair   : $PAIR   (whole scene, 3 subswaths)"
echo "master : $(basename "$MASTER")"
echo "slave  : $(basename "$SLAVE")"
echo "stage1 : $STAGE1"
echo

# ---------------------------------------------------------------- stage 1 ----
for SPEC in "${SWATHS[@]}"; do
  SWATH="${SPEC%%:*}"; REST="${SPEC#*:}"
  BF="${REST%%:*}"; BL="${REST##*:}"
  TGT="$STAGE1/${PAIR}_${SWATH}"

  if [ -f "$TGT.dim" ] && [ -d "$TGT.data" ]; then
    echo "== $SWATH bursts $BF-$BL: already done, skipping"
    continue
  fi

  echo "== $SWATH bursts $BF-$BL -> $TGT.dim"
  G="$OUT/graph_${PAIR}_${SWATH}.xml"

  cat > "$G" <<XML
<graph id="coseismic_${SWATH}">
  <version>1.0</version>

  <node id="ReadM"><operator>Read</operator>
    <parameters><file>$MASTER</file></parameters></node>
  <node id="ReadS"><operator>Read</operator>
    <parameters><file>$SLAVE</file></parameters></node>

  <!-- Both scenes MUST use identical burst numbers or coregistration has
       nothing to match. -->
  <node id="SplitM"><operator>TOPSAR-Split</operator>
    <sources><sourceProduct refid="ReadM"/></sources>
    <parameters>
      <subswath>$SWATH</subswath>
      <selectedPolarisations>VV</selectedPolarisations>
      <firstBurstIndex>$BF</firstBurstIndex>
      <lastBurstIndex>$BL</lastBurstIndex>
    </parameters></node>
  <node id="SplitS"><operator>TOPSAR-Split</operator>
    <sources><sourceProduct refid="ReadS"/></sources>
    <parameters>
      <subswath>$SWATH</subswath>
      <selectedPolarisations>VV</selectedPolarisations>
      <firstBurstIndex>$BF</firstBurstIndex>
      <lastBurstIndex>$BL</lastBurstIndex>
    </parameters></node>

  <node id="OrbM"><operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="SplitM"/></sources>
    <parameters>
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <continueOnFail>true</continueOnFail>
    </parameters></node>
  <node id="OrbS"><operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="SplitS"/></sources>
    <parameters>
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <continueOnFail>true</continueOnFail>
    </parameters></node>

  <node id="Coreg"><operator>Back-Geocoding</operator>
    <sources>
      <sourceProduct refid="OrbM"/>
      <sourceProduct.1 refid="OrbS"/>
    </sources>
    <parameters>
      <demName>SRTM 1Sec HGT</demName>
      <demResamplingMethod>BICUBIC_INTERPOLATION</demResamplingMethod>
      <resamplingType>BISINC_5_POINT_INTERPOLATION</resamplingType>
      <maskOutAreaWithoutElevation>true</maskOutAreaWithoutElevation>
    </parameters></node>

  <!-- Needs three or more bursts to estimate the azimuth shift; all three
       swath selections here satisfy that. -->
  <node id="ESD"><operator>Enhanced-Spectral-Diversity</operator>
    <sources><sourceProduct refid="Coreg"/></sources>
    <parameters/></node>

  <node id="Ifg"><operator>Interferogram</operator>
    <sources><sourceProduct refid="ESD"/></sources>
    <parameters>
      <subtractFlatEarthPhase>true</subtractFlatEarthPhase>
      <includeCoherence>true</includeCoherence>
      <cohWinAz>3</cohWinAz>
      <cohWinRg>10</cohWinRg>
      <squarePixel>true</squarePixel>
    </parameters></node>

  <!-- Stop at deburst. TOPSAR-Merge needs debursted, still-ungeocoded,
       still-full-resolution products; multilooking or geocoding here would
       make the swaths unmergeable. -->
  <node id="Deburst"><operator>TOPSAR-Deburst</operator>
    <sources><sourceProduct refid="Ifg"/></sources>
    <parameters><selectedPolarisations>VV</selectedPolarisations></parameters></node>

  <node id="Write"><operator>Write</operator>
    <sources><sourceProduct refid="Deburst"/></sources>
    <parameters>
      <file>$TGT.dim</file>
      <formatName>BEAM-DIMAP</formatName>
    </parameters></node>
</graph>
XML

  # -x frees the cache between nodes; without it a 7 GB SLC pair exhausts the
  # heap on the coregistration step.
  "$GPT" "$G" -c 8G -q 4 -x || { echo "!! $SWATH failed"; exit 1; }
  echo "-- $SWATH done"
  echo
done

# ---------------------------------------------------------------- stage 2 ----
TARGET="$OUT/${PAIR}_${STAGE2_SUFFIX}"
GM="$OUT/graph_${PAIR}_merge_${STAGE2_SUFFIX}.xml"

SRC=""; REFS=""; n=0
for SPEC in "${SWATHS[@]}"; do
  SWATH="${SPEC%%:*}"
  SRC="$SRC
  <node id=\"R$n\"><operator>Read</operator>
    <parameters><file>$STAGE1/${PAIR}_${SWATH}.dim</file></parameters></node>"
  if [ $n -eq 0 ]; then
    REFS="      <sourceProduct refid=\"R$n\"/>"
  else
    REFS="$REFS
      <sourceProduct.$n refid=\"R$n\"/>"
  fi
  n=$((n+1))
done

echo "== merging $n subswaths -> $TARGET.dim"

cat > "$GM" <<XML
<graph id="merge_$PAIR">
  <version>1.0</version>
$SRC

  <!-- Stitches adjacent subswaths and removes the range overlap between them.
       Order does not matter; SNAP sorts by subswath number. -->
  <node id="Merge"><operator>TOPSAR-Merge</operator>
    <sources>
$REFS
    </sources>
    <parameters><selectedPolarisations>VV</selectedPolarisations></parameters></node>

  <node id="Topo"><operator>TopoPhaseRemoval</operator>
    <sources><sourceProduct refid="Merge"/></sources>
    <parameters>
      <demName>SRTM 1Sec HGT</demName>
      <outputTopoPhaseBand>false</outputTopoPhaseBand>
    </parameters></node>

  <node id="ML"><operator>Multilook</operator>
    <sources><sourceProduct refid="Topo"/></sources>
    <parameters>
      <nRgLooks>4</nRgLooks>
      <nAzLooks>1</nAzLooks>
      <outputIntensity>false</outputIntensity>
    </parameters></node>

  <!-- 40 m, matching the IW2-only run so the two are directly comparable. -->
  <node id="TC"><operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="ML"/></sources>
    <parameters>
      <demName>SRTM 1Sec HGT</demName>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>40.0</pixelSpacingInMeter>
      <mapProjection>WGS84(DD)</mapProjection>
      <nodataValueAtSea>$SEA_FLAG</nodataValueAtSea>
      <saveDEM>true</saveDEM>
      <saveIncidenceAngleFromEllipsoid>true</saveIncidenceAngleFromEllipsoid>
    </parameters></node>

  <node id="Write"><operator>Write</operator>
    <sources><sourceProduct refid="TC"/></sources>
    <parameters>
      <file>$TARGET.dim</file>
      <formatName>BEAM-DIMAP</formatName>
    </parameters></node>
</graph>
XML

"$GPT" "$GM" -c 8G -q 4 -x
rc=$?
echo
if [ $rc -eq 0 ]; then
  echo "done: $TARGET.data"
  ls -la "$TARGET.data" 2>/dev/null | head
else
  echo "merge failed (rc=$rc); stage-1 swaths are intact in $STAGE1"
fi
exit $rc
