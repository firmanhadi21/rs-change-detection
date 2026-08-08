"""Sample hourly aerosol optical depth (CAMS via Open-Meteo) on a grid over the bbox."""
import sys, time, json
import numpy as np
import requests

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX

STEP = 0.2
lats = np.round(np.arange(LAT_MIN, LAT_MAX + 1e-9, STEP), 3)
lons = np.round(np.arange(LON_MIN, LON_MAX + 1e-9, STEP), 3)
print(f"grid {len(lats)} x {len(lons)} = {len(lats)*len(lons)} points")

points = [(la, lo) for la in lats for lo in lons]
BATCH = 50
url = "https://air-quality-api.open-meteo.com/v1/air-quality"

times_ref = None
aod = np.full((0,), 0.0)
values = {}  # (lat,lon) -> list of aod
pm = {}

for b in range(0, len(points), BATCH):
    chunk = points[b:b + BATCH]
    params = {
        "latitude": ",".join(str(p[0]) for p in chunk),
        "longitude": ",".join(str(p[1]) for p in chunk),
        "hourly": "aerosol_optical_depth,pm2_5",
        "past_days": 7,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=120)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            print("retry", attempt, e)
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError("open-meteo failed")
    if isinstance(data, dict):
        data = [data]
    for p, d in zip(chunk, data):
        h = d["hourly"]
        if times_ref is None:
            times_ref = h["time"]
        values[p] = h["aerosol_optical_depth"]
        pm[p] = h["pm2_5"]
    print(f"batch {b//BATCH + 1}/{(len(points)+BATCH-1)//BATCH} ok")
    time.sleep(0.4)

T = len(times_ref)
cube = np.full((T, len(lats), len(lons)), np.nan, dtype=np.float32)
pmcube = np.full((T, len(lats), len(lons)), np.nan, dtype=np.float32)
for i, la in enumerate(lats):
    for j, lo in enumerate(lons):
        v = values[(la, lo)]
        cube[:, i, j] = [np.nan if x is None else x for x in v]
        w = pm[(la, lo)]
        pmcube[:, i, j] = [np.nan if x is None else x for x in w]

np.save(DATA / "aod_cube.npy", cube)
np.save(DATA / "pm25_cube.npy", pmcube)
json.dump({"times": times_ref, "lats": lats.tolist(), "lons": lons.tolist()}, open(DATA / "aod_meta.json", "w"))
print("cube", cube.shape, "aod range", np.nanmin(cube), np.nanmax(cube))
print("valid fraction", float(np.mean(~np.isnan(cube))))
