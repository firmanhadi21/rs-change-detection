#!/usr/bin/env bash
#
# The fire-and-smoke chain, in causal order.
#
# There is no single command for this, and there should not be: each step
# answers a different question, several are expensive, and you will often want
# only two or three of them. What this script encodes is the ORDER, and the
# date arithmetic that is easy to get wrong.
#
#   1 drought        was it dry?                     precondition
#   2 fire-danger    is it dangerous, on whose land? FDRS, forward-looking
#   3 smoke-track    where is the smoke going?       forward trajectories
#   4 smoke-exposure who is breathing it?            person-days by ISPU class
#   5 smoke-track    where did their air come from?  backward, the defensible one
#   6 haze           what did it look like?          PM2.5 + fires + admin
#   7 fire-record    what happened, per designation? closed seasons only
#   8 fire-brief     assemble it into one deliverable  reads 1-7, no data
#
# --steps REPLACES the list, it does not add to it: --steps 7 runs only step 7.
# The default is 1,2,3,4,5,6,8 -- everything except the record, which is opt-in
# for the burned-area reason below. For all of it: --steps 1,2,3,4,5,6,7,8
#
# The trap this exists to handle: the seven steps read six archives and they do
# not end on the same day. Measured 2026-08-09 --
#
#   ERA5-Land daily     8 days behind   binds steps 1, 2, 7
#   ERA5 hourly         6 days behind   step 3 (kinematic)
#   GDAS1 on S3         2 days behind   step 5 (HYSPLIT)
#   FIRMS               1 day behind    seeds and hotspots
#   CAMS               runs 3 days AHEAD (a forecast)
#   MODIS burned area 100 days behind   step 7 -- see below
#   WorldPop            2020 is the last year, and age structure is 2020 only
#
# So the newest date the whole chain shares is ERA5-Land's end. Pass it as
# --end; the script derives everything else from it.
#
# Step 7 is deliberately not run for a current season. MODIS burned area lags
# about three months, so a fire-record for this year would report zero hectares
# burned and look like good news. Run it against a closed season instead.
#
# Usage:
#   scripts/fire_smoke_chain.sh --end 2026-08-01 --admin Ketapang --name Ketapang \
#       [--zones data/forest.gpkg --zone-field FUNGSI_HTN] \
#       [--wide 107.0,-4.0,115.0,3.0] [--out output/chain] [--steps 1,2,3]
#
set -euo pipefail

END=""; ADMIN=""; NAME=""; ZONES=""; ZFIELD=""; WIDE=""; OUT="output/chain"
STEPS="1,2,3,4,5,6,8"

while [ $# -gt 0 ]; do
  case "$1" in
    --end)        END="$2";    shift 2 ;;
    --admin)      ADMIN="$2";  shift 2 ;;
    --name)       NAME="$2";   shift 2 ;;
    --zones)      ZONES="$2";  shift 2 ;;
    --zone-field) ZFIELD="$2"; shift 2 ;;
    --wide)       WIDE="$2";   shift 2 ;;
    --out)        OUT="$2";    shift 2 ;;
    --steps)      STEPS="$2";  shift 2 ;;
    -h|--help)    sed -n '2,45p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -n "$END" ]   || { echo "--end YYYY-MM-DD is required (see --help)" >&2; exit 2; }
[ -n "$ADMIN" ] || { echo "--admin NAME is required" >&2; exit 2; }
NAME="${NAME:-$ADMIN}"

# Dates derived from --end, so there is one number to change.
#   season   the three months before --end, for exposure and drought context
#   hysplit  GDAS1 is fresher than ERA5, so the backward step can run later
SEASON_START=$(python3 -c "
import datetime as dt,sys
print((dt.date.fromisoformat(sys.argv[1]) - dt.timedelta(days=90)).isoformat())
" "$END")
# Step 7 needs a longer run-up than the rest. Drought Code has a ~52-day time
# lag and the build-up starts months before the burning, so a 90-day window
# opens after every zone has already crossed its thresholds and reports them
# all crossing on day one -- the window's left edge masquerading as a finding.
RECORD_START=$(python3 -c "
import datetime as dt,sys
print((dt.date.fromisoformat(sys.argv[1]) - dt.timedelta(days=210)).isoformat())
" "$END")
HY_DATE=$(python3 -c "
import datetime as dt,sys
print((dt.date.fromisoformat(sys.argv[1]) + dt.timedelta(days=4)).isoformat())
" "$END")

AREA=(--admin "$ADMIN" -n "$NAME")
# A district-sized AOI under-reports which districts the smoke crosses, so the
# two smoke steps take a wider box when one is given.
if [ -n "$WIDE" ]; then WIDE_AREA=(--bbox "$WIDE" -n "$NAME"); else WIDE_AREA=("${AREA[@]}"); fi
# macOS ships bash 3.2, where expanding an EMPTY array under `set -u` is an
# unbound-variable error rather than nothing. Hence the ${a[@]+"${a[@]}"} guard
# used at every call site below.
ZONE_ARGS=()
if [ -n "$ZONES" ]; then
  [ -n "$ZFIELD" ] || { echo "--zones needs --zone-field" >&2; exit 2; }
  ZONE_ARGS=(--zones "$ZONES" --zone-field "$ZFIELD")
fi
Z=(${ZONE_ARGS[@]+"${ZONE_ARGS[@]}"})

run_step() {
  case ",$STEPS," in *",$1,"*) ;; *) return 0 ;; esac
  echo; echo "── $1. $2"; shift 2; echo "   \$ $*"; "$@"
}

run_step 1 "drought — was it dry?" \
  earthchange -s drought "${AREA[@]}" \
    --drought-end "$END" --spi-months 3 --cdi -o "$OUT/1_drought"

run_step 2 "fire-danger — FDRS, and which designation is driest" \
  earthchange -s fire-danger "${AREA[@]}" \
    --date "$END" --spinup 60 ${Z[@]+"${Z[@]}"} -o "$OUT/2_fire_danger"

run_step 3 "smoke-track forward — where the smoke goes" \
  earthchange -s smoke-track "${AREA[@]}" \
    --date "$END" --track-hours 48 --track-parcels 25 -o "$OUT/3_track_fwd"

run_step 4 "smoke-exposure — who breathes it, person-days by ISPU class" \
  earthchange -s smoke-exposure "${WIDE_AREA[@]}" \
    --season "$SEASON_START:$END" --pop-year 2020 -o "$OUT/4_exposure"

# HYSPLIT, because backward on the kinematic engine is refused: reversing a
# single-level integrator looks like source attribution while being no more
# defensible than the forward fan.
run_step 5 "smoke-track backward — where their air came from (HYSPLIT)" \
  earthchange -s smoke-track "${WIDE_AREA[@]}" \
    --date "$HY_DATE" --engine hysplit --direction backward \
    --track-hours 48 --track-parcels 12 -o "$OUT/5_track_back"

run_step 6 "haze — PM2.5 with fires and admin context" \
  earthchange -s haze "${AREA[@]}" \
    --haze-start "$SEASON_START" --haze-end "$END" -o "$OUT/6_haze"

# Step 7 is opt-in and wants a CLOSED season, for the burned-area reason above.
run_step 7 "fire-record — per-designation accountability (closed seasons only)" \
  earthchange -s fire-record "${AREA[@]}" \
    --season "$RECORD_START:$END" ${Z[@]+"${Z[@]}"} -o "$OUT/7_record"

# Step 8 reads the folders the others wrote, so it runs last and needs no data.
# In the default step list because seven folders of PNGs is an evidence base,
# not something you can hand to anybody.
run_step 8 "fire-brief — assemble the six claims into one deliverable" \
  earthbrief "$OUT" --lang "${BRIEF_LANG:-id}"

echo; echo "All outputs under $OUT/"
