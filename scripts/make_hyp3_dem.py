"""Give HyP3 products the DEM band MintPy needs, without reprocessing them.

prep_hyp3.py requires a *_dem.tif beside each interferogram, and HyP3 only
produces one when the job was submitted with include_dem. Ours were not, and
resubmitting 705 pairs costs ~7000 credits and another 50 GB of download.

The band HyP3 would have written is Copernicus DEM GLO-30 resampled onto the
product grid. That DEM is free on Planetary Computer and needs no account, so
it can simply be built here instead. MintPy cannot tell the difference: the
values and the grid are the same.

Each product carries its own geocoded grid -- roughly ten distinct ones per
track -- so the mosaic is fetched once and reprojected per product.

    python3 scripts/make_hyp3_dem.py output/insar_flores_desc
"""

import argparse
import glob
import os
import sys

# PROJ_LIB from an OTB install shadows the current database and breaks every
# CRS operation below. The shell fix only helps shells started after it, so
# clear it here too -- this script is useless without working reprojection.
for var in ("PROJ_LIB", "GDAL_DATA"):
    if "OTB" in os.environ.get(var, ""):
        os.environ.pop(var)

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.merge import merge  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402

DEM_COLLECTION = "cop-dem-glo-30"


def fetch_dem(bounds, cache):
    """Mosaic Copernicus GLO-30 over a bbox, cached on disk."""
    if os.path.exists(cache):
        print(f"using cached DEM mosaic {cache}")
        return cache

    import planetary_computer
    import pystac_client

    cat = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=[DEM_COLLECTION],
                            bbox=list(bounds)).items())
    if not items:
        raise SystemExit(f"no {DEM_COLLECTION} tiles cover {bounds}")
    print(f"fetching {len(items)} DEM tiles")

    srcs = [rasterio.open(i.assets["data"].href) for i in items]
    mosaic, transform = merge(srcs)
    profile = srcs[0].profile
    profile.update(height=mosaic.shape[1], width=mosaic.shape[2],
                   transform=transform, count=1, compress="deflate")
    with rasterio.open(cache, "w", **profile) as d:
        d.write(mosaic[0], 1)
    for s in srcs:
        s.close()
    print(f"wrote {cache}  ({mosaic.shape[2]}x{mosaic.shape[1]})")
    return cache


def dem_for(product_dir, dem_path):
    """Write <stem>_dem.tif matching this product's grid. Returns the path."""
    unw = glob.glob(os.path.join(product_dir, "*_unw_phase.tif"))
    if not unw:
        return None
    stem = os.path.basename(unw[0])[: -len("_unw_phase.tif")]
    out = os.path.join(product_dir, f"{stem}_dem.tif")
    if os.path.exists(out):
        return out

    with rasterio.open(unw[0]) as ref:
        profile = ref.profile.copy()
        dst = np.zeros((ref.height, ref.width), dtype="float32")
        with rasterio.open(dem_path) as dem:
            reproject(
                source=rasterio.band(dem, 1), destination=dst,
                src_transform=dem.transform, src_crs=dem.crs,
                dst_transform=ref.transform, dst_crs=ref.crs,
                # Bilinear, as HyP3 does: a DEM is continuous, and nearest
                # would put terracing into the topographic correction.
                resampling=Resampling.bilinear, dst_nodata=np.nan)

    profile.update(count=1, dtype="float32", nodata=np.nan, compress="deflate")
    with rasterio.open(out, "w", **profile) as d:
        d.write(dst, 1)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", help="a run folder holding hyp3/")
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()

    hyp3 = os.path.join(a.run_dir, "hyp3")
    dirs = sorted(d for d in glob.glob(f"{hyp3}/*") if os.path.isdir(d))
    if not dirs:
        raise SystemExit(f"no products under {hyp3}")
    print(f"{len(dirs)} products in {a.run_dir}")

    # Union of every product's bounds, so one mosaic serves the whole track.
    lo_x = lo_y = float("inf")
    hi_x = hi_y = float("-inf")
    for d in dirs:
        unw = glob.glob(os.path.join(d, "*_unw_phase.tif"))
        if not unw:
            continue
        with rasterio.open(unw[0]) as s:
            b = s.bounds if s.crs and s.crs.is_geographic else \
                rasterio.warp.transform_bounds(s.crs, "EPSG:4326", *s.bounds)
        lo_x, lo_y = min(lo_x, b[0]), min(lo_y, b[1])
        hi_x, hi_y = max(hi_x, b[2]), max(hi_y, b[3])
    bounds = (lo_x - 0.05, lo_y - 0.05, hi_x + 0.05, hi_y + 0.05)
    print(f"track bounds: {[round(v, 3) for v in bounds]}")

    cache = a.cache or os.path.join(a.run_dir, "cop_dem_glo30.tif")
    dem = fetch_dem(bounds, cache)

    made = skipped = 0
    for i, d in enumerate(dirs, 1):
        before = os.path.exists(os.path.join(
            d, os.path.basename(glob.glob(f"{d}/*_unw_phase.tif")[0])
            .replace("_unw_phase.tif", "_dem.tif"))) if glob.glob(
                f"{d}/*_unw_phase.tif") else True
        p = dem_for(d, dem)
        if p is None:
            continue
        made += 0 if before else 1
        skipped += 1 if before else 0
        if i % 50 == 0 or i == len(dirs):
            print(f"  {i}/{len(dirs)}  written {made}, already present {skipped}",
                  flush=True)

    print(f"\ndone: {made} DEM bands written, {skipped} already present")


if __name__ == "__main__":
    sys.exit(main())
