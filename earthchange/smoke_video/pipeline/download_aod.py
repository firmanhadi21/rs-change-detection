"""Sample hourly aerosol optical depth (CAMS via Open-Meteo) on a grid over the bbox."""
import sys, time, json, random
import numpy as np
import requests

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX

STEP = 0.2
lats = np.round(np.arange(LAT_MIN, LAT_MAX + 1e-9, STEP), 3)
lons = np.round(np.arange(LON_MIN, LON_MAX + 1e-9, STEP), 3)
print(f"grid {len(lats)} x {len(lons)} = {len(lats)*len(lons)} points")

points = [(la, lo) for la in lats for lo in lons]
# Open-Meteo weights a call by locations x variables x days, so 50 points over
# 8 days with two variables is a heavy single request. Island-sized bboxes were
# reliably rate-limited at 50; 25 gets through.
BATCH = 25
PAUSE = 0.5          # between batches; raised for the rest of the run on a 429
url = "https://air-quality-api.open-meteo.com/v1/air-quality"


def fetch(params, tries=7):
    """One batch, backing off properly on 429.

    The old loop slept 3, 6, 9, 12 seconds and then gave up -- roughly half a
    minute against a limit measured per minute, so it retried straight back into
    the same wall and failed the whole run. This honours Retry-After when the
    server sends one, doubles the wait when it does not, and permanently slows
    the batch cadence after the first 429 so the rest of the run stops provoking
    it.
    """
    global PAUSE
    for attempt in range(tries):
        r = requests.get(url, params=params, timeout=120)
        if r.status_code != 429:
            r.raise_for_status()
            return r.json()
        wait = float(r.headers.get("Retry-After") or 0) or min(90, 5 * 2 ** attempt)
        wait += random.uniform(0, 2)                 # spread out concurrent runs
        PAUSE = min(PAUSE * 1.6, 6.0)
        print(f"  rate limited by Open-Meteo — waiting {wait:.0f}s, "
              f"batch pause now {PAUSE:.1f}s (attempt {attempt + 1}/{tries})")
        time.sleep(wait)
    raise SystemExit(
        "Open-Meteo kept returning 429 (too many requests).\n"
        "Its free tier is limited per minute, per hour and per day, and a\n"
        "whole-island bbox asks for thousands of points. Options: wait an hour\n"
        "and re-run, use a smaller --bbox, or set an API key if you have one.\n"
        "Everything downloaded so far is in data/, so a re-run is not wasted.")

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
    data = fetch(params)
    if isinstance(data, dict):
        data = [data]
    for p, d in zip(chunk, data):
        h = d["hourly"]
        if times_ref is None:
            times_ref = h["time"]
        values[p] = h["aerosol_optical_depth"]
        pm[p] = h["pm2_5"]
    print(f"batch {b//BATCH + 1}/{(len(points)+BATCH-1)//BATCH} ok")
    time.sleep(PAUSE)

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
