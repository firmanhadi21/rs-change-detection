# Ketapang Wildfire Smoke Animation — forge3d pipeline

Reproduces the Milos Popovic–style "Wildfire Smoke" animation for the Ketapang
(Kalimantan Barat) fires: dark forge3d-rendered terrain, animated CAMS smoke,
NASA FIRMS (VIIRS) fire detections, and live counters. 1080×1080 MP4 + GIF.

All data sources are public and need **no API keys**. The FIRMS feed is a
rolling 7-day window, so each run animates the most recent week — dates,
frame count, and the subtitle adapt automatically.

## Prerequisites

- Python 3.10+ and `ffmpeg` on your PATH
- Python packages: `pip install -r requirements.txt`
  (on Debian/Ubuntu system Python you may need `pip install --break-system-packages ...`)
- **Fonts**: the layout is designed for [Inter](https://rsms.me/inter/).
  - macOS: `brew install --cask font-inter` (or download and double-click the .otf files)
  - Debian/Ubuntu: `sudo apt install fonts-inter`
  - Or just drop the Inter `.otf` files into a `fonts/` folder next to the scripts.
  - Without Inter it falls back to Arial/Helvetica/DejaVu (layout may shift slightly).

### GPU / rendering backend

forge3d renders via wgpu and works offscreen (no window):

- **macOS**: works out of the box (Metal). Nothing to install.
- **Linux with a GPU**: works out of the box (Vulkan).
- **Headless Linux / no GPU** (e.g. a server or container):
  `sudo apt install mesa-vulkan-drivers` gives you llvmpipe software Vulkan —
  that's how the original run was produced; the 1080px render takes ~7 s on CPU.

## Run

```bash
bash run_all.sh          # everything: download -> render -> compose -> encode
```

or step by step:

```bash
python3 download_dem.py    # 1a. AWS Terrarium elevation tiles -> data/dem_mercator.npy
python3 download_fires.py  # 1b. FIRMS 7-day VIIRS CSVs (SNPP+NOAA20+NOAA21) -> data/fires_bbox.csv
python3 download_aod.py    # 1c. CAMS aerosol optical depth via Open-Meteo -> data/aod_cube.npy
python3 render_basemap.py  # 2.  forge3d offscreen terrain render -> data/terrain_raw.png
python3 regrade.py         # 3.  dark grade + land/sea separation -> data/basemap.png
python3 compose.py preview 96 156   # optional: single frames -> data/preview_*.png
python3 compose.py all     # 4.  all frames -> frames/f_0000.png ...
bash encode.sh             # 5.  -> out/ketapang_wildfire_smoke.{mp4,gif}
```

Full run takes roughly 10–15 minutes (mostly frame compositing and downloads).

## Customizing

- **Region**: edit the bbox, `CITIES`, `TITLE`/`SUBTITLE` in `config.py`.
  Keep the bbox roughly square in degrees. Verify city coordinates with
  `https://geocoding-api.open-meteo.com/v1/search?name=<city>`.
  Also update the sea/region labels in `build_static_overlay()` in `compose.py`
  (KARIMATA STRAIT, KALIMANTAN BARAT, ... are location-specific).
- **Period**: the pipeline animates the trailing 7 days. For a specific
  historical window you'd need a (free) NASA FIRMS MAP_KEY for the fire archive
  and the CAMS archive from the Copernicus ADS — not covered by these scripts.
- **Look**: smoke ramp and opacity in `smoke_rgba()` (compose.py); fire glow in
  `fire_layer()`; land/sea palette and coastline in `regrade.py`; relief
  strength via the `* 0.5` heightmap factor and light angles in `render_basemap.py`.
- **Output**: `WIDTH/HEIGHT` in config.py; fps/quality in `encode.sh`.

## How it works

1. **Terrain**: Terrarium PNG tiles (z10) are decoded to elevation, mosaicked,
   and cropped to the bbox in web-mercator pixel space. The DEM is smoothed
   (σ=4) because SRTM-derived data over Kalimantan carries forest-canopy noise
   that would render as fake hills.
2. **forge3d render**: `TerrainRenderer.render_terrain_pbr_pom` with a top-down
   near-orthographic camera (`cam_theta_deg=0.5`, `fov_y_deg=8.3`,
   `cam_radius=14`, `terrain_span=2.0`) — this maps the DEM exactly 1:1 onto
   the frame, so all overlays use a simple linear lon/lat→pixel mapping.
   Directional light az 315° / el 45° provides the hillshade.
3. **Grade**: the raw render's luminance is remapped to a dark theme; land gets
   a lighter slate base than the deep-navy sea, plus a shallow-water rim glow
   and a 1px coastline stroke so flat coastal peatlands stay distinguishable.
4. **Smoke**: hourly AOD on a 0.2° grid is time-interpolated per frame,
   upsampled, textured with slowly-evolving value noise, and mapped through a
   yellow→deep-red ramp with AOD-dependent opacity.
5. **Fires**: each frame shows detections from the trailing 12 h with a
   recency fade, drawn as additive orange glows (screen blend).
6. **Furniture**: title, UTC clock, cumulative/daily counters, graticule,
   labels, scale bar, AOD colorbar, credits — all PIL, in Inter.

## forge3d gotchas (v1.34)

- `TerrainRenderParams` requires `z_scale >= 0.1` — bake any smaller vertical
  scaling into the heightmap values instead.
- Sampler address mode is `"ClampToEdge"` (not `"Clamp"`).
- A perfectly top-down camera is degenerate; use a tiny `cam_theta_deg` (0.5).
- `Scene(colormap=...)` accepts only `viridis|magma|terrain`.
- On headless Linux, set `XDG_RUNTIME_DIR` (the scripts do this for you) and
  install `mesa-vulkan-drivers`.

## Credits / data

CAMS/ECMWF (via Open-Meteo Air Quality API) · NASA FIRMS (VIIRS SNPP, NOAA-20,
NOAA-21) · AWS Terrain Tiles (Terrarium) · forge3d by Milos Agathon.
Please keep the data credits in the video if you publish it.
