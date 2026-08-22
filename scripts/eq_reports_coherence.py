"""Does interferometric coherence loss predict where damage was reported?

This is the one question the reports can answer cleanly, and it is why the
pre-pre control pair was worth buying.

WHY THE OTHER QUESTIONS DO NOT WORK. Damage reflects SHAKING, which a M7.7
delivers over a wide area regardless of whether onshore static slip is 54 cm
or 6 cm, so damage cannot test the static-displacement prediction. And both
the report locations and the damage classifications are selection-biased:
reports come from where people and phones are, and BPBD classifies places it
inspected because they were already reported. Severity fractions computed over
those samples measure the sampling, not the earthquake.

WHY THIS ONE DOES WORK. Coherence change is a DIFFERENCE of two
interferograms over the same ground:

    drop = coherence(21 Jul -> 2 Aug, quiet) - coherence(2 -> 20 Aug, event)

Vegetation, slope, and land cover affect both pairs and largely cancel. What
does not cancel is ground that was rearranged between 2 and 20 August. The
reports are an INDEPENDENT observable -- nobody filing an aid request consulted
a radar image -- so agreement is not circular.

The control for sampling bias is the comparison itself: coherence drop at
report locations is compared against coherence drop at random coherent land
points drawn from the same scene, not against zero. If reports simply landed
on terrain that decorrelates anyway, both distributions match and the test
returns nothing.

    conda run -n insardev-test python scripts/eq_reports_coherence.py
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
CO = os.path.join(REPO, "output/coseismic",
                  "flores-coseismic-2026-desc61-f621-prepost-d2")
CTRL = os.path.join(REPO, "output/coseismic",
                    "flores-coseismic-2026-desc61-f621-prepre-d2")
OUT = os.path.join(REPO, "output/coseismic/eq_reports_coherence.png")


def load(d, name):
    import rioxarray  # noqa: F401
    import xarray as xr
    hits = glob.glob(os.path.join(d, f"*_{name}.tif"))
    if not hits:
        sys.exit(f"no {name} in {os.path.basename(d)}")
    da = xr.open_dataarray(hits[0], engine="rasterio")
    return da.isel(band=0) if "band" in da.dims else da


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-coh", type=float, default=0.2,
                    help="a pixel must be usable in BOTH pairs; too high a "
                         "floor throws away exactly the damaged ground the "
                         "test is looking for")
    ap.add_argument("--radius-px", type=int, default=3,
                    help="reports are geolocated to a village or building, "
                         "not a 40 m pixel, so sample a small neighbourhood")
    ap.add_argument("--co", default=CO, help="co-event product directory")
    ap.add_argument("--ctrl", default=CTRL, help="quiet control directory")
    ap.add_argument("--tag", default="desc61",
                    help="label for the plot and output filename")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.out is None:
        a.out = os.path.join(REPO, "output/coseismic",
                             f"eq_reports_coherence_{a.tag}.png")

    from pyproj import Transformer

    import xarray as xr

    # HyP3 clips each pair to its own reference/secondary overlap, so the two
    # products differ by a couple of pixels. Align on exact coordinate values
    # rather than reprojecting: both sit on the same 40 m UTM grid, so an
    # inner join is lossless, whereas resampling one onto the other would
    # smooth the very coherence contrast being measured.
    co = load(a.co, "corr")
    ct = load(a.ctrl, "corr")
    wat = load(a.co, "water_mask")
    co, ct, wat = xr.align(co, ct, wat, join="inner")
    print(f"aligned to {co.shape} (inner join on the shared 40 m grid)")
    if co.size == 0:
        sys.exit("the two products share no grid cells")
    water = wat.values
    c1, c2 = ct.values.astype("float64"), co.values.astype("float64")

    both = np.isfinite(c1) & np.isfinite(c2) & (water > 0) \
        & (c1 >= a.min_coh)
    drop = np.where(both, c1 - c2, np.nan)
    print(f"grid {c1.shape}, {int(both.sum()):,} pixels usable in both pairs")
    print(f"control mean coherence {np.nanmean(np.where(both, c1, np.nan)):.3f}"
          f", co-event {np.nanmean(np.where(both, c2, np.nan)):.3f}")
    print(f"scene-wide mean drop {np.nanmean(drop):+.4f}")

    xs = co[co.dims[-1]].values
    ys = co[co.dims[-2]].values
    fwd = Transformer.from_crs("EPSG:4326", co.rio.crs, always_xy=True)

    d = json.load(open(REPORTS))
    pts, lvls = [], []
    for f in d["features"]:
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        if not c:
            continue
        x, y = fwd.transform(float(c[0]), float(c[1]))
        ix = int(np.argmin(np.abs(xs - x)))
        iy = int(np.argmin(np.abs(ys - y)))
        # argmin always returns something; reject points outside the raster.
        if not (xs.min() <= x <= xs.max() and ys.min() <= y <= ys.max()):
            continue
        pts.append((iy, ix))
        lvls.append(f["properties"].get("damage_level"))
    print(f"\n{len(pts)} of {len(d['features'])} reports fall inside the "
          f"{a.tag} raster")
    if len(pts) < 20:
        sys.exit("too few reports inside the footprint for a comparison")

    r = a.radius_px

    def sample(iy, ix):
        w = drop[max(0, iy-r):iy+r+1, max(0, ix-r):ix+r+1]
        return np.nanmedian(w) if np.isfinite(w).any() else np.nan

    at_reports = np.array([sample(iy, ix) for iy, ix in pts])
    n_ok = int(np.isfinite(at_reports).sum())
    print(f"{n_ok} of those have coherent data in both pairs")
    if n_ok < 20:
        sys.exit("too few reports on coherent ground")

    # The null: random coherent land points from the same scene.
    rng = np.random.default_rng(0)
    iy_all, ix_all = np.nonzero(both)
    pick = rng.choice(len(iy_all), size=min(4000, len(iy_all)), replace=False)
    at_random = np.array([sample(iy_all[k], ix_all[k]) for k in pick])
    at_random = at_random[np.isfinite(at_random)]

    ar = at_reports[np.isfinite(at_reports)]
    print(f"\n  coherence drop at {len(ar)} report locations : "
          f"median {np.median(ar):+.4f}, mean {ar.mean():+.4f}")
    print(f"  coherence drop at {len(at_random)} random points: "
          f"median {np.median(at_random):+.4f}, "
          f"mean {at_random.mean():+.4f}")

    from scipy import stats
    u, p = stats.mannwhitneyu(ar, at_random, alternative="greater")
    diff = np.median(ar) - np.median(at_random)
    print(f"\n  difference in medians {diff:+.4f} coherence units")
    print(f"  Mann-Whitney U, reports > random: p = {p:.4g}")

    # DOSE-RESPONSE is the part that resists the sampling objection. A
    # difference between "reports" and "random" could be terrain: reports come
    # from villages, and villages sit on particular ground. But if coherence
    # loss also increases with REPORTED SEVERITY, terrain cannot explain it --
    # a severe and a light report in the same village stand on the same
    # ground. Measure it rather than infer it from two numbers.
    LABELS = {0: "tidak rusak", 1: "ringan", 2: "sedang", 3: "berat",
              4: "kolaps", -1: "unclassified (aid request)"}
    print(f"\n  {'level':>28}{'n':>6}{'median drop':>14}")
    print(f"  {'random coherent land':>28}{len(at_random):>6}"
          f"{np.median(at_random):>14.4f}")
    by_level = {}
    for lv in [-1, 0, 1, 2, 3, 4]:
        vals = np.array([sample(iy, ix) for (iy, ix), l in zip(pts, lvls)
                         if l == lv])
        vals = vals[np.isfinite(vals)] if vals.size else vals
        if vals.size == 0:
            continue
        by_level[lv] = vals
        print(f"  {LABELS[lv]:>28}{len(vals):>6}{np.median(vals):>14.4f}")

    sev = np.concatenate([by_level[l] for l in (3, 4) if l in by_level]) \
        if any(l in by_level for l in (3, 4)) else np.array([])
    light = np.concatenate([by_level[l] for l in (0, 1, 2) if l in by_level]) \
        if any(l in by_level for l in (0, 1, 2)) else np.array([])
    p_sev = p_light = None
    if len(sev) >= 8:
        _, p_sev = stats.mannwhitneyu(sev, at_random, alternative="greater")
        print(f"\n  {len(sev)} severe (berat/kolaps) vs random: "
              f"median {np.median(sev):+.4f}, p = {p_sev:.4g}")
        if len(light) >= 8:
            _, p_light = stats.mannwhitneyu(sev, light, alternative="greater")
            print(f"  severe vs light/moderate ({len(light)}): "
                  f"p = {p_light:.4g}"
                  f"   <- terrain cannot explain this one")
    else:
        print(f"\n  only {len(sev)} severe reports on coherent ground -- "
              f"not enough to test separately")

    # Land cover runs AGAINST the finding, which is worth stating. Built-up
    # ground normally holds coherence better than vegetation, so reports --
    # which come from villages -- should show a SMALLER drop than random land
    # if land cover were the only effect. They show a larger one.

    # The verdict weighs the SEVERITY contrast above the location contrast,
    # and an earlier version of this script did not -- it read only "reports
    # vs random" and declared a null on the ascending frame while the severity
    # test there was the strongest in the whole analysis (p = 0.0035).
    #
    # The severity contrast is the better evidence for a specific reason.
    # "Reports vs random" compares village locations against arbitrary land,
    # so anything that makes villages differ from open country -- land cover,
    # slope, and in a baseline-mismatched pair the extra decorrelation of a
    # longer interval -- leaks into it. "Severe vs light" compares reports
    # against other reports: same kind of place, same kind of terrain, often
    # the same village. Almost nothing except the earthquake distinguishes
    # them.
    print()
    loc = p < 0.01 and diff > 0.01
    dose = p_light is not None and p_light < 0.05
    if dose and loc:
        print("  Coherence loss tracks BOTH where reports were filed and how")
        print("  severe they were. The severity gradient is the stronger of")
        print("  the two, since it compares reports against other reports.")
    elif dose:
        print("  Reported SEVERITY tracks coherence loss (severe vs light, "
              f"p = {p_light:.3g}),")
        print("  while report locations as a whole are indistinguishable from")
        print("  random land. That combination is what a real but weak signal")
        print("  looks like: the radar cannot pick out a village that filed a")
        print("  report, but among villages that did, it separates the badly")
        print("  damaged from the lightly damaged.")
    elif loc:
        print("  Report locations lost more coherence than random land, but")
        print("  severity does not grade with it. Treat with caution: that is")
        print("  also what terrain or a baseline mismatch would produce.")
    else:
        print("  Neither report location nor reported severity tracks")
        print("  coherence loss here. At 40 m, coherence responds to")
        print("  vegetation and slope far more than to a collapsed building,")
        print("  which occupies a fraction of one pixel.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.5, 5))
    bins = np.linspace(-0.3, 0.5, 60)
    ax.hist(at_random, bins=bins, density=True, alpha=.55, color="#8fa8a0",
            label=f"random coherent land (n={len(at_random)})")
    ax.hist(ar, bins=bins, density=True, alpha=.75, color="#7a1fa2",
            label=f"report locations (n={len(ar)})")
    ax.axvline(np.median(at_random), color="#4a5f58", lw=1.6, ls="--")
    ax.axvline(np.median(ar), color="#7a1fa2", lw=2.0)
    ax.set_xlabel("coherence drop, control minus co-event "
                  "(positive = lost coherence)")
    ax.set_ylabel("density")
    ax.set_title("Does coherence loss track where damage was reported?\n"
                 f"{a.tag}, medians differ by {diff:+.3f}, "
                 f"p = {p:.3g}", fontsize=11, loc="left")
    ax.legend(fontsize=9)
    fig.tight_layout()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
