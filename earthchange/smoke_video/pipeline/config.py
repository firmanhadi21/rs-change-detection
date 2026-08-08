"""Shared config for the Ketapang wildfire smoke animation.

Edit the bbox, cities, and timeline here to point the pipeline at another
region or period. Keep the bbox square-ish in degrees for a square frame.
"""
from pathlib import Path

WORK = Path(__file__).resolve().parent
DATA = WORK / "data"
FRAMES = WORK / "frames"
OUT = WORK / "out"
for d in (DATA, FRAMES, OUT):
    d.mkdir(parents=True, exist_ok=True)

# Square bbox around Ketapang, Kalimantan Barat (WGS84)
LON_MIN, LON_MAX = 108.5, 111.8
LAT_MIN, LAT_MAX = -3.2, 0.1

WIDTH = HEIGHT = 1080

# Title block text (edit alongside the bbox)
TITLE = "WILDFIRE SMOKE"
SUBTITLE = "KETAPANG · WEST KALIMANTAN · {period} · CAMS + VIIRS"

CITIES = [
    # name, lon, lat, is_major  (verify coords: https://geocoding-api.open-meteo.com/v1/search?name=...)
    ("Ketapang",     109.977, -1.839, True),
    ("Sukadana",     109.950, -1.250, False),
    ("Kendawangan",  110.203, -2.519, False),
    ("Sandai",       110.517, -1.250, False),
    ("Nanga Pinoh",  111.748, -0.349, False),
    ("Pangkalan Bun",111.633, -2.683, True),
]
