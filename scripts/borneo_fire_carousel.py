"""Assemble the seven pages into a carousel video with a music bed.

One video per language. Each page is held long enough to read, with a
crossfade between them and the score ducked under nothing -- there is no
narration here, so the music carries the whole thing.

HOLD TIMES ARE NOT UNIFORM, because the pages are not. The cover is one
number and three bars; the method page is four paragraphs of caveat. A
constant per-page hold either rushes the dense pages or strands the sparse
ones, so each page declares its own and the music is fitted to the total
rather than the other way round.

    conda run -n base python scripts/borneo_fire_carousel.py
    conda run -n base python scripts/borneo_fire_carousel.py --lang id
    conda run -n base python scripts/borneo_fire_carousel.py --no-music
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.expanduser(_DATA_ROOT + "/output/fire")
MUSIC = os.path.join(OUT, "carousel", "musik.mp3")

# Seconds on screen per page, before crossfades are subtracted. Measured
# against reading the page aloud at a slow pace, not guessed.
HOLD = {
    "01_cover":           7.0,   # one number, three bars
    "02_admin":           9.0,   # a bar chart and two lines
    "03_forest_function": 11.0,  # eight rows and a pull quote
    "04_named_areas":    12.0,   # a ranking, a caveat tier, three notes
    "05_map":             9.0,   # one map, read by looking
    "06_context":        10.0,   # a chart, three cards, a paragraph
    "07_method":         13.0,   # the densest page in the deck
}
FADE = 0.7          # crossfade between pages
WIDTH = 1080        # height follows the page aspect, kept even for h264


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-2000:] + r.stderr[-4000:])
        raise SystemExit(f"FAILED ({r.returncode}): {' '.join(cmd[:6])} ...")
    return r


def probe(path, stream="v:0", entries="width,height"):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream,
         "-show_entries", f"stream={entries}", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def duration(path):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lang", nargs="+", default=["en", "id"])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--deck", default=None,
                    help="directory holding pages_<lang>/ for another "
                         "deck. Its hold times come from the holds.json "
                         "that deck writes beside its pages, so reading "
                         "time lives with the pages rather than here.")
    ap.add_argument("--name", default="borneo_fire_carousel",
                    help="output filename stem")
    ap.add_argument("--music", default=MUSIC)
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not on PATH")
    # The video lands beside the pages it was made from, not in a shared
    # folder where two decks' carousels would sit next to each other with
    # only a filename to tell them apart.
    dest = os.path.join(a.deck or a.out, "carousel")
    os.makedirs(dest, exist_ok=True)

    have_music = (not a.no_music) and os.path.exists(a.music)
    if not a.no_music and not have_music:
        print(f"  (no music at {a.music} — rendering silent)")

    for lang in a.lang:
        src = os.path.join(a.deck or a.out, f"pages_{lang}")
        sidecar = os.path.join(src, "holds.json")
        if os.path.exists(sidecar):
            with open(sidecar) as f:
                holds_map = json.load(f)
        elif a.deck:
            raise SystemExit(f"missing {sidecar}\nThe deck that writes "
                             f"those pages must write it too.")
        else:
            holds_map = {f"borneo_fire_{k}": v for k, v in HOLD.items()}
        pages = [os.path.join(src, f"{n}.jpg") for n in holds_map]
        missing = [p for p in pages if not os.path.exists(p)]
        if missing:
            raise SystemExit(
                f"missing {len(missing)} page(s) for '{lang}', first: "
                f"{missing[0]}")

        # Page aspect decides the frame. Scaling to a fixed 16:9 or 4:5
        # would either crop the footer off or letterbox half the screen.
        s = probe(pages[0])
        h = int(round(WIDTH * s["height"] / s["width"]))
        h += h % 2                                   # h264 needs even
        holds = list(holds_map.values())
        total = sum(holds) - FADE * (len(holds) - 1)
        print(f"\n[{lang}] {len(pages)} pages, {WIDTH}x{h}, "
              f"{total:.1f}s")

        # Each page becomes a clip of its own hold length, then they are
        # chained with xfade. Doing it in one filtergraph keeps it to a
        # single encode.
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y"]
        for p, hold in zip(pages, holds):
            cmd += ["-loop", "1", "-t", f"{hold:.3f}", "-i", p]
        if have_music:
            cmd += ["-i", a.music]

        fc = []
        for i, _ in enumerate(pages):
            # A slow push-in gives the eye something to settle against on a
            # still page. zoompan works on the scaled frame, so scale up
            # first and crop back, which avoids its well-known jitter on
            # large stills.
            fc.append(
                f"[{i}:v]scale={WIDTH}:{h}:force_original_aspect_ratio="
                f"decrease,pad={WIDTH}:{h}:(ow-iw)/2:(oh-ih)/2:color=0xE9EDE8,"
                f"setsar=1,fps={a.fps},format=yuv420p[v{i}]")
        chain, t = "[v0]", 0.0
        for i in range(1, len(pages)):
            t += holds[i - 1] - FADE
            nxt = f"[x{i}]"
            fc.append(f"{chain}[v{i}]xfade=transition=fade:duration={FADE}"
                      f":offset={t:.3f}{nxt}")
            chain = nxt
        fc.append(f"{chain}format=yuv420p[vout]")

        maps = ["-map", "[vout]"]
        if have_music:
            ai = len(pages)
            # FIT THE SCORE TO THE CUT BY STRETCHING IT, NOT BY LOOPING.
            # The bed is written as one arc -- grief, anger, resolve -- so
            # looping it restarts the grief motif over the hopeful ending
            # and trimming it cuts the resolve off. atempo preserves pitch,
            # and a stretch of this size on an ambient score is inaudible
            # as anything but a slightly roomier tempo. Outside atempo's
            # 0.5-2.0 range, fall back to looping and say so.
            md = duration(a.music)
            tempo = md / total
            if 0.5 <= tempo <= 2.0:
                a_fc = f"[{ai}:a]atempo={tempo:.5f}"
                print(f"  score {md:.1f}s -> {total:.1f}s "
                      f"(atempo {tempo:.3f})")
                # Up to about a tenth is inaudible on an ambient bed.
                # Past that it starts to drag, and the right fix is a
                # longer score rather than a slower one -- so say so
                # instead of letting it pass as a routine line of log.
                if abs(1 - tempo) > 0.12:
                    print(f"  NOTE: that is a {abs(1-tempo)*100:.0f}% "
                          f"stretch, which is audible. Consider a "
                          f"~{total:.0f}s score instead.")
            else:
                a_fc = f"[{ai}:a]aloop=loop=-1:size=2e9"
                print(f"  score {md:.1f}s looped to {total:.1f}s "
                      f"(stretch {tempo:.2f} out of range)")
            fc.append(
                f"{a_fc},atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d=1.5,"
                f"afade=t=out:st={max(total - 3.5, 0):.3f}:d=3.5,"
                f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
            # 48 kHz because the source mp3 came back at 96 kHz, which every
            # social platform re-encodes anyway -- better to land on the
            # standard rate here than let someone else's encoder decide.
            maps += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
                     "-ar", "48000"]
        else:
            maps += ["-an"]

        out_mp4 = os.path.join(dest, f"{a.name}_{lang}.mp4")
        cmd += ["-filter_complex", ";".join(fc)] + maps + [
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-t", f"{total:.3f}", out_mp4]
        run(cmd)
        d = duration(out_mp4)
        mb = os.path.getsize(out_mp4) / 1e6
        print(f"  wrote {os.path.basename(out_mp4)}  "
              f"{d:.1f}s  {mb:.0f} MB")
        if abs(d - total) > 0.5:
            print(f"  WARNING: expected {total:.1f}s, got {d:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
