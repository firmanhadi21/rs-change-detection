#!/bin/bash
# Decompose asc/desc into horizontal and vertical using MintPy's own tool.
#
# Preferred over the hand-rolled version in scripts/decompose.py now that real
# look vectors exist: asc_desc2horz_vert reads incidenceAngle AND azimuthAngle
# from each track's geometry, so the look directions are measured rather than
# assumed. It also implements Fialko et al. (2001) and warns about the
# north component, which near-polar orbits cannot resolve.
#
# Requires both inputs geocoded at the same resolution, which the common
# subset box already guarantees.
set -u
cd /Users/firmanhadi/GitHub/rs-change-detection || exit 1

A=output/insar_geom_asc/mintpy
D=output/insar_geom_desc/mintpy
OUT=output/decomposition
mkdir -p "$OUT"

for f in "$A/velocityERA5.h5" "$D/velocityERA5.h5" \
         "$A/inputs/geometryGeo.h5" "$D/inputs/geometryGeo.h5"; do
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
done

env -u PROJ_LIB -u GDAL_DATA conda run --no-capture-output -n mintpy \
  asc_desc2horz_vert.py \
    "$A/velocityERA5.h5" "$D/velocityERA5.h5" \
    -g "$A/inputs/geometryGeo.h5" "$D/inputs/geometryGeo.h5" \
    -d velocity \
    -o "$OUT/horizontal.h5" "$OUT/vertical.h5" 2>&1 | tail -25
