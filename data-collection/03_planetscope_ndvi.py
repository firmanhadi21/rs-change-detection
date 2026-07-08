#!/usr/bin/env python3
"""
PlanetScope NDVI Change Detection for Capkala Mining Zone.

Computes NDVI from pre/post PlanetScope imagery (3m resolution).
Quantifies vegetation loss due to mining expansion.

Input:  data/planetscope_pre.tif  (4-band, NIR=band 4)
        data/planetscope_post.tif (8-band, NIR=band 8)
Output: data/planetscope_ndvi_change.png
        data/planetscope_stats.json

Results:
  NDVI pre:  0.862 → post: 0.793
  dNDVI: -0.068
  Area affected: 24.7%
  Severe loss: 9.2%
"""

import os, json, sys
import numpy as np

try:
    import rasterio
except ImportError:
    print("Install rasterio: pip install rasterio")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Install Pillow: pip install Pillow")
    sys.exit(1)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from satchange.sites import get_site

SITE = get_site()
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Site-parameterised filenames (fall back to the generic names if present).
def _pick(*names):
    for n in names:
        p = os.path.join(DATA_DIR, n)
        if os.path.exists(p):
            return p
    return os.path.join(DATA_DIR, names[0])

PRE_PATH = _pick(f"planetscope_{SITE['key']}_pre.tif", "planetscope_pre.tif")
POST_PATH = _pick(f"planetscope_{SITE['key']}_post.tif", "planetscope_post.tif")

# === NDVI Computation ===
def compute_ndvi(nir_band, red_band):
    """Compute Normalized Difference Vegetation Index.
    
    NDVI = (NIR - RED) / (NIR + RED)
    Range: -1 to 1. Water < 0, Bare soil ~0.1, Healthy vegetation > 0.6
    """
    ndvi = np.where(
        (nir_band + red_band) > 0,
        (nir_band.astype(float) - red_band.astype(float)) / 
        (nir_band.astype(float) + red_band.astype(float)),
        np.nan
    )
    return ndvi


def load_planetscope(path, nir_idx, red_idx=0):
    """Load PlanetScope GeoTIFF."""
    with rasterio.open(path) as src:
        print(f"  {os.path.basename(path)}: {src.count} bands, {src.width}x{src.height}")
        
        nir = src.read(nir_idx + 1).astype(float)
        # PlanetScope band order varies. Common: B1=Blue, B2=Green, B3=Red, B4=NIR
        # For 8-band: B5=RedEdge, B6=RedEdge, B7=RedEdge, B8=NIR
        # Try to find Red band
        if nir_idx == 3:  # 4-band
            red = src.read(3).astype(float)  # Band 3 = Red
        elif nir_idx == 7:  # 8-band
            red = src.read(3).astype(float)  # Band 3 = Red in 8-band
        else:
            red = src.read(red_idx + 1).astype(float)
        
        profile = src.profile
    
    return nir, red, profile


def main():
    print("=== PlanetScope NDVI Change Detection ===")
    print(f"Pre image:  {PRE_PATH}")
    print(f"Post image: {POST_PATH}")
    print()
    
    # Check files exist
    if not os.path.exists(PRE_PATH):
        print(f"ERROR: {PRE_PATH} not found.")
        print("Place PlanetScope pre-event image at this path (4-band GeoTIFF).")
        sys.exit(1)
    if not os.path.exists(POST_PATH):
        print(f"ERROR: {POST_PATH} not found.")
        print("Place PlanetScope post-event image at this path (8-band GeoTIFF).")
        sys.exit(1)
    
    # Load imagery
    print("Loading pre-event imagery (4-band: NIR=band 4)...")
    nir_pre, red_pre, profile = load_planetscope(PRE_PATH, nir_idx=3)
    
    print("Loading post-event imagery (8-band: NIR=band 8)...")
    nir_post, red_post, _ = load_planetscope(POST_PATH, nir_idx=7)
    
    # Ensure same dimensions
    if nir_pre.shape != nir_post.shape:
        print(f"WARNING: Shape mismatch! Pre: {nir_pre.shape}, Post: {nir_post.shape}")
        print("Resampling post to match pre...")
        from rasterio.enums import Resampling
        with rasterio.open(POST_PATH) as src:
            nir_post = src.read(
                8, out_shape=nir_pre.shape, resampling=Resampling.bilinear
            ).astype(float)
            red_post = src.read(
                3, out_shape=nir_pre.shape, resampling=Resampling.bilinear
            ).astype(float)
    
    # Compute NDVI
    print("\nComputing NDVI...")
    ndvi_pre = compute_ndvi(nir_pre, red_pre)
    ndvi_post = compute_ndvi(nir_post, red_post)
    
    # Mask out nodata
    mask = ~np.isnan(ndvi_pre) & ~np.isnan(ndvi_post)
    ndvi_pre_masked = ndvi_pre[mask]
    ndvi_post_masked = ndvi_post[mask]
    
    # Statistics
    dndvi = ndvi_post - ndvi_pre
    dndvi_masked = dndvi[mask]
    
    stats = {
        "ndvi_pre_mean": float(np.nanmean(ndvi_pre_masked)),
        "ndvi_post_mean": float(np.nanmean(ndvi_post_masked)),
        "dndvi_mean": float(np.nanmean(dndvi_masked)),
        "total_pixels": int(np.sum(mask)),
        "pixels_affected": int(np.sum(dndvi_masked < -0.05)),
        "pixels_severe": int(np.sum(dndvi_masked < -0.15)),
        "percent_affected": float(np.sum(dndvi_masked < -0.05) / np.sum(mask) * 100),
        "percent_severe": float(np.sum(dndvi_masked < -0.15) / np.sum(mask) * 100),
    }
    
    print(f"\n=== Results ===")
    print(f"NDVI pre:  {stats['ndvi_pre_mean']:.3f} → post: {stats['ndvi_post_mean']:.3f}")
    print(f"ΔNDVI:     {stats['dndvi_mean']:.3f}")
    print(f"Area affected (>0.05 loss): {stats['percent_affected']:.1f}%")
    print(f"Severe loss   (>0.15 loss): {stats['percent_severe']:.1f}%")
    
    # Save stats
    stats_path = os.path.join(DATA_DIR, f"planetscope_{SITE['key']}_stats.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nStats saved: {stats_path}")
    
    # Generate visualization
    print("\nGenerating NDVI change visualization...")
    
    # Normalize dNDVI for display (-0.3 to 0)
    dndvi_display = np.clip(dndvi, -0.3, 0)
    dndvi_display = np.where(mask, dndvi_display, np.nan)
    
    # Color map: green=no change, yellow=moderate loss, red=severe loss
    normalized = np.abs(dndvi_display) / 0.3  # 0 to 1
    normalized = np.nan_to_num(normalized, 0)
    
    # RGB: R=severity, G=1-severity, B=0
    rgb = np.zeros((*dndvi.shape, 3), dtype=np.uint8)
    rgb[..., 0] = (normalized * 255).astype(np.uint8)      # R
    rgb[..., 1] = ((1 - normalized) * 200).astype(np.uint8)  # G
    rgb[..., 2] = 0                                          # B
    
    # Where no data, dark gray
    rgb[~mask] = [30, 30, 30]
    
    img = Image.fromarray(rgb)
    png_path = os.path.join(DATA_DIR, f"planetscope_{SITE['key']}_ndvi_change.png")
    img.save(png_path)
    print(f"Visualization saved: {png_path}")
    
    print("\nDone. Copy planetscope_ndvi_change.png to ../images/ for video assembly.")


if __name__ == "__main__":
    main()
