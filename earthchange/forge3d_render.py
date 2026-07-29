#!/usr/bin/env python3
"""True GPU 3-D spike render via forge3d (Miloš Popović's Rust/WebGPU library).

forge3d renders a raster as a 3-D height field: we feed the *larger* of the two
population epochs as elevation (so every populated cell becomes a peak — Miloš's
authentic per-cell spike look) and a class-coloured RGBA overlay for the change
(grey = present in both, green = gained, red = lost).

Pipeline mirrors forge3d's own examples/population_spike_worldpop/poland_population_spikes.py:
  1. reproject the height field to a metric CRS, clip outliers, write an
     uncompressed float32 TIFF the viewer can read;
  2. write a class-coloured RGBA PNG overlay;
  3. launch the forge3d viewer binary over IPC, load terrain + overlay, set the
     camera / sun / z-scale, take a snapshot.

Needs `pip install forge3d` and a working WebGPU GPU (Metal on macOS, Vulkan on
Linux). Data prep (steps 1–2) runs anywhere; the GPU snapshot (step 3) needs the
viewer. On failure this prints an actionable message and returns None — it never
crashes the surrounding scenario run.
"""

import os
import re
import socket
import subprocess
import time

TARGET_CRS = "EPSG:3857"          # metric, global; fine near the equator
CLIP_PERCENTILE = 99.0            # tame one giant city cell (as forge3d's example does)
# Colours match the matplotlib poster (present / gained / lost).
OVERLAY_RGB = {1: (154, 151, 141), 2: (26, 158, 106), 3: (210, 31, 31)}
GROUND_RGB = (205, 201, 190)      # light grey plateau (the island surface)
FLOOR_FRAC = 0.05                 # every land cell rises to ≥ this × the tallest
BASE_PCT = 75                     # land percentile treated as flat rural baseline
BG_COLOR = [0.02, 0.02, 0.025]


def available():
    """(ok, message) — whether forge3d + its viewer binary are importable."""
    try:
        import forge3d  # noqa: F401
        from forge3d.viewer_ipc import find_viewer_binary
    except Exception as e:  # noqa: BLE001
        return False, (f"forge3d not installed ({e.__class__.__name__}). "
                       "Install with: pip install 'earthchange[forge3d]'")
    try:
        find_viewer_binary()
    except Exception as e:  # noqa: BLE001
        return False, f"forge3d viewer binary not found ({e})."
    return True, "ok"


# ----------------------------- data prep -----------------------------
def _reproject(arr, src_transform, src_crs, resampling):
    """Reproject a single array from src to TARGET_CRS. Returns (out, transform)."""
    import numpy as np
    from rasterio.warp import calculate_default_transform, reproject
    h, w = arr.shape
    left, top = src_transform * (0, 0)
    right, bottom = src_transform * (w, h)
    dst_transform, dw, dh = calculate_default_transform(
        src_crs, TARGET_CRS, w, h, left, bottom, right, top)
    out = np.zeros((dh, dw), dtype=arr.dtype)
    reproject(source=arr, destination=out, src_transform=src_transform,
              src_crs=src_crs, dst_transform=dst_transform, dst_crs=TARGET_CRS,
              resampling=resampling)
    return out, dst_transform


def _prep(tif1, tif2, run_dir, neutral_pct, min_pop, floor_frac=FLOOR_FRAC):
    """Write the height DEM + class overlay. Returns (dem_path, overlay_path, meta)."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from PIL import Image
    from .population_change import _read, _classify
    p1, _ = _read(tif1)
    p2, _ = _read(tif2)
    r = min(p1.shape[0], p2.shape[0]); c = min(p1.shape[1], p2.shape[1])
    p1, p2 = p1[:r, :c], p2[:r, :c]
    cls, _, _, _ = _classify(p1, p2, neutral_pct, min_pop)
    height = np.maximum(p1, p2).astype("float32")

    with rasterio.open(tif1) as ds:
        src_transform, src_crs = ds.transform, ds.crs
    height, dst_t = _reproject(height[:r, :c], src_transform, src_crs, Resampling.bilinear)
    cls_rp, _ = _reproject(cls[:r, :c], src_transform, src_crs, Resampling.nearest)

    # Continuous landmass: fill small gaps so the island reads as a solid plateau
    # (like Miloš's country surface) instead of floating spikes.
    land = height > 0
    try:
        from scipy.ndimage import binary_closing, binary_fill_holes
        land = binary_fill_holes(binary_closing(land, iterations=2))
    except Exception:  # noqa: BLE001 — scipy optional; fall back to raw populated mask
        pass

    valid = height > 0
    clip_max = float(np.percentile(height[valid], CLIP_PERCENTILE)) if valid.any() else 1.0
    height = np.clip(height, 0.0, clip_max)
    # Rural baseline: on a uniformly dense island (Java) every rural cell has
    # population, which would bury the plateau in spikes. Subtract the median
    # land value so only *above-rural* population rises off the plateau —
    # rural land stays flat grey and cities spike, like the benchmark.
    base = float(np.percentile(height[valid], BASE_PCT)) if valid.any() else 0.0
    relief = np.maximum(height - base, 0.0)
    # Floor: every land cell sits on a low plateau (floor_frac of the tallest
    # relief) so the island reads as one solid slab with spikes on top.
    rmax = float(relief.max()) if relief.size else 1.0
    floor = floor_frac * max(rmax, 1.0)
    height = np.where(land, floor + relief, 0.0).astype("float32")
    clip_max = float(height.max()) if land.any() else 1.0

    dem = os.path.join(run_dir, "pop_height_3857.tif")
    Image.fromarray(np.ascontiguousarray(height, dtype="float32")).save(
        dem, format="TIFF", compression="raw")   # viewer needs uncompressed float32

    # Overlay: grey plateau over all land; green where gained, red where lost.
    overlay = np.zeros((*height.shape, 4), dtype="uint8")
    overlay[land] = (*GROUND_RGB, 255)
    overlay[cls_rp == 2] = (*OVERLAY_RGB[2], 255)
    overlay[cls_rp == 3] = (*OVERLAY_RGB[3], 255)
    ov = os.path.join(run_dir, "pop_overlay_3d.png")
    Image.fromarray(overlay).save(ov)
    meta = {"clip_max": clip_max, "px_m": abs(dst_t.a),
            "cols": height.shape[1], "rows": height.shape[0]}
    return dem, ov, meta


# ----------------------------- viewer render -----------------------------
def _ipc_render(dem, overlay, out_png, meta, size, zscale, camera):
    from forge3d.viewer_ipc import find_viewer_binary, send_ipc
    binary = find_viewer_binary()
    proc = subprocess.Popen([binary, "--ipc-port", "0", "--size", "1280x1280"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    port, ready = None, re.compile(r"FORGE3D_VIEWER_READY\s+port=(\d+)")
    start = time.time()
    while time.time() - start < 30:
        if proc.poll() is not None:
            raise RuntimeError("forge3d viewer exited before it was ready")
        line = proc.stdout.readline()
        m = ready.search(line) if line else None
        if m:
            port = int(m.group(1)); break
    if port is None:
        proc.terminate(); raise RuntimeError("timed out waiting for forge3d viewer")
    import threading
    threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()
    threading.Thread(target=lambda: [None for _ in proc.stderr], daemon=True).start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", port)); sock.settimeout(180.0)
    try:
        if os.path.exists(out_png):
            os.unlink(out_png)
        send_ipc(sock, {"cmd": "load_terrain", "path": os.path.abspath(dem)})
        time.sleep(6)
        send_ipc(sock, {"cmd": "set_terrain", "zscale": zscale, "background": BG_COLOR,
                        "sun_azimuth": 155.0, "sun_elevation": 16.0,
                        "sun_intensity": 4.0, "ambient": 0.10, **camera})
        send_ipc(sock, {"cmd": "set_terrain_pbr", "enabled": True, "exposure": 1.1,
                        "shadow_technique": "pcss", "shadow_map_res": 4096,
                        "msaa": 4, "normal_strength": 0.5})
        time.sleep(3)
        send_ipc(sock, {"cmd": "load_overlay", "name": "change",
                        "path": os.path.abspath(overlay), "opacity": 1.0})
        send_ipc(sock, {"cmd": "set_overlay_solid", "solid": False})
        time.sleep(4)
        send_ipc(sock, {"cmd": "snapshot", "path": os.path.abspath(out_png),
                        "width": size, "height": size})
        for _ in range(180):
            time.sleep(1)
            if os.path.exists(out_png) and os.path.getsize(out_png) > 0:
                return out_png
        raise RuntimeError("forge3d snapshot timed out")
    finally:
        try:
            send_ipc(sock, {"cmd": "close"})
        except Exception:  # noqa: BLE001
            pass
        sock.close(); proc.terminate()


def render(tif1, tif2, run_dir, name, years, neutral_pct=1.0, min_pop=150,
           size=4096, prep_only=False, phi=48.0, theta=52.0, fov=30.0,
           zscale_frac=0.35, radius_mult=2.6, floor_frac=FLOOR_FRAC):
    """Produce pop_spikes_3d.png via forge3d. Returns the path, or None on failure.

    `prep_only=True` writes just the DEM + overlay (no GPU) — useful for
    inspecting inputs or rendering later on a GPU box. Camera angle (`phi`,
    `theta`, `fov`), vertical exaggeration (`zscale_frac`), framing distance
    (`radius_mult`) and plateau `floor_frac` are tunable.
    """
    for mod in ("numpy", "rasterio", "PIL"):
        try:
            __import__(mod if mod != "PIL" else "PIL.Image")
        except ImportError:
            print(f"  (forge3d prep needs {mod}: pip install 'earthchange[maps]')")
            return None
    dem, overlay, meta = _prep(tif1, tif2, run_dir, neutral_pct, min_pop, floor_frac)
    print(f"  forge3d inputs: {os.path.basename(dem)} + {os.path.basename(overlay)} "
          f"({meta['cols']}×{meta['rows']}, px≈{meta['px_m']:.0f} m)")
    if prep_only:
        return dem

    ok, msg = available()
    if not ok:
        print(f"  (forge3d GPU render skipped: {msg})")
        print(f"     inputs are ready — render later with forge3d on a GPU machine.")
        return None

    # The viewer reads the raw TIFF as a grid indexed in PIXELS (no geotransform),
    # so horizontal extent = cols and height = value * zscale in the same units.
    # Make the tallest cell ~30% of the grid width; frame the whole grid.
    grid = max(meta["cols"], meta["rows"])
    zscale = zscale_frac * meta["cols"] / max(meta["clip_max"], 1.0)
    camera = {"phi": phi, "theta": theta, "fov": fov, "radius": radius_mult * grid}
    out = os.path.join(run_dir, "pop_spikes_3d.png")
    try:
        _ipc_render(dem, overlay, out, meta, size, zscale, camera)
        print(f"3D spikes: {os.path.normpath(out)}")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  (forge3d GPU render failed: {e.__class__.__name__}: {e})")
        return None
