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

For a non-default site, files are name-spaced by site key, e.g.
`planetscope_konawe_pre.tif` / `planetscope_konawe_post.tif` (the scripts fall
back to the generic `planetscope_pre.tif` if a site-specific file is absent).

SIRAD (`02_sirad_gee.py`) and the Sentinel-2 download run in Google Earth Engine
and write their results straight to `images/` (`sirad_<site>.png`,
`sentinel2_<site>.png`), so they need nothing in `data/`.

PlanetScope imagery is commercial — order it from https://www.planet.com/ (or
via an education/research grant). Everything else uses free, open data.
