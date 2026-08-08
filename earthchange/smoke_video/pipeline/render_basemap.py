"""Step 2 — render the top-down terrain with forge3d (offscreen, no window).

Produces data/terrain_raw.png (the raw forge3d PBR render). Run regrade.py
afterwards to produce the dark-themed data/basemap.png used by compose.py.

Works on macOS (Metal) out of the box. On a headless Linux box with no GPU,
install software Vulkan first:  sudo apt install mesa-vulkan-drivers
"""
import numpy as np, os, sys, tempfile, time

# harmless on macOS; avoids a Mesa warning on headless Linux
os.environ.setdefault("XDG_RUNTIME_DIR", tempfile.gettempdir())

import forge3d as f3d
from forge3d.terrain_params import (ClampSettings, IblSettings, LightSettings, LodSettings,
    PomSettings, SamplingSettings, ShadowSettings, TerrainRenderParams as TP, TriplanarSettings)
from forge3d.determinism import write_canonical_hdr
from scipy.ndimage import gaussian_filter
from PIL import Image as I

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA, WIDTH, HEIGHT

t0 = time.time()
dem = np.clip(np.load(DATA / "dem_mercator.npy"), 0, 2400)
# Terrarium DEM carries canopy/vegetation noise over Kalimantan: smooth it,
# otherwise flat peatlands render as fake mountains.
dem_s = gaussian_filter(dem, sigma=4.0)
hm_size = 1601
d = np.asarray(I.fromarray(dem_s).resize((hm_size, hm_size), I.Resampling.BILINEAR), dtype=np.float32)
# z_scale must be >= 0.1 in forge3d, so bake the rest of the vertical scaling
# into the heightmap itself (0.5 * 0.1 = effective 0.05 world-units max).
hm = (d / 2400.0 * 0.5).astype(np.float32)

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
