#!/usr/bin/env python3
"""Sulawesi-wide check of the team's RF peat map (data/peat/Sulawesi.tif; 50 m, EPSG:3857; 2 = peat,
1 = non-peat land, 0 = outside) against the Greifswald Global Peatland Map 2.0, with SRTM elevation as a
plausibility check (Sulawesi peat is lowland). BBSDLP is not used: its GFW layer has no Sulawesi polygons
(the 2011 atlas maps Sumatra, Kalimantan and Papua only).

Common grid: 0.009 deg (~1 km), EPSG:4326, over the Sulawesi.tif extent. RF -> % of each cell called peat
and % land (average of 0/100 masks); a cell is RF peat when >= 50% of it is. GPM 2.0 and SRTM from Earth
Engine (mode / mean at 1 km). Tinondo (PUPR swamp irrigation plots) is reported as a known-peat check.

Writes output/peat_sulawesi/compare.json and the 1 km layers (.tif).

    python scripts/sulawesi_peat_compare.py
"""
import json
import os
import sys
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
RF = os.path.join(_REPO_ROOT, "data", "peat", "Sulawesi.tif")
OUTD = os.path.join(_REPO_ROOT, "output", "peat_sulawesi")
STEP = 0.009
TINONDO = ("/Users/firmanhadi/Works/PUPR/data/shapefile-irigasi/01-BALAI WILAYAH SUNGAI/"
           "0117-BALAI WILAYAH SUNGAI SULAWESI IV/1170010-DIR. Tinondo-petak.shp")


def ee_layer(ee, img, x0, y1, w, h, name, reducer):
    import rasterio
    region = ee.Geometry.Rectangle([x0, y1 - h * STEP, x0 + w * STEP, y1], "EPSG:4326", False)
    im = img.reduceResolution(reducer, maxPixels=4096) if reducer is not None else img
    url = im.getDownloadURL({"region": region, "crs": "EPSG:4326", "dimensions": f"{w}x{h}",
                             "format": "GEO_TIFF"})
    p = os.path.join(OUTD, f"{name}_1km.tif")
    urllib.request.urlretrieve(url, p)
    with rasterio.open(p) as ds:
        a = ds.read(1)
    assert a.shape == (h, w), (name, a.shape, (h, w))
    return a


def main():
    import numpy as np
    import rasterio
    from rasterio.warp import Resampling, reproject, transform_bounds
    os.makedirs(OUTD, exist_ok=True)
    with rasterio.open(RF) as ds:
        b = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
        x0, y1 = round(b[0], 3), round(b[3], 3)
        w, h = int(np.ceil((b[2] - x0) / STEP)), int(np.ceil((y1 - b[1]) / STEP))
        dst_tr = rasterio.Affine(STEP, 0, x0, 0, -STEP, y1)
        a = ds.read(1)
        out = {}
        for key, src in (("rf_peat_pct", ((a == 2) * 100).astype(np.uint8)), ("land_pct", ((a > 0) * 100).astype(np.uint8))):
            d = np.zeros((h, w), np.uint8)
            reproject(src, d, src_transform=ds.transform, src_crs=ds.crs, dst_transform=dst_tr,
                      dst_crs="EPSG:4326", resampling=Resampling.average)
            out[key] = d
        del a
    rfp, land = out["rf_peat_pct"], out["land_pct"]

    from earthchange.gee_utils import initialize_ee
    import ee
    initialize_ee()
    gpm = ee_layer(ee, ee.Image("projects/sat-io/open-datasets/GLOBAL-PEATLAND-DATABASE").unmask(0).toInt16(),
                   x0, y1, w, h, "gpm", None)
    dem = ee_layer(ee, ee.Image("USGS/SRTMGL1_003").toInt16(), x0, y1, w, h, "srtm", None)

    L = land >= 50
    rf = (rfp >= 50) & L
    gp = (gpm >= 1) & L
    km2 = (STEP * 111.32) ** 2                       # equatorial approximation, ~1.0 km2
    n = L.sum()
    po = ((rf & gp).sum() + (~rf & ~gp & L).sum()) / n
    pe = (rf.sum() * gp.sum() + (n - rf.sum()) * (n - gp.sum())) / n ** 2
    res = {"grid_deg": STEP, "land_cells": int(n),
           "rf_peat_km2": float(rf.sum() * km2), "gpm_peat_km2": float(gp.sum() * km2),
           "both_km2": float((rf & gp).sum() * km2),
           "rf_peat_confirmed_by_gpm_pct": 100 * float((rf & gp).sum() / max(rf.sum(), 1)),
           "gpm_peat_found_by_rf_pct": 100 * float((rf & gp).sum() / max(gp.sum(), 1)),
           "kappa": float((po - pe) / (1 - pe)),
           "gpm_classes_on_land": {int(k): int(v) for k, v in zip(*np.unique(gpm[L], return_counts=True))}}
    for name, m in (("rf_peat", rf), ("gpm_peat", gp), ("rf_only", rf & ~gp), ("land", L)):
        e = dem[m]
        res[f"elev_{name}"] = {"median_m": float(np.median(e)) if e.size else None,
                               "share_above_100m_pct": 100 * float((e > 100).mean()) if e.size else None,
                               "share_above_300m_pct": 100 * float((e > 300).mean()) if e.size else None}
    # Tinondo
    try:
        import geopandas as gpd
        from rasterio.features import geometry_mask
        t = gpd.read_file(TINONDO).to_crs(4326)
        tm = ~geometry_mask(list(t.geometry.make_valid()), (h, w), dst_tr, all_touched=True)
        res["tinondo_cells"] = int(tm.sum())
        res["tinondo_rf_peat_pct"] = 100 * float(rf[tm].mean())
        res["tinondo_gpm_peat_pct"] = 100 * float(gp[tm].mean())
    except Exception as e:                                  # noqa: BLE001
        res["tinondo_error"] = str(e)
    for name, arr in (("rf_peat_pct", rfp), ("land_pct", land)):
        with rasterio.open(os.path.join(OUTD, f"{name}_1km.tif"), "w", driver="GTiff", height=h, width=w, count=1,
                           dtype="uint8", crs="EPSG:4326", transform=dst_tr, compress="deflate") as o:
            o.write(arr, 1)
    json.dump(res, open(os.path.join(OUTD, "compare.json"), "w"), indent=1)
    for k, v in res.items():
        print(f"  {k}: {v}")
    print(f"Saved: {OUTD}")


if __name__ == "__main__":
    main()
