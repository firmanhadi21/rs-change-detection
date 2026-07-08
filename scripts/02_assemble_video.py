#!/usr/bin/env python3
"""Assemble the 5 scene videos into the final documentary — pure Python.

Pairs each slide image (images/) with its narration audio (audio/), renders
one video per scene, then concatenates them into capkala_investigation.mp4.

Rendering is done with ffmpeg (a system binary), invoked via subprocess — no
shell script. ffmpeg + ffprobe must be on PATH (e.g. `brew install ffmpeg`).

Run scripts/01_generate_tts.py first to produce the audio files.

Input:  images/   (scene slides + raw satellite images)
        audio/    (scene_00.mp3 ... scene_04.mp3)
Output: scenes/   (individual scene videos)
        capkala_investigation.mp4 (final combined video)
"""

import os
import sys
import shutil
import tempfile
import subprocess

# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(SCRIPT_DIR)
IMG_DIR = os.path.join(PROJ_DIR, "images")
AUDIO_DIR = os.path.join(PROJ_DIR, "audio")
SCENE_DIR = os.path.join(PROJ_DIR, "scenes")
OUT = os.path.join(PROJ_DIR, "capkala_investigation.mp4")

# === Render settings ===
W, H, FPS = 1920, 1080, 30
TITLE_DUR = 1.5
# Scene-04 methodology step boundaries (seconds), proportional to narration.
SPLITS = [0.0, 11.0, 33.0, 51.0, 84.0]


def require_binaries():
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            sys.exit(
                f"ERROR: '{binary}' not found on PATH.\n"
                "Install ffmpeg first, e.g.  brew install ffmpeg  (macOS)\n"
                "                            sudo apt install ffmpeg  (Debian/Ubuntu)"
            )


def run(cmd):
    """Run an ffmpeg/ffprobe command, surfacing stderr only on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return proc


def duration(path):
    """Return media duration in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def scale_images(scaled_dir):
    """Letterbox every image in images/ to W×H and write as PNG."""
    print("=== Pre-scaling images ===")
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2")
    for name in sorted(os.listdir(IMG_DIR)):
        src = os.path.join(IMG_DIR, name)
        if not os.path.isfile(src):
            continue
        stem = os.path.splitext(name)[0]
        run(["ffmpeg", "-y", "-i", src, "-vf", vf,
             os.path.join(scaled_dir, f"{stem}.png")])


def render_still_scene(image, audio, out_path):
    """Render one still-image + audio scene."""
    run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS),
        "-i", image, "-i", audio,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-shortest", out_path,
    ])
    print(f"  {duration(out_path):.1f}s")


def render_methodology(scaled_dir, out_path):
    """Scene 4: 1.5s title card + 5 timed step images over one narration track."""
    print("Scene 4: METODOLOGI")
    meth_audio = os.path.join(AUDIO_DIR, "scene_03.mp3")
    step_images = [
        os.path.join(scaled_dir, f"{s}.png") for s in (
            "sentinel2_raw", "sirad_raw", "planetscope_before_after",
            "bhumi_screenshot", "infographic",
        )
    ]
    audio_dur = duration(meth_audio)

    with tempfile.TemporaryDirectory(prefix="capkala_pure_") as pure:
        step_videos = []
        for i in range(5):
            start = SPLITS[i]
            length = (audio_dur - SPLITS[4]) if i == 4 else (SPLITS[i + 1] - start)

            step_audio = os.path.join(pure, f"step_{i + 1}.mp3")
            run(["ffmpeg", "-y", "-ss", str(start), "-t", str(length),
                 "-i", meth_audio, "-c:a", "copy", step_audio])

            step_video = os.path.join(pure, f"pure_{i + 1:02d}.mp4")
            run([
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS),
                "-i", step_images[i], "-i", step_audio,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
                "-ar", "44100", "-ac", "2", "-pix_fmt", "yuv420p",
                "-r", str(FPS), "-shortest", step_video,
            ])
            step_videos.append(step_video)
            print(f"  Step {i + 1}: {length:.1f}s")

        # Concat the 5 step videos (same codec → stream copy)
        concat_list = os.path.join(pure, "concat.txt")
        with open(concat_list, "w") as f:
            for v in step_videos:
                f.write(f"file '{v}'\n")
        all_pure = os.path.join(pure, "all_pure.mp4")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy", all_pure])

        # Silent audio + title card
        silence = os.path.join(pure, "silence.m4a")
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", str(TITLE_DUR), "-c:a", "aac", "-b:a", "192k", silence])
        title = os.path.join(pure, "title.mp4")
        run([
            "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS),
            "-t", str(TITLE_DUR),
            "-i", os.path.join(scaled_dir, "scene_04_metodologi_title.png"),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-an", title,
        ])

        # Prepend title card to the methodology body
        run([
            "ffmpeg", "-y",
            "-i", title, "-i", all_pure, "-i", silence, "-i", meth_audio,
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p", "-r", str(FPS), out_path,
        ])
    print(f"  {duration(out_path):.1f}s")


def combine(scene_paths):
    """Concatenate all scenes into the final video."""
    print("\n=== Combining all 5 scenes ===")
    inputs = []
    for p in scene_paths:
        inputs += ["-i", p]
    streams = "".join(f"[{i}:v][{i}:a]" for i in range(len(scene_paths)))
    filt = f"{streams}concat=n={len(scene_paths)}:v=1:a=1[v][a]"
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filt, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p", "-r", str(FPS), OUT,
    ])


def main():
    require_binaries()

    # Fail early with a clear message if narration audio is missing.
    missing = [f"scene_{i:02d}.mp3" for i in range(5)
               if not os.path.exists(os.path.join(AUDIO_DIR, f"scene_{i:02d}.mp3"))]
    if missing:
        sys.exit(
            "ERROR: missing narration audio: " + ", ".join(missing) + "\n"
            "Run scripts/01_generate_tts.py first (or supply your own audio/*.mp3)."
        )

    os.makedirs(SCENE_DIR, exist_ok=True)
    for f in os.listdir(SCENE_DIR):
        if f.endswith(".mp4"):
            os.remove(os.path.join(SCENE_DIR, f))
    if os.path.exists(OUT):
        os.remove(OUT)

    with tempfile.TemporaryDirectory(prefix="capkala_scaled_") as scaled:
        scale_images(scaled)

        still_scenes = [
            ("scene_01_pendahuluan", "scene_00.mp3", "PENDAHULUAN"),
            ("scene_02_sentinel2", "scene_01.mp3", "CITRA SENTINEL-2"),
            ("scene_03_analisis_spasial", "scene_02.mp3", "ANALISIS SPASIAL"),
        ]
        scene_paths = []
        for i, (img_stem, audio_name, title) in enumerate(still_scenes, start=1):
            print(f"Scene {i}: {title}")
            out_path = os.path.join(SCENE_DIR, f"{img_stem}.mp4")
            render_still_scene(
                os.path.join(scaled, f"{img_stem}.png"),
                os.path.join(AUDIO_DIR, audio_name), out_path,
            )
            scene_paths.append(out_path)

        # Scene 4: methodology
        scene4 = os.path.join(SCENE_DIR, "scene_04_metodologi.mp4")
        render_methodology(scaled, scene4)
        scene_paths.append(scene4)

        # Scene 5: conclusion
        print("Scene 5: KESIMPULAN")
        scene5 = os.path.join(SCENE_DIR, "scene_05_kesimpulan.mp4")
        render_still_scene(
            os.path.join(scaled, "scene_05_kesimpulan.png"),
            os.path.join(AUDIO_DIR, "scene_04.mp3"), scene5,
        )
        scene_paths.append(scene5)

        combine(scene_paths)

    size_mb = os.path.getsize(OUT) / 1e6
    dur = duration(OUT)
    print(f"Final: {size_mb:.1f} MB, {dur:.1f}s ({dur / 60:.1f} min)")
    print("Done.")


if __name__ == "__main__":
    main()
