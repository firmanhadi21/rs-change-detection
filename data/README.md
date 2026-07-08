# data/ — raw satellite inputs (not tracked in git)

Place raw imagery here. These files are `.gitignore`d because they are large
and/or licensed; the scripts read from and write to this directory.

## Files expected

| File | Produced / supplied by | Consumed by |
|------|------------------------|-------------|
| `sentinel2_capkala.tif` | `data-collection/01_sentinel2_download.py` | manual → `images/` |
| `planetscope_pre.tif` (4-band, NIR=band 4) | You (Planet Labs order) | `data-collection/03_planetscope_ndvi.py` |
| `planetscope_post.tif` (8-band, NIR=band 8) | You (Planet Labs order) | `data-collection/03_planetscope_ndvi.py` |
| `planetscope_ndvi_change.png` | `03_planetscope_ndvi.py` (output) | manual → `images/` |
| `planetscope_stats.json` | `03_planetscope_ndvi.py` (output) | — |

SIRAD (`02_sirad_gee.py`) runs in Google Earth Engine and downloads its result
straight to `images/sirad_raw.png`, so it needs nothing in `data/`.

PlanetScope imagery is commercial — order it from https://www.planet.com/ (or
via an education/research grant). Everything else uses free, open data.
