#!/bin/bash
# Resume the descending run after relaxing minTempCoh.
#
# The previous attempt loaded all 354 interferograms (the grid normalisation
# worked) but started before minTempCoh was lowered, so it still died on the
# reliable-pixel gate that sits ahead of correct_troposphere.
#
# --no-capture-output: conda run otherwise buffers everything until the process
# exits, which left the log empty for a run that takes hours.
cd /Users/firmanhadi/GitHub/rs-change-detection/output/insar_geom_desc/mintpy || exit 1

nohup env -u PROJ_LIB -u GDAL_DATA \
  conda run --no-capture-output -n mintpy smallbaselineApp.py earthchange.cfg \
  > /Users/firmanhadi/mintpy_desc.log 2>&1 &

echo "desc restarted pid $! -> /Users/firmanhadi/mintpy_desc.log"
