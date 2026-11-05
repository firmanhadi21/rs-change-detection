"""Why did Malaysian Borneo miss the 2026 drought? Latitude vs border, and an independent rain check."""
import ee
import numpy as np
import pandas as pd
import geopandas as gpd
from rasterio import features
from rasterio.transform import from_origin
from earthchange.gee_utils import initialize_ee

z = np.load("data/kalimantan/dc_2026.npz", allow_pickle=True)
dc, dates = z["dc"], pd.to_datetime(z["dates"])
x0, yt, st = z["grid"]
ny, nx = dc.shape[1:]
tr = from_origin(x0, yt, st, st)
ne = gpd.read_file("data/kalimantan/ne_countries/ne_10m_admin_0_countries.zip")
ras = lambda iso: features.rasterize([(g, 1) for g in ne[ne.ADM0_A3 == iso].geometry],  # noqa: E731
                                     out_shape=(ny, nx), transform=tr) > 0
my, idn = ras("MYS"), ras("IDN")
lat = np.repeat((yt - (np.arange(ny) + 0.5) * st)[:, None], nx, axis=1)
jo = (dates >= "2026-07-01") & (dates < "2026-11-01")
yr = (dates >= "2026-01-01")
pk_jo, pk_yr = dc[jo].max(axis=0), dc[yr].max(axis=0)
when = np.array(dates[yr])[dc[yr].argmax(axis=0)]
print("1. Peak Drought Code by latitude band (ERA5-Land cells on Borneo)")
print(f"   {'band':<14}{'IDN Jul-Oct':>12}{'MYS Jul-Oct':>12}{'MYS Jan-Oct':>12}   MYS peak month")
for lo, hi in ((-4.5, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 4.5)):
    b = (lat >= lo) & (lat < hi)
    i, m = idn & b, my & b
    fi = f"{np.median(pk_jo[i]):12.0f}" if i.sum() > 20 else f"{'-':>12}"
    fm = f"{np.median(pk_jo[m]):12.0f}{np.median(pk_yr[m]):12.0f}" if m.sum() > 20 else f"{'-':>12}{'-':>12}"
    mon = pd.Series(pd.to_datetime(when[m]).month).mode().iloc[0] if m.sum() > 20 else "-"
    print(f"   {lo:+.1f} to {hi:+.1f}{fi}{fm}   {mon}")

print("\n2. CHIRPS rain Jul-Oct 2026 vs 2001-2025 mean (independent, gauge-blended)")
initialize_ee()
ch = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
last = ch.aggregate_max("system:time_start").getInfo()
end = min(pd.Timestamp("2026-11-01"), pd.Timestamp(last, unit="ms") + pd.Timedelta(days=1))
print(f"   CHIRPS daily to {pd.Timestamp(last, unit='ms'):%Y-%m-%d}; window 1 Jul - {end - pd.Timedelta(days=1):%d %b}")
w0, w1 = "07-01", f"{end:%m-%d}"
y26 = ch.filterDate(f"2026-{w0}", f"2026-{w1}").sum()
clim = ee.ImageCollection([ch.filterDate(f"{y}-{w0}", f"{y}-{w1}").sum() for y in range(2001, 2026)]).mean()
borneo = ne[ne.ADM0_A3.isin(["IDN", "MYS"])].clip((108.5, -4.3, 119.3, 4.5))
for iso in ("IDN", "MYS"):
    g = borneo[borneo.ADM0_A3 == iso].union_all()
    for lo, hi in ((-4.5, -2), (-2, 0), (0, 2), (2, 4.5)):
        part = g.intersection(gpd.GeoSeries.from_xy([0], [0]).iloc[0].buffer(0).union(
            __import__("shapely").geometry.box(108.5, lo, 119.3, hi)))
        if part.is_empty or part.area < 0.2:
            continue
        geom = ee.Geometry(part.__geo_interface__)
        a = y26.reduceRegion(ee.Reducer.mean(), geom, 5566, maxPixels=1e9).getInfo()["precipitation"]
        c = clim.reduceRegion(ee.Reducer.mean(), geom, 5566, maxPixels=1e9).getInfo()["precipitation"]
        print(f"   {iso} {lo:+.1f} to {hi:+.1f}: 2026 {a:5.0f} mm, normal {c:5.0f} mm  ({100 * a / c:4.0f}% of normal)")
