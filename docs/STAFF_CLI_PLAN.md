# earthchange for ordinary staff: short Indonesian commands

Status: steps 1–2 built (2026-11-16); steps 3–5 to do. Revised from an earlier QGIS-plugin plan,
which is kept below as a later option.

## Why

earthchange exists so that staff with limited remote-sensing and GIS skills can run common, repetitive
analyses (flood, burn area, forest loss, urban growth, surface water) and get a finished result.

The skill staff lack is remote sensing, not typing a command. A short command line is enough, as long as
the command asks only what staff know (a place and a date) and earthchange makes the remote-sensing
choices: sensor, before/after windows, thresholds, orbit, masks. General GIS applications (QGIS,
GeoLibre, RustGIS) give a workspace; earthchange gives the answer, and its GeoTIFFs open in any of them.

## The commands

```bash
earthchange banjir    "Pining, Gayo Lues"       2026-11-08     # flood after an event
earthchange kebakaran "Muara Pawan, Ketapang"   2026-09-15     # burned area after an event
earthchange hutan     "Sungai Kakap, Kubu Raya" 2019 2025      # vegetation (forest) loss
earthchange kota      "Kota Bekasi"             2020 2025      # new built-up land
earthchange air       "Kabupaten Demak"         2020 2025      # new surface water
earthchange                                              # short help (Indonesian)
```

| Command | Scenario | Windows chosen by earthchange |
|---|---|---|
| `banjir` | `flood` (Sentinel-1) | before: 45 days to the day before; after: event day + 12 days, cut at today |
| `kebakaran` | `burn` (Sentinel-2 dNBR) | before: 90 days; after: event day + 45 days, cut at today |
| `hutan` | `deforestation` (Sentinel-2 NDVI) | whole year 1 vs whole year 2 (current year to today) |
| `kota` | `urbanization` (Sentinel-2 NDBI) | same |
| `air` | `water` (Sentinel-2 NDWI) | same |

Options: `--keluar FOLDER`, `--paksa` (allow very large areas), `--debug` (show tracebacks).
The full expert CLI (`earthchange -s ...`) is unchanged.

## How it works (`earthchange/mudah.py`)

1. **Area by name.** The name is looked up on OpenStreetMap (Nominatim, Indonesia only), preferring an
   administrative boundary polygon; the result is cached in `~/.cache/earthchange/wilayah/`. If several
   areas match, an interactive terminal asks which one. A point with no boundary (a village centre)
   falls back to a 5 km circle, and the summary says so. A boundary file (`.geojson`, or `.gpkg`/`.shp`
   with geopandas) can be given instead of a name.
2. **Size guard.** Areas wider than ~100 km (a province) are refused without `--paksa`, since they take
   hours on an office laptop.
3. **Run.** The existing scenario runs on Planetary Computer (no account) over the square covering the
   boundary, with a print-ready map.
4. **Hectares inside the boundary.** The result GeoTIFF is masked by the boundary polygon and counted
   with latitude-correct pixel areas, so "Kecamatan Pining" means Pining, not a box around it.
5. **Summary.** `RINGKASAN.md` and `ringkasan.json` in Indonesian: area, windows, satellite, hectares,
   run-specific caveats (image dates actually used, masked steep ground, missing coverage) and the
   command's standing limits, plus `wilayah.geojson`.
6. **Errors in plain Indonesian** (unknown place, date in the future, no image yet, no internet), with
   `--debug` for the traceback.

### Flood method change found while testing

The first test, Pining (Gayo Lues) flash flood of 8 Nov 2026, returned "2,143 ha flooded": streaks along
mountain flanks, radar shadow read as water. The Planetary Computer flood method now applies a 50 m
median filter (as its Earth Engine twin already did) and masks slopes > 5°, the standard practice. The
same run then gives 12 ha with 96 % of the box masked as steep, and the summary warns that a flash flood
in narrow mountain valleys cannot be measured by satellite radar and that field reports should be used.
This is the kind of judgement the short commands must carry for users who cannot make it themselves.

## Next steps

3. **Interactive mode.** `earthchange tanya` asks one question at a time (which analysis, which area,
   which date), so nobody needs to remember the syntax.
4. **Windows installer.** One download that installs a self-contained runtime (conda-pack or pixi) and
   puts `earthchange` on the PATH; no Python setup by staff.
5. **Test with one office** (e.g. a BPBD or forestry office) on a normal office laptop; then add
   `tambang` (mining, SIRAD + NDVI) and report templates matching office formats.

Open questions: the Earth Engine twin of the flood method has no slope mask yet; the size cap per
command; whether the summary should also be written as PDF.

## Later option: QGIS plugin with a chat assistant

If offices ask for it, a QGIS plugin can sit on top of the same commands:

- A chat panel sends the user's sentence to our own LLM (e.g. DeepSeek Flash) through a small proxy that
  holds the API key and only returns a proposed tool call (`banjir`, area, date). The LLM never runs code.
- The plugin shows a confirmation card, then runs earthchange **locally** in its own Python runtime
  (separate from QGIS's Python) as a background task and loads the GeoTIFF as a styled layer.
- A plain form tab does the same without the LLM.
- Do not route the plugin through a general server-side agent: such agents run their own tools on the
  server and would put a key to a full-access agent inside every distributed plugin.
