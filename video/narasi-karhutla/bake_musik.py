#!/usr/bin/env python3
"""Bake the score's automation into the file, instead of riding it in Remotion.

Remotion turns a per-frame `volume` function into a single ffmpeg `volume`
expression, one `between()` clause per distinct value. Over a 134-second
bed with fades that expression grew past what ffmpeg's parser accepts --
"Missing ')' or too many args" -- and the render failed while still
exiting 0 through the pipeline, so a stale mp4 sat there looking finished.

All of this automation is fixed and known ahead of time, so it belongs in
the asset. What gets applied here:

  atempo   The 135 s score holds real content only to about 127.5 s and
           then decays to nothing, which left the closing line and the
           sources card over dead air. Stretched to cover the full film.
           atempo preserves pitch, which Remotion's playbackRate does not.
  volume   Up for the title card, down under the narration, up again for
           the sources card. Four breakpoints, one small expression.
  afade    In from silence at the top, out under the last card.

Reads src/jadwal.json, so the duck lands on the same frames the cut does.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

AKAR = Path(__file__).parent
J = json.loads((AKAR / "src/jadwal.json").read_text())
MASUK = AKAR / "public/audio/musik.mp3"
KELUAR = AKAR / "public/audio/musik-mix.mp3"

FPS = J["fps"]
M = J["musik"]

# Rebuild the film's length exactly as jadwal.ts does.
judul_f = round(J["judul_detik"] * FPS)
jeda_f = round(J["jeda_detik"] * FPS)
kursor = judul_f
for nama in J["urutan"]:
    # Must match jadwal.ts exactly: Math.ceil on the speech, then the beat.
    kursor += math.ceil(J["durasi"][nama] * FPS) + jeda_f
akhir_narasi_f = kursor
total_f = akhir_narasi_f + round(J["tutup_detik"] * FPS)

film = total_f / FPS
akhir_narasi = akhir_narasi_f / FPS
judul = judul_f / FPS

# Stretch so the score's content, not its decay, covers the whole film.
tempo = M["isi_berakhir_detik"] / film
if not 0.5 <= tempo <= 2.0:
    sys.exit(f"atempo {tempo:.3f} di luar jangkauan satu tahap")

A, B = M["gain_kartu"], M["gain_narasi"]
# Ramp down just before the first word, back up just after the last.
t1, t2 = judul - 0.7, judul + 0.3
t3, t4 = akhir_narasi - 0.3, akhir_narasi + 0.8

vol = (
    f"if(lt(t,{t1:.3f}),{A},"
    f"if(lt(t,{t2:.3f}),{A}+({B}-{A})*(t-{t1:.3f})/{t2 - t1:.3f},"
    f"if(lt(t,{t3:.3f}),{B},"
    f"if(lt(t,{t4:.3f}),{B}+({A}-{B})*(t-{t3:.3f})/{t4 - t3:.3f},{A}))))"
)

rantai = (
    f"atempo={tempo:.5f},"
    f"volume='{vol}':eval=frame,"
    f"afade=t=in:st=0:d=1.4,"
    f"afade=t=out:st={film - 1.8:.3f}:d=1.8"
)

print(f"film          : {total_f} frame / {film:.3f} s")
print(f"narasi sampai : {akhir_narasi:.3f} s")
print(f"atempo        : {tempo:.5f}  ({M['isi_berakhir_detik']} s -> {film:.1f} s)")
print(f"gain          : kartu {A}  narasi {B}")

subprocess.run(
    ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y",
     "-i", str(MASUK), "-af", rantai,
     "-t", f"{film:.3f}", "-c:a", "libmp3lame", "-q:a", "2", "-ar", "44100",
     str(KELUAR)],
    check=True)

keluar_s = float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "csv=p=0", str(KELUAR)],
    capture_output=True, text=True, check=True).stdout.strip())
print(f"\n{KELUAR.name}: {keluar_s:.3f} s")
if keluar_s < film - 0.1:
    sys.exit(f"bed terlalu pendek: {keluar_s:.3f} < {film:.3f}")
print("bed menutupi seluruh film")
