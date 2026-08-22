"""Where did coherence collapse with nobody reporting it?

Absence of reports is not absence of damage. Reports come from places with
people, phone signal, and an agency that got there; the rest of the map is
silent for reasons that have nothing to do with the earthquake. Every earlier
test in this investigation used "random coherent land" as the undamaged
control, which quietly assumed the opposite -- and if damaged-but-unreported
ground sits inside that control, the contrast is diluted and a null result is
what you would expect even if the radar were working perfectly. Those nulls
were therefore uninformative rather than negative.

Turning the objection around makes it productive. If unreported ground can be
damaged, then a cluster of severe coherence loss with no report near it is a
CANDIDATE for unreported damage, and that is a prediction someone can go and
check.

THE HARD PART IS THAT COHERENCE LOSS HAS MANY CAUSES. Harvest, ploughing,
landslides unrelated to shaking, river movement, cloud-shadowed slopes, and
simple temporal decorrelation all reduce coherence, and none of them are
earthquake damage. Three filters are used against that:

  BASELINE-MATCHED PAIRS ONLY. Ascending f1148 and descending 163 both use a
  12-day same-mission co-event against a 12-day same-mission control, so
  ordinary decorrelation largely cancels in the difference. Path 61 is
  excluded -- its 18-day cross-mission pair decorrelates more everywhere, and
  that artefact already fooled one analysis here.

  AGREEMENT BETWEEN TWO INDEPENDENT TRACKS. A cluster must appear in BOTH
  geometries. Farming, a processing artefact, or one day's weather is unlikely
  to hit two different tracks with different dates the same way.

  EXCEED THE SCENE, NOT ZERO. A cluster must lose substantially more coherence
  than the same scene's own median, so the threshold adapts to how noisy each
  pair is.

What comes out is a ranked list of places to look at, not a damage map. The
honest label is "worth checking".

    conda run -n insardev-test python scripts/eq_unreported_hotspots.py
"""

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

REPO = os.path.expanduser("~/GitHub/rs-change-detection")
REPORTS = os.path.join(REPO, "data/eq_reports.geojson")
OUT = os.path.join(REPO, "output/coseismic")
EPI = (121.3517, -8.3101)

# Baseline-matched tracks only. See the header for why path 61 is excluded.
TRACKS = {
    "asc-f1148": ("flores-coseismic-2026-asc-f1148-prepost-d2",
                  "flores-coseismic-2026-asc-f1148-prepre-d2"),
    "desc163": ("flores-coseismic-2026-desc163-f620-prepost-d2",
                "flores-coseismic-2026-desc163-f620-prepre-d2"),
}


def load(d, name):
    import rioxarray  # noqa: F401
    import xarray as xr
    hits = glob.glob(os.path.join(OUT, d, f"*_{name}.tif"))
    if not hits:
        sys.exit(f"no {name} in {d}")
    da = xr.open_dataarray(hits[0], engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def drop_field(track, min_coh, coast_px):
    """Coherence drop, with the shoreline excluded.

    THE SHORELINE HAD TO BE ADDED AFTER THE FIRST RUN. Its four strongest
    "candidates for unreported damage" formed a tidy contiguous patch 19-20 km
    from the epicentre, closer to the source than any report -- and a terrain
    check put every one of them at 0 m elevation, 0 degrees slope, 100 m from
    the sea. Tide, surf and a water mask that is a pixel or two too generous
    produce total decorrelation at the coast in both tracks at once, which
    defeats the two-track agreement test completely: the artefact is in the
    same place on every pass.

    HyP3's water_mask marks open water but not the intertidal fringe, so the
    mask is dilated inland by a few pixels. That discards real coastal ground,
    which is a real cost, but coastal ground is where this method cannot tell
    damage from tide.
    """
    import xarray as xr
    from scipy import ndimage

    co_d, ct_d = TRACKS[track]
    co, ct, wat = xr.align(load(co_d, "corr"), load(ct_d, "corr"),
                           load(co_d, "water_mask"), join="inner")
    c1 = ct.values.astype("float64")
    c2 = co.values.astype("float64")
    land = wat.values > 0
    if coast_px > 0:
        inland = ndimage.binary_erosion(
            land, structure=np.ones((3, 3)), iterations=coast_px,
            border_value=0)
        lost = int(land.sum() - inland.sum())
        print(f"  {track}: dropped {lost:,} pixels within {coast_px} px "
              f"of water ({100*lost/max(1, land.sum()):.1f}% of land)")
        land = inland
    ok = np.isfinite(c1) & np.isfinite(c2) & land & (c1 >= min_coh)
    return np.where(ok, c1 - c2, np.nan), co


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.35,
                    help="the control pair must have been WELL correlated; a "
                         "drop from 0.2 to 0.1 is noise, from 0.7 to 0.2 is "
                         "not")
    ap.add_argument("--block-km", type=float, default=2.0,
                    help="aggregate to blocks so single noisy pixels cannot "
                         "become a hotspot")
    ap.add_argument("--quantile", type=float, default=0.98,
                    help="a block must be in this top fraction of drop in "
                         "BOTH tracks")
    ap.add_argument("--away-km", type=float, default=5.0,
                    help="distance from the nearest report to count as "
                         "unreported")
    ap.add_argument("--max-km", type=float, default=120.0)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--coast-px", type=int, default=10,
                    help="erode the land mask inland by this many 40 m "
                         "pixels; the shoreline decorrelates in every pair "
                         "and defeats the two-track agreement test")
    a = ap.parse_args()

    from pyproj import Transformer

    # Both tracks are reprojected onto a common coarse block grid in lon/lat,
    # because they are on different UTM footprints and comparing them pixel by
    # pixel would need a resampling step that smooths the very contrast being
    # looked for.
    step = a.block_km / 111.32
    grids = {}
    for t in TRACKS:
        drop, ref = drop_field(t, a.min_coh, a.coast_px)
        inv = Transformer.from_crs(ref.rio.crs, "EPSG:4326", always_xy=True)
        xs = ref[ref.dims[-1]].values
        ys = ref[ref.dims[-2]].values
        X, Y = np.meshgrid(xs, ys)
        m = np.isfinite(drop)
        lon, lat = inv.transform(X[m], Y[m])
        val = drop[m]
        gi = np.floor(lat / step).astype(np.int64)
        gj = np.floor(lon / step).astype(np.int64)
        key = gi * 1_000_000 + gj
        order = np.argsort(key)
        key, val = key[order], val[order]
        uniq, start = np.unique(key, return_index=True)
        med = np.array([np.median(val[s:e]) for s, e in
                        zip(start, list(start[1:]) + [len(val)])])
        cnt = np.diff(list(start) + [len(val)])
        keep = cnt >= 50            # a block needs real support
        grids[t] = dict(zip(uniq[keep], med[keep]))
        print(f"{t}: {int(m.sum()):,} pixels -> {int(keep.sum()):,} blocks "
              f"of {a.block_km:.0f} km, scene median drop "
              f"{np.median(val):+.4f}")

    shared = set(grids["asc-f1148"]) & set(grids["desc163"])
    print(f"\nblocks observed by both tracks: {len(shared):,}")
    if len(shared) < 50:
        sys.exit("too little shared ground to compare")

    thr = {}
    for t in TRACKS:
        vals = np.array([grids[t][k] for k in shared])
        thr[t] = float(np.quantile(vals, a.quantile))
        print(f"  {t}: top-{100*(1-a.quantile):.0f}% threshold "
              f"{thr[t]:+.4f} (median {np.median(vals):+.4f})")

    hot = [k for k in shared
           if grids["asc-f1148"][k] >= thr["asc-f1148"]
           and grids["desc163"][k] >= thr["desc163"]]
    exp = len(shared) * (1 - a.quantile) ** 2
    print(f"\nblocks in the top {100*(1-a.quantile):.0f}% of BOTH tracks: "
          f"{len(hot)}")
    print(f"  expected by chance if the tracks were independent: {exp:.1f}")
    if len(hot) == 0:
        print("\n  No block loses coherence in both geometries. Whatever the")
        print("  hotspots are in each track separately, they do not agree,")
        print("  which is what farming or per-pair artefacts look like.")
        return 0

    d = json.load(open(REPORTS))
    rep = []
    for f in d["features"]:
        c = (f.get("geometry") or {}).get("coordinates")
        if c:
            rep.append((float(c[0]), float(c[1])))
    rep = np.array(rep)

    rows = []
    for k in hot:
        gi, gj = divmod(k, 1_000_000)
        lat = (gi + 0.5) * step
        lon = (gj + 0.5) * step
        dl = (rep[:, 0] - lon) * 111.32 * math.cos(math.radians(lat))
        dm = (rep[:, 1] - lat) * 111.32
        near = float(np.min(np.hypot(dl, dm)))
        r = math.hypot((lon - EPI[0]) * 111.32 * math.cos(math.radians(lat)),
                       (lat - EPI[1]) * 111.32)
        if r > a.max_km:
            continue
        rows.append((near, r, lat, lon,
                     grids["asc-f1148"][k], grids["desc163"][k]))

    unrep = sorted((r for r in rows if r[0] >= a.away_km), reverse=True,
                   key=lambda r: (r[4] + r[5]))
    near = [r for r in rows if r[0] < a.away_km]
    print(f"  within {a.max_km:.0f} km of the epicentre: {len(rows)}")
    print(f"    {len(near)} already have a report within {a.away_km:.0f} km")
    print(f"    {len(unrep)} do NOT -- candidates for unreported damage")

    # Is "9 of 11 already reported" impressive or trivial? It depends entirely
    # on how many ORDINARY blocks sit within the same distance of a report. If
    # most of the map is near a report, the hotspots being near reports means
    # nothing. This is the same presence-background logic as the AUC test,
    # applied to blocks instead of points.
    base = []
    for k in shared:
        gi, gj = divmod(k, 1_000_000)
        lat = (gi + 0.5) * step
        lon = (gj + 0.5) * step
        r = math.hypot((lon - EPI[0]) * 111.32 * math.cos(math.radians(lat)),
                       (lat - EPI[1]) * 111.32)
        if r > a.max_km:
            continue
        dl = (rep[:, 0] - lon) * 111.32 * math.cos(math.radians(lat))
        dm = (rep[:, 1] - lat) * 111.32
        base.append(float(np.min(np.hypot(dl, dm))))
    base = np.array(base)
    if len(base):
        frac_bg = float((base < a.away_km).mean())
        frac_hot = len(near) / max(1, len(rows))
        print(f"\n  blocks within {a.away_km:.0f} km of a report:")
        print(f"    among the {len(rows)} hotspots      {frac_hot*100:.0f}%")
        print(f"    among all {len(base)} shared blocks {frac_bg*100:.0f}%")
        if frac_bg > 0:
            print(f"    enrichment {frac_hot/frac_bg:.1f}x")
        if frac_hot > frac_bg + 0.15:
            print("    Hotspots land near reports more often than ordinary")
            print("    ground does, so the two-track coherence collapse is")
            print("    picking out something people also noticed.")
        else:
            print("    No enrichment. The hotspots are no closer to reports")
            print("    than ordinary ground, so this is not finding damage.")

    if unrep:
        print(f"\n  {'lat':>9}{'lon':>10}{'km to epi':>11}"
              f"{'km to report':>14}{'asc drop':>10}{'desc drop':>11}")
        for near_km, r, lat, lon, da_, dd in unrep[:a.top]:
            print(f"  {lat:>9.4f}{lon:>10.4f}{r:>11.0f}{near_km:>14.1f}"
                  f"{da_:>10.3f}{dd:>11.3f}")

    print()
    print("  These are places to LOOK AT, not damage. Coherence falls for")
    print("  many reasons and two tracks can agree on a landslide, a harvest")
    print("  or a river as readily as on a collapsed village. What the")
    print("  agreement rules out is a one-pair artefact.")
    print("  The useful next step is not more radar -- it is asking whether")
    print("  anyone has been to these coordinates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
