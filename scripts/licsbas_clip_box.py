"""Find the land clip box from the coherence map, for LiCSBAS step 05.

The official LiCSBAS sample clips to a small AOI before inverting. My run
processed the entire 2.57 x 1.91 degree frame, which over Flores is mostly
ocean: reference-point selection, loop statistics and the mask all spend their
effort on water.

Rather than eyeball a box off a map, take it from avg coherence -- the pixels
that actually carry signal define where the island is.

    python3 scripts/licsbas_clip_box.py
"""

import os
import sys

import numpy as np

TS = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/licsbas/TS_GEOCml10")


def par(path):
    d = {}
    for line in open(path, errors="ignore"):
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return d


def main():
    dem = par(f"{TS}/info/EQA.dem_par")
    w = int(dem["width"].split()[0])
    h = int(dem["nlines"].split()[0])
    lat0 = float(dem["corner_lat"].split()[0])
    lon0 = float(dem["corner_lon"].split()[0])
    dlat = float(dem["post_lat"].split()[0])
    dlon = float(dem["post_lon"].split()[0])

    coh = np.fromfile(f"{TS}/results/coh_avg", dtype=np.float32)
    if coh.size != w * h:
        raise SystemExit(f"coh_avg size {coh.size} != {w*h}")
    coh = coh.reshape(h, w)

    finite = np.isfinite(coh) & (coh > 0)
    print(f"frame {w} x {h}, {100*finite.mean():.1f}% with coherence")
    print(f"coherence: median {np.nanmedian(coh[finite]):.3f}  "
          f"p90 {np.nanpercentile(coh[finite], 90):.3f}")

    for thre in (0.10, 0.12, 0.15, 0.20):
        land = finite & (coh >= thre)
        if land.sum() < 50:
            print(f"  coh >= {thre}: too few pixels ({land.sum()})")
            continue
        rows = np.where(land.any(axis=1))[0]
        cols = np.where(land.any(axis=0))[0]
        n = lat0 + dlat * rows.min()
        s = lat0 + dlat * (rows.max() + 1)
        west = lon0 + dlon * cols.min()
        east = lon0 + dlon * (cols.max() + 1)
        area_frac = ((rows.max() - rows.min() + 1)
                     * (cols.max() - cols.min() + 1)) / (w * h)
        print(f"  coh >= {thre}: {land.sum():>6} px  "
              f"box {west:.3f}/{east:.3f}/{s:.3f}/{n:.3f}  "
              f"= {100*area_frac:.0f}% of frame")

    # Use a robust box: percentile bounds, so a few stray coherent pixels
    # offshore do not stretch it back to the full frame.
    land = finite & (coh >= 0.12)
    rows, cols = np.where(land)
    r1, r2 = np.percentile(rows, [1, 99])
    c1, c2 = np.percentile(cols, [1, 99])
    n = lat0 + dlat * r1
    s = lat0 + dlat * r2
    west = lon0 + dlon * c1
    east = lon0 + dlon * c2
    print(f"\nrobust box (1-99th pct of coh>=0.12 pixels):")
    print(f"  p05_clip_range_geo=\"{west:.3f}/{east:.3f}/{s:.3f}/{n:.3f}\"")
    print(f"  lon {west:.3f}..{east:.3f}   lat {s:.3f}..{n:.3f}")

    epi_lat, epi_lon = -8.3101, 121.3517
    inside = west <= epi_lon <= east and s <= epi_lat <= n
    print(f"  contains the epicentre ({epi_lat}, {epi_lon}): {inside}")
    if not inside:
        print("  WARNING: epicentre outside the box — widen before using it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
