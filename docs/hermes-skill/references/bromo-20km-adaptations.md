# Bromo 20km AOI — exact diffs applied (2026-08-06)

Worked example of running the Fable pipeline on a mid-size AOI (0.36° × 0.36°).
This is the **recommended minimum** for the pipeline — at 20km radius the CAMS
grid is 2×2 (vs 1×1 at 5km), giving visible smoke structure. Quality: 8.5/10.

## config.py
```python
LON_MIN, LON_MAX = 112.772, 113.134
LAT_MIN, LAT_MAX = -8.1225, -7.7625
WIDTH = HEIGHT = 1080
TITLE = "WILDFIRE SMOKE"
SUBTITLE = "GUNUNG BROMO · JAWA TIMUR · {period} · CAMS + VIIRS"
CITIES = [
    ("Cemoro Lawang", 112.958, -7.921, True),
    ("Sukapura",      113.046, -7.918, True),
    ("Ngadisari",     112.967, -7.933, False),
    ("Wonokitri",     112.953, -7.918, False),
    ("Tosari",        112.967, -7.887, False),
    ("Ngadiwono",     112.917, -7.917, False),
]
```

## compose.py — graticule ticks
```python
# BEFORE (Ketapang):
for lon in range(109, 112):
    d.text((x + 5, HEIGHT - 22), f"{lon}°E", …)
for lat in [-3, -2, -1, 0]:
    d.text((8, y + 4), f"{-lat}°S", …)

# AFTER (Bromo 20km):
for lon in np.arange(112.80, 113.15, 0.05):
    d.text((x + 5, HEIGHT - 22), f"{lon:.2f}°E", …)
for lat in np.arange(-8.10, -7.75, 0.05):
    d.text((8, y + 4), f"{-lat:.2f}°S", …)
```

## compose.py — region labels (volcanic complex, includes G. Semeru)
```python
# BEFORE (Ketapang):
# … KARIMATA STRAIT, KALIMANTAN BARAT, KALIMANTAN TENGAH

# AFTER (Bromo 20km):
x, y = to_px(112.953, -7.942)
d.text((x, y), spaced("GUNUNG BROMO"), font=F_SEA, fill=(*GREY, 130), anchor="mm")
x, y = to_px(112.953, -7.970)
d.text((x, y), spaced("TENGGER CALDERA", gap=""), font=F_REGION, fill=(*GREY, 105), anchor="mm")
x, y = to_px(112.933, -7.910)
d.text((x, y), "LAUT PASIR", font=F_REGION, fill=(*GREY, 95), anchor="mm", align="center")
x, y = to_px(112.920, -8.080)
d.text((x, y), "G. SEMERU", font=F_REGION, fill=(*GREY, 90), anchor="mm")
```

## compose.py — city label exceptions
```python
# BEFORE:
if name in ("Nanga Pinoh", "Pangkalan Bun"):

# AFTER:
if name in ("Sukapura",):
```

## compose.py — scale bar
```python
km = 5  # ~30% of 0.36° bbox
```

## compose.py — dynamic zoom (same fix as 5km, always needed for non-Ketapang bboxes)
```python
# BEFORE (line ~105):
a = zoom(a, 270 / 17, order=3)[:270, :270]

# AFTER:
n_grid = a.shape[0]
a = zoom(a, 270 / n_grid, order=1)[:270, :270]
```

## compose.py — smoke opacity (RESTORED to default at 20km; no reduction needed)
```python
alpha = np.clip((a - 0.20) / 1.7, 0, 1) ** 1.15 * 0.62  # default
```

## download_dem.py — bump zoom for detail
```python
Z = 14  # (vs 10 default) — gives 4235×4218px crop from 289 tiles
```

## render_basemap.py — reduce smoothing for volcanic terrain
```python
dem_s = gaussian_filter(dem, sigma=2.0)  # (vs 4.0 default)
```

## Results
- 142 FIRMS detections over 7 days (peak: 30 on Aug 5)
- CAMS AOD: 2×2 grid, cube (192, 2, 2) — visible smoke structure
- forge3d terrain at z14: 4235×4218px DEM crop, 289 tiles
- 349 frames, 1080×1080, 2.8MB MP4, 19.6MB GIF
- Quality: 8.5/10 — all components working; CAMS has structure at 2×2
