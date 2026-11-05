#!/usr/bin/env python3
"""Bake the companion film's music bed. Same method as bake_musik.py.

Reuses the first film's normalised score rather than generating a new
one: these are companion pieces and should sound like it, and an unused
generation costs credits for nothing.

The companion is shorter (about 108 s against 134 s), so atempo goes the
other way -- the bed is sped up slightly instead of slowed, which keeps
its climax landing on the closing line rather than halfway through.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

AKAR = Path(__file__).parent
# Any companion film can reuse this: pass its schedule and its output.
#   python3 bake_musik_bukti.py --jadwal src/jadwalKonsesi.json \
#       --keluar public/audio/konsesi/musik-konsesi.mp3
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--jadwal", default="src/jadwalBukti.json")
_ap.add_argument("--keluar", default="public/audio/bukti/musik-bukti.mp3")
# --sambung S: for a film much longer than the score (Part 4, ~205 s), join a second
# pass of the score from S seconds (past the intro) with an XF-second crossfade, so
# atempo stays near 1 instead of slowing the bed to ~60% and smearing it.
_ap.add_argument("--sambung", type=float, default=None)
_ap.add_argument("--silang", type=float, default=8.0)
_a = _ap.parse_args()
J = json.loads((AKAR / _a.jadwal).read_text())
MASUK = AKAR / "public/audio/musik.mp3"          # already -30 LUFS
KELUAR = AKAR / _a.keluar
KELUAR.parent.mkdir(parents=True, exist_ok=True)

FPS, M = J["fps"], J["musik"]
judul_f = round(J["judul_detik"] * FPS)
jeda_f = round(J["jeda_detik"] * FPS)
kursor = judul_f
for nama in J["urutan"]:
    kursor += math.ceil(J["durasi"][nama] * FPS) + jeda_f
akhir_narasi_f = kursor
total_f = akhir_narasi_f + round(J["tutup_detik"] * FPS)
film, akhir_narasi, judul = total_f / FPS, akhir_narasi_f / FPS, judul_f / FPS

isi = M["isi_berakhir_detik"]
if _a.sambung is not None:
    isi = 2 * isi - _a.sambung - _a.silang
tempo = isi / film
if not 0.5 <= tempo <= 2.0:
    sys.exit(f"atempo {tempo:.3f} di luar jangkauan satu tahap")

A, B = M["gain_kartu"], M["gain_narasi"]
t1, t2 = judul - 0.6, judul + 0.3
t3, t4 = akhir_narasi - 0.3, akhir_narasi + 0.8
vol = (f"if(lt(t,{t1:.3f}),{A},"
       f"if(lt(t,{t2:.3f}),{A}+({B}-{A})*(t-{t1:.3f})/{t2-t1:.3f},"
       f"if(lt(t,{t3:.3f}),{B},"
       f"if(lt(t,{t4:.3f}),{B}+({A}-{B})*(t-{t3:.3f})/{t4-t3:.3f},{A}))))")

print(f"film   {total_f} frame / {film:.3f} s")
print(f"atempo {tempo:.5f}  ({isi:.1f} s -> {film:.1f} s)")

rantai = (f"atempo={tempo:.5f},volume='{vol}':eval=frame,"
          f"afade=t=in:st=0:d=1.2,afade=t=out:st={film-1.6:.3f}:d=1.6")
if _a.sambung is None:
    saring = ["-af", rantai]
else:
    e = M["isi_berakhir_detik"]
    saring = ["-filter_complex",
              f"[0:a]atrim=0:{e},asetpts=PTS-STARTPTS[a];"
              f"[0:a]atrim={_a.sambung}:{e},asetpts=PTS-STARTPTS[b];"
              f"[a][b]acrossfade=d={_a.silang}:c1=tri:c2=tri,{rantai}[o]", "-map", "[o]"]
subprocess.run(
    ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y",
     "-i", str(MASUK), *saring,
     "-t", f"{film:.3f}", "-c:a", "libmp3lame", "-q:a", "2", "-ar", "44100",
     str(KELUAR)], check=True)

keluar_s = float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "csv=p=0", str(KELUAR)],
    capture_output=True, text=True, check=True).stdout.strip())
print(f"{KELUAR.name}: {keluar_s:.3f} s")
if keluar_s < film - 0.1:
    sys.exit(f"bed terlalu pendek: {keluar_s:.3f} < {film:.3f}")
print("bed menutupi seluruh film")
