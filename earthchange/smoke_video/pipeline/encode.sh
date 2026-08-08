#!/bin/bash
# Step 5 — encode frames to MP4 + GIF (requires ffmpeg)
set -e
cd "$(dirname "$0")"

# MP4: 24 fps, brief clone-hold at start and end
ffmpeg -y -framerate 24 -i frames/f_%04d.png \
  -vf "tpad=start_mode=clone:start_duration=1.2:stop_mode=clone:stop_duration=2.5,format=yuv420p" \
  -c:v libx264 -preset slow -crf 18 -movflags +faststart \
  out/ketapang_wildfire_smoke.mp4

# GIF: 540 px, 12 fps, optimized palette
ffmpeg -y -framerate 24 -i frames/f_%04d.png \
  -vf "tpad=stop_mode=clone:stop_duration=2,fps=12,scale=540:540:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" \
  out/ketapang_wildfire_smoke.gif

ls -la out/
