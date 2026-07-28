# grok_understand.md — Repository Understanding

**Repo:** `rs-change-detection`  
**Package (PyPI):** `satchange` v0.1.1  
**Author:** Firman Hadi (Universitas Diponegoro)  
**License:** MIT  
**Language:** Python 3.11+  
**Docs:** https://firmanhadi21.github.io/rs-change-detection/

---

## 1. What this project is

A **multipurpose satellite change-detection toolkit** for remote sensing analysis. One CLI picks a **scenario** (method) and a **location**; it pulls free Sentinel-1/2 or Landsat data, runs the analysis, and writes:

| Output | Purpose |
|--------|---------|
| PNG quick-look | Visual preview |
| GeoTIFF | Full-res, georeferenced (QGIS) |
| `.meta.json` | Sidecar for re-rendering maps |
| `stats.json` | Metrics (mean Δ, % affected, scene counts) |
| Optional A4 map PDF/PNG | Cartographic layout (`--map`) |

**Dual data backends:**

| Backend | Source | Account? |
|---------|--------|----------|
| `gee` (default) | Google Earth Engine | Yes (free EE account / service account) |
| `mpc` | Microsoft Planetary Computer (STAC) | **No** — anonymous signing |

The same scenarios, outputs, and map products work on both backends.

---

## 2. Two layers of the repo

The repo has **two related but distinct purposes**:

### A. Productized toolkit (`satchange` package)

Reusable CLI for any lat/lon worldwide:

```bash
pip install 'satchange[all]'
satchange -s deforestation --lat -3.333 --lon 122.25 --map
satmap output/<run-id>   # re-render maps without re-fetching
```

From source checkout without install:

```bash
python3 detect.py …   # root shim → satchange.detect
python3 make_map.py …
```

### B. Capkala PETI investigation case study

End-to-end evidence pipeline for **illegal gold mining (PETI)** at Capkala, Bengkayang, West Kalimantan (`0.6784°N, 109.0836°E`, radius 1.5 km):

- Sentinel-2 true color  
- SIRAD radar temporal RGB (activity after Mar 2026 police raid)  
- NDVI change (S2 + optional PlanetScope 3 m)  
- Legal verification (BHUMI empty rights, no IUP on MODI)  
- Documentary video (TTS + ffmpeg assembly)

`run_all.py` runs the generic site data-collection pipeline; video is Capkala-specific and separate.

---

## 3. Package architecture

```
satchange/
├── __init__.py       # package doc + __version__ (note: still 0.1.0 in code vs 0.1.1 pyproject)
├── detect.py         # main CLI → console script `satchange`
├── make_map.py       # map re-render CLI → `satmap`
├── mapmaker.py       # A4 cartography (matplotlib + contextily)
├── scenarios.py      # SCENARIOS registry + GEE run functions
├── indices.py        # spectral indices, S2/Landsat composites, S1 helpers (GEE)
├── mpc_backend.py    # full local reimplementation for Planetary Computer
├── gee_utils.py      # EE init, square AOI, cloud mask, PNG/GeoTIFF download
└── sites.py          # named AOI presets (capkala, konawe)
```

**Root shims** (for `python3 detect.py` without install):

- `detect.py` → `satchange.detect.main`
- `make_map.py` → `satchange.make_map.main`

**Entry points** (`pyproject.toml`):

- `satchange = satchange.detect:main`
- `satmap = satchange.make_map:main`

**Optional extras:** `gee`, `mpc`, `maps`, `all` (core deps only `requests`).

---

## 4. How a detection run works

### Control flow (`satchange/detect.py`)

1. Parse args: scenario, location (`--lat/--lon`, `-l`, or `--site`), windows, backend, method overrides, `--map`.
2. Resolve location + radius (site preset or CLI; default radius from scenario).
3. `build_params()` → date windows:
   - **pre/post** for optical & flood  
   - **3 epochs / SIRAD periods** for mining & urban-trend (`--epochs W1,W2,W3`)
4. `apply_overrides()` for optical: `--method`, `--thr`, `--severe`.
5. Create `output/<YYYYMMDD-HHMMSS>_<scenario>_<name>_<6hex>/`.
6. Dispatch:
   - `--backend gee` → `run_gee()` → Earth Engine server-side  
   - `--backend mpc` → `run_mpc()` → STAC download + local numpy/rasterio  
7. Write products + `stats.json`; optionally `render_map()`.

### AOI geometry

**Square clip**, not a circle: `square_aoi` = point buffer then `.bounds()` (GEE) / `square_bbox` (MPC). Side ≈ 2 × radius_km.

### Optical change (generic)

```
median composite(pre) → index → median composite(post) → index
delta = post_index − pre_index
direction "loss": affected = delta < thr; severe = delta < severe_thr
direction "gain": affected = delta > thr; severe = delta > severe_thr
```

Composites use **per-pixel cloud masking + multi-scene median** (near cloud-free).

---

## 5. Scenarios (`SCENARIOS` in `scenarios.py`)

| Key | Method | Sensor | Default need |
|-----|--------|--------|--------------|
| `deforestation` | ΔNDVI loss | S2 | pre/post (defaults 2023 / 2025) |
| `mining` | SIRAD RGB + ΔNDVI | S1 VH + S2 | 3 periods (R/G/B) |
| `urbanization` | ΔNDBI gain (default) | S2 (or Landsat for thermal methods) | pre/post 2020 / 2025 |
| `urban-trend` | NDBI @ 3 epochs → RGB timing | Landsat 5/8/9 | epochs 2010/2015/2020 |
| `flood` | SAR VV water event vs baseline | S1 VV | **required** pre/post |
| `burn` | dNBR loss | S2 | **required** pre/post |
| `water` | ΔNDWI gain | S2 | pre/post 2023 / 2025 |

### Method override (`--method`) for optical scenarios

| Method | Sensor | Use |
|--------|--------|-----|
| NDVI, NDBI, UI, BU, IBI, NDWI, NBR | Sentinel-2 | Default paths |
| NDISI, EBBI | **Landsat 8/9** (thermal) | Auto switch sensor |

Defaults live in `METHOD_DEFAULTS` (`indices.py`). Built-up aliases for urbanization: NDBI, UI, BU, IBI (+ thermal NDISI/EBBI).

### SIRAD (mining / radar temporal)

Mean VH backscatter for **three periods** stacked as R/G/B:

- White/gray = activity all periods  
- Blue = only last period (**new activity** — key Capkala claim post-raid)  
- Orbit ASC/DESC auto-picked for coverage in all windows  

Mining = SIRAD + NDVI loss between first and last period.

### Flood specifics

- Water ≈ low VV (default thr −16 dB)  
- Flood = water in event, not baseline  
- Ocean masked via SRTM mask; permanent ponds kept out via baseline  
- Speckle: focal median + connected-component ≥ 8 pixels  

MPC flood uses ESA WorldCover for land mask (not SRTM void mask).

### Urban-trend

Landsat SR (L5 + L8/9; **L7 excluded** SLC-off). Three epochs of NDBI → normalized RGB. Stats: % built-up first/last, % new.

---

## 6. Dual backend design

| Concern | GEE | MPC |
|---------|-----|-----|
| Code | `scenarios.py` + `indices.py` (server-side EE) | `mpc_backend.py` (local numpy) |
| Download | `gee_utils.download_png/geotiff` | `_write_png` / `_write_tif` from arrays |
| Catalog | EE ImageCollections | STAC (`sentinel-2-l2a`, `sentinel-1-grd`, `landsat-c2-l2`) |
| Auth | service account JSON or `earthengine authenticate` | anonymous `planetary_computer.sign` |

**Intentional parallelism:** MPC reimplements indices/SIRAD/flood/trend so both backends share the CLI contract and output shape, not one shared compute kernel.

GEE credential search order:

1. `./scripts/config/ee-geodetic.json`  
2. `~/.config/earthengine/ee-geodetic.json`  
3. Default user credentials  

GeoTIFF download may coarsen scale (up to 16×) if EE size limits hit.

---

## 7. Sites (`sites.py`)

| Key | Label | Lat, Lon | Radius | Focus |
|-----|-------|----------|--------|-------|
| `capkala` (default) | Capkala, Bengkayang, Kalbar | 0.6784, 109.0836 | 1.5 km | PETI gold |
| `konawe` | Mandiodo / Konawe Utara, Sultra | −3.333, 122.25 | 6.0 km | Nickel / deforestation demos |

Each site stores: AOI, optional S2 date, SIRAD periods, NDVI pre/post windows.  
Resolved via `--site NAME` or `$SITE`.

---

## 8. Map products (`mapmaker.py` / `satmap`)

`render_map(meta, out_base, basemap)` builds A4 landscape PDF+PNG:

- OSM / gray / none basemap (`contextily`)  
- Change layer + legend  
- Stats panel, location inset, grid, scale bar, north arrow, footer  

`make_map.py` / `satmap` re-renders from existing `.meta.json` (no re-fetch).  
Can take a run folder or a single `.tif`.

---

## 9. Capkala investigation pipeline

### Data collection (`data-collection/`)

| Script | Role |
|--------|------|
| `01_sentinel2_download.py` | True-color S2 via GEE |
| `02_sirad_gee.py` | SIRAD RGB (pre-package standalone; similar to scenario mining) |
| `03_ndvi_change_gee.py` | Free S2 NDVI change |
| `03_planetscope_ndvi.py` | Optional commercial 3 m NDVI |
| `04_legal_verification.md` | Manual BHUMI / MODI / police evidence chain |

### Orchestration

```bash
python3 run_all.py --site capkala   # or konawe; optional --drive
```

Steps 1–3 required; PlanetScope optional (skip if no commercial tifs).

### Video documentary

```
narration/capkala_narration_v4.txt
  → scripts/01_generate_tts.py  (ElevenLabs, Bian voice)
  → audio/scene_00..04.mp3
  → scripts/02_assemble_video.py (ffmpeg)
  → scenes/*.mp4 → capkala_investigation.mp4
```

**Not** part of `run_all.py`. Needs `ffmpeg` + ElevenLabs key.

### Evidence narrative (Capkala)

Four independent lines converge: optical clearing, SIRAD blue (post-raid 2026 activity), PlanetScope ΔNDVI (~−0.068, ~25% affected), legal void (no land right / no IUP). Conclusion: **PETI** (tambang tanpa izin).

---

## 10. Directory map (practical)

| Path | Role | Git? |
|------|------|------|
| `satchange/` | Installable package | yes |
| `detect.py`, `make_map.py`, `run_all.py` | Root entrypoints | yes |
| `data-collection/` | Case-study / site pipeline scripts | yes |
| `scripts/` | TTS + video assembly | yes |
| `docs/` | GitHub Pages tutorial (`index.html`) | yes |
| `images/`, `maps/` | Visual assets / example maps | partial |
| `data/` | Raw/example GeoTIFFs | mostly not (README only) |
| `output/` | Per-run detect results | gitignored |
| `audio/`, `scenes/`, `*.mp4` | Generated media | gitignored |
| `scripts/config/` | Secrets (EE key, ElevenLabs) | gitignored |
| `dist/` | Built wheel/sdist | present in tree |

---

## 11. Key design decisions

1. **Scenario registry, not hard-coded CLI** — add scenarios by extending `SCENARIOS` (+ optional run fn / indices).  
2. **Backend split, not plugin framework** — GEE stays EE-native; MPC is a parallel local stack with matching I/O.  
3. **Square AOI** — predictable clipping and map framing.  
4. **Median + SCL (or QA) masking** — robustness over single-scene “best date.”  
5. **Run-scoped output folders** — reproducible, non-clobbering, map-rehydratable via `.meta.json`.  
6. **Optional heavy deps** — PyPI core stays light; extras for GEE / MPC / maps.  
7. **Case study coexists with product** — Capkala proves the methods; package generalizes them.  
8. **Landsat for history** — S2 cannot do 2010; `urban-trend` uses L5/8/9.

---

## 12. Spectral indices reference

| Index | Formula (concept) | Typical change use |
|-------|-------------------|--------------------|
| NDVI | (NIR−Red)/(NIR+Red) | Vegetation loss (deforestation/mining) |
| NDBI | (SWIR1−NIR)/(SWIR1+NIR) | Built-up gain |
| UI | (SWIR2−NIR)/(SWIR2+NIR) | Built-up alt |
| BU | NDBI − NDVI | Built-up alt |
| IBI | Xu 2008 ratio form, clamped [−1,1] | Built-up alt |
| NDWI | (Green−NIR)/(Green+NIR) | Water gain/loss |
| NBR | (NIR−SWIR2)/(NIR+SWIR2) | Burn severity (dNBR) |
| NDISI | thermal + multi-band (Xu 2010) | Impervious (Landsat) |
| EBBI | SWIR/NIR/TIR (As-syakur 2012) | Built-up/bareness (Landsat) |

---

## 13. Dependencies (mental model)

- **Always useful:** `requests`  
- **GEE path:** `earthengine-api`  
- **MPC path:** `numpy`, `rasterio`, `pystac-client`, `planetary-computer`, `odc-stac`, `rioxarray`  
- **Maps:** `matplotlib`, `contextily` (+ rasterio/numpy)  
- **Video path only:** `elevenlabs`, system `ffmpeg`/`ffprobe`  
- **Full dev from source:** `requirements.txt` ≈ all of the above  

---

## 14. Common commands cheat sheet

```bash
# List scenarios / methods
python3 detect.py --list

# Deforestation (GEE)
python3 detect.py -s deforestation --lat -3.333 --lon 122.25 --map

# Same without EE account
python3 detect.py -s deforestation --lat -3.333 --lon 122.25 --backend mpc --map

# Mining at preset site
python3 detect.py -s mining --site konawe --map

# Flood with explicit windows
python3 detect.py -s flood --lat 27.2 --lon 68.3 \
  --pre 2022-07-01:2022-07-25 --post 2022-08-20:2022-09-10 --map

# Urban method swap + thermal Landsat
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method IBI
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method NDISI

# Multi-epoch urban growth
python3 detect.py -s urban-trend --lat -6.30 --lon 107.15 --radius 10 --map

# Re-render maps only
python3 make_map.py output/<run-id>
python3 make_map.py output/<run-id>/some.tif --basemap gray

# Site pipeline (Capkala/Konawe data collection)
python3 run_all.py --site konawe

# Capkala documentary
python3 scripts/01_generate_tts.py && python3 scripts/02_assemble_video.py
```

---

## 15. Extending the tool

| Goal | Where to change |
|------|-----------------|
| New location preset | `satchange/sites.py` → `SITES` |
| New scenario | `satchange/scenarios.py` → `SCENARIOS` + run fn; mirror in `mpc_backend.run_mpc` |
| New spectral index | `satchange/indices.py` (`INDEX_FN`, `METHOD_DEFAULTS`, `SENSOR`); mirror numpy version in `mpc_backend` |
| Map layout / elements | `satchange/mapmaker.py` |
| Download / EE auth | `satchange/gee_utils.py` |
| CLI flags | `satchange/detect.py` |

**Important:** New optical indices need both GEE (`indices.py`) and MPC (`mpc_backend.py`) implementations to keep backends feature-parity.

---

## 16. Publishing / versioning notes

- PyPI name: **`satchange`**  
- Build: hatchling; packaging guide in `PUBLISHING.md`  
- Public README is bilingual-leaning Indonesian + English tutorial site  
- `CITATION.cff` ready for academic citation  
- Package `__version__` in `__init__.py` is `0.1.0` while `pyproject.toml` / CITATION is `0.1.1` — slight drift  

---

## 17. Mental model (one paragraph)

**`rs-change-detection` is a pure-Python remote-sensing change-detection product (`satchange`) plus a forensic Capkala PETI case study.** You choose a scenario (which index/sensor method to use) and a place; the CLI runs either Earth Engine or Planetary Computer, writes a timestamped run folder with GeoTIFF/PNG/stats, and can stamp a cartographic map. Mining uses dual SIRAD+NDVI; floods use SAR water differencing; multi-decade urban growth uses Landsat epochs. Capkala scripts, legal notes, and a short documentary video demonstrate the same methods as real-world evidence gathering.

---

*Generated from a full repo read for agent/human onboarding. Prefer this file + README for orientation; prefer source in `satchange/` for implementation truth.*
