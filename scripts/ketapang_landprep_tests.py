#!/usr/bin/env python3
"""Was the 2026 burn inside the four Ketapang concessions land preparation for
oil palm? Four tests, each able to come out against it.

Builds on ketapang_fire_origin.py (25 m stack, burned mask, VIIRS lineage,
ignitions) and ketapang_planet_check.py (PlanetScope windows). Every test
compares the four concessions with OTHER concessions in the area and with
UNCONCEDED land, because a signal is only a signal if it differs from the
landscape around it.

TEST 1  FATE OF EARLIER BURNS. Fire used to prepare land is followed by
        planting. Land burned in 2015 (MCD64A1) that was not palm at the time:
        what share was palm by 2021 (Descals planting year 2015-2021), against
        unburned non-palm land in the same zone? 2019 burns are reported too,
        but a palm planted in 2019-2021 is not yet closed canopy in a 2021 map,
        so that conversion is undercounted. The PlanetScope windows add 2023,
        2025 and 2026 imagery of land that burned in 2015, 2019 and 2023.

TEST 2  PREPARATION BEFORE THE FIRE. Slash-and-burn clears vegetation first and
        burns it dry. Sentinel-2 NDVI, early (Dec 2025 - Mar 2026) against
        late pre-fire (15 May - 10 Jul 2026): a 2026-burned pixel that was
        green early (>= 0.6) and open late (< 0.45, drop >= 0.2) was cleared
        before the fire. Pixels with a VIIRS detection within 750 m before
        10 July are left out so an early fire is not read as clearing. In the
        PlanetScope windows, freshly cleared parcels (bare in July 2026, green
        in July 2025) are mapped and checked against the burn.

TEST 3  HOW THE FIRES STARTED. People light fires by day. Share of ignitions
        seen at the day overpass (~13:00 local) against the day share of all
        detections in the same zone (a smouldering peat fire is seen by day
        and night alike, so the baseline matters). And multi-point lighting:
        overpasses that show three or more new ignitions in the same zone,
        per 100 km2.

TEST 4  WHO CLEARED. Company land preparation works block by block (typically
        25-30 ha); households clear 1-2 ha. Size distribution of bare cleared
        parcels in the PlanetScope windows, 2023, 2025 and pre-fire 2026.

    conda run -n base python scripts/ketapang_landprep_tests.py
"""

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from ketapang_fire_origin import (CONC, FOUR, OUT as ORIGIN, GRID, TILES,  # noqa: E402
                                  BUF_DEG, SEASON, RING_KM, START, END)
from ketapang_planet_check import OUT as PLANET, read_ps, overlay  # noqa: E402

OUT = os.path.join(ORIGIN, "landprep")
YEARS = (2015, 2019, 2023)
GREEN, OPEN, DROP = 0.60, 0.45, 0.20
EARLY = ("2025-12-01", "2026-03-31")
LATE = ("2026-05-15", "2026-07-10")
CUTOFF = "2026-07-10"
DAY_HOURS = (10, 17)
# Cleared in PlanetScope: open AND bright. Freshly cleared parcels keep slash
# and early regrowth (NDVI ~0.5 where dense cover is 0.75-0.9), so an NDVI cut
# alone either misses them or catches shadow; red SR > 0.05 keeps bright
# soil / dry slash and drops shadow and water.
OPEN_PS, RED_PS, GREEN_PS = 0.60, 500, 0.70
MIN_PARCEL_HA = 0.1


# ----------------------------- Earth Engine -----------------------------
def ee_download(img, bbox, out_dir, prefix, step, tiles):
    """img on a lattice of `step` degrees anchored at 0,0, tiled, merged."""
    import ee
    import numpy as np
    import rasterio
    from rasterio.merge import merge
    from earthchange.gee_utils import download_geotiff
    os.makedirs(out_dir, exist_ok=True)
    x0, y0, x1, y1 = bbox
    c0, c1 = int(np.floor(x0 / step)), int(np.ceil(x1 / step))
    r0, r1 = int(np.floor(-y1 / step)), int(np.ceil(-y0 / step))
    cs = np.linspace(c0, c1, tiles + 1).astype(int)
    rs = np.linspace(r0, r1, tiles + 1).astype(int)
    paths = []
    for i in range(tiles):
        for j in range(tiles):
            p = os.path.join(out_dir, f"{prefix}_{i}{j}.tif")
            if not os.path.exists(p):
                reg = ee.Geometry.Rectangle(
                    [cs[j] * step, -rs[i + 1] * step, cs[j + 1] * step,
                     -rs[i] * step], None, False)
                if not download_geotiff(img, reg, p, max_scale_mult=1,
                                        crs_transform=[step, 0, 0, 0, -step, 0]):
                    raise SystemExit(f"download failed: {p}")
            paths.append(p)
    srcs = [rasterio.open(p) for p in paths]
    arr, tr = merge(srcs, method="first")
    for s in srcs:
        s.close()
    return arr, tr


def mcd64(years):
    import ee
    from earthchange.fire_national import BURN_IC
    bands = []
    for y in years:
        ic = (ee.ImageCollection(BURN_IC).filterDate(f"{y}-01-01", f"{y + 1}-01-01")
              .select("BurnDate"))
        bands.append(ic.map(lambda im: im.gt(0)).max().unmask(0)
                     .toUint8().rename(f"b{y}"))
    return ee.Image.cat(bands)


def s2_ndvi():
    import ee

    def comp(lo, hi):
        def one(im):
            scl = im.select("SCL")
            ok = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
            return im.normalizedDifference(["B8", "B4"]).updateMask(ok)
        return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterDate(lo, hi).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
                .map(one).median())
    return ee.Image.cat([comp(*EARLY).rename("early"), comp(*LATE).rename("late")]) \
        .multiply(1000).round().unmask(-32768).toInt16()


def on_grid(arr, src_tr, shape, tr):
    """Nest a coarser lattice array (integer multiple) onto the 25 m grid."""
    import numpy as np
    rep = int(round(src_tr.a / tr.a))
    u = np.kron(arr, np.ones((rep, rep), arr.dtype))
    oy = int(round((src_tr.f - tr.f) / tr.a))
    ox = int(round((tr.c - src_tr.c) / tr.a))
    u = u[max(-oy, 0):, max(ox, 0):][:shape[0], :shape[1]]
    full = np.zeros(shape, arr.dtype)
    full[:u.shape[0], :u.shape[1]] = u
    return full


# --------------------------------- zones --------------------------------
def zones(conc, conc4, bbox, tr, shape, land):
    """Masks: each of the four, the four together, other concessions, and
    unconceded land within RING_KM of the four."""
    import numpy as np
    from rasterio import features
    from scipy import ndimage
    z = {}
    for _, r in conc4.iterrows():
        z[r.acr] = (features.rasterize([(r.geometry, 1)], out_shape=shape,
                                       transform=tr, dtype="uint8") > 0) & land
    four = np.any([z[x] for x in FOUR], axis=0)
    near = conc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    anyc = features.rasterize([(g, 1) for g in near.geometry], out_shape=shape,
                              transform=tr, dtype="uint8") > 0
    dist = ndimage.distance_transform_edt(~four) * (GRID * 111.0)
    z["the four"] = four
    z["other concessions"] = anyc & ~four & land
    z[f"unconceded ≤{RING_KM:.0f} km"] = (~anyc) & land & (dist <= RING_KM)
    return z


# --------------------------------- tests --------------------------------
def test1(z, pha, burns, cls, py):
    import numpy as np
    rows = []
    palm = cls > 0
    for y in (2015, 2019):
        nonpalm_then = ~(palm & (py > 0) & (py < y))
        new_palm = palm & (py >= y) & (py <= 2021)
        b = burns[y]
        for name, m in z.items():
            base = m & nonpalm_then
            bur, unb = base & b, base & ~b
            rows.append({
                "burn_year": y, "zone": name,
                "burned_nonpalm_ha": float(pha[bur].sum()),
                "pct_burned_now_palm_by_2021": 100 * float(pha[bur & new_palm].sum())
                / max(float(pha[bur].sum()), 1e-9),
                "pct_unburned_now_palm_by_2021": 100 * float(pha[unb & new_palm].sum())
                / max(float(pha[unb].sum()), 1e-9),
                "burned_ha_again_in_2026": float(pha[bur & burns[2026]].sum()),
            })
    return rows


def test2(z, pha, burned26, ndvi, vmask_early):
    import numpy as np
    early, late = ndvi[0], ndvi[1]
    valid = (early != -32768) & (late != -32768)
    e, l = early / 1000.0, late / 1000.0
    cleared = valid & (e >= GREEN) & (l < OPEN) & ((e - l) >= DROP)
    rows = []
    for name, m in z.items():
        sel = m & burned26 & ~vmask_early
        v = sel & valid
        unb = m & ~burned26 & valid
        rows.append({
            "zone": name, "burned_2026_ha": float(pha[sel].sum()),
            "s2_valid_share": float(pha[v].sum() / max(pha[sel].sum(), 1e-9)),
            "pct_burned_cleared_before_fire": 100 * float(pha[v & cleared].sum())
            / max(float(pha[v].sum()), 1e-9),
            "pct_unburned_cleared_same_period": 100 * float(pha[unb & cleared].sum())
            / max(float(pha[unb].sum()), 1e-9),
            "pct_burned_open_already_early": 100 * float(
                pha[v & (e < OPEN)].sum()) / max(float(pha[v].sum()), 1e-9),
        })
    return rows, cleared


def test3(det, ign, zone_of_pts, z_area_km2):
    import numpy as np
    import pandas as pd
    rows = []
    det = det[det.month.between(*SEASON)]
    ign = ign[ign.month.between(*SEASON)]
    zd, zi = zone_of_pts(det), zone_of_pts(ign)
    for name in z_area_km2:
        if name == "the four":
            d, i = det[zd.isin(list(FOUR))], ign[zi.isin(list(FOUR))]
        else:
            d, i = det[zd == name], ign[zi == name]
        if not len(d):
            continue
        dday = d.hour.between(*DAY_HOURS).mean()
        iday = i.hour.between(*DAY_HOURS).mean() if len(i) else np.nan
        # overpass = same satellite pass; ignitions grouped within 15 min
        grp = (i.t // 900).astype(int)
        per = i.groupby(grp).size()
        rows.append({
            "zone": name, "detections": len(d), "ignitions": len(i),
            "day_share_all_detections": float(dday),
            "day_share_ignitions": float(iday),
            "ignition_day_ratio": float(iday / dday) if dday else np.nan,
            "ignitions_per_100km2": 100 * len(i) / z_area_km2[name],
            "overpasses_with_3plus_ignitions": int((per >= 3).sum()),
            "multi_ignition_overpasses_per_100km2": 100 * int((per >= 3).sum())
            / z_area_km2[name],
            "share_ignitions_in_multi_overpasses": float(
                per[per >= 3].sum() / max(len(i), 1)),
        })
    return rows


def ps_ndvi_on(ref_path, path):
    """NDVI of `path` warped onto the grid of `ref_path` (PlanetScope)."""
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling
    with rasterio.open(ref_path) as ref:
        shp, rtr, rcrs = (ref.height, ref.width), ref.transform, ref.crs
    a, tr, crs, _ = read_ps(path)
    nd = (a[3] - a[2]) / (a[3] + a[2] + 1e-9)
    out = []
    for band in (nd, a[2]):
        dst = np.full(shp, np.nan, np.float32)
        reproject(band.astype(np.float32), dst, src_transform=tr, src_crs=crs,
                  dst_transform=rtr, dst_crs=rcrs, resampling=Resampling.bilinear,
                  src_nodata=np.nan, dst_nodata=np.nan)
        out.append(dst)
    return np.stack(out), rtr


def parcels(bare, px_ha):
    import numpy as np
    from scipy import ndimage
    m = ndimage.binary_opening(bare, iterations=1)
    lab, n = ndimage.label(m)
    if not n:
        return np.array([])
    ha = np.bincount(lab.ravel())[1:] * px_ha
    return ha[ha >= MIN_PARCEL_HA]


def test4_and_ps(lc, burned25, tr25):
    """Bare-parcel sizes per window and date; fresh clearing 2025 -> 2026 and
    whether it burned."""
    import numpy as np
    plan = json.load(open(os.path.join(PLANET, "plan.json")))
    rows, fresh_rows, figs = [], [], []
    for s in plan:
        ref = s["pre"]["tif"]
        dates = {"pre-fire 2026": ref}
        for yr, h in (s.get("history") or {}).items():
            if h and os.path.exists(h["tif"]):
                dates[yr] = h["tif"]
        nd = {}
        for lab, p in dates.items():
            nd[lab], rtr = ps_ndvi_on(ref, p)
        px_ha = abs(rtr.a * rtr.e) / 1e4
        def cleared(x):
            ok = np.isfinite(x[0]) & np.isfinite(x[1])
            return ok, ok & (x[0] < OPEN_PS) & (x[1] > RED_PS)

        for lab, v in nd.items():
            ok, bare = cleared(v)
            ha = parcels(bare, px_ha)
            tot = ha.sum() if ha.size else 0.0
            rows.append({
                "site": s["site"], "kind": s["kind"], "date": lab,
                "valid_share": float(ok.mean()),
                "bare_share": float(bare.sum() / max(ok.sum(), 1)),
                "n_parcels": int(ha.size),
                "median_parcel_ha": float(np.median(ha)) if ha.size else None,
                "pct_area_in_parcels_lt2ha": 100 * float(ha[ha < 2].sum() / tot) if tot else None,
                "pct_area_in_parcels_2_10ha": 100 * float(ha[(ha >= 2) & (ha < 10)].sum() / tot) if tot else None,
                "pct_area_in_parcels_ge10ha": 100 * float(ha[ha >= 10].sum() / tot) if tot else None,
                "largest_parcel_ha": float(ha.max()) if ha.size else None,
            })
        if "2025" in nd:
            v25, v26 = nd["2025"], nd["pre-fire 2026"]
            ok, now_cleared = cleared(v26)
            fresh = now_cleared & np.isfinite(v25[0]) & (v25[0] >= GREEN_PS)
            ha = parcels(fresh, px_ha)
            ov = overlay(ref, lc, burned25, tr25)
            from scipy import ndimage
            fm = ndimage.binary_opening(fresh, iterations=1)
            fresh_rows.append({
                "site": s["site"], "fresh_cleared_ha": float(fm.sum() * px_ha),
                "n_fresh_parcels": int(ha.size),
                "median_fresh_parcel_ha": float(np.median(ha)) if ha.size else None,
                "pct_fresh_cleared_that_burned": 100 * float((fm & ov["burned"]).sum())
                / max(int(fm.sum()), 1),
                "pct_window_burned": 100 * float((ov["burned"] & ok).sum()) / max(int(ok.sum()), 1),
            })
            figs.append((s, ref, v25, v26, fm, ov["burned"]))
    return rows, fresh_rows, figs


def render_fresh(figs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from ketapang_planet_check import rgb
    from matplotlib.lines import Line2D
    fig, axes = plt.subplots(len(figs), 3, figsize=(14, 4.8 * len(figs)), dpi=140,
                             squeeze=False)
    for row, (s, ref, _v25, _v26, fm, bur) in zip(axes, figs):
        a, *_ = read_ps(ref)
        hist = s["history"]["2025"]["tif"]
        b, *_ = read_ps(hist)
        for ax, img, t in ((row[0], b, f"July 2025 ({s['history']['2025']['acquired'][:10]})"),
                           (row[1], a, f"pre-fire 2026 ({s['pre']['acquired'][:10]})")):
            ax.imshow(rgb(img), interpolation="nearest")
            ax.set_title(f"{s['concession']} · {t}", fontsize=9, loc="left")
            ax.set_xticks([]); ax.set_yticks([])
        ax = row[2]
        ax.imshow(rgb(a), interpolation="nearest")
        ax.contour(fm.astype(float), levels=[0.5], colors="#00e5ff", linewidths=0.8)
        ax.contour(bur.astype(float), levels=[0.5], colors="#ffd400", linewidths=0.6)
        ax.set_title("cleared Jul 2025 → Jul 2026 (cyan) · burned 2026 (yellow)",
                     fontsize=9, loc="left")
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Fresh clearing before the 2026 fire (PlanetScope 3 m, 2.5 km windows)",
                 x=0.01, ha="left", fontsize=13, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# --------------------------------- main ---------------------------------
def main():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio import features
    from rasterio.merge import merge
    from scipy import ndimage
    from earthchange.gee_utils import initialize_ee
    initialize_ee()

    os.makedirs(OUT, exist_ok=True)
    srcs = [rasterio.open(p) for p in sorted(glob.glob(os.path.join(ORIGIN, "stack", "stack_*.tif")))]
    stack, tr = merge(srcs, method="first")
    for s in srcs:
        s.close()
    cls, py, landb = stack[0], stack[1], stack[5]
    shape = cls.shape
    land = landb == 1
    with rasterio.open(os.path.join(ORIGIN, "landcover_burned.tif")) as ds:
        lc, burned26 = ds.read(1), ds.read(2).astype(bool)
    lat = tr.f + (np.arange(shape[0]) + 0.5) * tr.e
    pha = np.broadcast_to((111320.0 * GRID) * (110574.0 * GRID)
                          * np.cos(np.radians(lat))[:, None] / 1e4, shape)

    conc = gpd.read_file(CONC).to_crs(4326)
    conc["geometry"] = conc.geometry.make_valid()
    rows = []
    for acr, name in FOUR.items():
        s = conc[conc.company.str.contains(name, case=False, na=False)]
        rows.append(s.iloc[0].to_dict() | {"acr": acr})
    conc4 = gpd.GeoDataFrame(rows, crs=4326)
    x0, y0, x1, y1 = conc4.total_bounds          # same AOI (and tiling) as the stack
    bbox = (x0 - BUF_DEG, y0 - BUF_DEG, x1 + BUF_DEG, y1 + BUF_DEG)
    z = zones(conc, conc4, bbox, tr, shape, land)
    z_area = {k: float(pha[m].sum() / 100) for k, m in z.items()}
    print("zones km²:", {k: round(v) for k, v in z_area.items()})

    # --- MCD64A1 2015 / 2019 / 2023 on the 500 m lattice -> 25 m
    print("MCD64A1 2015, 2019, 2023 ...")
    marr, mtr = ee_download(mcd64(YEARS), bbox, os.path.join(OUT, "mcd64"), "mcd",
                            0.0045, 1)
    burns = {y: on_grid(marr[i], mtr, shape, tr) > 0 for i, y in enumerate(YEARS)}
    burns[2026] = burned26

    # ---------------- TEST 1
    t1 = pd.DataFrame(test1(z, pha, burns, cls, py))
    t1.to_csv(os.path.join(OUT, "test1_fate_of_past_burns.csv"), index=False)
    print("\nTEST 1\n", t1.round(1).to_string(index=False))

    # PlanetScope windows: how much of each burned in 2015/2019/2023
    plan = json.load(open(os.path.join(PLANET, "plan.json")))
    win_hist = []
    for s in plan:
        w, so, e, n = s["bbox"]
        c0, r0 = ~tr * (w, n)
        c1, r1 = ~tr * (e, so)
        sl = (slice(int(r0), int(r1)), slice(int(c0), int(c1)))
        win_hist.append({"site": s["site"], **{f"burned_{y}_pct": 100 * float(burns[y][sl].mean())
                                               for y in (2015, 2019, 2023, 2026)}})
    wh = pd.DataFrame(win_hist)
    wh.to_csv(os.path.join(OUT, "test1_windows_burn_history.csv"), index=False)
    print(wh.round(0).to_string(index=False))

    # ---------------- TEST 2
    print("\nSentinel-2 NDVI early / late pre-fire ...")
    ndvi, ntr = ee_download(s2_ndvi(), bbox, os.path.join(OUT, "s2ndvi"), "ndvi",
                            GRID, TILES)
    if (abs(ntr.c - tr.c) > 1e-9 or abs(ntr.f - tr.f) > 1e-9
            or ndvi.shape[1:] != shape):
        raise SystemExit(f"S2 grid {ntr} {ndvi.shape} != stack {tr} {shape}")
    det = pd.read_csv(os.path.join(ORIGIN, f"viirs_{START}_{END}.csv"))
    det = det[det.confidence >= 1].copy()
    det["time"] = pd.to_datetime(det.acq_epoch, unit="s", utc=True).dt.tz_convert("Asia/Pontianak")
    det["month"] = det.time.dt.month
    det["hour"] = det.time.dt.hour
    det["t"] = det.acq_epoch.astype(float)
    early_pts = det[det.time < pd.Timestamp(CUTOFF, tz="Asia/Pontianak")]
    vm = features.rasterize([({"type": "Point", "coordinates": (x, y)}, 1)
                             for x, y in zip(early_pts.lon, early_pts.lat)],
                            out_shape=shape, transform=tr, dtype="uint8") > 0
    r = int(750 / 25)
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    vm = ndimage.binary_dilation(vm, structure=(xx ** 2 + yy ** 2) <= r * r)
    t2rows, cleared = test2(z, pha, burned26, ndvi, vm)
    t2 = pd.DataFrame(t2rows)
    t2.to_csv(os.path.join(OUT, "test2_prefire_clearing.csv"), index=False)
    print("\nTEST 2\n", t2.round(1).to_string(index=False))

    # ---------------- TEST 3
    ign = pd.read_csv(os.path.join(ORIGIN, "ignitions.csv"))
    ign["time"] = pd.to_datetime(ign.time)
    ign["hour"] = ign.time.dt.hour
    ign["t"] = (ign.time.dt.tz_convert("UTC")
                - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()

    zlab = np.zeros(shape, np.uint8)
    names = list(z)
    order = ["other concessions", f"unconceded ≤{RING_KM:.0f} km"] + list(FOUR)
    for k in order:                       # four last so they win
        zlab[z[k]] = names.index(k) + 1

    def zone_of_pts(df):
        rr, cc = rasterio.transform.rowcol(tr, df.lon.to_numpy(), df.lat.to_numpy())
        rr, cc = np.asarray(rr), np.asarray(cc)
        ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
        out = np.zeros(len(df), np.uint8)
        out[ok] = zlab[rr[ok], cc[ok]]
        lab = np.array([""] + names, dtype=object)[out]
        return pd.Series(lab, index=df.index)

    t3 = pd.DataFrame(test3(det, ign, zone_of_pts, z_area))
    t3.to_csv(os.path.join(OUT, "test3_ignition_behaviour.csv"), index=False)
    print("\nTEST 3\n", t3.round(2).to_string(index=False))

    # ---------------- TEST 4 (+ PlanetScope part of test 2)
    t4rows, fresh, figs = test4_and_ps(lc, burned26, tr)
    t4 = pd.DataFrame(t4rows)
    t4.to_csv(os.path.join(OUT, "test4_parcels.csv"), index=False)
    fr = pd.DataFrame(fresh)
    fr.to_csv(os.path.join(OUT, "test2_planet_fresh_clearing.csv"), index=False)
    print("\nTEST 4\n", t4.round(2).to_string(index=False))
    print("\nTEST 2 (PlanetScope fresh clearing)\n", fr.round(1).to_string(index=False))
    if figs:
        render_fresh(figs, os.path.join(OUT, "fresh_clearing_prefire.png"))

    json.dump({"test1": t1.to_dict("records"), "test1_windows": wh.to_dict("records"),
               "test2": t2.to_dict("records"), "test2_planet": fr.to_dict("records"),
               "test3": t3.to_dict("records"), "test4": t4.to_dict("records")},
              open(os.path.join(OUT, "summary.json"), "w"), indent=2, default=str)


if __name__ == "__main__":
    main()
