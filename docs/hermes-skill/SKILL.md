---
name: wildfire-smoke-map-video
description: "Produce a Milos-Popovic-style wildfire smoke map video (dark forge3d terrain + real CAMS AOD smoke + FIRMS VIIRS fire dots + live counters) for any region. Runs the proven Fable pipeline on the Hetzner box. Trigger: user asks for a wildfire/fire-smoke map video or animation for a region/period, on any channel (WhatsApp/Telegram/CLI)."
version: 1.1.0
metadata:
  hermes:
    tags: [gis, wildfire, fires, firms, cams, aod, forge3d, video, whatsapp]
---

# Wildfire Smoke Map Video (Fable pipeline)

Produces the "WILDFIRE SMOKE" dark-map animation: forge3d-rendered dark
terrain, REAL CAMS aerosol-optical-depth smoke (Open-Meteo Air Quality API),
NASA FIRMS VIIRS fire dots with 12h recency glow, live cumulative/today
counters, Inter typography. 1080x1080, 24fps, MP4 + GIF. Matches the
@milos_gis / greece_fire.mp4 reference style.

WORKING PIPELINE (proven end-to-end on this box):
`/home/firman/owy/fable/ketapang-wildfire-forge3d/`
Final video: `.../out/ketapang_wildfire_smoke.mp4`

## Environment facts (Hetzner box)
- ALWAYS use the venv python: `/home/firman/owy/f3d_venv/bin/python` (has
  forge3d 1.34, numpy, scipy, pandas, pillow, requests, rasterio, mapbox-vector-tile).
- `python3 -m venv` is BROKEN (no ensurepip): bootstrap with
  `python3 -m venv --without-pip VENV && curl -sSL https://bootstrap.pypa.io/get-pip.py | VENV/bin/python`
- Headless forge3d works via lavapipe (mesa-vulkan-drivers) — no GPU needed;
  the scripts set XDG_RUNTIME_DIR themselves.
- No passwordless sudo (apt install fonts-inter FAILS — fonts are already
  installed in the pipeline's fonts/ dir; don't re-install).

## Pipeline steps (run in pipeline dir)
```bash
cd /home/firman/owy/fable/ketapang-wildfire-forge3d
P=/home/firman/owy/f3d_venv/bin/python

# 1. downloads (DEM tiles, FIRMS 7-day CSVs, CAMS AOD cube) — need network
$P download_dem.py      # -> data/dem_mercator.npy (+dem_meta.txt)
$P download_fires.py    # -> data/fires_bbox.csv (rolling 7-day FIRMS window)
$P download_aod.py      # -> data/aod_cube.npy, pm25_cube.npy, aod_meta.json
# 2. forge3d PBR terrain render
$P render_basemap.py    # -> data/terrain_raw.png
# 3. dark grade (land/sea/coastline)
$P regrade.py           # -> data/basemap.png, basemap_preview.png
# 4. compose frames
$P compose.py preview 96 156     # quick look (optional)
$P compose.py all                # -> frames/f_0000.png ... (326 frames ≈ 85s)
# 5. encode
bash encode.sh          # -> out/ketapang_wildfire_smoke.{mp4,gif}
```
Or one shot: `bash run_all.sh`
**⚠️ run_all.sh uses system `python3`, NOT the venv python.** Individual steps
need `$P` (venv python). run_all.sh works for Ketapang default but won't for
customized regions. Prefer running steps individually with `$P`.

## CRITICAL: sea_mask.npy
compose.py loads `data/sea_mask.npy` but NO script generates it. After a fresh
download_dem.py, regenerate it (missing file -> NameError/FileNotFound in compose):
```bash
$P -c "import numpy as np; from PIL import Image as I; \
d=np.load('data/dem_mercator.npy'); d=np.clip(d,0,2400); \
f=np.asarray(I.fromarray(d).resize((1080,1080)),dtype=np.float32); \
np.save('data/sea_mask.npy', f<=0)"
```

## Customizing for another region/period

### ALWAYS: back up originals before editing
```bash
cp config.py config_ketapang.bak
cp compose.py compose_ketapang.bak
# … run the pipeline for the new region …
cp config_ketapang.bak config.py   # restore
cp compose_ketapang.bak compose.py
```
The pipeline dir is shared across regions — **restore the Ketapang config after
every non-Ketapang run**, otherwise the next session will silently render the
wrong region.

### Checklist (every item must be touched)

1. `config.py`:
   - LON_MIN/LON_MAX, LAT_MIN/LAT_MAX — keep roughly SQUARE in degrees.
     **Minimum recommended span: 0.5°** (see Small AOI section below).
   - CITIES list: (name, lon, lat, is_major). Verify with
     https://geocoding-api.open-meteo.com/v1/search?name=<city>
   - TITLE/SUBTITLE (SUBTITLE has a {period} placeholder filled automatically).

2. `compose.py` → build_static_overlay() — FOUR hardcoded sections:
   - **Graticule ticks** (lines ~202-210): the `range(109, 112)` / `[-3, -2, -1, 0]`
     are Ketapang-specific. Replace with `np.arange()` covering the new bbox.
   - **Sea/region labels** (lines ~212-219): "KARIMATA STRAIT" etc. Replace with
     appropriate labels for the new region. Inland regions: use geographic feature
     names, not sea labels.
   - **City label placement** (line ~227): `if name in ("Nanga Pinoh", …)` is
     Ketapang-specific. Update the city-name exceptions to match the new CITIES list
     (or remove if not needed).
   - **Scale bar** (line ~240): `km = 100` is for the ~330km Ketapang bbox.
     Scale to the new span: `km = round(bbox_degrees * 111.32 * 0.3)` for a bar
     that spans ~30% of the frame.

3. `render_basemap.py` (line ~28): `gaussian_filter(dem, sigma=4.0)` is tuned
   for Kalimantan canopy noise. Reduce to sigma=1.0–2.0 for volcanic, mountainous,
   or arid terrain where sharp relief is desirable. Increase for dense forest.

4. `download_dem.py` (line ~10): zoom level 10 gives ~66px crop for a 0.09°
   bbox — far too coarse for forge3d. For AOIs under ~0.5°, bump to z=14
   (gives ~1000px crop). Restore to z=10 after.

5. Timeline is derived: starts at beginning of the 7-day AOD window, ends at
   last fire detection (30-min step). Dates/subtitle adapt automatically.

6. The FIRMS feed is a ROLLING 7-DAY window — each run animates the most recent
   week. For a specific historical window you need a (free) NASA FIRMS MAP_KEY
   (archive) or the CAMS archive from Copernicus ADS — not covered by scripts.

### Small AOI adaptations (bbox span < 0.5°)

CAMS AOD native resolution is ~0.4°. For bboxes smaller than ~0.5°, the grid
shrinks to 1×1 or 2×2 points, causing:

1. **compose.py crash** — `zoom(a, 270/17, order=3)` hardcodes 17 as the grid
   width. Fix: compute dynamically (`n_grid = a.shape[0]; zoom(a, 270/n_grid, …)`).
   See `references/bromo-5km-adaptations.md` and `references/bromo-20km-adaptations.md`
   for exact diffs.

2. **Uniform smoke blob** — the single AOD value zooms to cover the whole frame.
   Reduce smoke opacity: in `smoke_rgba()`, change alpha to
   `np.clip((a - 0.25) / 1.5, 0, 1) ** 0.8 * 0.25`
   (default is `max 0.62`). Restore after the run. Only needed for ≤1×1 CAMS grids;
   2×2 grids at ~0.4° bbox work fine with default opacity.

3. **DEM detail** — bump `download_dem.py` Z to 14. Restore to 10 after.

4. **Terrain smoothing** — reduce sigma to 1.0–2.0 in render_basemap.py.
   Restore after.

**Recommended minimum: ~0.4° bbox (≈20km radius).** At this scale: CAMS 2×2
grid gives visible smoke structure, DEM at z14 gives 4000+ px crop, and FIRMS
picks up 140+ detections. See `references/bromo-20km-adaptations.md` for a
worked 8.5/10 example. Below 0.2° (≈10km), CAMS becomes 1×1 and smoke is
inherently limited — see `references/bromo-5km-adaptations.md` (7.5/10).

## Tight / small AOIs (<= 25 km radius) — REQUIRED fixes
Tested for Gunung Bromo 5 km and 20 km radius. The original Ketapang config is
tuned for a ~330 km region; for small bboxes you MUST change all of these or
the output is broken:
1. `download_dem.py`: raise `Z = 10` → `Z = 14`. At Z=10 a 0.09° bbox yields a
   ~66×66 px DEM and forge3d renders a blurry grey mess; Z=14 gives ~1000×1000.
2. `render_basemap.py`: reduce `gaussian_filter(dem, sigma=4.0)` → `sigma=2.0`
   (4.0 was for Kalimantan canopy noise; it erases volcanic/rugged detail).
3. `compose.py` `smoke_layer()`: the hardcoded `zoom(a, 270/17, order=3)` only
   works for Ketapang's 17×17 CAMS grid. Make it dynamic:
   `n_grid = a.shape[0]; a = zoom(a, 270 / n_grid, order=1)[:270, :270]`.
   Without this, a 1×1 or 2×2 AOD grid crashes with a broadcast error.
4. CAMS AOD STEP=0.2° in `download_aod.py`: bbox < 0.2° gives a 1×1 grid →
   uniform smoke that drowns the terrain. 5 km = 1×1 (reduce smoke alpha in
   `smoke_rgba()` from 0.62 → ~0.25 and raise threshold); 20 km = 2×2
   (acceptable, keep 0.62); 25 km+ recommended for real smoke structure.
5. `compose.py` `build_static_overlay()`: graticule ticks, sea/region labels,
   and `draw_scalebar()` km are hardcoded for Ketapang — edit for the region
   (inland areas: drop the strait label, use 1–5 km scale bar, 0.02–0.05° ticks).
6. Region switching: back up `config.py`/`compose.py` (cp ... .bak) BEFORE
   editing, and re-apply fix #3 every time you restore the backup — the dynamic
   zoom edit is lost on restore and the next run crashes.

## Look & feel knobs (compose.py)
- `SMOKE_STOPS` — smoke colormap (yellow->orange->deep red); `smoke_rgba()`
  controls AOD threshold (0.22..2.2) and opacity (max 0.62).
- `fire_layer()` — glow: recency window (12h), intensity (0.4+0.6*sqrt(frp/120)).
- `regrade.py` — SEA/LAND_LO/LAND_HI colors, coastline, shallow-water rim.
- `render_basemap.py` — relief: heightmap `* 0.5` factor, z_scale 0.1,
  light az 315 / el 45. DEM smoothed sigma=4 (SRTM canopy noise over
  Kalimantan otherwise renders as fake hills).
- `encode.sh` — fps (24), crf (18), clone-hold start 1.2s / end 2.5s.

## Fonts
Inter .otf files are already in `fonts/` (ExtraBold, SemiBold, Medium,
MediumItalic, Regular). Without them compose.py falls back to DejaVu/PIL
default and prints a WARNING (layout shifts slightly). Do not re-install via apt.

## forge3d gotchas (v1.34) — baked into these scripts, don't "fix" them
- TerrainRenderParams requires z_scale >= 0.1; smaller scaling is baked into
  the heightmap values (hm = d/2400*0.5).
- Sampler address mode is "ClampToEdge" (not "Clamp").
- Perfectly top-down camera is degenerate — use tiny cam_theta_deg (0.5).
- Scene(colormap=...) accepts only viridis|magma|terrain; this pipeline uses
  the lower-level TerrainRenderer.render_terrain_pbr_pom path instead.
- THIS pipeline maps the DEM 1:1 onto the frame (terrain_span=2.0, top-down
  camera), so the lon/lat->pixel projection is LINEAR (compose.py to_px):
  x=(lon-LON_MIN)/(LON_MAX-LON_MIN)*W, y=(merc_y(lat)-MY0)/(MY1-MY0)*H with
  merc_y=ln(tan(pi/4+lat/2)). No calibration needed. Do NOT use the old
  MapScene+dot-grid approach for this template.

## Older alternative (only if user explicitly wants a tight 25km AOI)
`/home/firman/owy/ketapang/` (ketapang_render.py: procedural smoke from fire
points, MapScene dark colormap). Inferior to Fable pipeline (no real CAMS
AOD); use only on explicit request.

## Pitfalls / verification
- **USE THIS SKILL, NOT FROM-SCRATCH CODE.** When the user asks for a wildfire
  smoke map video, run the Fable pipeline — do NOT build a new smoke simulation
  from raw numpy/forge3d. The pipeline has proven physics, cartography, fonts,
  and encode settings. Building from scratch wastes time and produces inferior
  results. This skill IS the answer; load it and follow it.
- Long renders: don't pipe through `tail` (buffered). Watch the frames dir:
  `ls frames | wc -l` or use background=true + notify_on_complete.
- After compose, verify progression on 3-4 extracted frames (dates advance,
  smoke grows, counters climb) before delivering: vision_analyze the strip.
- Deliverable path: out/ketapang_wildfire_smoke.mp4. Copy to a stable name
  (e.g. <region>_wildfire_smoke.mp4) before sending via WhatsApp (MEDIA: tag).
- FIRMS dedupe across satellites is NOT in these scripts — CSVs already merged;
  counts may include overlaps (acceptable for the visual).
- **Restore the Ketapang config after every run.** The pipeline dir is shared;
  forgetting to restore breaks the next session's Ketapang render.
