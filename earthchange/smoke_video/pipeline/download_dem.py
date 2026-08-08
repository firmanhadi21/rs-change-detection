"""Download AWS Terrarium elevation tiles and build a DEM mosaic for the bbox."""
import io, math, sys, time
import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX

def _zoom_for(span_deg, target_px=3000, lo=8, hi=14):
    """Tile zoom giving roughly target_px across the bbox.

    Was fixed at 10, which suits a ~3-degree box and leaves a 0.36-degree one
    mushy. The rule reproduces both known-good values: z10 for Ketapang's 3.3
    degrees, z14 for Bromo's 0.36. Clamped because each step up quadruples the
    tile count.
    """
    z = math.log2(max(target_px, 1) * 360.0 / (256.0 * max(span_deg, 1e-6)))
    return int(max(lo, min(hi, round(z))))


try:
    from config import DEM_ZOOM as Z            # explicit override wins
except ImportError:
    Z = _zoom_for(max(LON_MAX - LON_MIN, LAT_MAX - LAT_MIN))
print(f"DEM zoom z{Z} for a {max(LON_MAX-LON_MIN, LAT_MAX-LAT_MIN):.3f}° span")
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def tile_xy(lon, lat, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


x0f, y0f = tile_xy(LON_MIN, LAT_MAX, Z)  # top-left
x1f, y1f = tile_xy(LON_MAX, LAT_MIN, Z)  # bottom-right
x0, y0 = int(math.floor(x0f)), int(math.floor(y0f))
x1, y1 = int(math.floor(x1f)), int(math.floor(y1f))
nx, ny = x1 - x0 + 1, y1 - y0 + 1
print(f"z{Z}: tiles x {x0}..{x1} ({nx}), y {y0}..{y1} ({ny}) = {nx*ny} tiles")

mosaic = np.zeros((ny * 256, nx * 256), dtype=np.float32)
sess = requests.Session()
for j, ty in enumerate(range(y0, y1 + 1)):
    for i, tx in enumerate(range(x0, x1 + 1)):
        for attempt in range(3):
            try:
                r = sess.get(URL.format(z=Z, x=tx, y=ty), timeout=30)
                r.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
        img = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=np.float32)
        elev = img[..., 0] * 256.0 + img[..., 1] + img[..., 2] / 256.0 - 32768.0
        mosaic[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = elev
    print(f"row {j+1}/{ny} done")

# crop mosaic to exact bbox (in fractional tile coords)
px0 = int(round((x0f - x0) * 256))
py0 = int(round((y0f - y0) * 256))
px1 = int(round((x1f - x0) * 256))
py1 = int(round((y1f - y0) * 256))
crop = mosaic[py0:py1, px0:px1]
print("mosaic", mosaic.shape, "crop", crop.shape, "elev range", crop.min(), crop.max())

np.save(DATA / "dem_mercator.npy", crop)  # web-mercator pixel grid over bbox
# Vertical ceiling for the render, from the terrain itself. This was fixed at
# 2400 m, which is fine for Kalimantan (nothing reaches it) and wrong for a
# volcano: Semeru is 3669 m, so Bromo's summits were flattened to a plateau.
# The 99.9th percentile rather than the max, so one spike pixel cannot squash
# everything else.
_land = crop[crop > 0]
_ceil = float(np.percentile(_land, 99.9)) if _land.size else 1200.0
_ceil = max(1200.0, round(_ceil / 100.0) * 100.0)
print(f"DEM ceiling {_ceil:.0f} m (terrain max {crop.max():.0f} m)")

with open(DATA / "dem_meta.txt", "w") as f:
    # Fields: width height zoom ceiling. render_basemap.py and regrade.py both
    # read this; importing this module to get them would re-run the download.
    f.write(f"{crop.shape[1]} {crop.shape[0]} {Z} {_ceil:.0f}\n")
print("saved")
