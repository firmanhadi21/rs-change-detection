"""Where Borneo is burning this season, and whether it is early or intense.

Two questions a total cannot answer:

  WHERE. A hotspot density map of the current year to date, with the province
  and national borders drawn, so a number attached to "Kalteng" can be checked
  against where the detections actually are.

  WHEN. Cumulative hotspots by day of year, this year against every previous
  year. A season that is merely EARLY looks alarming in an August total and
  ends up ordinary; a season that is genuinely INTENSE separates from the pack
  and stays separated. The two are indistinguishable from a single number, and
  conflating them is the standard way fire reporting goes wrong in August.

    conda run -n base python scripts/borneo_hotspot_map.py
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.borneo_hotspots import build_regions, init_gee   # noqa: E402

OUT = os.path.expanduser("~/GitHub/rs-change-detection/output/fire")
BORNEO_BBOX = [108.5, -4.5, 119.5, 7.5]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=2001)
    ap.add_argument("--min-confidence", type=int, default=30)
    ap.add_argument("--scale", type=int, default=5000,
                    help="metres per pixel for the downloaded density map")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    ee = init_gee()
    os.makedirs(a.out, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    firms = ee.ImageCollection("FIRMS")
    end_str = (firms.limit(1, "system:time_start", False).first()
               .date().format("YYYY-MM-dd").getInfo())
    this_year, md_end = int(end_str[:4]), end_str[5:]
    doy_end = (np.datetime64(end_str)
               - np.datetime64(f"{this_year}-01-01")).astype("timedelta64[D]"
                                                             ).astype(int) + 1
    regions = build_regions(ee)
    aoi = ee.Geometry.Rectangle(BORNEO_BBOX)
    print(f"FIRMS to {end_str} (day {doy_end} of {this_year})")

    # ---- 1. density map --------------------------------------------------
    ic = (firms.filterDate(f"{this_year}-01-01", f"{this_year}-{md_end}")
          .select(["confidence"]))
    dens = (ic.map(lambda i: i.gte(a.min_confidence).rename("n"))
            .sum().unmask(0).clip(aoi))
    url = dens.getDownloadURL({"scale": a.scale, "region": aoi,
                               "format": "NPY"})
    import urllib.request
    import io
    with urllib.request.urlopen(url) as r:
        buf = io.BytesIO(r.read())
    grid = np.load(buf, allow_pickle=True)["n"].astype(float)
    print(f"  density grid {grid.shape} at {a.scale} m, "
          f"max {grid.max():.0f} pixel-days, {100*(grid>0).mean():.1f}% burnt")

    # ---- 2. cumulative-by-day curves ------------------------------------
    # Monthly steps rather than daily: 26 years x 365 reduceRegion calls would
    # be absurd, and month ends are enough to separate early from intense.
    years = list(range(a.start_year, this_year + 1))
    months = list(range(1, 13))
    cum = np.full((len(years), 12), np.nan)
    for yi, y in enumerate(years):
        imgs = []
        for m in months:
            stop = (f"{y}-{m+1:02d}-01" if m < 12 else f"{y+1}-01-01")
            if y == this_year and m > int(md_end[:2]):
                break
            if y == this_year and m == int(md_end[:2]):
                stop = f"{y}-{md_end}"
            sub = (firms.filterDate(f"{y}-01-01", stop).select("confidence")
                   .map(lambda i: i.gte(a.min_confidence).rename("n")))
            imgs.append(sub.sum().unmask(0).rename(f"m{m:02d}"))
        if not imgs:
            continue
        stack = ee.Image.cat(imgs)
        vals = stack.reduceRegion(ee.Reducer.sum(), regions.geometry(),
                                  1000, maxPixels=int(1e10),
                                  tileScale=4).getInfo()
        for m in months:
            k = f"m{m:02d}"
            if k in vals and vals[k] is not None:
                cum[yi, m - 1] = float(vals[k])
        print(f"  {y} cumulative to date: {np.nanmax(cum[yi]):>9,.0f}")

    # ---- figure ----------------------------------------------------------
    fig, ax = plt.subplots(1, 2, figsize=(15.5, 6.6),
                           gridspec_kw={"width_ratios": [1.05, 1]})

    ext = [BORNEO_BBOX[0], BORNEO_BBOX[2], BORNEO_BBOX[1], BORNEO_BBOX[3]]
    shown = np.where(grid > 0, grid, np.nan)
    im = ax[0].imshow(shown, extent=ext, origin="upper", cmap="inferno",
                      norm=matplotlib.colors.LogNorm(
                          vmin=1, vmax=max(2, np.nanmax(shown))),
                      interpolation="nearest")
    try:
        import geopandas as gpd
        from shapely.geometry import shape
        gj = regions.getInfo()
        polys = [shape(f["geometry"]) for f in gj["features"]]
        gpd.GeoSeries(polys, crs=4326).boundary.plot(
            ax=ax[0], color="#5a5a5a", linewidth=.6)
    except Exception as exc:                              # noqa: BLE001
        print(f"  (borders not drawn: {exc.__class__.__name__})")
    ax[0].set_xlim(ext[0], ext[1])
    ax[0].set_ylim(ext[2], ext[3])
    ax[0].set_title(f"Hotspot density, 1 Jan - {md_end} {this_year}\n"
                    f"MODIS pixel-days per {a.scale//1000} km cell, log scale",
                    fontsize=10.5, loc="left")
    ax[0].set_xlabel("lon")
    ax[0].set_ylabel("lat")
    fig.colorbar(im, ax=ax[0], shrink=.82, pad=.02, label="pixel-days")

    x = np.arange(1, 13)
    for yi, y in enumerate(years[:-1]):
        ax[1].plot(x, cum[yi], "-", lw=.9, color="#b9c4cf", zorder=1)
    # Name the years that actually matter rather than all 25.
    for y, col in ((2015, "#d1495b"), (2019, "#e08a1e"), (2023, "#7a5195")):
        if y in years:
            ax[1].plot(x, cum[years.index(y)], "-", lw=1.8, color=col,
                       label=f"{y} (El Nino)" if y in (2015, 2019) else str(y),
                       zorder=2)
    ax[1].plot(x, cum[-1], "-o", lw=2.6, ms=4, color="#111111",
               label=f"{this_year}", zorder=3)
    ax[1].set_xticks(x)
    ax[1].set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O",
                           "N", "D"])
    ax[1].set_yscale("symlog", linthresh=1000)
    ax[1].set_ylabel("cumulative hotspot pixel-days")
    ax[1].set_title("Cumulative hotspots through the year\n"
                    "an EARLY season rejoins the pack; an INTENSE one does not",
                    fontsize=10.5, loc="left")
    ax[1].grid(alpha=.25)
    ax[1].legend(fontsize=9, loc="upper left")

    fig.suptitle("Borneo fire season — Kalimantan, Sabah, Sarawak, Labuan, "
                 "Brunei (MODIS FIRMS)", fontsize=13, y=.98)
    fig.tight_layout(rect=[0, 0, 1, .94])
    out = os.path.join(a.out, "borneo_hotspots.png")
    fig.savefig(out, dpi=130)
    np.save(os.path.join(a.out, "borneo_cumulative.npy"), cum)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
