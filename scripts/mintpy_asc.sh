#!/bin/bash
# Resume the ascending run after relaxing minTempCoh.
#
# ifgramStack.h5 and timeseries.h5 are kept, so smallbaselineApp skips the
# expensive load and inversion and picks up at the mask step -- the gate that
# aborted the run before correct_troposphere could ever execute.
cd /Users/firmanhadi/GitHub/rs-change-detection/output/insar_geom_asc/mintpy || exit 1

nohup env -u PROJ_LIB -u GDAL_DATA \
  conda run -n mintpy smallbaselineApp.py earthchange.cfg \
  > /Users/firmanhadi/mintpy_asc.log 2>&1 &

echo "asc restarted pid $! -> /Users/firmanhadi/mintpy_asc.log"
