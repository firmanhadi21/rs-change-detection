#!/usr/bin/env python3
"""Narration for the concessions film: generate, level, measure.

  1. each line of src/narasiKonsesi.json -> public/audio/konsesi/mentah/<id>.mp3
     via ElevenLabs. A clip that already exists is NOT regenerated: takes cost
     credits and never come back the same, and the cut is measured off them.
     Delete a clip to redo just that one.
  2. two-pass loudnorm to -16 LUFS / -1.5 dBTP -> public/audio/konsesi/<id>.mp3,
     the same target normalisasi.sh gives the other two films.
  3. ffprobe each levelled clip and write its length into
     src/jadwalKonsesi.json, which is what the cut and the bed are built from.

    ELEVENLABS_API_KEY=... python3 tts_konsesi.py
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

AKAR = Path(__file__).parent
N = json.loads((AKAR / "src/narasiKonsesi.json").read_text())
JP = AKAR / "src/jadwalKonsesi.json"
J = json.loads(JP.read_text())
AUD = AKAR / "public/audio/konsesi"
MENTAH = AUD / "mentah"
MENTAH.mkdir(parents=True, exist_ok=True)


def durasi(p):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)], capture_output=True, text=True,
        check=True).stdout.strip())


def buat(nama, teks):
    from elevenlabs.client import ElevenLabs
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY tidak ada")
    c = ElevenLabs(api_key=key)
    audio = c.text_to_speech.convert(voice_id=N["suara"], model_id=N["model"],
                                     text=teks, output_format="mp3_44100_128")
    tmp = MENTAH / f"{nama}.mp3.part"
    tmp.write_bytes(b"".join(audio))
    tmp.rename(MENTAH / f"{nama}.mp3")


def normalkan(src, dst, I=-16, TP=-1.5, LRA=7):
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(src),
         "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json",
         "-f", "null", "-"], capture_output=True, text=True, check=True)
    # loudnorm prints its JSON block last-but-not-always-last; take the
    # final {...} in stderr.
    blok = re.findall(r"\{[^{}]*\}", r.stderr, re.S)
    if not blok:
        sys.exit(f"loudnorm tidak mengeluarkan JSON untuk {src.name}")
    m = json.loads(blok[-1])
    af = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={m['input_i']}"
          f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
          f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
          f":linear=true")
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y",
                    "-i", str(src), "-af", af, "-c:a", "libmp3lame", "-q:a",
                    "2", "-ar", "44100", str(dst)], check=True)
    a, b = durasi(src), durasi(dst)
    if abs(a - b) > 0.05:
        sys.exit(f"GESER {dst.name}: {a:.3f} -> {b:.3f}")
    return b


for nama in J["urutan"]:
    if not (MENTAH / f"{nama}.mp3").exists():
        print(f"ElevenLabs  {nama}")
        buat(nama, N["teks"][nama])
    d = normalkan(MENTAH / f"{nama}.mp3", AUD / f"{nama}.mp3")
    J["durasi"][nama] = round(d, 2)
    print(f"  {nama:<16} {d:6.2f} s")

JP.write_text(json.dumps(J, indent=2, ensure_ascii=False) + "\n")
print(f"narasi total {sum(J['durasi'].values()):.1f} s -> {JP.name}")
