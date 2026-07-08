#!/bin/bash
# Assemble all 5 scene videos from images + audio.
# Run 01_generate_tts.py first to produce audio files.
#
# Input:  images/   (scene slides + raw satellite images)
#         audio/    (scene_00.mp3 ... scene_04.mp3)
# Output: scenes/   (individual scene videos)
#         capkala_investigation.mp4 (final combined video)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJ_DIR="$(dirname "$SCRIPT_DIR")"
IMG_DIR="$PROJ_DIR/images"
AUDIO_DIR="$PROJ_DIR/audio"
SCENE_DIR="$PROJ_DIR/scenes"
OUT="$PROJ_DIR/capkala_investigation.mp4"

W=1920; H=1080; FPS=30
TITLE_DUR=1.5

mkdir -p "$SCENE_DIR"
rm -f "$SCENE_DIR"/*.mp4 "$OUT"

echo "=== Pre-scaling images ==="
SCALED="/tmp/capkala_scaled"
mkdir -p "$SCALED"
for img in "$IMG_DIR"/scene_*.png "$IMG_DIR"/*_raw.png "$IMG_DIR"/*.jpg "$IMG_DIR"/*.png; do
    [ -f "$img" ] || continue
    base=$(basename "$img")
    ffmpeg -y -i "$img" -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2" \
        "$SCALED/${base%.*}.png" 2>/dev/null
done

# === Scene 1: PENDAHULUAN ===
echo "Scene 1: PENDAHULUAN"
ffmpeg -y -loop 1 -framerate $FPS -i "$SCALED/scene_01_pendahuluan.png" -i "$AUDIO_DIR/scene_00.mp3" \
    -c:v libx264 -preset fast -crf 18 -tune stillimage -c:a aac -b:a 192k -ar 44100 -ac 2 \
    -pix_fmt yuv420p -r $FPS -shortest "$SCENE_DIR/scene_01_pendahuluan.mp4" 2>/dev/null
echo "  $(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SCENE_DIR/scene_01_pendahuluan.mp4")s"

# === Scene 2: CITRA SENTINEL-2 ===
echo "Scene 2: CITRA SENTINEL-2"
ffmpeg -y -loop 1 -framerate $FPS -i "$SCALED/scene_02_sentinel2.png" -i "$AUDIO_DIR/scene_01.mp3" \
    -c:v libx264 -preset fast -crf 18 -tune stillimage -c:a aac -b:a 192k -ar 44100 -ac 2 \
    -pix_fmt yuv420p -r $FPS -shortest "$SCENE_DIR/scene_02_sentinel2.mp4" 2>/dev/null
echo "  $(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SCENE_DIR/scene_02_sentinel2.mp4")s"

# === Scene 3: ANALISIS SPASIAL ===
echo "Scene 3: ANALISIS SPASIAL"
ffmpeg -y -loop 1 -framerate $FPS -i "$SCALED/scene_03_analisis_spasial.png" -i "$AUDIO_DIR/scene_02.mp3" \
    -c:v libx264 -preset fast -crf 18 -tune stillimage -c:a aac -b:a 192k -ar 44100 -ac 2 \
    -pix_fmt yuv420p -r $FPS -shortest "$SCENE_DIR/scene_03_analisis_spasial.mp4" 2>/dev/null
echo "  $(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SCENE_DIR/scene_03_analisis_spasial.mp4")s"

# === Scene 4: METODOLOGI (title card + 5 pure images) ===
echo "Scene 4: METODOLOGI"
METH_AUDIO="$AUDIO_DIR/scene_03.mp3"
PURE_DIR="/tmp/capkala_pure"
mkdir -p "$PURE_DIR"
rm -f "$PURE_DIR"/*.mp4

# Step durations (proportional to narration char count)
SPLITS=(0 11.0 33.0 51.0 84.0)
STEP_IMAGES=(
    "$SCALED/sentinel2_raw.png"
    "$SCALED/sirad_raw.png"
    "$SCALED/planetscope_before_after.png"
    "$SCALED/bhumi_screenshot.png"
    "$SCALED/infographic.png"
)
AUDIO_DUR=$(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$METH_AUDIO")
LAST_DUR=$(python3 -c "print($AUDIO_DUR - 84.0)")

# Split and render each step
for i in 0 1 2 3 4; do
    start=${SPLITS[$i]}
    if [ $i -eq 4 ]; then
        len=$LAST_DUR
    else
        next=${SPLITS[$((i+1))]}
        len=$(python3 -c "print($next - $start)")
    fi
    
    ffmpeg -y -ss $start -t $len -i "$METH_AUDIO" -c:a copy "$PURE_DIR/step_$((i+1)).mp3" 2>/dev/null
    
    ffmpeg -y -loop 1 -framerate $FPS -i "${STEP_IMAGES[$i]}" -i "$PURE_DIR/step_$((i+1)).mp3" \
        -c:v libx264 -preset ultrafast -crf 23 -tune stillimage \
        -c:a aac -b:a 192k -ar 44100 -ac 2 -pix_fmt yuv420p -r $FPS -shortest \
        "$PURE_DIR/pure_0$((i+1)).mp4" 2>/dev/null
    echo "  Step $((i+1)): ${len}s"
done

# Concat steps
cat > "$PURE_DIR/concat.txt" << 'PUREEOF'
file 'pure_01.mp4'
file 'pure_02.mp4'
file 'pure_03.mp4'
file 'pure_04.mp4'
file 'pure_05.mp4'
PUREEOF
ffmpeg -y -f concat -safe 0 -i "$PURE_DIR/concat.txt" -c copy "$PURE_DIR/all_pure.mp4" 2>/dev/null

# Title card + silent audio
ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t $TITLE_DUR -c:a aac -b:a 192k "$PURE_DIR/silence.m4a" 2>/dev/null
ffmpeg -y -loop 1 -framerate $FPS -t $TITLE_DUR -i "$SCALED/scene_04_metodologi_title.png" \
    -c:v libx264 -preset ultrafast -crf 18 -tune stillimage -pix_fmt yuv420p -r $FPS -an \
    "$PURE_DIR/title.mp4" 2>/dev/null

# Prepend title to methodology
ffmpeg -y \
    -i "$PURE_DIR/title.mp4" -i "$PURE_DIR/all_pure.mp4" \
    -i "$PURE_DIR/silence.m4a" -i "$METH_AUDIO" \
    -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]" \
    -map "[v]" -map "[a]" -c:v libx264 -preset fast -crf 18 \
    -c:a aac -b:a 192k -ar 44100 -ac 2 -pix_fmt yuv420p -r $FPS \
    "$SCENE_DIR/scene_04_metodologi.mp4" 2>/dev/null
echo "  $(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SCENE_DIR/scene_04_metodologi.mp4")s"

# === Scene 5: KESIMPULAN ===
echo "Scene 5: KESIMPULAN"
ffmpeg -y -loop 1 -framerate $FPS -i "$SCALED/scene_05_kesimpulan.png" -i "$AUDIO_DIR/scene_04.mp3" \
    -c:v libx264 -preset fast -crf 18 -tune stillimage -c:a aac -b:a 192k -ar 44100 -ac 2 \
    -pix_fmt yuv420p -r $FPS -shortest "$SCENE_DIR/scene_05_kesimpulan.mp4" 2>/dev/null
echo "  $(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SCENE_DIR/scene_05_kesimpulan.mp4")s"

# === Final assembly ===
echo ""
echo "=== Combining all 5 scenes ==="
ffmpeg -y \
    -i "$SCENE_DIR/scene_01_pendahuluan.mp4" \
    -i "$SCENE_DIR/scene_02_sentinel2.mp4" \
    -i "$SCENE_DIR/scene_03_analisis_spasial.mp4" \
    -i "$SCENE_DIR/scene_04_metodologi.mp4" \
    -i "$SCENE_DIR/scene_05_kesimpulan.mp4" \
    -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a][3:v][3:a][4:v][4:a]concat=n=5:v=1:a=1[v][a]" \
    -map "[v]" -map "[a]" \
    -c:v libx264 -preset fast -crf 18 -c:a aac -b:a 192k -ar 44100 -ac 2 \
    -pix_fmt yuv420p -r $FPS "$OUT" 2>/dev/null

SIZE=$(ls -lh "$OUT" | awk '{print $5}')
DUR=$(ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT")
echo "Final: $SIZE, ${DUR}s ($(python3 -c "print(f'{float($DUR)/60:.1f}')") min)"

# Cleanup
rm -rf "$SCALED" "$PURE_DIR"
echo "Done."
