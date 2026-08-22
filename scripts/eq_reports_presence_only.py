"""Presence-only analysis: does coherence loss carry information about damage?

Every earlier version of this test compared damage reports against "random
coherent land" and read a null as evidence of no relationship. That is a
presence-ABSENCE reading, and the data cannot support it. Unreported ground is
not undamaged ground -- it is ground with no people, no phone signal, or no
agency visit. Damaged-but-unreported places sit inside the control, diluting
the contrast, so a null was the expected outcome whether or not the radar
works. The nulls I reported were uninformative, not negative.

Presence-only methods exist for exactly this situation: confirmed presences,
no confirmed absences. The unlabelled sample becomes BACKGROUND rather than
absence, and what is estimated is a RELATIVE occurrence rate -- how much more
likely a presence is at one covariate value than another -- never an absolute
probability of damage. That limitation is intrinsic, not a shortcoming of this
implementation.

TWO BACKGROUNDS, AND THE SECOND IS THE POINT.

  Random landscape background. The naive choice. Contaminated by reporting
  bias: presences sit near roads and settlements, background does not, so any
  covariate correlated with accessibility looks predictive.

  Target-group background. Presences are the SEVERE reports; background is
  ALL report locations, including the aid requests. Every background point is
  therefore a place where somebody was present, had signal, and did file
  something. Accessibility, population and connectivity are held fixed by
  construction, and what remains is whether coherence loss separates severe
  damage from other reporting within the same population of reachable places.
  This is the standard fix for presence-only sampling bias and it is the
  analysis that should be believed.

Reported as AUC with a bootstrap interval. AUC 0.5 means the covariate carries
no information; it is not a p-value and does not become one.

    conda run -n insardev-test python scripts/eq_reports_presence_only.py
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
    "desc163": ("flores-coseismic-2026-desc163-f620-prepost-d2",
                "flores-coseismic-2026-desc163-f620-prepre-d2"),
    "desc61": ("flores-coseismic-2026-desc61-f621-prepost-d2",
               "flores-coseismic-2026-desc61-f621-prepre-d2"),
}


def load(d, name):
    import rioxarray  # noqa: F401
    import xarray as xr
    hits = glob.glob(os.path.join(OUT, d, f"*_{name}.tif"))
    if not hits:
        sys.exit(f"no {name} in {d}")
    da = xr.open_dataarray(hits[0], engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def auc(pres, bg):
    """P(a random presence scores above a random background point).

    Mann-Whitney U over (n_pres * n_bg), which is the standard presence-only
    discrimination measure. Ties count half.
    """
    if len(pres) == 0 or len(bg) == 0:
        return np.nan
    allv = np.concatenate([pres, bg])
    order = allv.argsort()
    ranks = np.empty(len(allv), dtype=float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # average ranks for ties so a covariate with many equal values is not
    # rewarded
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]
    r1 = ranks[:len(pres)].sum()
    u = r1 - len(pres) * (len(pres) + 1) / 2.0
    return u / (len(pres) * len(bg))


def boot_auc(pres, bg, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    vals = np.empty(n)
    for i in range(n):
        p = rng.choice(pres, size=len(pres), replace=True)
        b = rng.choice(bg, size=len(bg), replace=True)
        vals[i] = auc(p, b)
    return np.nanpercentile(vals, [2.5, 97.5])


def sample_track(track, lonlat, min_coh, r, n_bg, seed=0):
    import xarray as xr
    from pyproj import Transformer

    co_d, ct_d = TRACKS[track]
    co, ct, wat = xr.align(load(co_d, "corr"), load(ct_d, "corr"),
                           load(co_d, "water_mask"), join="inner")
    c1 = ct.values.astype("float64")
    c2 = co.values.astype("float64")
    ok = np.isfinite(c1) & np.isfinite(c2) & (wat.values > 0) & (c1 >= min_coh)
    drop = np.where(ok, c1 - c2, np.nan)

    xs = co[co.dims[-1]].values
    ys = co[co.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", co.rio.crs, always_xy=True)

    def at(lon, lat):
        x, y = fwd.transform(lon, lat)
        if not (xs.min() <= x <= xs.max() and ys.min() <= y <= ys.max()):
            return np.nan
        iy = int(np.argmin(np.abs(ys - y)))
        ix = int(np.argmin(np.abs(xs - x)))
        w = drop[max(0, iy-r):iy+r+1, max(0, ix-r):ix+r+1]
        return np.nanmedian(w) if np.isfinite(w).any() else np.nan

    vals = np.array([at(lon, lat) for lon, lat in lonlat])

    rng = np.random.default_rng(seed)
    iy_all, ix_all = np.nonzero(ok)
    pick = rng.choice(len(iy_all), size=min(n_bg, len(iy_all)), replace=False)
    land = np.array([np.nanmedian(
        drop[max(0, iy_all[k]-r):iy_all[k]+r+1,
             max(0, ix_all[k]-r):ix_all[k]+r+1]) for k in pick])
    return vals, land[np.isfinite(land)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.2)
    ap.add_argument("--radius-px", type=int, default=3)
    ap.add_argument("--n-bg", type=int, default=4000)
    ap.add_argument("--min-pres", type=int, default=8)
    a = ap.parse_args()

    d = json.load(open(REPORTS))
    lonlat, lvls = [], []
    for f in d["features"]:
        c = (f.get("geometry") or {}).get("coordinates")
        if not c:
            continue
        lonlat.append((float(c[0]), float(c[1])))
        v = f["properties"].get("damage_level")
        lvls.append(v if isinstance(v, (int, float)) else -99)
    lvls = np.array(lvls)
    print(f"{len(lonlat)} reports  "
          f"({int((lvls >= 3).sum())} severe, "
          f"{int(((lvls >= 0) & (lvls <= 2)).sum())} light/moderate, "
          f"{int((lvls == -1).sum())} aid requests)")

    print("\nAUC = P(a severe report scores above a background point).")
    print("0.50 means the coherence drop carries no information.\n")
    print(f"  {'track':>11}{'background':>22}{'n pres':>8}{'n bg':>7}"
          f"{'AUC':>8}{'95% CI':>18}")

    for t in TRACKS:
        vals, land = sample_track(t, lonlat, a.min_coh, a.radius_px, a.n_bg)
        obs = np.isfinite(vals)
        pres = vals[obs & (lvls >= 3)]
        # Target group: every OTHER report this track observes. Excluding the
        # presences themselves keeps the two samples disjoint.
        tgb = vals[obs & (lvls < 3)]
        if len(pres) < a.min_pres:
            print(f"  {t:>11}{'--':>22}{len(pres):>8}{'':>7}"
                  f"{'too few presences':>26}")
            continue
        for label, bg in (("random landscape", land),
                          ("target-group (reports)", tgb)):
            if len(bg) < a.min_pres:
                print(f"  {t:>11}{label:>22}{len(pres):>8}{len(bg):>7}"
                      f"{'too little background':>26}")
                continue
            v = auc(pres, bg)
            lo, hi = boot_auc(pres, bg)
            flag = "" if (lo <= 0.5 <= hi) else "  *"
            print(f"  {t:>11}{label:>22}{len(pres):>8}{len(bg):>7}"
                  f"{v:>8.3f}   [{lo:.3f}, {hi:.3f}]{flag}")

    print("\n  * = 95% interval excludes 0.5")
    print("\n  The target-group rows are the ones to read. Their background")
    print("  is other reports, so accessibility, population and phone")
    print("  coverage are held fixed by construction and cannot manufacture")
    print("  discrimination. The random-landscape rows are shown only to")
    print("  make the size of that bias visible.")
    print("\n  Presence-only estimates a RELATIVE occurrence rate. Nothing")
    print("  here yields a probability that a given place was damaged, and")
    print("  no amount of extra radar would change that -- it needs")
    print("  confirmed absences, which means someone visiting places that")
    print("  filed no report and recording that they were undamaged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
