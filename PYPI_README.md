# earthchange

**Multipurpose satellite environmental monitoring and change detection, in pure
Python.** 29 scenarios from free public archives: fire danger (Canadian FWI on
BMKG thresholds), smoke exposure in person-days, air-parcel trajectories
(HYSPLIT), drought, paddy-field drought per plot (planting delay from
Sentinel-1, water adequacy, a 7-day outlook), land-surface heat, floods,
deforestation, mining, urbanisation and surface-water change — via **Google Earth Engine** or
**Microsoft Planetary Computer** (no account needed). Export georeferenced
GeoTIFFs, quick-look PNGs, statistics, print-ready A4 maps, citable Markdown
records, and a one-file brief that assembles a whole assessment. Every output
carries its own limits.

- 📖 **Full hands-on tutorial (English & Bahasa Indonesia):** <https://firmanhadi21.github.io/rs-change-detection/>
- 💻 **Source, examples & case study:** <https://github.com/firmanhadi21/rs-change-detection>

## Install

Heavy dependencies are optional *extras*, so the install stays lean:

```bash
pip install 'earthchange[gee]'       # Google Earth Engine backend (free account)
pip install 'earthchange[mpc,maps]'  # Planetary Computer + maps (no account)
pip install 'earthchange[all]'       # everything
```

## Quick start

```bash
# Deforestation around a coordinate, with a finished map
earthchange -s deforestation --lat -3.333 --lon 122.25 --radius 6 --map

# Flood extent from Sentinel-1 SAR — no Earth Engine account needed
earthchange -s flood --lat 27.2 --lon 68.3 \
    --pre 2022-07-01:2022-07-25 --post 2022-08-20:2022-09-10 --backend mpc

# Urban growth timing across 2010/2015/2020 (Landsat 5/8/9)
earthchange -s urban-trend --lat -6.30 --lon 107.15 --map

# List everything
earthchange --list
```

Each run writes a self-contained `output/<run-id>/` folder containing the PNG,
GeoTIFF, statistics JSON, metadata, and any maps.

### Short commands (Indonesian, for routine tasks)

Name a place and a date; earthchange picks the sensor, windows and thresholds,
uses Planetary Computer (no account), counts hectares inside the place's
OpenStreetMap boundary, and writes an Indonesian `RINGKASAN.md` with the limits.

```bash
earthchange banjir    "Pining, Gayo Lues"       2026-11-08     # flood after an event
earthchange kebakaran "Muara Pawan, Ketapang"   2026-09-15     # burned area
earthchange hutan     "Sungai Kakap, Kubu Raya" 2019 2025      # vegetation loss
earthchange kota      "Kota Bekasi"             2020 2025      # new built-up land
earthchange air       "Kabupaten Demak"         2020 2025      # new surface water
```

### From Python

Every scenario is one call. Keyword arguments are the command-line options with
`-` written as `_`; the result holds the run folder and its statistics.

```python
import earthchange as ec

run = ec.run("deforestation", out_dir="deforestasi", lat=-3.333, lon=122.25,
             radius=5, map=True)
run.stats["results"]["pct_affected"]   # 4.1
run.tif()                              # path of the GeoTIFF
run.command                            # the equivalent terminal command

ec.short("banjir", "Pining, Gayo Lues", "2026-11-08")   # a short command
```

## Scenarios

| Scenario | Method | Sensor |
|----------|--------|--------|
| `deforestation` | NDVI loss | Sentinel-2 |
| `urbanization` | Built-up gain — `NDBI` (default), `UI`, `BU`, `IBI`, or thermal `NDISI`/`EBBI` via `--method` | Sentinel-2 / Landsat |
| `water` | NDWI change | Sentinel-2 |
| `burn` | dNBR severity | Sentinel-2 |
| `mining` | SIRAD radar temporal + NDVI loss | Sentinel-1 + S2 |
| `flood` | SAR water extent (event vs baseline) | Sentinel-1 |
| `urban-trend` | NDBI at 3 epochs → RGB growth-timing map | Landsat 5/8/9 |
| `coastline` | Sea boundary + shoreline change (erosion/accretion) + retreat rate m/yr | S1 / S2 / Landsat |
| `transit-access` | % population with access to public transport (SDG 11.2.1) | WorldPop + OSM |
| `island-heat` | SST + LST + wet-bulb (humid heat) trends for small islands | OISST / Landsat / ERA5 |
| `urban-heat` | Urban heat island (SUHII) + hot-spot map + decadal trend | GHSL + Landsat + MODIS |
| `forest-history` | Multi-epoch deforestation: year-of-loss map + forest-area trajectory | S2 / Landsat NDVI |
| `forest-account` | Tree-cover loss by year, primary forest and driver, per regency; optional open ground | Hansen GFC + WRI/Google + Dynamic World |
| `timelapse` | One cloud-free frame per year → PNGs + MP4 | Landsat (1984+) / Sentinel-2 |
| `embeddings` | Foundation-model embeddings: change, similarity, few-shot classes, expansion timeline, clusters | AlphaEarth (GEE) / TESSERA |
| `population-change` | Two-epoch population change: Miloš-style spike poster + map + optional true GPU 3D via forge3d | GHSL GHS_POP |
| `haze` | Smoke & air quality during fires: PM2.5 (ISPU), aerosol index, hotspots | CAMS + Sentinel-5P + FIRMS |
| `fire-history` | Multi-year fire record: burned area per year (peat vs mineral), recurrence map, fire season | MODIS MCD64A1 + FIRMS |

## Two backends

| `--backend` | Data source | Account? |
|-------------|-------------|----------|
| `gee` (default) | Google Earth Engine | free account + `earthengine authenticate` |
| `mpc` | Microsoft Planetary Computer (STAC) | **none** — streams COGs, processes locally |

Optical scenarios build cloud-masked median composites; radar scenarios
auto-select the Sentinel-1 orbit with coverage. The AOI is a square centred on
your coordinate. Landsat 7 is skipped (SLC-off gaps).

## Make maps from a finished run

```bash
earthmap output/<run-id>            # render A4 map sheets offline (no GEE)
```

Map sheets include an OpenStreetMap basemap, the change layer, legend, a
statistics panel, a location inset, coordinate grid, scale bar and north arrow.

## License

MIT © Firman Hadi. Data: Copernicus Sentinel (ESA) and Landsat (USGS/NASA),
via Google Earth Engine or Microsoft Planetary Computer.
