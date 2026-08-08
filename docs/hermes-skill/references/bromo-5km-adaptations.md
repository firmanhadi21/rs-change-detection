# Bromo 5km AOI — exact diffs applied (2026-08-06)

Worked example of running the Fable pipeline on a very small AOI (0.09° × 0.09°).
These were the exact changes applied to the Ketapang-default pipeline.

## config.py
```python
LON_MIN, LON_MAX = 112.908, 112.998
LAT_MIN, LAT_MAX = -7.9875, -7.8975
TITLE = "WILDFIRE SMOKE"
SUBTITLE = "GUNUNG BROMO · JAWA TIMUR · {period} · CAMS + VIIRS"
CITIES = [
    ("Cemoro Lawang", 112.958, -7.921, True),
    ("Ngadisari",     112.967, -7.933, False),
    ("Wonokitri",     112.953, -7.918, False),
]
```

## compose.py — graticule ticks
```python
# BEFORE (Ketapang):
for lon in range(109, 112):
    d.text((x + 5, HEIGHT - 22), f"{lon}°E", …)
for lat in [-3, -2, -1, 0]:
    d.text((8, y + 4), f"{-lat}°S", …)

# AFTER (Bromo 5km):
for lon in np.arange(112.92, 113.00, 0.02):
    d.text((x + 5, HEIGHT - 22), f"{lon:.2f}°E", …)
for lat in np.arange(-7.98, -7.88, 0.02):
    d.text((8, y + 4), f"{-lat:.2f}°S", …)
```

## compose.py — region labels (inland volcano, no sea)
```python
# BEFORE (Ketapang):
x, y = to_px(108.95, -0.75)
d.text((x, y), spaced("KARIMATA"), font=F_SEA, fill=(*GREY, 120), anchor="mm")
# … KARIMATA STRAIT, KALIMANTAN BARAT, KALIMANTAN TENGAH

# AFTER (Bromo):
x, y = to_px(112.953, -7.942)
d.text((x, y), spaced("GUNUNG BROMO"), font=F_SEA, fill=(*GREY, 130), anchor="mm")
x, y = to_px(112.953, -7.960)
d.text((x, y), spaced("TENGGER CALDERA", gap=""), font=F_REGION, fill=(*GREY, 105), anchor="mm")
x, y = to_px(112.933, -7.912)
d.text((x, y), "LAUT PASIR", font=F_REGION, fill=(*GREY, 95), anchor="mm", align="center")
```

## compose.py — city label exceptions
```python
# BEFORE:
if name in ("Nanga Pinoh", "Pangkalan Bun"):

# AFTER:
if name in ("Ngadisari",):
```

## compose.py — scale bar
```python
# BEFORE:
km = 100

# AFTER:
km = 1
```

## compose.py — dynamic zoom (fix crash on 1×1 CAMS grid)
```python
# BEFORE (line ~105):
a = cube[i0] * (1 - f) + cube[i0 + 1] * f          # 17x17
a = zoom(a, 270 / 17, order=3)[:270, :270]

# AFTER:
a = cube[i0] * (1 - f) + cube[i0 + 1] * f          # (H_aod, W_aod)
n_grid = a.shape[0]
a = zoom(a, 270 / n_grid, order=1)[:270, :270]
```

## compose.py — reduced smoke opacity (small AOI)
```python
# BEFORE:
alpha = np.clip((a - 0.20) / 1.7, 0, 1) ** 1.15 * 0.62

# AFTER:
alpha = np.clip((a - 0.25) / 1.5, 0, 1) ** 0.8 * 0.25
```

## download_dem.py — bump zoom for detail
```python
# BEFORE:
Z = 10

# AFTER:
Z = 14
```

## render_basemap.py — reduce smoothing for volcanic terrain
```python
# BEFORE:
dem_s = gaussian_filter(dem, sigma=4.0)

# AFTER:
dem_s = gaussian_filter(dem, sigma=2.0)  # reduced for volcanic terrain detail
```

## Results
- 51 FIRMS detections in 5km radius over 7 days (peak: 20 on Aug 5)
- CAMS AOD: 1×1 grid (single value per frame) — uniform haze
- forge3d terrain at z14: 1059×1048px DEM crop, 25 tiles
- 349 frames, 1080×1080, 2.3MB MP4
- Quality: 7.5/10 — terrain and labels good, CAMS smoke inherently limited at this scale
