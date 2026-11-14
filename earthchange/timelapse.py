#!/usr/bin/env python3
"""Timelapse — one cloud-masked true-colour composite per year, as frames + MP4.

For watching a mine, an industrial estate or a clearing front grow, year by
year. Each frame is a median of every clear scene in its window:

  --sensor landsat   Landsat 5/7/8/9 Collection 2 L2, back to 1984 (default).
                     Landsat 7 is used only where nothing else flies (2012) or
                     before 2013 if --with-l7; its SLC-off stripes mostly vanish
                     in a 2-year median.
  --sensor s2        Sentinel-2 L2A with Cloud Score+ (2019+ is dense; 2017-18
                     is patchy over the tropics).

--window-years 2 (default) makes each frame the median of the year shown and
the one before, which is what removes the last clouds in the tropics; use 1
for a strict single-year frame. Large areas exceed Earth Engine's per-request
memory, so the frame is fetched as tiles and stitched locally.

Outputs: frames/<year>.png (year burnt in), timelapse.mp4, contact_sheet.jpg,
stats.json (scene counts per frame). Backend: needs --backend gee.
"""

import io
import json
import math
import os
import shutil
import subprocess
import urllib.request

TILE_PX = 600                      # tile edge that stays under the memory limit
VIS = {"landsat": {"min": 0.0, "max": 0.17, "gamma": 1.25},
       "s2": {"min": 0.0, "max": 0.17, "gamma": 1.25}}


# ----------------------------- pure helpers (testable) -----------------------------
def tile_grid(bounds, width, tile_px=TILE_PX):
    """Split (w, s, e, n) into an n x n grid so each tile is <= tile_px wide.

    Returns (tiles, tile_w, tile_h, n) where tiles are (col, row, (w, s, e, n))
    with row 0 at the top. The output height follows the box's aspect ratio in
    degrees (the thumbnails are plate carrée).
    """
    w, s, e, n_ = bounds
    n = max(1, math.ceil(width / tile_px))
    tw = width // n
    th = max(1, int(round(tw * (n_ - s) / (e - w))))
    dx, dy = (e - w) / n, (n_ - s) / n
    tiles = [(i, j, (w + i * dx, n_ - (j + 1) * dy, w + (i + 1) * dx, n_ - j * dy))
             for j in range(n) for i in range(n)]
    return tiles, tw, th, n


def frame_window(year, window_years):
    """[start, end) dates of the composite that represents `year`."""
    return f"{year - window_years + 1}-01-01", f"{year + 1}-01-01"


# ----------------------------- GEE building blocks -----------------------------
def _landsat(geom, start, end, with_l7):
    import ee

    def get(cid, bands):
        def prep(img):
            m = img.select("QA_PIXEL").bitwiseAnd(0b11111).eq(0)
            return img.select(bands, ["B", "G", "R"]).multiply(0.0000275).add(-0.2).updateMask(m)
        return ee.ImageCollection(cid).filterBounds(geom).filterDate(start, end).map(prep)

    oli = ["SR_B2", "SR_B3", "SR_B4"]
    tm = ["SR_B1", "SR_B2", "SR_B3"]
    c = (get("LANDSAT/LC08/C02/T1_L2", oli).merge(get("LANDSAT/LC09/C02/T1_L2", oli))
         .merge(get("LANDSAT/LT05/C02/T1_L2", tm)))
    y0, y1 = int(start[:4]), int(end[:4]) - 1
    if with_l7 or (y0 <= 2012 <= y1):            # 2012: L5 is gone and L8 not yet up
        c = c.merge(get("LANDSAT/LE07/C02/T1_L2", tm))
    return c


def _s2(geom, start, end):
    import ee
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom)
            .filterDate(start, end).linkCollection(cs, ["cs_cdf"])
            .map(lambda i: i.updateMask(i.select("cs_cdf").gte(0.6))
                 .select(["B2", "B3", "B4"], ["B", "G", "R"]).divide(10000)))


def composite(geom, year, sensor="landsat", window_years=2, with_l7=False):
    """(visualised RGB image, scene count) for one frame."""
    import ee
    start, end = frame_window(year, window_years)
    col = _s2(geom, start, end) if sensor == "s2" else _landsat(geom, start, end, with_l7)
    vis = (col.median().select(["R", "G", "B"]).visualize(**VIS[sensor])
           .unmask(ee.Image.constant([25, 25, 25]).visualize(min=0, max=255)))
    return vis, col.size()


def fetch_frame(geom_bounds, year, width, sensor, window_years, with_l7):
    """Download one frame as a PIL image, tile by tile. Returns (image, scenes)."""
    import ee
    from PIL import Image
    tiles, tw, th, n = tile_grid(geom_bounds, width)
    out = Image.new("RGB", (tw * n, th * n))
    scenes = None
    for i, j, (w, s, e, nn) in tiles:
        g = ee.Geometry.Rectangle([w, s, e, nn])
        vis, cnt = composite(g, year, sensor, window_years, with_l7)
        if scenes is None:
            scenes = cnt
        url = vis.getThumbURL({"region": g, "dimensions": f"{tw}x{th}", "format": "png"})
        data = urllib.request.urlopen(url, timeout=300).read()
        out.paste(Image.open(io.BytesIO(data)).convert("RGB"), (i * tw, j * th))
    return out, scenes


# ----------------------------- frames -> video -----------------------------
def _font(size):
    from PIL import ImageFont
    try:
        import matplotlib
        p = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf",
                         "DejaVuSans-Bold.ttf")
        return ImageFont.truetype(p, size)
    except Exception:  # noqa: BLE001 — fall back to the bitmap font
        return ImageFont.load_default()


def label_frame(img, text, credit):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    big = _font(max(18, img.width // 18))
    small = _font(max(10, img.width // 90))
    x, y = img.width - img.width // 40, img.height - img.height // 30
    d.text((x, y), text, font=big, fill="white", anchor="rs", stroke_width=3, stroke_fill="black")
    d.text((10, img.height - 8), credit, font=small, fill="white", anchor="ls",
           stroke_width=2, stroke_fill="black")
    return img


def make_video(frame_paths, out_mp4, seconds_per_frame=0.7, fade=0.3):
    """Crossfaded MP4 from equally sized PNG frames (ffmpeg xfade)."""
    if not shutil.which("ffmpeg"):
        print("  (ffmpeg not found: frames written, video skipped)")
        return False
    if len(frame_paths) == 1:
        cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", "2", "-i", frame_paths[0],
               "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", out_mp4]
        return subprocess.run(cmd).returncode == 0
    hold = seconds_per_frame + fade
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for p in frame_paths:
        cmd += ["-loop", "1", "-t", f"{hold:.3f}", "-i", p]
    chain, last = [], "[0:v]"
    for k in range(1, len(frame_paths)):
        off = k * seconds_per_frame
        tag = f"[v{k}]"
        chain.append(f"{last}[{k}:v]xfade=transition=fade:duration={fade}:offset={off:.3f}{tag}")
        last = tag
    chain.append(f"{last}scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p[out]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "[out]", "-r", "30",
            "-c:v", "libx264", "-crf", "20", out_mp4]
    r = subprocess.run(cmd)
    return r.returncode == 0


def contact_sheet(frame_paths, out_jpg, cols=6, w=320):
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in frame_paths]
    h = int(ims[0].height * w / ims[0].width)
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * w, rows * h), "white")
    for k, im in enumerate(ims):
        sheet.paste(im.resize((w, h)), ((k % cols) * w, (k // cols) * h))
    sheet.save(out_jpg, quality=85)


# ----------------------------- entry point -----------------------------
def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        admin=None, bbox=None, start_year=None, end_year=None, sensor="landsat",
        window_years=2, width=1600, with_l7=False, seconds_per_frame=0.7):
    if backend != "gee":
        raise SystemExit("timelapse needs --backend gee.")
    import datetime as dt
    import ee
    from .gee_utils import initialize_ee
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)
    geom = _resolve_aoi(admin, bbox, lon, lat, radius)
    ring = geom.bounds().getInfo()["coordinates"][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    y0 = start_year or (2019 if sensor == "s2" else 2000)
    y1 = end_year or dt.date.today().year
    if sensor == "s2" and y0 < 2017:
        raise SystemExit("--sensor s2 starts in 2017; use --sensor landsat for earlier years.")
    fdir = os.path.join(run_dir, "frames")
    os.makedirs(fdir, exist_ok=True)
    credit = ("Landsat (USGS)" if sensor == "landsat" else "Contains modified Copernicus Sentinel data") \
        + f", {window_years}-yr median ending in the year shown"
    paths, counts = [], {}
    for y in range(y0, y1 + 1):
        p = os.path.join(fdir, f"{y}.png")
        try:
            img, n = fetch_frame(bounds, y, width, sensor, window_years, with_l7)
            counts[y] = int(ee.Number(n).getInfo())
        except Exception as e:  # noqa: BLE001 — one bad year must not sink the run
            print(f"  {y}: failed ({str(e)[:120]})")
            continue
        if counts[y] == 0:
            print(f"  {y}: no clear scenes, skipped")
            continue
        label_frame(img, str(y), credit).save(p)
        paths.append(p)
        print(f"  {y}: {counts[y]} scenes")
    if not paths:
        raise SystemExit("No frames could be made for this area and period.")
    mp4 = os.path.join(run_dir, f"timelapse_{name}.mp4")
    ok = make_video(paths, mp4, seconds_per_frame)
    contact_sheet(paths, os.path.join(run_dir, "contact_sheet.jpg"))
    stats = {"run_id": run_id, "scenario": "timelapse", "name": name, "bounds": bounds,
             "sensor": sensor, "window_years": window_years, "width_px": width,
             "scenes_per_frame_first_tile": {str(k): v for k, v in counts.items()},
             "frames": len(paths), "video": mp4 if ok else None}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(f"\n{len(paths)} frames -> {mp4 if ok else fdir}")
    return stats
