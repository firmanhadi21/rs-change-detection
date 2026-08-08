"""Download FIRMS public 7-day VIIRS active-fire CSVs and filter to bbox."""
import sys
import pandas as pd
import requests, io

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX

# FIRMS publishes its 7-day CSVs per continent, so the region has to match the
# bbox. Hardcoding SouthEast_Asia meant the pipeline returned zero fires
# anywhere else -- and silently, since an empty bbox filter looks the same as a
# quiet fire week.
try:
    from config import FIRMS_REGION
except ImportError:
    FIRMS_REGION = "SouthEast_Asia"

_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
FEEDS = {
    "snpp": f"{_BASE}/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_{FIRMS_REGION}_7d.csv",
    "noaa20": f"{_BASE}/noaa-20-viirs-c2/csv/J1_VIIRS_C2_{FIRMS_REGION}_7d.csv",
    "noaa21": f"{_BASE}/noaa-21-viirs-c2/csv/J2_VIIRS_C2_{FIRMS_REGION}_7d.csv",
}

frames = []
for name, url in FEEDS.items():
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df["sat"] = name
        frames.append(df)
        print(name, len(df), "rows")
    except Exception as e:
        print(name, "FAILED:", e)

if not frames:
    raise SystemExit(
        f"No FIRMS feed downloaded for region {FIRMS_REGION!r}. Check the "
        f"region name (SouthEast_Asia, South_America, Europe, Africa, "
        f"North_America, Russia_Asia, Australia_NewZealand, "
        f"Central_America, South_Asia, Canada, USA_contiguous_and_Hawaii) "
        f"and your network.")

all_df = pd.concat(frames, ignore_index=True)
m = (
    (all_df.longitude >= LON_MIN) & (all_df.longitude <= LON_MAX)
    & (all_df.latitude >= LAT_MIN) & (all_df.latitude <= LAT_MAX)
)
sub = all_df[m].copy()
# build UTC datetime
sub["acq_time"] = sub["acq_time"].astype(int)
sub["dt_utc"] = pd.to_datetime(
    sub["acq_date"] + " " + (sub["acq_time"] // 100).astype(str).str.zfill(2) + ":" + (sub["acq_time"] % 100).astype(str).str.zfill(2),
    utc=True,
)
sub = sub.sort_values("dt_utc")
sub.to_csv(DATA / "fires_bbox.csv", index=False)
print("bbox detections:", len(sub))
print(sub.groupby("acq_date").size())
print("frp stats:", sub.frp.describe().round(1).to_dict())
