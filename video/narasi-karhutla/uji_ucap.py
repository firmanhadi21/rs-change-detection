#!/usr/bin/env python3
"""Pronunciation test takes for an acronym: same voice, model and sentence,
several spellings, so a listener can pick the one the voice says right.

  ELEVENLABS_API_KEY=... python3 uji_ucap.py

Writes public/audio/telusur/uji/<n>.mp3 and uji_semua.mp3 (all takes in
order, 1.2 s apart). Nothing in the film changes until a spelling is chosen.
"""
import json
import os
import subprocess
from pathlib import Path

AKAR = Path(__file__).parent
N = json.loads((AKAR / "src/narasiTelusur.json").read_text())
OUT = AKAR / "public/audio/telusur/uji"
OUT.mkdir(parents=True, exist_ok=True)
KALIMAT = "Lain halnya dengan {}. Hampir sembilan puluh persen arealnya tumpang tindih."
EJAAN = {
    "A": "pé-té-a-ém",        # current spelling, a fresh take
    "B": "pé té a ém",        # letters spaced, no hyphens
    "C": "péh-téh-a-ém",      # trailing h holds the open e
    "D": "pay-tay-a-em",      # anglicised vowels
}

from elevenlabs.client import ElevenLabs
c = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
daftar = []
for k, e in EJAAN.items():
    p = OUT / f"{k}.mp3"
    if not p.exists():
        audio = c.text_to_speech.convert(voice_id=N["suara"], model_id=N["model"],
                                         text=KALIMAT.format(e),
                                         output_format="mp3_44100_128")
        p.write_bytes(b"".join(audio))
    print(f"{k}: {e:<16} -> {p}")
    daftar.append(p)

# all takes in one file, with a short gap between them
sil = OUT / "jeda.mp3"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "anullsrc=r=44100:cl=mono", "-t", "1.2", "-q:a", "2", str(sil)], check=True)
lst = OUT / "daftar.txt"
lst.write_text("".join(f"file '{p}'\nfile '{sil}'\n" for p in daftar))
semua = OUT / "uji_semua.mp3"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-ac", "1", "-ar", "44100", "-q:a", "2", str(semua)], check=True)
print(f"all takes, in order A B C D: {semua}")
