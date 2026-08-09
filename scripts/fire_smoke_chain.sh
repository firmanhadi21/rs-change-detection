#!/usr/bin/env bash
#
# Superseded by `earthchain`, which ships with the package and therefore works
# from any directory instead of only from a checkout of this repo.
#
#   pip install earthchange
#   earthchain --end 2026-08-01 --admin Ketapang --zones forest.gpkg \
#              --zone-field FUNGSI_HTN --wide 107.0,-4.0,115.0,3.0
#
# Kept as a shim because it was documented and people have it in their history.
# It forwards every argument unchanged; the flags are identical.
#
set -euo pipefail
echo "note: fire_smoke_chain.sh is now a shim for 'earthchain'," >&2
echo "      which works from any directory. Same flags." >&2
exec earthchain "$@"
