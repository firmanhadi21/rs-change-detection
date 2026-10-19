"""Burnt land in West Sumatra that later became oil palm, by land status.

The question behind this is not whether burnt land becomes plantation --
on land released for other use (APL) that is lawful and unremarkable. It
is whether it happens INSIDE THE FOREST ESTATE, where it is not. That is
what the Kompas report of 19 Oct 2026 describes in Dharmasraya, and the
record can be asked whether the pattern is there across two decades.

METHOD. Three layers on one 200 m grid:

  first burn year   MCD64A1, 2001-2018, earliest year each cell burnt
  oil palm          Descals et al. (BIOPAMA/GlobalOilPalm/v1_2), 10 m,
                    classes 1 industrial and 2 smallholder
  planting year     the same product's planting_year band
  land status       KLHK Penunjukan Kawasan Hutan 1:250k, FUNGSI_HTN

A cell counts as burn-then-palm when it burnt in year Y and carries palm
whose planting_year is strictly greater than Y. Strictly, so palm that
was already standing when the fire went through is not read as a
consequence of it.

WHY 2018 AND NOT LATER. Planting is observed to 2021, so a burn in 2018
has three years to show a plantation and a burn in 2001 has twenty. Later
burns are excluded rather than counted as evidence that fire does not
lead to planting.

FOUR THINGS THIS DOES NOT ESTABLISH, and they matter:

  1. Intent. An association over observational data does not separate
     "burnt in order to plant" from "cleared by burning on land already
     destined for planting" from "both follow from being flat and near a
     road". The lag histogram bears on this but does not settle it.
  2. Illegality. Forest-estate boundaries move, releases and swaps
     happen, and a cell inside today's HPT may have been APL when it was
     planted. Only the gazette for that parcel settles that.
  3. Small clearing. MCD64A1 is 500 m and cannot see a burn of a few
     hectares, which is the scale the Dharmasraya case operates at and
     probably most of the pathway. Everything here is large burns only.
  4. Which fire. A cell that burnt more than once is credited to its
     first burn, so a later re-burn before planting is not visible.

    conda run -n base python scripts/sumbar_burn_palm_sites.py
"""

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
OUT = os.path.expanduser(_DATA_ROOT + "/output/fire/sumbar")
STACK = os.path.join(OUT, "sumbar_burn_palm_200m.tif")
FOREST = os.path.expanduser(_DATA_ROOT + "/data/forest.gpkg")
LAYER = "pnunjukkwshutan_ar_250k"

# Inside the forest estate, conversion to plantation needs a release.
ESTATE = {"HUTAN PRODUKSI", "HUTAN PRODUKSI TERBATAS",
          "HUTAN PRODUKSI KONVERSI", "HUTAN LINDUNG"}
CONSERVATION = {"CAGAR ALAM", "TAMAN NASIONAL", "SUAKA MARGASATWA",
                "TAMAN HUTAN RAYA", "HUTAN WISATA", "TAMAN BURU",
                "KSA/KPA", "HUTAN SUAKA ALAM DAN MARGASATWA",
                "TAMAN WISATA ALAM", "CAGAR ALAM LAUT",
                "SUAKA MARGASATWA LAUT", "TAMAN NASIONAL LAUT",
                "HUTAN SUAKA ALAM LAUT", "HUTAN WISATA LAUT"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=STACK)
    ap.add_argument("--forest", default=FOREST)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--min-ha", type=float, default=16.0,
                    help="smallest contiguous site to list (4 cells)")
    a = ap.parse_args()

    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.features import rasterize, shapes

    if not os.path.exists(a.stack):
        raise SystemExit(f"missing {a.stack}\nExport it first (see the "
                         f"scratchpad exporter in the commit message).")

    with rasterio.open(a.stack) as s:
        burn, pclass, pyear = s.read()
        tr, crs, shape = s.transform, s.crs, (s.height, s.width)
        # Cell area in hectares, at this latitude. Degrees are not metres;
        # computing it from the transform and a cos(lat) factor keeps the
        # totals honest without reprojecting 4.5M cells.
        lat = s.bounds.bottom + (s.bounds.top - s.bounds.bottom) / 2
        dy = abs(tr.e) * 111_320.0
        dx = abs(tr.a) * 111_320.0 * np.cos(np.radians(lat))
        cell_ha = dx * dy / 1e4
    print(f"grid {shape[1]}x{shape[0]}, cell ~{cell_ha:.2f} ha")

    # --- land status on the same grid --------------------------------
    print("rasterising KLHK ...")
    with rasterio.open(a.stack) as s:
        bounds = s.bounds
    kw = gpd.read_file(a.forest, layer=LAYER, bbox=tuple(bounds))
    kw["geometry"] = kw.geometry.force_2d()
    kw["FUNGSI_HTN"] = kw.FUNGSI_HTN.fillna("").str.strip().str.upper()
    codes, names = {}, []
    for i, n in enumerate(sorted(kw.FUNGSI_HTN.unique()), start=1):
        codes[n] = i
        names.append(n)
    status = rasterize(
        ((g, codes[n]) for g, n in zip(kw.geometry, kw.FUNGSI_HTN)),
        out_shape=shape, transform=tr, fill=0, dtype="int32")
    print(f"  {len(kw)} polygons, {len(names)} designations")

    # --- the test -----------------------------------------------------
    is_palm = np.isin(pclass, (1, 2))
    burnt = burn > 0
    # planting_year is only meaningful where the map says palm
    after = is_palm & (pyear > 0) & (pyear > burn)
    btp = burnt & after

    def ha(m):
        return float(m.sum()) * cell_ha

    # No province total is printed. The burn and palm bands are clipped
    # to West Sumatra at export, so everything below is the province --
    # but the KLHK layer is read by bounding box and spills into Jambi and
    # Riau, so any "total land" computed here would be of the box, not the
    # province. The masks below all require `burnt`, which is clipped, so
    # they are unaffected; a headline total would not have been.
    print(f"\nWest Sumatra, 200 m grid")
    print(f"  oil palm            {ha(is_palm):>12,.0f} ha")
    print(f"  burnt 2001-2018     {ha(burnt):>12,.0f} ha")
    print(f"  burnt, then planted {ha(btp):>12,.0f} ha"
          f"   ({100*ha(btp)/max(ha(burnt), 1):.1f}% of burnt)")

    # --- by land status ----------------------------------------------
    print(f"\n{'designation':<34}{'burnt ha':>10}{'then palm':>11}"
          f"{'share':>8}")
    rows = []
    for n in names:
        m = status == codes[n]
        b, p = ha(burnt & m), ha(btp & m)
        if b < cell_ha:
            continue
        rows.append({"status": n, "burnt_ha": b, "then_palm_ha": p,
                     "share": p / b if b else 0.0})
    for r in sorted(rows, key=lambda r: -r["then_palm_ha"]):
        print(f"  {r['status'][:31]:<32}{r['burnt_ha']:>10,.0f}"
              f"{r['then_palm_ha']:>11,.0f}{100*r['share']:>7.1f}%")
    out_est = status == 0
    b, p = ha(burnt & out_est), ha(btp & out_est)
    print(f"  {'(outside any kawasan polygon)':<32}{b:>10,.0f}"
          f"{p:>11,.0f}{100*p/max(b,1):>7.1f}%")

    est_mask = np.isin(status, [codes[n] for n in ESTATE if n in codes])
    con_mask = np.isin(status, [codes[n] for n in CONSERVATION
                                if n in codes])
    print(f"\n  INSIDE the forest estate (HP/HPT/HPK/HL)")
    print(f"    burnt {ha(burnt & est_mask):,.0f} ha -> "
          f"{ha(btp & est_mask):,.0f} ha now palm planted after the fire")
    print(f"  INSIDE conservation areas")
    print(f"    burnt {ha(burnt & con_mask):,.0f} ha -> "
          f"{ha(btp & con_mask):,.0f} ha now palm planted after the fire")

    # --- how long after the fire -------------------------------------
    lag = (pyear - burn)[btp]
    lag_hist = []
    if lag.size:
        print(f"\nyears from fire to planting (n={lag.size:,} cells)")
        print(f"  median {np.median(lag):.0f}   mean {lag.mean():.1f}")
        hist, edges = np.histogram(lag, bins=[1, 2, 3, 4, 6, 9, 13, 21])
        for i, c in enumerate(hist):
            lo, hi = edges[i], edges[i + 1]
            bar = "#" * int(40 * c / max(hist.max(), 1))
            rng = f"{lo}" if hi - lo == 1 else f"{lo}–{hi-1}"
            lag_hist.append([rng, int(c)])
            print(f"  {rng:>6} yr {c:>7,}  {bar}")

    # --- named sites inside the estate -------------------------------
    print(f"\nlargest burn-then-palm sites inside the forest estate")
    sites = []
    m = (btp & est_mask).astype("uint8")
    for geom, val in shapes(m, mask=m.astype(bool), transform=tr):
        if val != 1:
            continue
        from shapely.geometry import shape as shp
        g = shp(geom)
        n_cells = g.area / (abs(tr.a) * abs(tr.e))
        area = n_cells * cell_ha
        if area < a.min_ha:
            continue
        c = g.centroid
        r, cc = rasterio.transform.rowcol(tr, c.x, c.y)
        r = min(max(r, 0), shape[0] - 1); cc = min(max(cc, 0), shape[1] - 1)
        sites.append({"lon": round(c.x, 4), "lat": round(c.y, 4),
                      "ha": round(area, 1),
                      "burn_year": int(burn[r, cc]),
                      "palm_year": int(pyear[r, cc]),
                      "status": names[status[r, cc] - 1]
                      if status[r, cc] else "?"})
    sites.sort(key=lambda s: -s["ha"])
    print(f"  {len(sites)} sites of {a.min_ha:.0f} ha or more")
    print(f"  {'lon':>10}{'lat':>10}{'ha':>8}{'burnt':>7}{'planted':>9}"
          f"  status")
    for s_ in sites[:20]:
        print(f"  {s_['lon']:>10.4f}{s_['lat']:>10.4f}{s_['ha']:>8.0f}"
              f"{s_['burn_year']:>7}{s_['palm_year']:>9}  {s_['status']}")

    # A classified raster for the map page: 1 where planting was
    # permitted (APL/HPK), 2 where it was not (HP/HPT/HL/conservation).
    # Written here rather than recomputed in the pages script, so the map
    # and the bar chart cannot disagree about the same cell.
    lawful_names = {"AREA PENGGUNAAN LAIN", "HUTAN PRODUKSI KONVERSI"}
    lawful = np.isin(status, [codes[n] for n in lawful_names
                              if n in codes])
    cls = np.zeros(status.shape, dtype="uint8")
    cls[btp & lawful] = 1
    cls[btp & ~lawful] = 2
    tif = os.path.join(a.out, "btp_class.tif")
    with rasterio.open(a.stack) as s:
        prof = s.profile
    prof.update(count=1, dtype="uint8", compress="deflate", nodata=0)
    with rasterio.open(tif, "w", **prof) as d:
        d.write(cls, 1)
    print(f"\nwrote {tif}  "
          f"({int((cls == 1).sum()):,} lawful, "
          f"{int((cls == 2).sum()):,} restricted cells)")

    dest = os.path.join(a.out, "burn_palm_sites.json")
    with open(dest, "w") as f:
        json.dump({"cell_ha": cell_ha, "by_status": rows,
                   "min_ha": a.min_ha,
                   "total_burnt_ha": ha(burnt),
                   "total_then_palm_ha": ha(btp),
                   "palm_any_ha": ha(is_palm),
                   "lag_hist": lag_hist,
                   "estate_burnt_ha": ha(burnt & est_mask),
                   "estate_then_palm_ha": ha(btp & est_mask),
                   "conservation_burnt_ha": ha(burnt & con_mask),
                   "conservation_then_palm_ha": ha(btp & con_mask),
                   "lag_median": float(np.median(lag)) if lag.size else None,
                   "sites": sites}, f, indent=1)
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
