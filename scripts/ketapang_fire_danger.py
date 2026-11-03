#!/usr/bin/env python3
"""Fire danger on the Ketapang coast, 2014-2026: why did 2026 burn, and when?

The Canadian Fire Weather Index (FWI) System, which BMKG runs operationally
as Indonesia's SPBK / SPARTAN, computed day by day from ERA5-Land noon
weather at three points over the four concessions (PT SPAS/SKM, PT MKK,
PT AM). Same equations (Van Wagner 1987), equatorial day-length factors
(Le 9.0, Lf 1.4) and BMKG class breaks as earthchange/fire_danger.py; that
module maps one date across an area, this one needs long daily series, so
the codes are run locally on series pulled once from Earth Engine.

WHAT IT ANSWERS
  timing      the day DC, BUI and FFMC crossed BMKG's High and Extreme breaks
              in 2026, against the day burning took off (VIIRS)
  severity    2026's DC against every year since 2014, with 2015, 2019 and
              2023 (the last three big fire years) drawn for comparison
  response    MODIS FIRMS detections per day over the AOI against DC,
              2014-2026: the DC above which this coast burns
  ignitions   the danger class on the day of each 2026 ignition (from
              ketapang_fire_origin.py) against the share of days in that
              class -- inside the four concessions and outside

WHAT IT CANNOT ANSWER. Fire weather says when the landscape could burn and
how hard; it is the same inside a concession and across its boundary. It does
not explain why peat inside burned 1.5-2x more than peat outside (fuel and
drainage do), and it says nothing about who lit the fires. ERA5-Land is a
~9 km reanalysis: rain from a local storm can be missed. FWI is defined for
surface fuels; on peat DC is used as a proxy for the drying of the upper
organic layer, not a measured water table.

    conda run -n base python scripts/ketapang_fire_danger.py
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

from earthchange.fire_danger import (BMKG_BREAKS, BMKG_COLOURS,  # noqa: E402
                                     DMC_LE_EQ, DC_LF_EQ, ERA5_HOURLY,
                                     FFMC_START, DMC_START, DC_START)
from ketapang_fire_origin import OUT as ORIGIN, START, END, SEASON  # noqa: E402

OUT = os.path.join(ORIGIN, "danger")
POINTS = {"PT SPAS/SKM": (110.10, -1.68), "PT MKK": (110.19, -1.95),
          "PT AM": (110.45, -2.00)}
Y0, Y1 = 2014, 2026
NOON_UTC = 5                     # local solar noon at 110 E is ~04:40 UTC
FIRE_YEARS = (2015, 2019, 2023)
AOI = (109.84, -2.27, 110.74, -1.27)


# ----------------------------- Earth Engine -----------------------------
def era5_series(year, cache):
    """Hourly t, td, u, v, precip at each point for one year (getRegion)."""
    import ee
    import pandas as pd
    p = os.path.join(cache, f"era5_{year}.csv")
    if os.path.exists(p):
        return pd.read_csv(p, parse_dates=["time"])
    bands = ["temperature_2m", "dewpoint_temperature_2m",
             "u_component_of_wind_10m", "v_component_of_wind_10m",
             "total_precipitation_hourly"]
    frames = []
    # quarters: a whole year in one getRegion can exceed EE's memory limit
    for q0, q1 in (("01-01", "04-01"), ("04-01", "07-01"), ("07-01", "10-01"),
                   ("10-01", None)):
        end = f"{year}-{q1}" if q1 else f"{year + 1}-01-01"
        ic = ee.ImageCollection(ERA5_HOURLY).filterDate(f"{year}-{q0}", end) \
            .select(bands)
        if ic.size().getInfo() == 0:
            continue
        for name, (lon, lat) in POINTS.items():
            rows = ic.getRegion(ee.Geometry.Point(lon, lat), 11132).getInfo()
            df = pd.DataFrame(rows[1:], columns=rows[0])
            df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
            df["point"] = name
            frames.append(df[["time", "point"] + bands])
    out = pd.concat(frames)
    out.to_csv(p, index=False)
    print(f"  ERA5-Land {year}: {len(out):,} rows")
    return out


def firms_daily(year, cache):
    """MODIS FIRMS (conf >= 30) detections per day over AOI."""
    import ee
    import pandas as pd
    p = os.path.join(cache, f"firms_{year}.csv")
    if os.path.exists(p):
        return pd.read_csv(p, parse_dates=["date"])
    from earthchange.fire_hotspot import _points
    pts = _points(ee, ee.ImageCollection("FIRMS"), ee.Date(f"{year}-01-01"),
                  ee.Date(f"{year}-12-31"),
                  ee.Geometry.Rectangle(list(AOI), None, False), 30)
    df = pd.DataFrame(pts, columns=["lon", "lat", "confidence", "date"])
    d = df.groupby("date").size().rename("n").reset_index()
    d["date"] = pd.to_datetime(d.date)
    d.to_csv(p, index=False)
    print(f"  FIRMS {year}: {len(df):,} detections")
    return d


def chirps_check():
    """Independent rain check (CHIRPS, gauge-blended): ERA5-Land's long rain-
    free spell drives DC; confirm it is in the station-informed record too."""
    import ee
    import pandas as pd
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(*p), {"n": n})
                                for n, p in POINTS.items()])
    ic = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    rows = []
    for y in range(Y0, Y1 + 1):
        for lo, hi, tag in ((f"{y}-07-01", f"{y}-09-16", "jul1_sep15_mm"),
                            (f"{y}-06-01", f"{y}-11-01", "jun_oct_mm")):
            c = ic.filterDate(lo, hi)
            v = c.sum().reduceRegions(pts, ee.Reducer.first(), 5566) \
                .aggregate_mean("first").getInfo()
            rows.append({"year": y, "window": tag, "mm": v,
                         "days": c.size().getInfo()})
    d = pd.DataFrame(rows).pivot(index="year", columns="window", values="mm")
    d["days_in_jun_oct"] = pd.DataFrame(rows).query("window=='jun_oct_mm'") \
        .set_index("year").days
    return d


# ------------------------------- FWI codes ------------------------------
def ffmc(f0, t, h, w, r):
    import math
    mo = 147.2 * (101 - f0) / (59.5 + f0)
    if r > 0.5:
        rf = r - 0.5
        add = 42.5 * rf * math.exp(-100 / (251 - mo)) * (1 - math.exp(-6.93 / rf))
        if mo > 150:
            add += 0.0015 * (mo - 150) ** 2 * math.sqrt(rf)
        mo = min(mo + add, 250)
    ed = (0.942 * h ** 0.679 + 11 * math.exp((h - 100) / 10)
          + 0.18 * (21.1 - t) * (1 - math.exp(-0.115 * h)))
    if mo > ed:
        ko = (0.424 * (1 - (h / 100) ** 1.7)
              + 0.0694 * math.sqrt(w) * (1 - (h / 100) ** 8))
        m = ed + (mo - ed) * 10 ** (-(ko * 0.581 * math.exp(0.0365 * t)))
    else:
        ew = (0.618 * h ** 0.753 + 10 * math.exp((h - 100) / 10)
              + 0.18 * (21.1 - t) * (1 - math.exp(-0.115 * h)))
        if mo < ew:
            k1 = (0.424 * (1 - ((100 - h) / 100) ** 1.7)
                  + 0.0694 * math.sqrt(w) * (1 - ((100 - h) / 100) ** 8))
            m = ew - (ew - mo) * 10 ** (-(k1 * 0.581 * math.exp(0.0365 * t)))
        else:
            m = mo
    return min(max(59.5 * (250 - m) / (147.2 + m), 0), 101)


def dmc(p0, t, h, r, le=DMC_LE_EQ):
    import math
    t = max(t, -1.1)
    rk = 1.894 * (t + 1.1) * (100 - h) * le * 1e-4
    pr = p0
    if r > 1.5:
        rw = 0.92 * r - 1.27
        wmi = 20 + 280 / math.exp(0.023 * p0)
        if p0 <= 33:
            b = 100 / (0.5 + 0.3 * p0)
        elif p0 <= 65:
            b = 14 - 1.3 * math.log(p0)
        else:
            b = 6.2 * math.log(p0) - 17.2
        wmr = wmi + 1000 * rw / (48.77 + b * rw)
        pr = max(244.72 - 43.43 * math.log(wmr - 20), 0)
    return max(pr + rk, 0)


def dc(d0, t, r, lf=DC_LF_EQ):
    import math
    t = max(t, -2.8)
    pe = max((0.36 * (t + 2.8) + lf) / 2, 0)
    dr = d0
    if r > 2.8:
        rw = 0.83 * r - 1.27
        smi = 800 * math.exp(-d0 / 400)
        dr = max(d0 - 400 * math.log(1 + 3.937 * rw / smi), 0)
    return max(dr + pe, 0)


def isi(f, w):
    import math
    mo = 147.2 * (101 - f) / (59.5 + f)
    ff = 19.115 * math.exp(-0.1386 * mo) * (1 + mo ** 5.31 / 4.93e7)
    return ff * math.exp(0.05039 * w)


def bui(p, d):
    if p == 0 and d == 0:
        return 0.0
    if p <= 0.4 * d:
        u = 0.8 * p * d / (p + 0.4 * d)
    else:
        u = p - (1 - 0.8 * d / (p + 0.4 * d)) * (0.92 + (0.0114 * p) ** 1.7)
    return max(u, 0)


def fwi(i, u):
    import math
    if u <= 80:
        bb = 0.1 * i * (0.626 * u ** 0.809 + 2)
    else:
        bb = 0.1 * i * (1000 / (25 + 108.64 * math.exp(-0.023 * u)))
    return bb if bb <= 1 else math.exp(2.72 * (0.434 * math.log(bb)) ** 0.647)


def daily_codes(h):
    """Hourly ERA5 at one point -> daily noon codes, run continuously."""
    import numpy as np
    import pandas as pd
    h = h.sort_values("time").set_index("time")
    rain_mm = h["total_precipitation_hourly"] * 1000
    noon = h[h.index.hour == NOON_UTC].copy()
    t = noon["temperature_2m"] - 273.15
    td = noon["dewpoint_temperature_2m"] - 273.15

    def sat(x):
        return np.exp(17.625 * x / (x + 243.04))
    rh = (100 * sat(td) / sat(t)).clip(0, 100)
    wind = np.hypot(noon["u_component_of_wind_10m"],
                    noon["v_component_of_wind_10m"]) * 3.6
    # 24 h rain ending at noon: hourly ERA5 accumulations end at the stamp
    r24 = rain_mm.rolling("24h", closed="right").sum().reindex(noon.index)
    out, f0, p0, d0 = [], FFMC_START, DMC_START, DC_START
    for ts, tt, hh, ww, rr in zip(noon.index, t, rh, wind, r24.fillna(0)):
        f0 = ffmc(f0, tt, hh, ww, rr)
        p0 = dmc(p0, tt, hh, rr)
        d0 = dc(d0, tt, rr)
        i = isi(f0, ww)
        u = bui(p0, d0)
        out.append({"date": (ts + pd.Timedelta(hours=7)).normalize().tz_localize(None),
                    "t": tt, "rh": hh, "wind": ww, "rain": rr, "FFMC": f0,
                    "DMC": p0, "DC": d0, "ISI": i, "BUI": u, "FWI": fwi(i, u)})
    return pd.DataFrame(out)


def bmkg_class(code, v):
    import numpy as np
    b = BMKG_BREAKS[code]
    return np.digitize(v, b)          # 0 low, 1 moderate, 2 high, 3 extreme


CLASS_NAMES = ["low", "moderate", "high", "extreme"]


# -------------------------------- figures -------------------------------
def fig_2026(codes, det, ign, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    c = codes[codes.date.dt.year == 2026]
    days = pd.date_range("2026-01-01", c.date.max())
    fig, ax = plt.subplots(4, 1, figsize=(12, 10.5), sharex=True, dpi=150,
                           gridspec_kw={"height_ratios": [1.3, 1, 0.7, 1.2]})
    for k, (code, a) in enumerate((("DC", ax[0]), ("FFMC", ax[1]))):
        b = BMKG_BREAKS[code]
        lo, hi = (0, 800) if code == "DC" else (40, 100)
        edges = [lo] + b + [hi]
        for j in range(4):
            a.axhspan(edges[j], edges[j + 1], color=BMKG_COLOURS[j], alpha=0.12)
        a.plot(c.date, c[code], color="black", lw=1.2)
        a.set_ylim(lo, max(hi, c[code].max() * 1.05) if code == "DC" else hi)
        a.set_ylabel(code, rotation=0, ha="right", weight="bold")
    ax[0].set_title("Ketapang coast 2026: fire danger (FWI System, BMKG classes) "
                    "and fire activity", loc="left")
    ax[2].bar(c.date, c.rain, color="#2f7fd1", width=1)
    ax[2].set_ylabel("rain\nmm/day", rotation=0, ha="right")
    d = det.groupby(["date", "zone"]).size().unstack(fill_value=0).reindex(days, fill_value=0)
    ax[3].bar(d.index, d.get("inside the four", 0), color="#b3001b", width=1,
              label="VIIRS detections inside the four concessions")
    ax[3].bar(d.index, d.get("outside", 0), bottom=d.get("inside the four", 0),
              color="#f08a24", width=1, label="elsewhere in the AOI")
    ig = ign.groupby("date").size().reindex(days, fill_value=0)
    a2 = ax[3].twinx()
    a2.plot(ig.index, ig, color="black", lw=0.7, drawstyle="steps-mid",
            label="new ignitions (right)")
    ax[3].set_ylabel("detections\n/day", rotation=0, ha="right")
    h1, l1 = ax[3].get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    ax[3].legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=False)
    for a in ax:
        a.margins(x=0)
    fig.text(0.01, 0.005, "Weather: ERA5-Land noon, mean of 3 points over the "
             "concessions. Classes: BMKG SPARTAN breaks (blue low, green "
             "moderate, yellow high, red extreme). Fire: VIIRS 375 m.",
             fontsize=7, color="#444")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


def fig_years(codes, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    c = codes.copy()
    c["doy"] = c.date.dt.dayofyear
    c["year"] = c.date.dt.year
    base = c[(c.year >= Y0 + 1) & (c.year <= 2025)]
    q = base.groupby("doy").DC.quantile([0.1, 0.5, 0.9]).unstack()
    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=150)
    ax.fill_between(q.index, q[0.1], q[0.9], color="#bbb", alpha=0.5,
                    label=f"{Y0 + 1}-2025, 10th-90th percentile")
    ax.plot(q.index, q[0.5], color="#777", lw=1, label="median")
    cols = {2015: "#7b3294", 2019: "#c2a5cf", 2023: "#008837", 2026: "#d7191c"}
    for y, col in cols.items():
        s = c[c.year == y]
        ax.plot(s.doy, s.DC, color=col, lw=2.2 if y == 2026 else 1.4, label=str(y))
    for j, v in enumerate(BMKG_BREAKS["DC"]):
        ax.axhline(v, color=BMKG_COLOURS[j + 1], lw=0.8, ls="--")
    ax.text(3, BMKG_BREAKS["DC"][2] + 8, "BMKG extreme (DC 350)", fontsize=8,
            color="#e03131")
    ax.set_xticks([1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335])
    ax.set_xticklabels("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())
    ax.set_ylabel("Drought Code (DC)")
    ax.set_title("Deep drying on the Ketapang coast: 2026 against the fire years "
                 "and the 2015-2025 range", loc="left")
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.margins(x=0)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


def fig_response(resp, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
    ax.bar(range(len(resp)), resp.share_days_ge10, color="#e03131")
    ax.set_xticks(range(len(resp)))
    ax.set_xticklabels(resp.index.astype(str), rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("share of days with ≥10 MODIS detections")
    ax2 = ax.twinx()
    ax2.plot(range(len(resp)), resp.mean_detections, color="black", marker="o")
    ax2.set_ylabel("mean detections / day")
    ax.set_xlabel("Drought Code on the day")
    for j, v in enumerate(BMKG_BREAKS["DC"]):
        pass
    ax.set_title("How this coast responds to drying, 2014-2026 (MODIS FIRMS)",
                 loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")


# --------------------------------- main ---------------------------------
def main():
    import numpy as np
    import pandas as pd
    import rasterio  # noqa: F401
    from earthchange.gee_utils import initialize_ee
    initialize_ee()

    cache = os.path.join(OUT, "cache")
    os.makedirs(cache, exist_ok=True)
    print("ERA5-Land hourly ...")
    hourly = pd.concat([era5_series(y, cache) for y in range(Y0, Y1 + 1)])
    hourly["time"] = pd.to_datetime(hourly.time, utc=True)
    per_pt = []
    for name, h in hourly.groupby("point"):
        d = daily_codes(h)
        d["point"] = name
        per_pt.append(d)
    pts = pd.concat(per_pt)
    pts.to_csv(os.path.join(OUT, "fwi_daily_by_point.csv"), index=False)
    codes = pts.groupby("date")[["t", "rh", "wind", "rain", "FFMC", "DMC", "DC",
                                 "ISI", "BUI", "FWI"]].mean().reset_index()
    codes = codes[codes.date >= f"{Y0}-03-01"]          # 60-day DC spin-up
    for k in ("FFMC", "DC", "BUI", "FWI"):
        codes[f"{k}_class"] = bmkg_class(k, codes[k])
    codes.to_csv(os.path.join(OUT, "fwi_daily_mean.csv"), index=False)

    # ---- timing in 2026
    c26 = codes[codes.date.dt.year == 2026]
    first = {}
    for k in ("DC", "BUI", "FFMC", "FWI"):
        for j, nm in ((2, "high"), (3, "extreme")):
            s = c26[c26[f"{k}_class"] >= j]
            first[f"{k}_first_{nm}"] = str(s.date.min().date()) if len(s) else None
        first[f"{k}_days_extreme_2026"] = int((c26[f"{k}_class"] == 3).sum())
    first["DC_peak_2026"] = float(c26.DC.max())
    first["DC_peak_date_2026"] = str(c26.loc[c26.DC.idxmax(), "date"].date())

    det = pd.read_csv(os.path.join(ORIGIN, f"viirs_{START}_{END}.csv"))
    det = det[det.confidence >= 1].copy()
    det["time"] = pd.to_datetime(det.acq_epoch, unit="s", utc=True).dt.tz_convert("Asia/Pontianak")
    det["date"] = det.time.dt.tz_localize(None).dt.normalize()
    ign = pd.read_csv(os.path.join(ORIGIN, "ignitions.csv"))
    ign["date"] = pd.to_datetime(ign.date)
    four = ["PT AM", "PT SKM", "PT MKK", "PT SPAS"]
    # detection zone via the ignition table's labels is not available for all
    # detections; use the concession polygons
    import geopandas as gpd
    from ketapang_fire_origin import CONC, FOUR
    conc = gpd.read_file(CONC).to_crs(4326)
    g4 = conc[conc.company.str.contains("|".join(FOUR.values()), na=False)]
    gd = gpd.GeoDataFrame(det, geometry=gpd.points_from_xy(det.lon, det.lat), crs=4326)
    inside = gpd.sjoin(gd[["geometry"]], g4[["geometry"]], predicate="within", how="left")
    inside = inside[~inside.index.duplicated()]
    det["zone"] = np.where(inside.index_right.notna(), "inside the four", "outside")

    daily = det.groupby("date").size()
    big = daily[daily >= 100]
    first["first_day_ge100_viirs_2026"] = str(big.index.min().date()) if len(big) else None
    first["first_day_ge20_viirs_jun_on"] = str(
        daily[(daily >= 20) & (daily.index >= "2026-06-01")].index.min().date())

    # ---- severity by year
    codes["year"] = codes.date.dt.year
    by_year = codes.groupby("year").agg(
        DC_peak=("DC", "max"), DC_days_extreme=("DC_class", lambda s: int((s == 3).sum())),
        FFMC_days_extreme=("FFMC_class", lambda s: int((s == 3).sum())),
        rain_jun_oct_mm=("rain", lambda s: float(s[codes.loc[s.index, "date"].dt.month.between(6, 10)].sum())),
    )
    print("FIRMS daily ...")
    firms = pd.concat([firms_daily(y, cache) for y in range(Y0, Y1 + 1)])
    fy = firms.assign(year=firms.date.dt.year).groupby("year").n.sum()
    by_year["modis_detections"] = fy.reindex(by_year.index).fillna(0).astype(int)
    ch = chirps_check()
    by_year["chirps_jul1_sep15_mm"] = ch["jul1_sep15_mm"]
    by_year["chirps_jun_oct_mm"] = ch["jun_oct_mm"]
    by_year["chirps_days_jun_oct"] = ch["days_in_jun_oct"]
    by_year.to_csv(os.path.join(OUT, "by_year.csv"))
    print(by_year.round(0).to_string())

    # ---- response: detections per day vs DC bin
    m = codes.merge(firms, on="date", how="left").fillna({"n": 0})
    bins = [0, 100, 200, 261, 300, 350, 400, 450, 500, 600, 2000]
    m["DC_bin"] = pd.cut(m.DC, bins, right=False)
    resp = m.groupby("DC_bin", observed=True).agg(
        days=("n", "size"), mean_detections=("n", "mean"),
        share_days_ge10=("n", lambda s: float((s >= 10).mean())))
    resp.to_csv(os.path.join(OUT, "response_dc_bins.csv"))
    print(resp.round(2).to_string())

    # ---- ignitions by danger class (Jul-Oct 2026 and all 2026)
    ign26 = ign[ign.date.dt.year == 2026].merge(codes[["date", "DC_class", "FFMC_class",
                                                       "FWI_class", "DC", "FFMC"]],
                                                on="date", how="left")
    ign26["zone"] = np.where(ign26["where"].isin(four), "inside the four", "outside")
    lift_rows = []
    for k in ("DC", "FFMC", "FWI"):
        days_share = c26[f"{k}_class"].value_counts(normalize=True)
        for z, d in ign26.groupby("zone"):
            ish = d[f"{k}_class"].value_counts(normalize=True)
            for j in range(4):
                lift_rows.append({
                    "code": k, "zone": z, "class": CLASS_NAMES[j],
                    "share_of_days_2026": float(days_share.get(j, 0)),
                    "share_of_ignitions": float(ish.get(j, 0)),
                    "lift": float(ish.get(j, 0) / days_share.get(j, np.nan))
                    if days_share.get(j, 0) else None,
                    "n_ignitions": int((d[f"{k}_class"] == j).sum())})
    lift = pd.DataFrame(lift_rows)
    lift.to_csv(os.path.join(OUT, "ignitions_by_danger_class.csv"), index=False)
    print(lift.round(2).to_string(index=False))
    q = ign26.groupby("zone")[["DC", "FFMC"]].median()
    print("median DC/FFMC on ignition days:\n", q.round(0))

    json.dump({"timing_2026": first, "by_year": by_year.reset_index().to_dict("records"),
               "ignition_day_median": q.reset_index().to_dict("records")},
              open(os.path.join(OUT, "summary.json"), "w"), indent=2, default=str)
    print(json.dumps(first, indent=1))

    fig_2026(codes, det[det.date.dt.year == 2026], ign26,
             os.path.join(OUT, "danger_2026.png"))
    fig_years(codes, os.path.join(OUT, "dc_by_year.png"))
    fig_response(resp, os.path.join(OUT, "response_dc.png"))


if __name__ == "__main__":
    main()
