#!/usr/bin/env python3
"""Generate TTS audio for all 5 scenes using ElevenLabs Bian voice.

Requirements:
    pip install elevenlabs
    ELEVENLABS_API_KEY set via (checked in order):
      1. environment variable ELEVENLABS_API_KEY
      2. a `.env` file in the repository root
      3. ~/.hermes/.env

Input:  narration/capkala_narration_v4.txt
Output: audio/scene_00.mp3 ... scene_04.mp3
"""

import os, subprocess, re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _key_from_env_file(path):
    """Return ELEVENLABS_API_KEY from a KEY=value .env file, or None."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            m = re.match(r'^\s*ELEVENLABS_API_KEY\s*=\s*(.+)', line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


# Resolve API key: env var → repo .env → ~/.hermes/.env
key = (
    os.environ.get("ELEVENLABS_API_KEY")
    or _key_from_env_file(os.path.join(REPO_ROOT, ".env"))
    or _key_from_env_file(os.path.expanduser("~/.hermes/.env"))
)
if not key:
    raise RuntimeError(
        "ELEVENLABS_API_KEY not found.\n"
        "Set it one of these ways:\n"
        "  export ELEVENLABS_API_KEY=your_key_here      # environment variable\n"
        "  echo 'ELEVENLABS_API_KEY=your_key_here' > .env   # repo root .env file\n"
        "Get a key at https://elevenlabs.io/"
    )

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
