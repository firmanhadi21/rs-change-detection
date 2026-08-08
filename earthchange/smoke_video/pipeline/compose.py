"""Compose animation frames: basemap + smoke + fires + cartography.

Usage:
  python3 compose.py preview t0 t1 ...   # render single preview frames at hour offsets
  python3 compose.py all                 # render all frames
"""
import sys, json, math, datetime as dt
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter, zoom
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import (DATA, FRAMES, WIDTH, HEIGHT, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX,
                    CITIES, TITLE, SUBTITLE)

# ---------- timeline ----------
# Derived from the downloaded data below: starts at the beginning of the
# 7-day AOD window, ends at the last fire detection (floored to a 30-min step).
STEP_H = 0.5

# ---------- projection (web mercator linear within bbox) ----------
def merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))

MY0, MY1 = merc_y(LAT_MAX), merc_y(LAT_MIN)  # top, bottom

def to_px(lon, lat):
    x = (lon - LON_MIN) / (LON_MAX - LON_MIN) * WIDTH
    y = (merc_y(lat) - MY0) / (MY1 - MY0) * HEIGHT
    return x, y

# ---------- static assets ----------
base = np.asarray(Image.open(DATA / "basemap.png").convert("RGB"), dtype=np.float32) / 255.0
sea = np.load(DATA / "sea_mask.npy")

# ---------- AOD cube ----------
meta = json.load(open(DATA / "aod_meta.json"))
aod_times = [dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc) for t in meta["times"]]
aod_t0 = aod_times[0]
cube = np.load(DATA / "aod_cube.npy")  # (T, lat asc, lon asc)
cube = np.nan_to_num(cube, nan=0.0)
cube = cube[:, ::-1, :]  # row 0 = north

T_START = aod_t0  # 00:00 UTC, 7 days ago

# temporal smoothing to hide CAMS 12h analysis steps
cube = gaussian_filter(cube, sigma=(1.5, 0, 0))

# ---------- fires ----------
fires = pd.read_csv(DATA / "fires_bbox.csv", parse_dates=["dt_utc"])
fx, fy = to_px(fires.longitude.values, fires.latitude.values)
f_sec = (fires.dt_utc.dt.tz_convert("UTC") - T_START).dt.total_seconds().values
f_frp = np.clip(fires.frp.values, 0.5, 120.0)
f_date = fires.acq_date.values  # 'YYYY-MM-DD'

_end_sec = math.floor(f_sec.max() / (STEP_H * 3600)) * (STEP_H * 3600)
T_END = T_START + dt.timedelta(seconds=_end_sec)
N_FRAMES = int(_end_sec / 3600 / STEP_H) + 1
PERIOD = f"{T_START.day} {T_START:%b} \u2013 {T_END.day} {T_END:%b %Y}".upper()
print(f"timeline: {T_START:%Y-%m-%d %H:%M} -> {T_END:%Y-%m-%d %H:%M} UTC, {N_FRAMES} frames")

# ---------- noise fields for smoke texture ----------
rng = np.random.default_rng(42)
N_NOISE = 8
noise_keys = []
for i in range(N_NOISE):
    n = rng.standard_normal((68, 68))
    n = gaussian_filter(n, 3.0)
    n = (n - n.mean()) / (n.std() + 1e-9)
    noise_keys.append(n.astype(np.float32))

def noise_field(hours):
    """Slowly evolving multiplicative texture, 270x270."""
    ph = (hours / 30.0) % N_NOISE
    i0 = int(ph) % N_NOISE
    i1 = (i0 + 1) % N_NOISE
    f = ph - int(ph)
    n = noise_keys[i0] * (1 - f) + noise_keys[i1] * f
    # 68 is this module's own noise-key size, not region-derived, but route it
    # through the same helper so a stray rounding pixel cannot desynchronise
    # the two grids again.
    n = _to_noise_grid(n, order=1)
    return 1.0 + 0.28 * n

# ---------- smoke colormap ----------
SMOKE_STOPS = np.array([
    [1.00, 0.86, 0.40],
    [0.98, 0.66, 0.22],
    [0.92, 0.38, 0.13],
    [0.72, 0.15, 0.10],
    [0.45, 0.06, 0.08],
], dtype=np.float32)

def smoke_rgba(a):
    """a: AOD field (H,W) -> color (H,W,3), alpha (H,W)"""
    t = np.clip((a - 0.22) / (2.2 - 0.22), 0, 1) ** 0.9
    idx = t * (len(SMOKE_STOPS) - 1)
    i0 = np.clip(idx.astype(int), 0, len(SMOKE_STOPS) - 2)
    f = (idx - i0)[..., None]
    col = SMOKE_STOPS[i0] * (1 - f) + SMOKE_STOPS[i0 + 1] * f
    alpha = np.clip((a - 0.20) / 1.7, 0, 1) ** 1.15 * 0.62
    return col, alpha.astype(np.float32)

def _to_noise_grid(a, n=270, order=3):
    """Resize an array to exactly n x n.

    The zoom factor has to come from the array's own shape. It was hardcoded as
    270/17, where 17 was simply the AOD grid the original bbox happened to
    produce -- the grid is np.arange(LAT_MIN, LAT_MAX, STEP), so it changes with
    the region. A 14x14 cube then zoomed to 222x222 and failed to broadcast
    against the fixed 270x270 noise field. Rounding can also land a pixel short,
    so the result is padded by edge repetition rather than trusted.
    """
    a = zoom(a, n / a.shape[0], order=order)[:n, :n]
    if a.shape != (n, n):
        a = np.pad(a, ((0, max(0, n - a.shape[0])),
                       (0, max(0, n - a.shape[1]))), mode="edge")
    return a


def smoke_layer(t_utc):
    hours = (t_utc - aod_t0).total_seconds() / 3600.0
    i0 = int(np.clip(math.floor(hours), 0, cube.shape[0] - 2))
    f = np.clip(hours - i0, 0, 1)
    a = cube[i0] * (1 - f) + cube[i0 + 1] * f      # grid size follows the bbox
    a = _to_noise_grid(a)
    a = np.clip(a, 0, None) * noise_field(hours)
    a = gaussian_filter(a, 3.0)
    a = zoom(a, WIDTH / 270, order=1)[:HEIGHT, :WIDTH]
    return smoke_rgba(a)

# ---------- fire layer ----------
def fire_layer(t_sec):
    """Additive RGB glow layer for detections within the last 12 h."""
    w = (t_sec - f_sec)
    m = (w >= 0) & (w < 12 * 3600)
    lay = np.zeros((HEIGHT, WIDTH), np.float32)
    if m.any():
        recency = 1.0 - w[m] / (12 * 3600)          # 1 fresh -> 0 old
        inten = (0.25 + 0.75 * recency) * (0.4 + 0.6 * np.sqrt(f_frp[m] / 120.0))
        xi = np.clip(fx[m].astype(int), 0, WIDTH - 1)
        yi = np.clip(fy[m].astype(int), 0, HEIGHT - 1)
        np.add.at(lay, (yi, xi), inten)
    core = gaussian_filter(lay, 1.0)
    glow = gaussian_filter(lay, 4.5)
    r = np.clip(core * 7.0 + glow * 5.5, 0, 1)
    g = np.clip(core * 4.6 + glow * 2.4, 0, 1)
    b = np.clip(core * 2.2 + glow * 0.6, 0, 1)
    return np.stack([r, g, b], axis=-1)

# ---------- fonts ----------
# Searches common locations for Inter (recommended; matches the reference style),
# falling back to system fonts, then PIL's default.
import glob as _glob, os as _os, pathlib as _pl

_FONT_DIRS = [
    str(_pl.Path(__file__).resolve().parent / "fonts"),   # drop Inter .otf files here
    "/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/inter",
    _os.path.expanduser("~/Library/Fonts"), "/Library/Fonts",   # macOS
    "/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts",
]
_FALLBACKS = {
    "ExtraBold":    ["Inter-ExtraBold", "Arial Black", "Arialbd", "Helvetica-Bold", "DejaVuSans-Bold"],
    "SemiBold":     ["Inter-SemiBold", "Arialbd", "Arial Bold", "DejaVuSans-Bold"],
    "Medium":       ["Inter-Medium", "Arial", "Helvetica", "DejaVuSans"],
    "MediumItalic": ["Inter-MediumItalic", "Ariali", "Arial Italic", "DejaVuSans-Oblique"],
    "Regular":      ["Inter-Regular", "Arial", "Helvetica", "DejaVuSans"],
}

def _find_font(style):
    for name in _FALLBACKS.get(style, [style]):
        for d in _FONT_DIRS:
            for ext in (".otf", ".ttf", ".ttc"):
                hits = _glob.glob(_os.path.join(d, name + ext))
                if hits:
                    return hits[0]
    return None

_missing = [s for s in _FALLBACKS if _find_font(s) is None]
if _missing:
    print(f"WARNING: no font found for styles {_missing}; using PIL default. "
          "Typography will not match the reference style, and characters "
          "outside ASCII render as visible boxes.\n"
          "         Install Inter (https://rsms.me/inter/) or drop its .otf "
          "files into ./fonts/")


def ascii_safe(s):
    """Replace typographic characters PIL's default font cannot draw.

    A missing glyph comes out as a visible tofu box rather than as nothing --
    the en dash in the period subtitle rendered as one. Only applied when a real
    font is absent, so proper typography survives when Inter is installed.

    Deliberately narrow. The degree sign and middle dot DO render in PIL's
    default font; substituting them turned clean "109°E" tick labels into
    "109 degE", which is worse than the problem. Only add a character here after
    seeing it fail.
    """
    if not _missing:
        return s
    for bad, good in (("–", "-"), ("—", "-"), ("→", "->"), ("’", "'")):
        s = s.replace(bad, good)
    return s

def font(style, size):
    path = _find_font(style)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)

F_TITLE = font("ExtraBold", 52)
F_SUB = font("Medium", 21)
F_DATE = font("ExtraBold", 40)
F_TIME = font("Medium", 22)
F_NUM = font("ExtraBold", 40)
F_NUMLAB = font("Medium", 16)
F_CITY = font("Medium", 21)
F_CITY_B = font("SemiBold", 23)
F_SMALL = font("Regular", 15)
F_TICK = font("Regular", 15)
F_SEA = font("MediumItalic", 19)
F_REGION = font("Medium", 18)

ORANGE = (255, 158, 44)
WHITE = (240, 243, 247)
GREY = (150, 158, 170)
DIM = (110, 118, 132)

def spaced(text, gap=" "):
    return gap.join(list(text))

def draw_text_shadow(d, xy, text, font, fill, anchor="la", shadow=(0, 0, 0), soff=2):
    d.text((xy[0] + soff, xy[1] + soff), text, font=font, fill=shadow, anchor=anchor)
    d.text(xy, text, font=font, fill=fill, anchor=anchor)

# ---------- static overlay (graticule, labels, furniture skeleton) ----------
def build_static_overlay():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # graticule
    for lon in range(109, 112):
        x, _ = to_px(lon, 0)
        d.line([(x, 0), (x, HEIGHT)], fill=(255, 255, 255, 14), width=1)
        d.text((x + 5, HEIGHT - 22), ascii_safe(f"{lon}°E"), font=F_TICK, fill=(*GREY, 150))
    for lat in [-3, -2, -1, 0]:
        _, y = to_px(0, lat)
        d.line([(0, y), (WIDTH, y)], fill=(255, 255, 255, 14), width=1)
        lab = "0°" if lat == 0 else f"{-lat}°S"
        d.text((8, y + 4), ascii_safe(lab), font=F_TICK, fill=(*GREY, 150))

    # sea + region labels
    x, y = to_px(108.95, -0.75)
    d.text((x, y), spaced("KARIMATA"), font=F_SEA, fill=(*GREY, 120), anchor="mm")
    d.text((x, y + 26), spaced("STRAIT"), font=F_SEA, fill=(*GREY, 120), anchor="mm")
    x, y = to_px(110.85, -0.62)
    d.text((x, y), spaced("KALIMANTAN BARAT", gap=""), font=F_REGION, fill=(*GREY, 105), anchor="mm")
    x, y = to_px(111.35, -2.35)
    d.text((x, y), "KALIMANTAN\nTENGAH", font=F_REGION, fill=(*GREY, 95), anchor="mm", align="center")

    # cities
    for name, lon, lat, major in CITIES:
        x, y = to_px(lon, lat)
        r = 4 if major else 3
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*WHITE, 235), outline=(0, 0, 0, 180), width=1)
        f = F_CITY_B if major else F_CITY
        # label placement: right of dot, except tweaks
        ax, ay, anchor = x + 9, y - 2, "lm"
        if name in ("Nanga Pinoh", "Pangkalan Bun"):
            ax, anchor = x - 9, "rm"
        draw_text_shadow(d, (ax, ay), name, f, (*WHITE, 240), anchor=anchor)

    # north arrow
    nx, ny = WIDTH - 52, 190
    d.polygon([(nx, ny - 16), (nx - 8, ny + 8), (nx + 8, ny + 8)], fill=(*WHITE, 200))
    d.text((nx, ny + 22), "N", font=F_SUB, fill=(*WHITE, 210), anchor="mm")
    return img

STATIC = build_static_overlay()

# ---------- scale bar ----------
def draw_scalebar(d):
    km = 100
    deg = km / 111.32
    px = deg / (LON_MAX - LON_MIN) * WIDTH
    x0, y0 = 150, HEIGHT - 68
    d.line([(x0, y0), (x0 + px, y0)], fill=(*WHITE, 220), width=3)
    d.line([(x0, y0 - 6), (x0, y0 + 6)], fill=(*WHITE, 220), width=3)
    d.line([(x0 + px, y0 - 6), (x0 + px, y0 + 6)], fill=(*WHITE, 220), width=3)
    d.text((x0, y0 + 12), "0", font=F_SMALL, fill=(*GREY, 220))
    d.text((x0 + px, y0 + 12), f"{km} km", font=F_SMALL, fill=(*GREY, 220), anchor="ra")

# ---------- legend ----------
def draw_legend(img, d):
    lw, lh = 210, 12
    x0 = WIDTH - lw - 40
    y0 = HEIGHT - 116
    grad = np.linspace(0.12, 1.8, lw)
    col, alpha = smoke_rgba(np.tile(grad, (lh, 1)))
    seg = (col * (alpha[..., None] * 0.9 + 0.1) * 255).astype(np.uint8)
    img.paste(Image.fromarray(seg), (x0, y0))
    d.rectangle([x0, y0, x0 + lw, y0 + lh], outline=(255, 255, 255, 60), width=1)
    d.text((x0, y0 + lh + 6), "low", font=F_SMALL, fill=(*GREY, 220))
    d.text((x0 + lw, y0 + lh + 6), "high", font=F_SMALL, fill=(*GREY, 220), anchor="ra")
    d.text((x0 + lw + 10, y0 - 2), "wildfire aerosol (AOD)", font=F_SMALL, fill=(*WHITE, 220), anchor="lm") if False else None
    d.text((x0 - 10, y0 + lh / 2), "wildfire aerosol (AOD)", font=F_SMALL, fill=(*WHITE, 225), anchor="rm")
    # fire dot legend
    yd = y0 + lh + 42
    d.ellipse([x0 - 4, yd - 4, x0 + 4, yd + 4], fill=(255, 190, 90, 255))
    d.ellipse([x0 - 2, yd - 2, x0 + 2, yd + 2], fill=(255, 240, 200, 255))
    d.text((x0 + 12, yd), "active fires (VIIRS)", font=F_SMALL, fill=(*WHITE, 225), anchor="lm")
    # credits
    d.text((WIDTH - 34, HEIGHT - 34),
           "CAMS/ECMWF via Open-Meteo  ·  NASA FIRMS (VIIRS)  ·  AWS Terrain  ·  forge3d",
           font=F_SMALL, fill=(*DIM, 210), anchor="ra")

# ---------- per-frame furniture ----------
def draw_dynamic(d, t_utc, t_sec):
    # title block
    draw_text_shadow(d, (36, 28), TITLE, F_TITLE, (*WHITE, 255))
    d.rectangle([38, 92, 138, 97], fill=(*ORANGE, 255))
    d.text((38, 110), ascii_safe(SUBTITLE.format(period=PERIOD)), font=F_SUB, fill=(*GREY, 235))

    # date/time top right
    draw_text_shadow(d, (WIDTH - 96, 34), t_utc.strftime("%d %b %Y").upper(), F_DATE, (*WHITE, 255), anchor="ra")
    d.text((WIDTH - 96, 84), t_utc.strftime("%H:%M UTC"), font=F_TIME, fill=(*GREY, 235), anchor="ra")

    # counters (left, over sea)
    cum = int(((f_sec >= 0) & (f_sec <= t_sec)).sum())
    today = int(((f_date == t_utc.strftime("%Y-%m-%d")) & (f_sec <= t_sec)).sum())
    cx, cy = 40, 508
    draw_text_shadow(d, (cx, cy), f"{cum:,}", F_NUM, (*ORANGE, 255))
    d.text((cx, cy + 48), spaced("VIIRS FIRE DETECTIONS (CUM.)", gap=""), font=F_NUMLAB, fill=(*GREY, 220))
    draw_text_shadow(d, (cx, cy + 86), f"{today:,}", F_NUM, (*ORANGE, 255))
    d.text((cx, cy + 134), spaced("DETECTIONS TODAY", gap=""), font=F_NUMLAB, fill=(*GREY, 220))

# ---------- compose one frame ----------
def render_frame(i, out_path):
    t_utc = T_START + dt.timedelta(hours=i * STEP_H)
    t_sec = (t_utc - T_START).total_seconds()

    img = base.copy()
    scol, salpha = smoke_layer(t_utc)
    img = img * (1 - salpha[..., None]) + scol * salpha[..., None]
    img = 1 - (1 - img) * (1 - fire_layer(t_sec))       # screen blend
    frame = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).convert("RGBA")

    frame.alpha_composite(STATIC)
    d = ImageDraw.Draw(frame)
    draw_dynamic(d, t_utc, t_sec)
    draw_scalebar(d)
    draw_legend(frame, d)
    frame.convert("RGB").save(out_path, "PNG")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if mode == "preview":
        for h in [float(x) for x in sys.argv[2:]] or [96.0]:
            i = int(h / STEP_H)
            render_frame(i, DATA / f"preview_{int(h):03d}h.png")
            print("preview", h)
    else:
        import time
        t0 = time.time()
        for i in range(N_FRAMES):
            render_frame(i, FRAMES / f"f_{i:04d}.png")
            if i % 40 == 0:
                print(f"{i}/{N_FRAMES} {time.time()-t0:.0f}s", flush=True)
        print("done", time.time() - t0)
