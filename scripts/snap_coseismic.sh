#!/bin/bash
# Co-seismic interferogram from raw SLCs, with SNAP instead of HyP3.
#
# ASF has not mirrored the 18 Aug acquisition, but Copernicus has it, so the
# three scenes were downloaded directly. This does locally what HyP3 would have
# done remotely -- and unlike HyP3 it costs no credits and waits for nobody.
#
# IW2, bursts 6-9. All three subswaths touch Flores, but IW2 spans
# 121.34-122.31 E, which covers the epicentre's meridian and central Flores.
# Processing one subswath instead of three cuts the work to a third.
#
# Two pairs, both 12 days, so the coherence comparison is baseline-matched:
#   PRE-PRE   20260725 -> 20260806   baseline coherence, nothing happened
#   PRE-POST  20260806 -> 20260818   spans the rupture
#
# Coherence needs no unwrapping, so this stops before SNAPHU. Displacement
# would need unwrapping; that is a separate run.
#
#   bash scripts/snap_coseismic.sh prepre
#   bash scripts/snap_coseismic.sh prepost
set -u

GPT=/Applications/esa-snap/bin/gpt
DL="$HOME/Downloads"
OUT="$HOME/GitHub/rs-change-detection/output/coseismic/snap"
SWATH=IW2
BURST_FIRST=6
BURST_LAST=9

PAIR="${1:?usage: snap_coseismic.sh prepre|prepost}"
case "$PAIR" in
  prepre)  M=20260725T101603; S=20260806T101603 ;;
  prepost) M=20260806T101603; S=20260818T101604 ;;
  *) echo "pair must be prepre or prepost"; exit 1 ;;
esac

find_zip () { ls "$DL"/S1D_IW_SLC__1SDV_"$1"*.zip 2>/dev/null | head -1; }
MASTER=$(find_zip "$M"); SLAVE=$(find_zip "$S")
[ -f "$MASTER" ] || { echo "missing master $M"; exit 1; }
[ -f "$SLAVE" ]  || { echo "missing slave  $S"; exit 1; }

mkdir -p "$OUT"
GRAPH="$OUT/graph_$PAIR.xml"
TARGET="$OUT/${PAIR}_coh"

echo "pair   : $PAIR"
echo "master : $(basename "$MASTER")"
echo "slave  : $(basename "$SLAVE")"
echo "swath  : $SWATH bursts $BURST_FIRST-$BURST_LAST"
echo "target : $TARGET.dim"
echo

cat > "$GRAPH" <<XML
<graph id="coseismic">
  <version>1.0</version>

  <node id="ReadM"><operator>Read</operator>
    <parameters><file>$MASTER</file></parameters></node>
  <node id="ReadS"><operator>Read</operator>
    <parameters><file>$SLAVE</file></parameters></node>

  <!-- One subswath, four bursts. Both scenes MUST use identical numbers or
       coregistration has nothing to match. -->
  <node id="SplitM"><operator>TOPSAR-Split</operator>
    <sources><sourceProduct refid="ReadM"/></sources>
    <parameters>
      <subswath>$SWATH</subswath>
      <selectedPolarisations>VV</selectedPolarisations>
      <firstBurstIndex>$BURST_FIRST</firstBurstIndex>
      <lastBurstIndex>$BURST_LAST</lastBurstIndex>
    </parameters></node>
  <node id="SplitS"><operator>TOPSAR-Split</operator>
    <sources><sourceProduct refid="ReadS"/></sources>
    <parameters>
      <subswath>$SWATH</subswath>
      <selectedPolarisations>VV</selectedPolarisations>
      <firstBurstIndex>$BURST_FIRST</firstBurstIndex>
      <lastBurstIndex>$BURST_LAST</lastBurstIndex>
    </parameters></node>

  <!-- Precise orbits. Downloaded on first use; without them the geometry is
       good to metres rather than centimetres, which matters for phase. -->
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

  <!-- Coregistration against a DEM. The slowest step, and the one that decides
       whether coherence is real or noise. -->
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

  <!-- Refines azimuth alignment to a hundredth of a pixel. Skipping it leaves
       phase jumps at burst boundaries that look like deformation. -->
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

  <node id="Deburst"><operator>TOPSAR-Deburst</operator>
    <sources><sourceProduct refid="Ifg"/></sources>
    <parameters><selectedPolarisations>VV</selectedPolarisations></parameters></node>

  <!-- Remove the topographic contribution, so what remains is displacement
       plus atmosphere rather than terrain. -->
  <node id="Topo"><operator>TopoPhaseRemoval</operator>
    <sources><sourceProduct refid="Deburst"/></sources>
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

  <!-- Geocode to WGS84 at 40 m, matching the HyP3 products already downloaded
       so the two can be compared without resampling either. -->
  <node id="TC"><operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="ML"/></sources>
    <parameters>
      <demName>SRTM 1Sec HGT</demName>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>40.0</pixelSpacingInMeter>
      <mapProjection>WGS84(DD)</mapProjection>
      <nodataValueAtSea>true</nodataValueAtSea>
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

echo "graph written, starting gpt (expect 1-3 hours)"
echo

# -x frees the cache between nodes; without it a 7 GB SLC pair exhausts the
# heap on the coregistration step.
"$GPT" "$GRAPH" -c 8G -q 4 -x

rc=$?
echo
if [ $rc -eq 0 ]; then
  echo "done: $TARGET.data"
  ls -la "$TARGET.data" 2>/dev/null | head
  echo
  echo "coherence band is coh_*; export to GeoTIFF with:"
  echo "  $GPT Subset -Ssource=$TARGET.dim -PsourceBands=<coh band> \\"
  echo "      -f GeoTIFF -t $TARGET.tif"
else
  echo "gpt failed (rc=$rc)"
fi
exit $rc
