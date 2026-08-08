"""Re-grade basemap from the saved forge3d render: stronger land/sea separation + coastline."""
import sys
import numpy as np
from scipy.ndimage import binary_erosion, gaussian_filter
from PIL import Image as I

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, WIDTH, HEIGHT

raw = np.asarray(I.open(DATA / "terrain_raw.png").convert("RGB"), dtype=np.float32) / 255.0
lum = raw @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

dem = np.clip(np.load(DATA / "dem_mercator.npy"), 0, 2400)
dfull = np.asarray(I.fromarray(dem).resize((WIDTH, HEIGHT), I.Resampling.BILINEAR), dtype=np.float32)
sea = dfull <= 0.0

ll = lum[~sea]
base = np.percentile(ll, 55)
hi = np.percentile(ll, 99.9)
t = np.clip((lum - base) / (hi - base + 1e-6), 0, 1) ** 2.0 * 0.9

SEA     = np.array([9, 14, 26], np.float32) / 255.0    # deeper navy
LAND_LO = np.array([36, 41, 53], np.float32) / 255.0   # clearly lighter slate
LAND_HI = np.array([172, 180, 192], np.float32) / 255.0

img = LAND_LO * (1 - t[..., None]) + LAND_HI * t[..., None]
img[sea] = SEA

# shallow-water rim: soft glow of the coast bleeding into the sea
land_f = (~sea).astype(np.float32)
rim = gaussian_filter(land_f, 5.0)
rim = np.clip(rim - 0.5, 0, 0.5) * 2.0          # 1 on land, fades in sea
rim_sea = np.where(sea, rim, 0.0)
RIM_COL = np.array([44, 58, 82], np.float32) / 255.0
img = img + rim_sea[..., None] * (RIM_COL - SEA) * 0.9

# crisp coastline stroke
edge = land_f - binary_erosion(~sea, iterations=1).astype(np.float32)
edge = gaussian_filter(edge, 0.6)
COAST = np.array([118, 136, 160], np.float32) / 255.0
a = np.clip(edge, 0, 1)[..., None] * 0.55
img = img * (1 - a) + COAST * a

out = (np.clip(img, 0, 1) * 255).astype(np.uint8)
I.fromarray(out).save(DATA / "basemap.png")
I.fromarray(out).resize((540, 540)).save(DATA / "basemap_preview.png")

# compose.py needs this mask to keep smoke and fire dots off the water. Nothing
# in the transferred pipeline wrote it -- the original working directory simply
# had one left over from an earlier run, so a fresh machine failed at step 4
# with a missing sea_mask.npy. It is computed here anyway, so save it.
np.save(DATA / "sea_mask.npy", sea)
print("regraded")
