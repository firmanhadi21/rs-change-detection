"""Download AWS Terrarium elevation tiles and build a DEM mosaic for the bbox."""
import io, math, sys, time
import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX

Z = 10
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
with open(DATA / "dem_meta.txt", "w") as f:
    f.write(f"{crop.shape[1]} {crop.shape[0]}\n")
print("saved")
