#!/usr/bin/env python3
"""How much of each of the four Ketapang oil-palm concessions overlaps a
wood-fibre (HTI, pulpwood) concession, and how much of its 2026 burn?

Prompted by PlanetScope: PT AM's "unplanted" window showed dark closed
canopy in crisp rectangular blocks with a harvest cycle, which is a planted
tree crop the palm map does not call palm. GFW's "Indonesia wood fiber
concessions" layer (Ministry of Forestry, 2010; updated 2017) places most of
PT AM inside pulpwood permits. Both layers are a decade or more old: an
overlap says two permits were drawn over the same ground, not which one is
in force today.

Needs landcover_burned.tif from ketapang_fire_origin.py.

    conda run -n base python scripts/ketapang_permit_overlap.py
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import CONC, FOUR, OUT  # noqa: E402

HTI_URL = ("https://gis-gfw.wri.org/arcgis/rest/services/country_data/asia/"
           "MapServer/0/query")


def main():
    import numpy as np
    import requests
    import rasterio
    import geopandas as gpd
    from rasterio import features
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    with rasterio.open(os.path.join(OUT, "landcover_burned.tif")) as ds:
        lc, burned, tr, b = ds.read(1), ds.read(2).astype(bool), ds.transform, ds.bounds
    r = requests.get(HTI_URL, params={
        "where": "1=1", "outFields": "*", "f": "json", "outSR": 4326,
        "inSR": 4326, "geometry": f"{b.left},{b.bottom},{b.right},{b.top}",
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects"}, timeout=120)
    r.raise_for_status()
    rows = []
    for f in r.json()["features"]:
        rings = [[tuple(p[:2]) for p in ring] for ring in f["geometry"]["rings"]]
        g = unary_union([Polygon(x).buffer(0) for x in rings if len(x) >= 4])
        at = f["attributes"]
        rows.append({"name": at.get("name"), "group": at.get("group_comp"),
                     "source": at.get("source"), "geometry": g})
    hti = gpd.GeoDataFrame(rows, crs=4326)
    hti.to_file(os.path.join(OUT, "hti_wood_fibre_aoi.gpkg"))

    hm = features.rasterize([(g, 1) for g in hti.geometry],
                            out_shape=lc.shape, transform=tr) > 0
    lat = tr.f + (np.arange(lc.shape[0]) + 0.5) * tr.e
    pha = np.broadcast_to((111320 * tr.a) * (110574 * -tr.e)
                          * np.cos(np.radians(lat))[:, None] / 1e4, lc.shape)
    land = lc < 255
    conc = gpd.read_file(CONC).to_crs(4326)
    out = {}
    for acr, name in FOUR.items():
        g = conc[conc.company.str.contains(name, na=False)].geometry.iloc[0].buffer(0)
        ins = (features.rasterize([(g, 1)], out_shape=lc.shape, transform=tr) > 0) & land
        ov = ins & hm
        who = hti[hti.intersects(g)].copy()
        who["overlap_ha"] = who.geometry.intersection(g).to_crs(32749).area / 1e4
        who = who[who.overlap_ha > 100].sort_values("overlap_ha", ascending=False)
        out[acr] = {
            "area_ha": float(pha[ins].sum()),
            "in_hti_ha": float(pha[ov].sum()),
            "burned_ha": float(pha[ins & burned].sum()),
            "burned_in_hti_ha": float(pha[ov & burned].sum()),
            "hti_permits": [{"name": w["name"], "group": w["group"],
                             "overlap_ha": float(w.overlap_ha)}
                            for _, w in who.iterrows()],
        }
        o = out[acr]
        print(f"{acr}: {o['in_hti_ha']:,.0f} of {o['area_ha']:,.0f} ha in HTI; "
              f"burned there {o['burned_in_hti_ha']:,.0f} of {o['burned_ha']:,.0f} ha")
    with open(os.path.join(OUT, "permit_overlap.json"), "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
