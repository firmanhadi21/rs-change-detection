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
#   bash decompose_mintpy.sh stack/insar_asc stack/insar_desc [outdir]
set -u

A="${1:?usage: decompose_mintpy.sh <asc_dir> <desc_dir> [outdir]}/mintpy"
D="${2:?usage: decompose_mintpy.sh <asc_dir> <desc_dir> [outdir]}/mintpy"
OUT="${3:-decomposition}"
mkdir -p "$OUT"

for f in "$A/velocityERA5.h5" "$D/velocityERA5.h5" \
         "$A/inputs/geometryGeo.h5" "$D/inputs/geometryGeo.h5"; do
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
done

# Called directly rather than via `conda run -n mintpy`: OpenScienceLab names
# its environment opensarlab_mintpy_recipe_book, so hardcoding one fails there.
env -u PROJ_LIB -u GDAL_DATA \
  asc_desc2horz_vert.py \
    "$A/velocityERA5.h5" "$D/velocityERA5.h5" \
    -g "$A/inputs/geometryGeo.h5" "$D/inputs/geometryGeo.h5" \
    -d velocity \
    -o "$OUT/horizontal.h5" "$OUT/vertical.h5" 2>&1 | tail -25
