#!/usr/bin/env python3
"""Generate TTS audio for all 5 scenes using ElevenLabs Bian voice.

Requirements:
    pip install elevenlabs
    ELEVENLABS_API_KEY in ~/.hermes/.env

Input:  narration/capkala_narration_v4.txt
Output: audio/scene_00.mp3 ... scene_04.mp3
"""

import os, subprocess, re

# Read API key
key = None
env_path = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            m = re.match(r'^ELEVENLABS_API_KEY\s*=\s*(.+)', line.strip())
            if m:
                key = m.group(1).strip().strip('"').strip("'")
                break
if not key:
    raise RuntimeError("ELEVENLABS_API_KEY not found in ~/.hermes/.env")

from elevenlabs.client import ElevenLabs
client = ElevenLabs(api_key=key)

# Parse narration
narration_path = os.path.join(os.path.dirname(__file__), "..", "narration", "capkala_narration_v4.txt")
with open(narration_path) as f:
    lines = f.readlines()

scenes = []
current_name = None
current_text = []
for line in lines:
    line = line.strip()
    if line.startswith("## SCENE"):
        if current_name:
            scenes.append((current_name, " ".join(current_text)))
        current_name = line.replace("## SCENE", "").strip()
        current_text = []
    elif line and not line.startswith("#"):
        current_text.append(line)
if current_name:
    scenes.append((current_name, " ".join(current_text)))

print(f"Parsed {len(scenes)} scenes")

VOICE_ID = "1k39YpzqXZn52BgyLyGO"  # Bian - ElevenLabs Indonesian
outdir = os.path.join(os.path.dirname(__file__), "..", "audio")
os.makedirs(outdir, exist_ok=True)

# Clean old
for f in os.listdir(outdir):
    if f.endswith('.mp3'):
        os.remove(os.path.join(outdir, f))

total_dur = 0
for i, (name, text) in enumerate(scenes):
    outpath = os.path.join(outdir, f"scene_{i:02d}.mp3")
    short_name = name.split("\u2014")[0].strip() if "\u2014" in name else name[:40]
    print(f"Scene {i}: {short_name}... ({len(text)} chars)")

    audio = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        model_id="eleven_multilingual_v2",
        text=text,
    )
    with open(outpath, "wb") as f:
        f.write(b"".join(audio))

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", outpath],
        capture_output=True, text=True
    )
    dur = float(result.stdout.strip())
    total_dur += dur
    print(f"  {dur:.1f}s | total {total_dur/60:.1f} min")

print(f"\nDone. Total: {total_dur/60:.1f} min")
