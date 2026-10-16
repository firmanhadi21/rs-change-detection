#!/bin/bash
# Level the ElevenLabs renders so the voice carries and the bed stays under it.
#
# As generated, the narration sits at about -26.8 LUFS and the music at
# -14.1 -- the bed is louder than the voice by a wide margin, and even cut
# to a fifth of its gain it ended up only 1.3 LU below the narration, which
# is nowhere near enough to speak over. Both are normalised here, once, with
# two-pass loudnorm, so the Remotion side can use plain gain of 1.0 and the
# mix does not depend on a volume number someone guessed.
#
#   narasi -> -16 LUFS, true peak -1.5 dBTP   (the voice)
#   musik  -> -30 LUFS, true peak -9 dBTP     (14 LU under the voice)
#
# -9 is loudnorm's lowest permitted TP, and here it is only a backstop: the
# bed's crest is about 14 dB, so at -30 LUFS it peaks near -16 dBFS on its
# own and the limiter never engages. That matters because bake_musik.py
# lifts the bed 2.5x over the two cards, which still leaves ~8 dB spare.
#
# Afterwards, run bake_musik.py -- it stretches the bed over the film and
# bakes its automation in, and that is the file the film actually plays.
#
# Raw downloads are kept in public/audio/mentah/ and never overwritten, so
# this is re-runnable and the originals stay auditable.
set -euo pipefail

cd "$(dirname "$0")"
AUDIO=public/audio
MENTAH=$AUDIO/mentah
mkdir -p "$MENTAH"

# First run: move the untouched downloads aside.
for f in "$AUDIO"/*.mp3; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  [ -e "$MENTAH/$base" ] || mv "$f" "$MENTAH/$base"
done

normalkan() {
  local src=$1 dst=$2 I=$3 TP=$4 LRA=$5

  # Pass one: measure.
  local json
  json=$(ffmpeg -nostdin -hide_banner -nostats -v info -i "$src" \
    -af "loudnorm=I=$I:TP=$TP:LRA=$LRA:print_format=json" \
    -f null - 2>&1 | sed -n '/^{/,/^}/p')

  local get
  get() { echo "$json" | grep "\"$1\"" | sed 's/.*: *"//;s/".*//'; }

  # Pass two: apply, linearly where the headroom allows.
  ffmpeg -nostdin -hide_banner -nostats -v error -y -i "$src" \
    -af "loudnorm=I=$I:TP=$TP:LRA=$LRA\
:measured_I=$(get input_i)\
:measured_TP=$(get input_tp)\
:measured_LRA=$(get input_lra)\
:measured_thresh=$(get input_thresh)\
:offset=$(get target_offset)\
:linear=true:print_format=summary" \
    -c:a libmp3lame -q:a 2 -ar 44100 "$dst"

  # The edit is cut to these lengths, so a shift here would desync the film.
  local a b
  a=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$src")
  b=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$dst")
  awk -v a="$a" -v b="$b" -v n="$(basename "$dst")" \
    'BEGIN { d = a - b; if (d < 0) d = -d;
             if (d > 0.05) { printf "GESER %s: %.3f -> %.3f\n", n, a, b; exit 1 }
             printf "  %-16s %.3f s\n", n, b }'
}

for f in "$MENTAH"/*.mp3; do
  base=$(basename "$f")
  if [ "$base" = "musik.mp3" ]; then
    normalkan "$f" "$AUDIO/$base" -30 -9 11
  else
    normalkan "$f" "$AUDIO/$base" -16 -1.5 7
  fi
done

echo "selesai — narasi -16 LUFS, musik -30 LUFS"
python3 -I "$(dirname "$0")/bake_musik.py"
