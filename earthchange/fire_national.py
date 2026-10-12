#!/usr/bin/env python3
"""National fire recurrence and peat — one raster per province, resumable.

The question this answers is not "where did it burn this year" but "where does
it burn again and again, and how much of that is peat". Repeat burning is the
signal that matters: a one-off fire can be an accident, and a pixel that has
burned in six of eleven years is a land-use regime.

Three design choices, each forced by something measured:

  * **Complete years only.** MCD64A1 is published monthly and currently ends
    in July 2026, so the 2026 burned-area year is two-thirds of a year and
    misses the Aug-Oct season entirely. Mixing it into a recurrence count
    would silently understate 2026 against every other year. The recurrence
    product therefore runs to the last complete year, and the running season
    is reported separately from FIRMS, which is current to within two days.

  * **A bitmask, not a band per year.** Eleven years as eleven byte bands over
    Maluku's bounding box is ~42 MB, close enough to Earth Engine's 50,331,648
    byte request ceiling to fail on a bad day. The same eleven years packed
    into one uint16 — bit i set means "burned in years[i]" — is 6 bytes per
    pixel for the whole stack, and every per-year figure, every recurrence
    count and every epoch combination is unpacked from it locally. One
    download, one source of truth: no statistic is computed server-side that
    the raster could contradict.

  * **A shared global grid.** Every province is pinned to the same
    0.0045 degree lattice anchored at (0, 0), so the 38 rasters mosaic without
    resampling and a pixel means the same thing in Riau and in Papua Selatan.

Peat is the weak link and the documentation says so loudly. Neither default is
an official map: OpenLandMap soil carbon over-predicts in Kalimantan, and
PEATGRIDS is a 1 km global model. For a citable peat figure pass the KLHK or
BBSDLP map with --peat-file.

A hotspot or a burn scar inside someone's concession is not evidence that they
lit it. This module counts pixels; attribution is a legal question.

Backend: needs --backend gee.
"""

import csv
import json
import os

from . import LIGHT_BASEMAP
from .fire_history import BURN_IC, FIRMS_IC, PEAT_THR, _peat_mask

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

GRID_DEG = 0.0045               # 500.9 m at the equator; anchored at (0, 0)
BURN_SCALE = 500
HOTSPOT_SCALE = 1000
DEFAULT_START = 2015            # the year of the crisis the record is read against
SEASON_START_MD = "08-01"       # the Indonesian fire season, Aug onward
MAX_YEARS = 16                  # the bitmask is uint16
COUNTRY = "Indonesia"
GAUL1 = "FAO/GAUL/2025/level1"
GAUL_COUNTRY = "GAUL0_NAME"
GAUL_NAME = "GAUL1_NAME"

# The peat columns are inserted after the fourth, one block per definition
# carried -- see csv_fields().
FIELDS = ("province", "land_ha", "burned_ha", "repeat_ha",
          "repeat3_ha", "max_times", "burned_pct_of_land",
          "repeat_share_of_burned_pct", "hotspots_season", "hotspots_baseline",
          "hotspots_ratio")


def slug(name):
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


def grid_transform(deg=GRID_DEG):
    """crs_transform for the shared lattice: [dx, 0, x0, 0, -dy, y0]."""
    return [deg, 0.0, 0.0, 0.0, -deg, 0.0]


# ----------------------------- Earth Engine -----------------------------
def last_complete_year(ic_name=BURN_IC):
    """Last calendar year MCD64A1 covers in full.

    The collection is monthly and runs a few months behind. A year whose
    December is not published yet is not a year you can rank against others.
    """
    import ee
    last = (ee.ImageCollection(ic_name).sort("system:time_start", False)
            .first().get("system:time_start"))
    iso = ee.Date(last).format("YYYY-MM").getInfo()
    y, m = (int(v) for v in iso.split("-"))
    return y if m == 12 else y - 1


def province_names(names=None):
    """Indonesian admin-1 names from GAUL 2025, or the subset asked for."""
    import ee
    fc = ee.FeatureCollection(GAUL1).filter(
        ee.Filter.eq(GAUL_COUNTRY, COUNTRY))
    have = sorted(fc.aggregate_array(GAUL_NAME).getInfo())
    if not names:
        return have
    lower = {n.lower(): n for n in have}
    out, bad = [], []
    for n in names:
        key = n.strip().lower()
        (out.append(lower[key]) if key in lower else bad.append(n))
    if bad:
        raise SystemExit(
            f"not a GAUL 2025 Indonesian province: {', '.join(bad)}\n"
            f"  known: {', '.join(have)}")
    return out


def province_geom(name):
    import ee
    return (ee.FeatureCollection(GAUL1)
            .filter(ee.Filter.eq(GAUL_COUNTRY, COUNTRY))
            .filter(ee.Filter.eq(GAUL_NAME, name)).geometry())


def year_burn(year):
    """Burned-at-least-once mask for a calendar year.

    Guarded against an empty month range: MCD64A1's last months are missing
    for the current year, and ee.ImageCollection.max() over nothing returns a
    band-less image that fails on rename rather than returning zeros.
    """
    import ee
    base = ee.Image(0).rename("burn").byte()
    ic = (ee.ImageCollection(BURN_IC)
          .filterDate(f"{year}-01-01", f"{year + 1}-01-01").select("BurnDate")
          .map(lambda im: im.gt(0).rename("burn").byte())
          .merge(ee.ImageCollection([base])))
    return ic.max().unmask(0).rename("burn")


def burn_bits(years):
    """One uint16: bit i set where the pixel burned in years[i]."""
    import ee
    if len(years) > MAX_YEARS:
        raise SystemExit(f"the bitmask holds {MAX_YEARS} years, not {len(years)}; "
                         "raise --start-year")
    img = ee.Image(0)
    for i, y in enumerate(years):
        img = img.add(year_burn(y).multiply(1 << i))
    return img.toUint16().rename("bits")


def peat_layers(peat_source, peat_file, peat_thr=PEAT_THR):
    """The peat definitions to carry, as [(key, label, ee.Image | None)].

    Both proxies travel by default because measured against the provinces
    where an official figure exists they fail in opposite directions: on Riau,
    OpenLandMap soil carbon gives 3.91 million ha against KLHK's ~4.0 while
    PEATGRIDS gives 5.83; over Kalimantan Tengah they differ from each other
    by 1.35 million ha and both sit well above the official peat area. There
    is no defensible way to pick one, so neither is picked: the burned-peat
    figure is published as the range the two produce.

    A --peat-file leads, because a supplied map -- Gumbricht 2017 or the
    official KLHK one -- is the citable number. It does not silence the
    proxies: they ride behind it, so the reader sees the figure to quote and
    the spread it sits in at once.
    """
    def one(key, path):
        img, label = _peat_mask(key, path, peat_thr)
        return key, label, img

    proxies = ([one("soc", None), one("peatgrids", None)]
               if peat_source == "both" else [one(peat_source, None)])
    if not peat_file:
        return proxies
    # A supplied map is the citable one, so it leads. With --peat-source both
    # the proxies ride along behind it, which is how a reader sees the number
    # to quote and the spread it sits in at the same time.
    return [one("file", peat_file)] + (proxies if peat_source == "both" else [])


def stack(geom, years, peats, inside_fc=None):
    """inside / one band per peat definition / bits, clipped, as uint16.

    `inside_fc` paints a FeatureCollection instead of clipping to a geometry.
    That is how the national overview gets a coastline: GAUL's Indonesia as a
    single union is 2.49 million edges and Earth Engine refuses a geometry
    over two million, but painting the same features into a raster has no such
    limit. Without it the map's bounding box would put Sarawak's and Papua New
    Guinea's fires under a title that says Indonesia.
    """
    import ee
    inside = (ee.Image(1) if inside_fc is None
              else ee.Image(0).paint(inside_fc, 1)).rename("inside")
    bands = [inside]
    for key, _, img in peats:
        bands.append((ee.Image(0) if img is None else img).rename(f"peat_{key}"))
    bands.append(burn_bits(years))
    out = ee.Image.cat(bands).toUint16().clip(geom)
    return out if inside_fc is None else out.updateMask(inside)


def season_hotspots(fc, years, md_start, md_end):
    """FIRMS pixel-days per province for the same calendar window each year.

    Burned area lags by months, so it cannot describe a season still running;
    hotspots can. The window is identical every year, which is the only way a
    part-finished season compares honestly against the record.
    """
    import ee
    out = {}
    for y in years:
        ic = (ee.ImageCollection(FIRMS_IC)
              .filterDate(f"{y}-{md_start}", f"{y}-{md_end}").select("T21"))
        cnt = ic.map(lambda i: i.gt(0)).sum().unmask(0).rename("hs")
        red = cnt.reduceRegions(collection=fc, reducer=ee.Reducer.sum(),
                                scale=HOTSPOT_SCALE)
        # Drop the geometry before it crosses the wire. reduceRegions hands
        # each province's polygon back with its count, and the 38 Indonesian
        # outlines are 2.49 million edges -- a getInfo that returns them is
        # hundreds of megabytes of JSON to carry two numbers per province.
        pairs = red.map(lambda f: ee.Feature(None, {
            "n": f.get(GAUL_NAME), "v": f.get("sum")}))
        rows = pairs.getInfo()["features"]
        out[y] = {f["properties"]["n"]: int(f["properties"].get("v") or 0)
                  for f in rows}
    return out


# ----------------------------- local accounting -----------------------------
def _popcount(nbits=MAX_YEARS):
    import numpy as np
    return np.array([bin(i).count("1") for i in range(1 << nbits)], dtype="uint8")


PEAT_BLOCK_ROWS = 256           # target rows resampled at a time


def _local_peat(peat_file, tif, thr=None, block=PEAT_BLOCK_ROWS):
    """A supplied peat raster as the *fraction* of each fire cell it covers.

    Returns (fraction in 0..1, covered) where `covered` marks the cells the
    supplied raster actually has data for -- outside its extent the fraction
    is zero, which means "not surveyed", not "no peat", and the two must not
    be confused for a province the map does not reach.

    Fraction rather than a nearest-neighbour yes/no, because a supplied map is
    usually much finer than the 500 m fire grid: the 2019 Kalimantan model is
    50 m, so one fire cell holds a hundred of its pixels. Nearest would pick
    one of that hundred and throw the rest away, making each cell's peat
    status close to a coin flip at the edges of a peat dome. Averaging the
    hundred instead turns "is this cell peat" into "how much of it is", which
    is the question the burned-peat area actually needs.

    Nodata is recoded to zero before averaging rather than declared to GDAL.
    Declared, average resampling *skips* nodata, so a cell holding one peat
    pixel and ninety-nine nodata would come back 1.0 instead of 0.01. Here
    nodata means "not peat", so it has to be averaged in as zero.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import reproject, Resampling
    from rasterio.windows import Window, bounds as win_bounds, from_bounds
    with rasterio.open(tif) as ref:
        dst_tr, H, W, crs = ref.transform, ref.height, ref.width, ref.crs
    frac = np.zeros((H, W), dtype="float32")
    covered = np.zeros((H, W), dtype=bool)
    with rasterio.open(peat_file) as src:
        sw, ss, se, sn = src.bounds
        for r0 in range(0, H, block):
            h = min(block, H - r0)
            win = Window(0, r0, W, h)
            sub_tr = rasterio.windows.transform(win, dst_tr)
            w, s, e, n = win_bounds(win, dst_tr)
            if e <= sw or w >= se or n <= ss or s >= sn:
                continue                      # this band is off the map
            sub = from_bounds(w, s, e, n, transform=src.transform)
            sub = sub.round_offsets().round_lengths()
            # one pixel of padding, so an edge cell averages over whole pixels
            sub = Window(sub.col_off - 1, sub.row_off - 1,
                         sub.width + 2, sub.height + 2)
            a = src.read(1, window=sub, boundless=True,
                         fill_value=(src.nodata if src.nodata is not None
                                     else 0))
            m = (a > thr if thr is not None else a > 0).astype("float32")
            out = np.zeros((h, W), dtype="float32")
            reproject(source=m, destination=out,
                      src_transform=rasterio.windows.transform(sub,
                                                               src.transform),
                      src_crs=src.crs, dst_transform=sub_tr, dst_crs=crs,
                      resampling=Resampling.average)
            frac[r0:r0 + h] = out
            # the part of this band the supplied raster actually reaches
            cols = np.arange(W)
            xs = dst_tr.c + (cols + 0.5) * dst_tr.a
            ys = n - (np.arange(h) + 0.5) * abs(dst_tr.e)
            covered[r0:r0 + h] = (((xs >= sw) & (xs <= se))[None, :]
                                  & ((ys >= ss) & (ys <= sn))[:, None])
    return np.clip(frac, 0.0, 1.0), covered


def province_stats(tif, years, peat_keys=("soc", "peatgrids"), peat_file=None,
                   peat_thr=None):
    """Every hectare figure for one province, unpacked from its own raster.

    Deliberately the only place areas are computed. Earth Engine could sum the
    same masks server-side, and the two answers would differ by the projection
    and by how each counts a part-covered pixel -- a disagreement that reaches
    the reader as two numbers for one thing.

    A peat layer is a weight in 0..1, not a flag: the server proxies are 0 or
    1, a supplied raster finer than this grid is the fraction of each cell it
    covers. Where a supplied raster does not reach, its figures come back
    None -- a province the map does not cover has unknown peat, not none.
    """
    import numpy as np
    import rasterio
    from .paddy_island import row_areas_ha
    keys = list(peat_keys)
    with rasterio.open(tif) as ds:
        arr = ds.read()
        ha = row_areas_ha(ds.transform, ds.height)[:, None]
        tr = ds.transform
    if arr.shape[0] != len(keys) + 2:
        raise SystemExit(f"{os.path.basename(tif)} has {arr.shape[0]} bands, "
                         f"not the {len(keys) + 2} these peat definitions need")
    inside = arr[0] > 0
    bits = arr[-1]
    peats = {k: ((arr[i + 1] > 0) & inside).astype("float32")
             for i, k in enumerate(keys)}
    coverage = {k: 1.0 for k in keys}
    if peat_file:
        # A local raster is not in the download -- its band came down as
        # zeros -- so it is read onto this grid now. Only that one band is
        # replaced; any proxies riding with it keep their server values.
        frac, cov = _local_peat(peat_file, tif, thr=peat_thr)
        peats["file"] = frac * inside
        land_px = int(inside.sum())
        coverage["file"] = (float((inside & cov).sum()) / land_px
                            if land_px else 0.0)
    times = _popcount()[bits]
    burned = times >= 1
    rep = times >= 2

    # Rounded once, at the end. Rounding each mask to 0.1 ha and then deriving
    # a share from the rounded pair is how a histogram stops summing to its own
    # total, and how 50% prints as 49.95.
    area = lambda m: float((m * ha).sum())                  # noqa: E731
    by_year = {}
    for i, y in enumerate(years):
        by_year[y] = ((bits >> i) & 1).astype(bool)
    hist = {int(t): area(times == t) for t in range(1, len(years) + 1)
            if (times == t).any()}
    land_ha, burned_ha, rep_ha = area(inside), area(burned), area(rep)
    r1 = lambda v: round(v, 1)                              # noqa: E731
    bp = {k: area(burned * p) for k, p in peats.items()}
    out = {
        "years": list(years),
        "peat_keys": keys,
        "land_ha": r1(land_ha),
        "burned_ha": r1(burned_ha),             # distinct area, burned >= once
        "repeat_ha": r1(rep_ha),
        "repeat3_ha": r1(area(times >= 3)),
        "max_times": int(times.max()),
        "burned_ha_by_year": {y: r1(area(m)) for y, m in by_year.items()},
        "recurrence_ha": {t: r1(v) for t, v in hist.items()},
        "burned_pct_of_land": round(100 * burned_ha / (land_ha or 1), 2),
        "repeat_share_of_burned_pct": round(
            100 * rep_ha / (burned_ha or 1), 1),
        "grid_deg": abs(tr.a),
        "note": ("burned_ha is the distinct area that burned at least once, "
                 "not the sum of the annual figures -- a pixel burning in six "
                 "years is one hectare here and six in that sum"),
    }
    # Per peat definition, never collapsed to one: see peat_layers().
    for k, p in peats.items():
        cv = coverage[k]
        out[f"peat_coverage_pct_{k}"] = round(100 * cv, 1)
        if cv <= 0:
            # The map does not reach this province. Zero would read as "no
            # peat here", which is a different and much stronger claim.
            for f in ("peat_ha", "burned_peat_ha", "repeat_peat_ha",
                      "peat_share_of_burned_pct", "peat_burned_ha_by_year"):
                out[f"{f}_{k}"] = None
            continue
        out[f"peat_ha_{k}"] = r1(area(p))
        out[f"burned_peat_ha_{k}"] = r1(bp[k])
        out[f"repeat_peat_ha_{k}"] = r1(area(rep * p))
        out[f"peat_share_of_burned_pct_{k}"] = round(
            100 * bp[k] / (burned_ha or 1), 1)
        out[f"peat_burned_ha_by_year_{k}"] = {
            y: r1(area(m * p)) for y, m in by_year.items()}
    # Only definitions that actually cover this province span the range. An
    # uncovered one contributes nothing, and letting its zero in would drag
    # every range's floor to 0% the moment one island's map is supplied.
    have = [v for k, v in bp.items() if coverage[k] > 0]
    if have:
        lo, hi = min(have), max(have)
        out["burned_peat_ha_range"] = [r1(lo), r1(hi)]
        out["peat_share_of_burned_pct_range"] = [
            round(100 * lo / (burned_ha or 1), 1),
            round(100 * hi / (burned_ha or 1), 1)]
    else:
        out["burned_peat_ha_range"] = None
        out["peat_share_of_burned_pct_range"] = None
    return out


# ----------------------------- the run -----------------------------
def _usable(path, bands):
    """A raster that opens, has the bands asked for, and whose last one reads.

    A download killed part-way leaves an intact header over missing pixels,
    and a resumable run would treat it as cached for ever. The band count is
    checked too, so a cache written under a different set of peat definitions
    is refetched rather than misread.
    """
    import rasterio
    try:
        with rasterio.open(path) as ds:
            if ds.count != bands:
                return False
            w = rasterio.windows.Window(ds.width - 1, ds.height - 1, 1, 1)
            ds.read(ds.count, window=w)
        return True
    except Exception:       # noqa: BLE001 — any failure means "fetch it again"
        return False


def one_province(name, years, peats, peat_file, out_dir, refresh=False,
                 peat_thr=None):
    """Download (or reuse) one province's stack and derive its statistics."""
    from .gee_utils import download_geotiff
    os.makedirs(out_dir, exist_ok=True)
    keys = [k for k, _, _ in peats]
    labels = {k: lab for k, lab, _ in peats}
    tif = os.path.join(out_dir, "recurrence.tif")
    sjson = os.path.join(out_dir, "stats.json")
    if not refresh and _usable(tif, len(keys) + 2) and os.path.exists(sjson):
        with open(sjson) as f:
            st = json.load(f)
        if (st.get("peat_definitions") == labels
                and st.get("years") == list(years)):
            print(f"  {name}: cached")
            return st
    geom = province_geom(name)
    if download_geotiff(stack(geom, years, peats), geom.bounds(), tif,
                        scale=BURN_SCALE,
                        crs_transform=grid_transform()) is None:
        raise SystemExit(f"{name}: stack download failed")
    st = province_stats(tif, years, peat_keys=keys, peat_file=peat_file,
                        peat_thr=peat_thr)
    st.update(province=name, peat_definitions=labels,
              raster=os.path.relpath(tif, os.path.dirname(out_dir)))
    with open(sjson, "w") as f:
        json.dump(st, f, indent=2)
    rng = st["peat_share_of_burned_pct_range"]
    if not rng:
        share = "n/a"
    else:
        lo, hi = rng
        share = f"{lo:.0f}%" if lo == hi else f"{lo:.0f}–{hi:.0f}%"
    cov = st.get("peat_coverage_pct_file")
    if cov is not None and 0 < cov < 99.5:
        share += f" ({cov:.0f}% terpeta)"
    print(f"  {name}: {st['burned_ha']:>12,.0f} ha burned · "
          f"{st['repeat_share_of_burned_pct']:>4.0f}% berulang · "
          f"{share:>8} gambut")
    return st


def mosaic_bounds(provinces_dir):
    """The extent the downloaded province rasters cover, as [w, s, e, n]."""
    import glob

    import rasterio
    box = None
    for p in sorted(glob.glob(os.path.join(provinces_dir, "*",
                                           "recurrence.tif"))):
        with rasterio.open(p) as ds:
            b = ds.bounds
        box = (b if box is None else
               (min(box[0], b[0]), min(box[1], b[1]),
                max(box[2], b[2]), max(box[3], b[3])))
    if box is None:
        raise SystemExit(f"no province rasters in {provinces_dir}")
    return [float(v) for v in box]


def csv_fields(peat_keys):
    """The table's columns: one peat block per definition carried."""
    per_peat = [f"{c}_{k}" for k in peat_keys for c in
                ("peat_ha", "burned_peat_ha", "repeat_peat_ha",
                 "peat_share_of_burned_pct")]
    return list(FIELDS[:4]) + per_peat + list(FIELDS[4:])


def _write_csv(rows, peat_keys, path):
    fields = csv_fields(peat_keys)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"Table: {os.path.normpath(path)}")


def _hotspot_summary(series, current):
    """Per province: the current window, the prior-year mean, and the ratio."""
    out = {}
    prior = [y for y in series if y != current]
    for name in series.get(current, {}):
        vals = [series[y].get(name, 0) for y in prior]
        base = sum(vals) / len(vals) if vals else 0
        cur = series[current].get(name, 0)
        out[name] = {"hotspots_season": cur,
                     "hotspots_baseline": round(base, 1),
                     "hotspots_ratio": round(cur / base, 2) if base else None}
    return out


# ----------------------------- rendering -----------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _render_map(tif, run_dir, years, nbands):
    """The national recurrence map: how many years each pixel burned."""
    import numpy as np
    import rasterio
    from matplotlib.colors import ListedColormap, BoundaryNorm
    plt = _plt()
    with rasterio.open(tif) as ds:
        bits = ds.read(nbands)              # bits is always the last band
        w, s, e, n = ds.bounds
    a = _popcount()[bits].astype("float64")
    a[a <= 0] = np.nan
    top = max(int(np.nanmax(a)) if np.isfinite(a).any() else 1, 1)
    # Start a third of the way into YlOrRd. At 2 km over a country, burned
    # pixels are a thin scatter, and the pale end of the ramp disappears
    # against a light basemap -- the once-burned class, which is most of the
    # area, would simply not be on the map.
    src = plt.get_cmap("YlOrRd")
    colors = [src(0.33 + 0.67 * i / max(top - 1, 1)) for i in range(top)]
    cmap = ListedColormap(colors); cmap.set_bad((0, 0, 0, 0))
    norm = BoundaryNorm(np.arange(0.5, top + 1.5, 1), cmap.N)
    fig, ax = plt.subplots(figsize=(16, 7), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.set_xlim(w, e); ax.set_ylim(s, n)
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=LIGHT_BASEMAP,
                       attribution_size=5)
    except Exception as ex:   # noqa: BLE001
        print(f"  (basemap skipped: {ex.__class__.__name__})")
    im = ax.imshow(a, extent=[w, e, s, n], origin="upper", cmap=cmap,
                   norm=norm, interpolation="nearest", zorder=2)
    cb = fig.colorbar(im, ax=ax, fraction=0.022, pad=0.01,
                      ticks=range(1, top + 1))
    cb.set_label(f"jumlah tahun terbakar, {years[0]}–{years[-1]}", fontsize=9)
    ax.set_title(f"Keberulangan kebakaran Indonesia, {years[0]}–{years[-1]}\n"
                 "MODIS MCD64A1 — piksel merah tua terbakar berkali-kali",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.3)
    fig.tight_layout()
    out = os.path.join(run_dir, "fire_recurrence_national.png")
    fig.savefig(out, facecolor="#faf8f4"); plt.close(fig)
    print(f"Map: {os.path.normpath(out)}")


def _render_ranking(rows, run_dir, years, peat_keys, top=20):
    """Provinces ranked by repeat-burn area, split peat vs mineral.

    The peat split is drawn as the band the two peat definitions span, not as
    a line: a solid bar to the lower figure, hatched out to the higher one.
    Drawing the mean would invent a precision neither proxy supports.
    """
    import numpy as np
    plt = _plt()
    rs = sorted(rows, key=lambda r: -r["repeat_ha"])[:top]
    names = [r["province"] for r in rs]
    y = np.arange(len(rs))
    # A definition that does not reach a province contributes nothing to its
    # bar rather than a zero, which would draw as "no peat burned here".
    pk = [[r[f"repeat_peat_ha_{k}"] / 1e3 for k in peat_keys
           if r.get(f"repeat_peat_ha_{k}") is not None] or [0.0] for r in rs]
    lo = [min(v) for v in pk]
    hi = [max(v) for v in pk]
    rep = [r["repeat_ha"] / 1e3 for r in rs]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 0.42 * len(rs) + 2.6),
                                 dpi=150, gridspec_kw={"width_ratios": [2, 1]})
    fig.patch.set_facecolor("#faf8f4")
    a1.barh(y, rep, color="#fdae6b", label="Tanah mineral")
    a1.barh(y, lo, color="#7f2704", label="Gambut (batas bawah)")
    if any(h > l for h, l in zip(hi, lo)):
        a1.barh(y, [h - l for h, l in zip(hi, lo)], left=lo, color="#7f2704",
                alpha=0.45, hatch="///", edgecolor="#7f2704", linewidth=0,
                label="selisih dua definisi gambut")
    a1.set_yticks(y); a1.set_yticklabels(names, fontsize=9); a1.invert_yaxis()
    a1.set_xlabel("ribu ha terbakar ≥ 2 tahun", fontsize=9)
    a1.set_title("Luas terbakar berulang", fontsize=11, fontweight="bold",
                 loc="left")
    a1.legend(fontsize=8, loc="lower right")
    a1.grid(True, axis="x", ls=":", alpha=0.35)
    share = [r["repeat_share_of_burned_pct"] for r in rs]
    a2.barh(y, share, color="#b30000")
    a2.set_yticks(y); a2.set_yticklabels([]); a2.invert_yaxis()
    a2.set_xlabel("% area terbakar yang terbakar lagi", fontsize=9)
    a2.set_title("Porsi berulang", fontsize=11, fontweight="bold", loc="left")
    for i, v in enumerate(share):
        a2.text(v + 0.6, i, f"{v:.0f}%", va="center", fontsize=8)
    a2.grid(True, axis="x", ls=":", alpha=0.35)
    fig.suptitle(f"Kebakaran berulang per provinsi, {years[0]}–{years[-1]}",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(run_dir, "fire_national_ranking.png")
    fig.savefig(out, facecolor="#faf8f4"); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


def _render_season(hot, run_dir, window, current, top=15):
    """The running season against the same window in every prior year."""
    import numpy as np
    plt = _plt()
    rs = sorted(hot.items(), key=lambda kv: -kv[1]["hotspots_season"])[:top]
    if not rs or not rs[0][1]["hotspots_season"]:
        print("  (season chart skipped: no hotspots in the window)")
        return
    names = [k for k, _ in rs]
    y = np.arange(len(rs))
    cur = [v["hotspots_season"] for _, v in rs]
    base = [v["hotspots_baseline"] for _, v in rs]
    fig, ax = plt.subplots(figsize=(11, 0.42 * len(rs) + 2.4), dpi=150)
    fig.patch.set_facecolor("#faf8f4")
    ax.barh(y - 0.2, cur, height=0.4, color="#b30000", label=f"{current}")
    ax.barh(y + 0.2, base, height=0.4, color="#c8c4b8",
            label="rata-rata tahun sebelumnya")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=9); ax.invert_yaxis()
    ax.set_xlabel("titik panas (piksel-hari, FIRMS)", fontsize=9)
    for i, (_, v) in enumerate(rs):
        if v["hotspots_ratio"]:
            ax.text(max(cur[i], base[i]) * 1.02, i, f"×{v['hotspots_ratio']:.1f}",
                    va="center", fontsize=8, fontweight="bold", color="#b30000")
    ax.set_title(f"Musim berjalan vs rekor — {window}\n"
                 "jendela tanggal yang sama setiap tahun",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(True, axis="x", ls=":", alpha=0.35)
    fig.tight_layout()
    out = os.path.join(run_dir, "fire_national_season.png")
    fig.savefig(out, facecolor="#faf8f4"); plt.close(fig)
    print(f"Chart: {os.path.normpath(out)}")


# ----------------------------- entry point -----------------------------
def run(backend, name, run_dir, run_id, config_key=None,
        start_year=DEFAULT_START, end_year=None, provinces=None,
        peat_file=None, peat_thr=PEAT_THR, peat_source="both",
        peat_raster_thr=None, season_start=SEASON_START_MD, season_end=None,
        overview_km=2.0, refresh=False, **_):
    """National fire recurrence + peat, province by province (GEE)."""
    for mod in ("numpy", "matplotlib", "rasterio"):
        try:
            __import__(mod)
        except ImportError:
            raise SystemExit(
                f"fire-national needs {mod}: pip install 'earthchange[maps]'")
    if backend == "mpc":
        raise SystemExit("fire-national needs --backend gee (MODIS MCD64A1).")
    import datetime as _dt
    import ee
    from .gee_utils import download_geotiff, initialize_ee
    initialize_ee(config_key)

    end_year = int(end_year) if end_year else last_complete_year()
    start_year = int(start_year)
    if end_year < start_year:
        raise SystemExit(f"--end-year {end_year} is before --start-year {start_year}")
    years = list(range(start_year, end_year + 1))
    if len(years) > MAX_YEARS:
        raise SystemExit(f"at most {MAX_YEARS} years fit the bitmask; "
                         f"asked for {len(years)}")

    local_peat = bool(peat_file) and peat_file.lower().endswith((".tif", ".tiff", ".vrt"))
    peats = peat_layers(peat_source, peat_file, peat_thr)
    peat_keys = [k for k, _, _ in peats]
    names = province_names(provinces)
    today = _dt.date.today()
    season_end = season_end or today.strftime("%m-%d")

    for _, lab, _ in peats:
        print(f"  {lab}")
    if local_peat:
        cut = (f"> {peat_raster_thr:g}" if peat_raster_thr is not None
               else "> 0")
        print(f"  supplied raster counted as peat where {cut}, averaged to "
              f"the fraction of each {GRID_DEG * 111320:.0f} m cell it covers")
    if len(peats) > 1:
        print("  all are carried: the burned-peat figure is published as the "
              "range they span, not as one of them")
    print(f"  recurrence {years[0]}–{years[-1]} ({len(years)} complete years), "
          f"{len(names)} provinces, grid {GRID_DEG}° (~{GRID_DEG * 111320:.0f} m)")

    pdir = os.path.join(run_dir, "provinces")
    os.makedirs(pdir, exist_ok=True)
    rows, failed = [], []
    for i, p in enumerate(names, 1):
        print(f"[{i}/{len(names)}] {p}")
        try:
            rows.append(one_province(p, years, peats,
                                     peat_file if local_peat else None,
                                     os.path.join(pdir, slug(p)), refresh,
                                     peat_thr=peat_raster_thr))
        except SystemExit as e:
            print(f"  skipped: {e}"); failed.append(p)
        except Exception as e:      # noqa: BLE001 — one province must not end the run
            print(f"  skipped: {e.__class__.__name__}: {e}"); failed.append(p)
    if not rows:
        raise SystemExit("no province produced output.")

    # The running season, from hotspots: burned area cannot describe it yet.
    fc = ee.FeatureCollection(GAUL1).filter(ee.Filter.eq(GAUL_COUNTRY, COUNTRY))
    if provinces:
        fc = fc.filter(ee.Filter.inList(GAUL_NAME, names))
    hyears = list(range(start_year, today.year + 1))
    window = (f"{season_start} – {season_end}")
    print(f"  hotspots {window}, {hyears[0]}–{hyears[-1]} (FIRMS)")
    try:
        series = season_hotspots(fc, hyears, season_start, season_end)
        hot = _hotspot_summary(series, today.year)
    except Exception as e:          # noqa: BLE001 — the recurrence product stands alone
        print(f"  (hotspot series skipped: {e.__class__.__name__}: {e})")
        series, hot = {}, {}

    # A coarse national raster, only so the map does not need 38 files open.
    # The land comes from painting the provinces -- see stack(). An overview,
    # not an accounting layer: every hectare published comes from the 500 m
    # per-province rasters.
    #
    # The extent is read off those rasters rather than asked of Earth Engine.
    # fc.geometry() unions 2.49 million edges and is refused, and an
    # ErrorMargin does not save it -- the union is evaluated before the margin
    # is applied, so the request fails before it can be simplified.
    over = os.path.join(run_dir, "fire_recurrence_overview.tif")
    deg = overview_km * 1000 / 111320.0
    country = ee.Geometry.Rectangle(mosaic_bounds(pdir), proj="EPSG:4326",
                                    geodesic=False)
    if download_geotiff(stack(country, years, peats, inside_fc=fc), country, over,
                        scale=overview_km * 1000,
                        crs_transform=[deg, 0, 0, 0, -deg, 0]) is not None:
        _render_map(over, run_dir, years, len(peats) + 2)
    _render_ranking(rows, run_dir, years, peat_keys)
    if hot:
        _render_season(hot, run_dir, window, today.year)

    flat = [{**r, **hot.get(r["province"], {})} for r in rows]
    _write_csv(flat, peat_keys, os.path.join(run_dir, "provinces.csv"))

    keys = ["land_ha", "burned_ha", "repeat_ha", "repeat3_ha"]
    tot = {k: round(sum(r[k] for r in rows), 1) for k in keys}
    # A peat definition is totalled only over the provinces it reaches, and
    # the national figure says how much of the burned area that was. A
    # one-island map summed as if it were national would read as a country
    # with almost no peat.
    reach = {}
    for k in peat_keys:
        got = [r for r in rows if r.get(f"burned_peat_ha_{k}") is not None]
        for c in ("peat_ha", "burned_peat_ha", "repeat_peat_ha"):
            tot[f"{c}_{k}"] = round(sum(r[f"{c}_{k}"] for r in got), 1)
        reach[k] = {
            "provinces": len(got),
            "burned_ha_covered": round(sum(r["burned_ha"] for r in got), 1),
            "pct_of_national_burned": round(
                100 * sum(r["burned_ha"] for r in got)
                / (tot["burned_ha"] or 1), 1)}
    full = [k for k in peat_keys if reach[k]["provinces"] == len(rows)]
    bp = [tot[f"burned_peat_ha_{k}"] for k in (full or peat_keys)]
    stats = {
        "run_id": run_id, "scenario": "fire-national", "name": name,
        "dataset": "MODIS MCD64A1 burned area (500 m) + FIRMS hotspots",
        "peat_definitions": {k: lab for k, lab, _ in peats},
        "years": years, "grid_deg": GRID_DEG,
        "provinces_run": [r["province"] for r in rows], "provinces_failed": failed,
        "national": tot,
        "burned_pct_of_land": round(100 * tot["burned_ha"] / (tot["land_ha"] or 1), 2),
        "burned_peat_ha_range": [min(bp), max(bp)],
        "peat_share_of_burned_pct_range": [
            round(100 * min(bp) / (tot["burned_ha"] or 1), 1),
            round(100 * max(bp) / (tot["burned_ha"] or 1), 1)],
        "peat_range_from": full or list(peat_keys),
        "peat_coverage": reach,
        "repeat_share_of_burned_pct": round(
            100 * tot["repeat_ha"] / (tot["burned_ha"] or 1), 1),
        "by_province": {r["province"]: r for r in flat},
        "hotspot_window": window,
        "hotspots_by_year": {str(y): v for y, v in series.items()},
        "hotspots_national_by_year": {str(y): sum(v.values())
                                      for y, v in series.items()},
        "caveats": [
            "A burn scar or hotspot inside a concession is not evidence that "
            "the concession holder lit it. These are screening layers.",
            "Peat is " + " and ".join(lab for _, lab, _ in peats) +
            " — neither is an official KLHK/BBSDLP map, and on the provinces "
            "where an official figure exists they fail in opposite directions, "
            "so the burned-peat figure is a range. Pass the official map with "
            "--peat-file for a citable single number.",
            f"MCD64A1 is 500 m: fires smaller than a few hectares are missed, "
            "so these are lower bounds, most severely for smallholder burning.",
            "burned_ha is the distinct area that burned at least once over the "
            "whole period, not the sum of the annual figures.",
            "Hotspots are FIRMS/MODIS pixel-days at 1 km, a detection count "
            "and not an area; VIIRS at 375 m would resolve more.",
        ],
    }
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    lo, hi = stats["peat_share_of_burned_pct_range"]
    gam = f"{lo:.0f}%" if lo == hi else f"{lo:.0f}–{hi:.0f}%"
    print(f"\nNasional {years[0]}–{years[-1]}: {tot['burned_ha']:,.0f} ha terbakar "
          f"({stats['burned_pct_of_land']:.1f}% daratan), "
          f"{gam} di gambut, "
          f"{stats['repeat_share_of_burned_pct']:.0f}% terbakar berulang")
    print(f"  {tot['repeat_ha']:,.0f} ha terbakar ≥2 tahun · "
          f"{tot['repeat3_ha']:,.0f} ha ≥3 tahun")
    nat_hs = stats["hotspots_national_by_year"]
    if nat_hs and str(today.year) in nat_hs:
        cur = nat_hs[str(today.year)]
        prior = {y: v for y, v in nat_hs.items() if y != str(today.year)}
        if prior:
            worst = max(prior, key=prior.get)
            print(f"  titik panas {window} {today.year}: {cur:,} piksel-hari · "
                  f"×{cur / (sum(prior.values()) / len(prior)):.1f} rata-rata · "
                  f"tahun terburuk sebelumnya {worst} ({prior[worst]:,})")
    top = sorted(rows, key=lambda r: -r["repeat_ha"])[:5]
    for r in top:
        print(f"    {r['province']:<24}{r['repeat_ha']:>12,.0f} ha berulang "
              f"({r['repeat_share_of_burned_pct']:.0f}% dari yang terbakar)")
    if failed:
        print(f"  gagal: {', '.join(failed)} — jalankan ulang untuk melanjutkan")
    return stats
