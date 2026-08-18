#!/bin/bash
# Mosaic two along-track HyP3 frames with Orfeo ToolBox.
#
# Preferred over rasterio.merge for this because OTB Mosaic can FEATHER the
# seam. rasterio can only pick a winner per pixel (first/last/min/max) or
# average, all of which leave a hard edge where the two frames meet. Feathering
# blends across a transition zone, which matters when the mosaic is going into
# a figure rather than straight into further arithmetic.
#
# Two OTB-specific traps handled below:
#
#   PROJ CONFLICT. otbenv.profile exports PROJ_LIB pointing at OTB's own PROJ
#   database, which is layout version 1.2 where modern PROJ needs >= 6. Once
#   exported it breaks rasterio and GDAL in every other environment on this
#   machine, so it is confined to a subshell and never leaks out.
#
#   NODATA IS NOT NAN. The masked coherence rasters use NaN for nodata, but OTB
#   Mosaic's -nodata takes a float and compares numerically, and NaN never
#   compares equal to anything. Feeding it NaN silently mosaics the nodata as
#   if it were data. The inputs are converted to 0-nodata first.
#
#   bash merge_frames_otb.sh a.tif b.tif out.tif [feather_length_m]
set -u

A="${1:?usage: merge_frames_otb.sh <a.tif> <b.tif> <out.tif> [feather_m]}"
B="${2:?need a second input}"
OUT="${3:?need an output path}"
FEATHER="${4:-2000}"     # metres; ~50 px at 40 m posting

OTB="$HOME/OTB-8.1.2-Darwin64"
[ -x "$OTB/bin/otbcli_Mosaic" ] || { echo "otbcli_Mosaic not found in $OTB"; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "=== converting NaN nodata to 0 for OTB ==="
# OTB compares -nodata numerically; NaN never equals NaN, so NaN-nodata would
# be mosaicked as if it were valid data.
python3 - "$A" "$B" "$TMP" <<'PY'
import os, sys
for v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(v, None)
import numpy as np, rasterio
a, b, tmp = sys.argv[1], sys.argv[2], sys.argv[3]
for i, p in enumerate((a, b)):
    with rasterio.open(p) as s:
        d = s.read(1)
        prof = s.profile.copy()
    d = np.where(np.isfinite(d), d, 0).astype("float32")
    prof.update(dtype="float32", nodata=0, compress="deflate")
    out = os.path.join(tmp, f"in{i}.tif")
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(d, 1)
    print(f"  {os.path.basename(p)[:44]} -> {os.path.basename(out)} "
          f"({100*(d > 0).mean():.1f}% valid)")
PY

echo
echo "=== otbcli_Mosaic (feather=slim, ${FEATHER} m) ==="
# Subshell: otbenv exports PROJ_LIB, which must not survive into the parent
# environment or it breaks every other geospatial tool here.
(
  set +u
  source "$OTB/otbenv.profile"
  "$OTB/bin/otbcli_Mosaic" \
    -il "$TMP/in0.tif" "$TMP/in1.tif" \
    -comp.feather slim \
    -comp.feather.slim.length "$FEATHER" \
    -harmo.method none \
    -nodata 0 \
    -interpolator nn \
    -ram 2048 \
    -out "$OUT" float
)
rc=$?
[ $rc -ne 0 ] && { echo "OTB Mosaic failed (rc=$rc)"; exit $rc; }

echo
echo "=== result ==="
python3 - "$OUT" <<'PY'
import os, sys
for v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(v, None)
import numpy as np, rasterio
with rasterio.open(sys.argv[1]) as s:
    d = s.read(1)
    print(f"  {s.width} x {s.height}  {s.crs}  res {s.res[0]:.1f} m")
v = d[np.isfinite(d) & (d > 0)]
print(f"  valid pixels: {v.size:,} ({100*v.size/d.size:.1f}% of mosaic)")
if v.size:
    for q in (25, 50, 75, 95):
        print(f"    p{q:<3} {np.percentile(v, q):.3f}")
    print(f"    mean {v.mean():.3f}")
PY

echo
echo "harmo.method is none on purpose: both frames come from the SAME"
echo "acquisition pair and already agree to 0.002 in the overlap, so"
echo "radiometric harmonisation would adjust values that are already correct."
