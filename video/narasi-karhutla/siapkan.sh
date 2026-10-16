#!/bin/bash
# Put the footage and the backdrop still into public/.
#
# Neither is committed: the mp4 is 9 MB and the still is derived from it, so
# both are rebuilt here from the smoke-video run instead. The narration and
# music mp3s are NOT rebuilt by this script -- they come from ElevenLabs and
# cost credits, so they are kept out of the repo and have to be restored
# from a backup or regenerated. See README.md.
set -euo pipefail

cd "$(dirname "$0")"
ASAP=../../output/smoke_video_indonesia/indonesia_wildfire_smoke.mp4

if [ ! -f "$ASAP" ]; then
  echo "tidak ada $ASAP" >&2
  echo "jalankan dulu: earthchange detect --scenario smoke-video ... (Indonesia)" >&2
  exit 1
fi

mkdir -p public
cp -v "$ASAP" public/asap.mp4

# One frame from late in the clip, when the season's smoke is at its widest.
# Blurred to near-texture in LatarDiam, so only its colour really matters.
ffmpeg -nostdin -v error -y -ss 14 -i "$ASAP" -frames:v 1 public/latar.png
echo "latar.png dibuat"

missing=0
for f in 01-buka 02-sepekan 03-pulau 04-rekor 05-gambut 06-khg 07-berulang 08-tutup musik; do
  [ -f "public/audio/$f.mp3" ] || { echo "kurang: public/audio/$f.mp3"; missing=1; }
done
[ "$missing" = 0 ] && echo "audio lengkap" || echo "audio belum lengkap — lihat README.md"
