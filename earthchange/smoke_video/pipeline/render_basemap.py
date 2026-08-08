"""Step 2 — render the top-down terrain with forge3d (offscreen, no window).

Produces data/terrain_raw.png (the raw forge3d PBR render). Run regrade.py
afterwards to produce the dark-themed data/basemap.png used by compose.py.

Works on macOS (Metal) out of the box. On a headless Linux box with no GPU,
install software Vulkan first:  sudo apt install mesa-vulkan-drivers
"""
import math, numpy as np, os, sys, tempfile, time

# harmless on macOS; avoids a Mesa warning on headless Linux
os.environ.setdefault("XDG_RUNTIME_DIR", tempfile.gettempdir())

import forge3d as f3d
from forge3d.terrain_params import (ClampSettings, IblSettings, LightSettings, LodSettings,
    PomSettings, SamplingSettings, ShadowSettings, TerrainRenderParams as TP, TriplanarSettings)
from forge3d.determinism import write_canonical_hdr
from scipy.ndimage import gaussian_filter
from PIL import Image as I

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, WIDTH, HEIGHT, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX

def _dem_meta(idx, default, cast=int):
    """A field download_dem.py recorded: 2=tile zoom, 3=elevation ceiling.

    Read rather than imported: importing that module would re-run the download.
    """
    try:
        parts = (DATA / "dem_meta.txt").read_text().split()
        return cast(parts[idx]) if len(parts) > idx else default
    except Exception:                                              # noqa: BLE001
        return default


# Vertical ceiling from the terrain itself, not a fixed 2400 m. That number
# suits Kalimantan, where nothing reaches it; over Bromo, Semeru's 3669 m was
# clipped and the summits rendered as a plateau.
DEM_CEIL = _dem_meta(3, 2400.0, float)

t0 = time.time()
dem = np.clip(np.load(DATA / "dem_mercator.npy"), 0, DEM_CEIL)
# Terrarium DEM carries canopy noise over lowland forest: smooth it, or flat
# peatland renders as fake mountains. But the right amount scales with the tile
# zoom -- a fixed 4.0 was tuned for z10, and at z14 over volcanic terrain it
# erases the relief the animation exists to show.
try:
    from config import TERRAIN_SMOOTH as _SIGMA
except ImportError:
    _SIGMA = float(np.clip(4.0 - (_dem_meta(2, 10) - 10) * 0.5, 1.5, 5.0))
print(f"DEM ceiling {DEM_CEIL:.0f} m · smoothing sigma {_SIGMA}")
dem_s = gaussian_filter(dem, sigma=_SIGMA)
hm_size = 1601
d = np.asarray(I.fromarray(dem_s).resize((hm_size, hm_size), I.Resampling.BILINEAR), dtype=np.float32)
# z_scale must be >= 0.1 in forge3d, so the rest of the vertical scaling is
# baked into the heightmap. The factor cannot be a constant: terrain_span maps
# the DEM to 2.0 world units whatever the real width, so a fixed 0.5 means the
# exaggeration depends on how wide the frame is. It was tuned for Ketapang --
# 365 km across, 1.7 km of relief, about 5x exaggerated. The same 0.5 over
# Bromo (80 km across, 3.7 km of relief) renders at 0.55x, i.e. FLATTER than
# reality, which is why volcanic terrain came out featureless.
#
# Solve instead for a constant exaggeration: relief of DEM_CEIL should occupy
# (DEM_CEIL / half-span) * EXAG world units, and hm * z_scale is what it gets.
EXAG, _Z_SCALE = 5.0, 0.1
_span_km = ((LON_MAX - LON_MIN) * 111.32
            * math.cos(math.radians((LAT_MIN + LAT_MAX) / 2)))
_hm_max = float(np.clip((DEM_CEIL / 1000.0) * 2.0 / max(_span_km, 1e-6)
                        * EXAG / _Z_SCALE, 0.15, 2.0))
print(f"span {_span_km:.0f} km · vertical exaggeration {EXAG}x "
      f"· heightmap max {_hm_max:.2f}")
hm = (d / DEM_CEIL * _hm_max).astype(np.float32)

session = f3d.Session(window=False)
renderer = f3d.TerrainRenderer(session)
mat = f3d.MaterialSet.terrain_default()
with tempfile.TemporaryDirectory() as td:
    hdr = os.path.join(td, "env.hdr"); write_canonical_hdr(hdr)
    env = f3d.IBL.from_hdr(hdr, intensity=1.0)

# Top-down, near-orthographic camera: tiny theta (0 is degenerate), small fov,
# large radius. With terrain_span=2.0 this maps the DEM 1:1 onto the frame.
cfg = TP(size_px=(WIDTH, HEIGHT), render_scale=1.0, terrain_span=2.0, msaa_samples=1,
    z_scale=0.1, cam_target=[0.0, 0.0, 0.0], cam_radius=14.0, cam_phi_deg=0.0,
    cam_theta_deg=0.5, cam_gamma_deg=0.0, fov_y_deg=8.3, clip=(0.1, 250.0),
    light=LightSettings("Directional", 315.0, 45.0, 3.0, [1.0, 1.0, 1.0]),
    ibl=IblSettings(True, 0.30, 0.0),
    shadows=ShadowSettings(False, "PCF", 512, 2, 250.0, 1.0, 0.8, 0.002, 0.001, 0.3, 1e-4, 0.5, 2.0, 0.9),
    triplanar=TriplanarSettings(6.0, 4.0, 1.0), pom=PomSettings(False, "Occlusion", 0.0, 1, 1, 0, False, False),
    lod=LodSettings(0, 0.0, 0.0),
    sampling=SamplingSettings("Linear", "Linear", "Linear", 1, "ClampToEdge", "ClampToEdge", "ClampToEdge"),
    clamp=ClampSettings((0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)),
    overlays=[], exposure=1.0, gamma=2.2, albedo_mode="colormap", colormap_strength=1.0)
frame = renderer.render_terrain_pbr_pom(material_set=mat, env_maps=env,
    params=f3d.TerrainRenderParams(cfg), heightmap=hm, target=None, certificate=False)
frame.save(str(DATA / "terrain_raw.png"))
print("forge3d render done", round(time.time() - t0, 1), "s ->", DATA / "terrain_raw.png")
print("now run: python3 regrade.py")
