"""The coherence-damage test on ONE set of reports, across all three tracks.

Three tracks have now been tested and they disagree:

    ascending f1148   severe vs light   p = 0.0035   (n = 27 vs 22)
    descending 61     severe vs light   p = 0.043    (n = 32 vs 13)
    descending 163    severe vs light   p = 0.98     (n = 11 vs 10, REVERSED)

Each test used whatever reports happened to fall inside that track's
footprint, so the three used different reports over different ground. A
disagreement could therefore be geography -- different villages, different
terrain, different shaking -- rather than anything about the radar. This was
named as a confound in docs/desc163_predictions.md before path 163 was
processed, and now that the tracks disagree it has to be settled rather than
argued about.

Restricting every track to the reports that all three observe removes
geography entirely: the same villages, judged three times by three
interferogram pairs.

The cost is sample size, and it may well be fatal. Path 163 contributed only
107 reports with coherent data on its own; the three-way intersection will be
smaller. This script therefore reports the achievable n FIRST and refuses to
present a p-value it cannot support, because an underpowered null looks
exactly like a real null and must not be mistaken for one.

    conda run -n insardev-test python scripts/eq_reports_common.py
"""

import argparse
import glob
import json
import os
import sys

import numpy as np


# Repo root from THIS file's location, never from the
# home directory: two clones of this repository exist on
# this machine and a hardcoded ~ path wrote to whichever
# one was not being used.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = _REPO_ROOT
REPORTS = os.path.join(REPO, "data/eq_reports.geojson")
OUT = os.path.join(REPO, "output/coseismic")

TRACKS = {
    "asc-f1148": ("flores-coseismic-2026-asc-f1148-prepost-d2",
                  "flores-coseismic-2026-asc-f1148-prepre-d2"),
    "desc61": ("flores-coseismic-2026-desc61-f621-prepost-d2",
               "flores-coseismic-2026-desc61-f621-prepre-d2"),
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


def drops_for(track, lonlat, min_coh, r):
    """Coherence drop at each report location, NaN where not observable."""
    import xarray as xr
    from pyproj import Transformer

    co_d, ct_d = TRACKS[track]
    co, ct, wat = xr.align(load(co_d, "corr"), load(ct_d, "corr"),
                           load(co_d, "water_mask"), join="inner")
    c1 = ct.values.astype("float64")
    c2 = co.values.astype("float64")
    both = np.isfinite(c1) & np.isfinite(c2) & (wat.values > 0) \
        & (c1 >= min_coh)
    drop = np.where(both, c1 - c2, np.nan)

    xs = co[co.dims[-1]].values
    ys = co[co.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", co.rio.crs, always_xy=True)

    out = np.full(len(lonlat), np.nan)
    for k, (lon, lat) in enumerate(lonlat):
        x, y = fwd.transform(lon, lat)
        if not (xs.min() <= x <= xs.max() and ys.min() <= y <= ys.max()):
            continue
        iy = int(np.argmin(np.abs(ys - y)))
        ix = int(np.argmin(np.abs(xs - x)))
        w = drop[max(0, iy-r):iy+r+1, max(0, ix-r):ix+r+1]
        if np.isfinite(w).any():
            out[k] = np.nanmedian(w)
    return out, float(np.nanmedian(drop))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.2)
    ap.add_argument("--radius-px", type=int, default=3)
    ap.add_argument("--min-n", type=int, default=8,
                    help="minimum per group before a p-value is reported at "
                         "all")
    a = ap.parse_args()

    d = json.load(open(REPORTS))
    lonlat, lvls = [], []
    for f in d["features"]:
        c = (f.get("geometry") or {}).get("coordinates")
        if not c:
            continue
        lonlat.append((float(c[0]), float(c[1])))
        lvls.append(f["properties"].get("damage_level"))
    lvls = np.array([l if isinstance(l, (int, float)) else -99 for l in lvls])
    print(f"{len(lonlat)} reports with coordinates")

    per, scene = {}, {}
    for t in TRACKS:
        per[t], scene[t] = drops_for(t, lonlat, a.min_coh, a.radius_px)
        print(f"  {t:>10}: {int(np.isfinite(per[t]).sum()):>4} reports "
              f"observable   scene-wide median drop {scene[t]:+.4f}")

    # Pairwise before three-way. If the three-way intersection is empty it
    # matters enormously WHY: two tracks sharing plenty of reports and a third
    # sharing none is a different situation from three mutually disjoint
    # footprints, and only the second means the tests were never comparable.
    names = list(TRACKS)
    print(f"\n  {'':>12}" + "".join(f"{t:>12}" for t in names))
    for t1 in names:
        row = f"  {t1:>12}"
        for t2 in names:
            n = int((np.isfinite(per[t1]) & np.isfinite(per[t2])).sum())
            row += f"{n:>12}"
        print(row)
    cls = lvls >= 0
    print(f"\n  same, counting only the {int(cls.sum())} CLASSIFIED reports:")
    print(f"  {'':>12}" + "".join(f"{t:>12}" for t in names))
    for t1 in names:
        row = f"  {t1:>12}"
        for t2 in names:
            n = int((np.isfinite(per[t1]) & np.isfinite(per[t2])
                     & cls).sum())
            row += f"{n:>12}"
        print(row)

    common = np.all([np.isfinite(per[t]) for t in TRACKS], axis=0)
    n_common = int(common.sum())
    print(f"\nobserved by ALL three tracks: {n_common} reports")

    sev = common & (lvls >= 3)
    light = common & (lvls >= 0) & (lvls <= 2)
    print(f"  severe (>=3): {int(sev.sum())}   light/moderate (0-2): "
          f"{int(light.sum())}")

    # The three-way intersection being empty does not end the question. The
    # two DESCENDING tracks share no reports at all, but ascending overlaps
    # both, so each descending track can still be compared against ascending
    # on the reports they do share. Those are the only comparisons in which
    # geography is held fixed.
    from scipy import stats
    print("\npairwise, on reports BOTH tracks observe "
          "(geography held fixed):")
    for t1, t2 in [("asc-f1148", "desc61"), ("asc-f1148", "desc163"),
                   ("desc61", "desc163")]:
        sh = np.isfinite(per[t1]) & np.isfinite(per[t2])
        s = sh & (lvls >= 3)
        l = sh & (lvls >= 0) & (lvls <= 2)
        print(f"\n  {t1} vs {t2}: {int(sh.sum())} shared reports, "
              f"{int(s.sum())} severe / {int(l.sum())} light")
        if int(s.sum()) < a.min_n or int(l.sum()) < a.min_n:
            print(f"    underpowered (need {a.min_n} per group) -- "
                  f"medians only")
            for t in (t1, t2):
                sm = np.nanmedian(per[t][s]) if s.sum() else np.nan
                lm = np.nanmedian(per[t][l]) if l.sum() else np.nan
                print(f"      {t:>10}  severe {sm:+.4f}  light {lm:+.4f}  "
                      f"diff {sm-lm:+.4f}")
            continue
        for t in (t1, t2):
            _, p = stats.mannwhitneyu(per[t][s], per[t][l],
                                      alternative="greater")
            print(f"      {t:>10}  severe {np.median(per[t][s]):+.4f}  "
                  f"light {np.median(per[t][l]):+.4f}  p = {p:.4g}")

    if int(sev.sum()) < a.min_n or int(light.sum()) < a.min_n:
        print(f"\n  UNDERPOWERED. Fewer than {a.min_n} per group, so no "
              f"p-value is reported.")
        print("  An underpowered null is indistinguishable from a real null,")
        print("  and presenting one here would settle the disagreement by")
        print("  arithmetic accident rather than evidence.")
        print("\n  Medians on the common reports, for description only:")
        print(f"  {'track':>10}{'severe':>10}{'light':>10}{'diff':>9}")
        for t in TRACKS:
            s = np.nanmedian(per[t][sev]) if sev.sum() else np.nan
            l = np.nanmedian(per[t][light]) if light.sum() else np.nan
            print(f"  {t:>10}{s:>10.4f}{l:>10.4f}{s-l:>9.4f}")
        print("\n  The three tracks cannot be adjudicated on these reports.")
        print("  Settling it needs more classified reports inside the shared")
        print("  footprint, not more interferograms.")
        return 2

    from scipy import stats
    print(f"\n  {'track':>10}{'severe':>10}{'light':>10}{'diff':>9}{'p':>10}")
    for t in TRACKS:
        s = per[t][sev]
        l = per[t][light]
        _, p = stats.mannwhitneyu(s, l, alternative="greater")
        print(f"  {t:>10}{np.median(s):>10.4f}{np.median(l):>10.4f}"
              f"{np.median(s)-np.median(l):>9.4f}{p:>10.4g}")

    print("\n  Same villages, same damage classifications, three")
    print("  interferogram pairs. Any remaining disagreement is about the")
    print("  radar, not about geography.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
