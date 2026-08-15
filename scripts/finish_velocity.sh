#!/bin/bash
# Produce a comparable velocity for each track, without deramping either.
#
# Ascending cannot be deramped: its temporal-coherence mask keeps only 2.31% of
# the frame, too sparse and too clustered to fit a plane through, so the fit
# goes singular and the field explodes to 1e22 mm. Descending deramps fine
# (7.24% mask) -- but comparing a deramped track against an underamped one
# would put a spurious plane straight into the asc/desc agreement test, so
# neither is deramped. Residual orbital ramp is a known, stated limitation.
#
# smallbaselineApp dies after correct_topography in residual_RMS, inside a
# matplotlib call ("Axis limits cannot be NaN or Inf"). That is a PLOTTING
# failure with the science products already on disk, so velocity is computed
# directly rather than by fighting the plot.
set -u
cd /Users/firmanhadi/GitHub/rs-change-detection || exit 1

# Most-corrected first. Both tracks must end up on the SAME one, or the
# agreement test measures a processing asymmetry instead of the ground.
CHAIN="timeseries_SET_ERA5_demErr.h5 timeseries_ERA5_demErr.h5"

pick=""
for cand in $CHAIN; do
  if [ -f "output/insar_geom_asc/mintpy/$cand" ] && \
     [ -f "output/insar_geom_desc/mintpy/$cand" ]; then
    pick="$cand"; break
  fi
done
if [ -z "$pick" ]; then
  echo "no corrected time series present on BOTH tracks yet"; exit 1
fi
echo "using $pick on both tracks"

for track in insar_geom_asc insar_geom_desc; do
  d="output/$track/mintpy"
  src="$d/$pick"
  echo "=== $track ==="
  env -u PROJ_LIB -u GDAL_DATA conda run --no-capture-output -n mintpy \
    timeseries2velocity.py "$src" -o "$d/velocityERA5.h5" 2>&1 | tail -3
done
