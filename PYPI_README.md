# satchange

**Multipurpose satellite change detection in pure Python.** Map deforestation,
mining, urbanisation, floods, burns, surface-water change and multi-epoch urban
growth anywhere on Earth from free Sentinel-1/2 and Landsat data — via **Google
Earth Engine** or **Microsoft Planetary Computer** (no account needed). Export
georeferenced GeoTIFFs, quick-look PNGs, statistics, and print-ready A4 maps.

- 📖 **Full hands-on tutorial (English & Bahasa Indonesia):** <https://firmanhadi21.github.io/rs-change-detection/>
- 💻 **Source, examples & case study:** <https://github.com/firmanhadi21/rs-change-detection>

## Install

Heavy dependencies are optional *extras*, so the install stays lean:

```bash
pip install 'satchange[gee]'       # Google Earth Engine backend (free account)
pip install 'satchange[mpc,maps]'  # Planetary Computer + maps (no account)
pip install 'satchange[all]'       # everything
```

## Quick start

```bash
# Deforestation around a coordinate, with a finished map
satchange -s deforestation --lat -3.333 --lon 122.25 --radius 6 --map

# Flood extent from Sentinel-1 SAR — no Earth Engine account needed
satchange -s flood --lat 27.2 --lon 68.3 \
    --pre 2022-07-01:2022-07-25 --post 2022-08-20:2022-09-10 --backend mpc

# Urban growth timing across 2010/2015/2020 (Landsat 5/8/9)
satchange -s urban-trend --lat -6.30 --lon 107.15 --map

# List everything
satchange --list
```

Each run writes a self-contained `output/<run-id>/` folder containing the PNG,
GeoTIFF, statistics JSON, metadata, and any maps.

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
satmap output/<run-id>            # render A4 map sheets offline (no GEE)
```

Map sheets include an OpenStreetMap basemap, the change layer, legend, a
statistics panel, a location inset, coordinate grid, scale bar and north arrow.

## License

MIT © Firman Hadi. Data: Copernicus Sentinel (ESA) and Landsat (USGS/NASA),
via Google Earth Engine or Microsoft Planetary Computer.
