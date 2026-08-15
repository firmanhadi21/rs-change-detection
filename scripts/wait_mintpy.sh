#!/bin/bash
# Block until both smallbaselineApp runs finish, then summarise.
#
# Exists so progress is reported on completion rather than by polling on a
# timer: the interesting moment is when velocity.h5 lands, not any fixed
# interval. Prints enough state to tell success from silent failure, since the
# failure mode here has repeatedly been a run that ends early rather than one
# that errors.
cd /Users/firmanhadi/GitHub/rs-change-detection || exit 1

while pgrep -f "smallbaselineApp.py" > /dev/null 2>&1; do
  sleep 60
done

echo "=== both runs ended $(date) ==="
for t in desc asc; do
  d=output/insar_geom_$t/mintpy
  echo "--- $t ---"
  echo -n "  velocity.h5: "
  [ -f "$d/velocity.h5" ] && echo "PRESENT" || echo "ABSENT"
  echo -n "  ERA5 grib downloaded: "
  ls "$d/ERA5" 2>/dev/null | grep -c grb
  echo -n "  last step reached: "
  grep -aoE "^step - [a-zA-Z_]+" "/Users/firmanhadi/mintpy_$t.log" 2>/dev/null | tail -1 || echo "unknown"
  # A run that died leaves its traceback here; a clean one leaves nothing.
  grep -aE "RuntimeError|Traceback|Error:" "/Users/firmanhadi/mintpy_$t.log" 2>/dev/null | tail -2
done
