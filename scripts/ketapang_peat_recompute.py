#!/usr/bin/env python3
"""Fire-on-peat statistics for the four Ketapang concessions, recomputed
under three peat maps, because the team's old map (Kalimantan_3857.tif)
scored 36% accuracy at field points and calls 92% of them peat:

  old     Kalimantan_3857.tif (as used so far in the analysis and the film)
  bbsdlp  BBSDLP / Ministry of Agriculture peat polygons (GFW layer 10)
  rf      final field-weighted random forest (peat_rf_gee.py --stage final/map),
          peat = probability >= calibrated threshold; also the
          probability-weighted (expected) hectares as a soft estimate

Reads output/fire/ketapang_origin/landcover_burned.tif (band 1 class,
band 2 burned) so nothing upstream is re-run.

    conda run -n base python scripts/ketapang_peat_recompute.py
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import (CONC, FOUR, PEAT, PEAT_OWN, RING_KM, GRID,  # noqa: E402
                                  own_peat_on_grid, _DATA_ROOT)

ORIGIN = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin")
RF_DIR = os.path.join(_DATA_ROOT, "output", "peat_rf")


def main():
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio import features
    from rasterio.warp import reproject, Resampling
    from scipy import ndimage

    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as ds:
        lc, burned = ds.read(1), ds.read(2).astype(bool)
        tr, shape = ds.transform, (ds.height, ds.width)
        b = ds.bounds
    bbox = (b.left, b.bottom, b.right, b.top)
    land = lc != 255
    lat = tr.f + (np.arange(shape[0]) + 0.5) * tr.e
    pha = np.broadcast_to((111320.0 * GRID) * (110574.0 * GRID)
                          * np.cos(np.radians(lat))[:, None] / 1e4, shape)

    rep = json.load(open(os.path.join(RF_DIR, "final_report.json")))
    thr = rep["threshold"]
    prob = np.zeros(shape, np.float32)
    with rasterio.open(os.path.join(RF_DIR, "peat_prob_ketapang_25m.tif")) as src:
        reproject(rasterio.band(src, 1), prob, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=tr, dst_crs="EPSG:4326", resampling=Resampling.nearest)
    prob = np.clip(prob / 1000.0, 0, 1) * land

    pg = gpd.read_file(PEAT)
    peat = {
        "old": own_peat_on_grid(PEAT_OWN, bbox, tr, shape) & land,
        "bbsdlp": (features.rasterize([(g, 1) for g in pg.geometry if g is not None and not g.is_empty],
                                      out_shape=shape, transform=tr, dtype="uint8") > 0) & land,
        "rf": (prob >= thr) & land,
    }

    def h(m, w=None):
        return float((pha * (m if w is None else m * w)).sum())

    conc = gpd.read_file(CONC).to_crs(4326)
    conc["geometry"] = conc.geometry.make_valid()
    any_conc = np.zeros(shape, bool)
    for g in conc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]].geometry:
        any_conc |= features.rasterize([(g, 1)], out_shape=shape, transform=tr, dtype="uint8") > 0

    out = {"threshold": thr, "aoi_land": {k: h(v) for k, v in peat.items()}}
    out["aoi_land"]["rf_expected"] = h(land, prob)
    out["aoi_land"]["iou"] = {f"{x}_vs_{y}": h(peat[x] & peat[y]) / max(h(peat[x] | peat[y]), 1e-9)
                              for x, y in (("rf", "bbsdlp"), ("rf", "old"), ("old", "bbsdlp"))}
    print(f"AOI land peat ha: old {out['aoi_land']['old']:,.0f}  bbsdlp {out['aoi_land']['bbsdlp']:,.0f}  "
          f"rf {out['aoi_land']['rf']:,.0f}  rf-expected {out['aoi_land']['rf_expected']:,.0f}")
    print("  IoU:", {k: round(v, 2) for k, v in out["aoi_land"]["iou"].items()})

    print(f"\n{'':6}{'map':8}{'peat ha':>10}{'peat %':>8}{'burn ha':>9}{'on peat':>9}"
          f"{'share':>7}{'%peat brn':>10}{'%min brn':>9}{'ring %peat':>11}{'ring %min':>10}")
    for acr, name in FOUR.items():
        s = conc[conc.company.str.contains(name, case=False, na=False)].iloc[0]
        inside = (features.rasterize([(s.geometry, 1)], out_shape=shape, transform=tr,
                                     dtype="uint8") > 0) & land
        dist = ndimage.distance_transform_edt(~inside) * 25 / 1000
        ring = (dist > 0) & (dist <= RING_KM) & land & ~any_conc
        ps = {}
        for k, pm in peat.items():
            ip, im, rp, rm = inside & pm, inside & ~pm, ring & pm, ring & ~pm
            ps[k] = {"peat_ha": h(ip), "peat_share_of_concession": h(ip) / h(inside),
                     "burned_ha": h(inside & burned), "burned_on_peat_ha": h(ip & burned),
                     "burn_share_on_peat": h(ip & burned) / max(h(inside & burned), 1e-9),
                     "burned_pct_of_peat": 100 * h(ip & burned) / max(h(ip), 1e-9),
                     "burned_pct_of_mineral": 100 * h(im & burned) / max(h(im), 1e-9),
                     "ring_burned_pct_of_peat": 100 * h(rp & burned) / max(h(rp), 1e-9),
                     "ring_burned_pct_of_mineral": 100 * h(rm & burned) / max(h(rm), 1e-9)}
            r = ps[k]
            print(f"{acr:6}{k:8}{r['peat_ha']:>10,.0f}{100 * r['peat_share_of_concession']:>7.0f}%"
                  f"{r['burned_ha']:>9,.0f}{r['burned_on_peat_ha']:>9,.0f}{100 * r['burn_share_on_peat']:>6.0f}%"
                  f"{r['burned_pct_of_peat']:>9.1f}%{r['burned_pct_of_mineral']:>8.1f}%"
                  f"{r['ring_burned_pct_of_peat']:>10.1f}%{r['ring_burned_pct_of_mineral']:>9.1f}%")
        ps["rf_expected"] = {"peat_ha": h(inside, prob), "burned_on_peat_ha": h(inside & burned, prob)}
        out[acr] = ps
    p = os.path.join(ORIGIN, "peat_stats_three_maps.json")
    json.dump(out, open(p, "w"), indent=2)
    print(f"\nSaved: {p}")


if __name__ == "__main__":
    main()
