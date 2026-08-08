#!/usr/bin/env python3
"""Smoke exposure — who breathed what, for how long, during a fire season.

A haze map says the air was bad. This says how many people were in it, where,
for how many days, and which of them were children under five or adults over
sixty-five. Those two groups carry most of the health burden, so a headcount
alone ranks districts wrongly.

Per district, per day: the CAMS PM2.5 field is classified into Indonesian ISPU
categories and multiplied by the population underneath. The result is
PERSON-DAYS by category -- 40,000 people for 3 days is 120,000 person-days,
the same as 120,000 people for one day, which is the right way to compare a
long moderate episode against a short severe one.

WHY RETROSPECTIVE. The whole chain -- CAMS to population to ISPU to district --
has never been checked. Run over a past season it can be held against published
health estimates, reported school and airport closures, and the districts
officials actually named at the time. Run forward it produces a number nobody
can verify. The same code does both; this one can be checked first.

Everything is computed server-side: CAMS, WorldPop and the GAUL district
boundaries are all in Earth Engine, so no count raster is ever resampled.

Backend: needs --backend gee.
"""

import datetime as dt
import json
import os

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

CAMS_IC = "ECMWF/CAMS/NRT"
CAMS_PM25 = "particulate_matter_d_less_than_25_um_surface"       # kg/m3
CAMS_SCALE = 44453
# CAMS/NRT begins here; 2015 is out of reach, which rules out the worst
# Indonesian season on record.
CAMS_START = dt.date(2016, 6, 22)

WORLDPOP = "WorldPop/GP/100m/pop"                 # annual totals, 2000-
WORLDPOP_AGE = "WorldPop/GP/100m/pop_age_sex"     # age structure, 2020 only
POP_SCALE = 93
GAUL2 = "FAO/GAUL/2015/level2"

# Under-5 and over-65, the groups the health literature treats as vulnerable.
UNDER5 = ["M_0", "M_1", "F_0", "F_1"]
OVER65 = ["M_65", "M_70", "M_75", "M_80", "F_65", "F_70", "F_75", "F_80"]

# Indonesian ISPU PM2.5 breakpoints (PermenLHK P.14/2020), ug/m3 — the same
# table the haze scenario uses, so the two are directly comparable.
ISPU = [(15.5, {"id": "Baik", "en": "Good"}, "#2e9e4f"),
        (55.4, {"id": "Sedang", "en": "Moderate"}, "#2f7fd1"),
        (150.4, {"id": "Tidak Sehat", "en": "Unhealthy"}, "#e8a33d"),
        (250.4, {"id": "Sangat Tidak Sehat", "en": "Very unhealthy"}, "#d1372f"),
        (float("inf"), {"id": "Berbahaya", "en": "Hazardous"}, "#6b2020")]
BREAKS = [r[0] for r in ISPU[:-1]]


def _label(row, lang):
    return row[1].get(lang, row[1]["id"])


def _daily_pm25(aoi, days):
    """One band per day: mean surface PM2.5 in ug/m3.

    A daily mean, not a snapshot: CAMS/NRT carries several forecast steps for
    each valid time, so picking one image would weight an arbitrary lead time.
    Stacked into a single multi-band image so the whole season costs ONE
    reduceRegions rather than one per day.
    """
    import ee
    coll = ee.ImageCollection(CAMS_IC).select(CAMS_PM25)
    bands = []
    for d in days:
        s = ee.Date(d.isoformat())
        one = coll.filterDate(s, s.advance(1, "day")).mean().multiply(1e9)
        bands.append(one.rename(f"d{d:%Y%m%d}"))
    return ee.Image.cat(bands).clip(aoi)


def _population(year):
    """Total, under-5 and over-65 counts per pixel.

    Age structure exists for 2020 only, so its FRACTIONS are applied to the
    requested year's total. Age composition barely moves in a few years; the
    total does. Stated in the output rather than hidden.
    """
    import ee
    total = (ee.ImageCollection(WORLDPOP).filter(ee.Filter.eq("year", year))
             .mosaic().select("population").rename("total"))
    age = ee.ImageCollection(WORLDPOP_AGE).mosaic()
    age_tot = age.select("population").max(1e-6)
    u5 = age.select(UNDER5).reduce(ee.Reducer.sum()).divide(age_tot)
    o65 = age.select(OVER65).reduce(ee.Reducer.sum()).divide(age_tot)
    return (total
            .addBands(total.multiply(u5).rename("under5"))
            .addBands(total.multiply(o65).rename("over65")))


def _districts(aoi, admin=None):
    import ee
    fc = ee.FeatureCollection(GAUL2).filterBounds(aoi)
    if admin:
        fc = fc.filter(ee.Filter.eq("ADM1_NAME", admin))
    return fc


def _class_of(pm):
    """ISPU class index for a concentration, or None if there is no value."""
    if pm is None:
        return None
    for i, b in enumerate(BREAKS):
        if pm <= b:
            return i
    return len(BREAKS)


def _init_records(pop_rows, labels):
    """One empty record per district that actually has people in it."""
    out = {}
    for f in pop_rows:
        p = f["properties"]
        tot = p.get("total") or 0.0
        if tot <= 0:
            continue
        out[p.get("ADM2_NAME") or "(unnamed)"] = {
            "province": p.get("ADM1_NAME"),
            "population": round(tot),
            "under5": round(p.get("under5") or 0.0),
            "over65": round(p.get("over65") or 0.0),
            "days_by_class": {lb: 0 for lb in labels},
            "person_days_by_class": {lb: 0 for lb in labels},
            # Class index per day, kept so the figure can show WHEN the burden
            # fell. Counts alone cannot distinguish one long episode from two
            # short ones, and over Kalimantan in 2019 that turns out to matter.
            "class_by_day": [],
            "worst_pm25": None, "worst_date": None,
        }
    return out


def _tally(rec, props, days, labels):
    """Add one district's daily classes to its record."""
    for d in days:
        pm = props.get(f"d{d:%Y%m%d}")
        c = _class_of(pm)
        rec["class_by_day"].append(-1 if c is None else c)
        if c is None:
            continue
        lb = labels[c]
        rec["days_by_class"][lb] += 1
        rec["person_days_by_class"][lb] += rec["population"]
        if rec["worst_pm25"] is None or pm > rec["worst_pm25"]:
            rec["worst_pm25"] = round(pm, 1)
            rec["worst_date"] = d.isoformat()


def _accumulate(pop_rows, pm_rows, days, lang):
    """Person-days per district per ISPU class, from the two reductions.

    The district-day mean is classified once and the whole district counted in
    that class. Kalimantan districts are mostly larger than a 44 km CAMS pixel,
    so splitting finer would imply detail the smoke field does not carry.
    """
    labels = [_label(r, lang) for r in ISPU]
    out = _init_records(pop_rows, labels)
    for f in pm_rows:
        rec = out.get(f["properties"].get("ADM2_NAME") or "(unnamed)")
        if rec is not None:
            _tally(rec, f["properties"], days, labels)
    return out, labels


def _summarise(recs, labels, lang):
    """Totals across all districts, and the ranking that matters.

    Ranked by person-days at Tidak Sehat or worse, not by population: a large
    district with clean air should not outrank a small one under smoke.
    """
    bad = labels[2:]                       # Tidak Sehat and above
    for r in recs.values():
        r["person_days_unhealthy"] = sum(r["person_days_by_class"][k] for k in bad)
        r["days_unhealthy"] = sum(r["days_by_class"][k] for k in bad)
        # Vulnerable person-days: the same exposure weighted to who bears it.
        share = ((r["under5"] + r["over65"]) / r["population"]
                 if r["population"] else 0.0)
        r["vulnerable_person_days_unhealthy"] = round(
            r["person_days_unhealthy"] * share)
    order = sorted(recs.items(), key=lambda kv: -kv[1]["person_days_unhealthy"])
    tot = {
        "districts": len(recs),
        "population": sum(r["population"] for r in recs.values()),
        "under5": sum(r["under5"] for r in recs.values()),
        "over65": sum(r["over65"] for r in recs.values()),
        "person_days_by_class": {
            lb: sum(r["person_days_by_class"][lb] for r in recs.values())
            for lb in labels},
        "person_days_unhealthy": sum(
            r["person_days_unhealthy"] for r in recs.values()),
        "vulnerable_person_days_unhealthy": sum(
            r["vulnerable_person_days_unhealthy"] for r in recs.values()),
    }
    return order, tot


def _write_report(path, order, tot, labels, meta):
    """The citable document: who breathed what, ranked by burden."""
    bad = labels[2:]
    L = [f"# Paparan asap — {meta['name']}", "",
         f"**Musim:** {meta['season'][0]} sampai {meta['season'][1]} "
         f"({meta['days']} hari)  ",
         f"**Penduduk dalam cakupan:** {tot['population']:,} jiwa di "
         f"{tot['districts']} kabupaten/kota  ",
         f"**Dihitung:** {dt.date.today().isoformat()} dengan "
         f"`earthchange -s smoke-exposure`", "",
         "Person-day = satu orang terpapar satu hari. 40.000 orang selama 3 "
         "hari sama dengan 120.000 person-day, sehingga episode panjang yang "
         "sedang dapat dibandingkan dengan episode pendek yang parah.", "",
         "## Ringkasan", ""]
    L.append(f"| Kelas ISPU | Person-day |")
    L.append("|---|---:|")
    for lb in labels:
        L.append(f"| {lb} | {tot['person_days_by_class'][lb]:,} |")
    L.append("")
    L.append(f"**Tidak Sehat atau lebih buruk: "
             f"{tot['person_days_unhealthy']:,} person-day**, di antaranya "
             f"{tot['vulnerable_person_days_unhealthy']:,} pada balita dan "
             f"lansia ({tot['under5']:,} balita dan {tot['over65']:,} lansia "
             f"tinggal di wilayah ini).")
    L.append("")
    L.append("## Kabupaten/kota paling terdampak")
    L.append("")
    L.append("| Kabupaten/kota | Provinsi | Penduduk | Balita | Lansia | "
             "Hari ≥Tidak Sehat | Person-day ≥Tidak Sehat | PM2.5 puncak |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for nm, r in order[:25]:
        L.append(f"| {nm} | {r['province'] or '—'} | {r['population']:,} | "
                 f"{r['under5']:,} | {r['over65']:,} | {r['days_unhealthy']} | "
                 f"{r['person_days_unhealthy']:,} | "
                 f"{r['worst_pm25'] or 0:.0f} ({r['worst_date'] or '—'}) |")
    L += ["", "## Sumber dan batasan", "",
          f"- PM2.5: CAMS ({CAMS_IC}), rerata harian, ~{CAMS_SCALE/1000:.0f} km",
          "- Penduduk: WorldPop 100 m; struktur umur 2020 diterapkan pada "
          f"total {meta['pop_year']}, karena rincian umur hanya tersedia 2020",
          "- Kelas ISPU PermenLHK P.14/2020; batas PM2.5 15,5 / 55,4 / 150,4 / 250,4",
          "- Batas wilayah: FAO GAUL 2015 level 2",
          "", "**Yang tidak diukur di sini.** Konsentrasi luar ruangan bukan "
          "paparan sebenarnya: orang berada di dalam rumah, sebagian memakai "
          "masker, sebagian tidak bisa mengungsi. Angka ini adalah proksi "
          "bahaya, bukan luaran kesehatan. Bidang CAMS ~44 km jauh lebih kasar "
          "daripada data penduduk 100 m, sehingga satuan yang bermakna adalah "
          "kabupaten, bukan desa — seluruh kabupaten dihitung pada satu kelas "
          "per hari. CAMS di Earth Engine baru dimulai 22 Juni 2016, sehingga "
          "musim 2015 — yang terburuk — tidak dapat dihitung dengan cara ini."]
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    return path


def _render(run_dir, name, order, tot, labels, days, meta, top=20):
    """Who, how much, and when — on one figure.

    The ranked bars answer 'where to send people'. The heatmap beside them
    answers 'when', which the totals cannot: a district with 46 unhealthy days
    spread over two separate episodes needs a different response from one with
    46 consecutive. Sharing the vertical axis means each district's burden and
    its timing are read on the same row.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import Patch

    rows = order[:top]
    if not rows:
        return None
    cols = [r[2] for r in ISPU]
    n = len(rows)

    grid = np.full((n, len(days)), np.nan)
    for i, (_, r) in enumerate(rows):
        seq = r.get("class_by_day") or []
        for j, c in enumerate(seq[:len(days)]):
            if c >= 0:
                grid[i, j] = c

    fig = plt.figure(figsize=(17, max(6.0, 0.42 * n + 3.2)), dpi=160)
    fig.patch.set_facecolor("#faf8f4")
    gs = GridSpec(1, 2, figure=fig, width_ratios=[2.05, 1], wspace=.02)
    axh = fig.add_subplot(gs[0, 0])
    axb = fig.add_subplot(gs[0, 1], sharey=axh)

    x = [mdates.date2num(d) for d in days]
    axh.imshow(np.ma.masked_invalid(grid), aspect="auto",
               cmap=ListedColormap(cols),
               norm=BoundaryNorm([-.5, .5, 1.5, 2.5, 3.5, 4.5], len(cols)),
               extent=[x[0], x[-1], n - .5, -.5], interpolation="nearest")
    axh.set_yticks(range(n))
    axh.set_yticklabels([f"{nm[:26]}" for nm, _ in rows], fontsize=9)
    axh.xaxis_date()
    axh.xaxis.set_major_locator(mdates.MonthLocator())
    axh.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    axh.set_title("Kelas ISPU harian per kabupaten/kota",
                  fontsize=11, fontweight="bold", loc="left")
    axh.grid(axis="x", ls=":", alpha=.35, color="#fff")
    axh.set_axisbelow(False)

    pd_all = [r["person_days_unhealthy"] / 1e6 for _, r in rows]
    pd_vul = [r["vulnerable_person_days_unhealthy"] / 1e6 for _, r in rows]
    y = np.arange(n)
    axb.barh(y, pd_all, color="#c9ccd4", edgecolor="#8a8d94", linewidth=.5)
    axb.barh(y, pd_vul, color="#b5121b", edgecolor="#7a0c12", linewidth=.5)
    for i, (a, v) in enumerate(zip(pd_all, pd_vul)):
        axb.text(a + max(pd_all) * .015, i, f"{a:,.1f} jt", va="center",
                 fontsize=8.5)
        _ = v
    axb.set_xlim(0, max(pd_all) * 1.22)
    # No invert_yaxis: the heatmap's extent already puts row 0 at the top, and
    # the axes share y. Inverting sent the worst-affected district to the
    # bottom, which reads as a ranking upside down.
    axb.tick_params(labelleft=False)
    axb.set_xlabel("juta person-day ≥ Tidak Sehat", fontsize=9)
    axb.set_title("Beban paparan", fontsize=11, fontweight="bold", loc="left")
    axb.grid(axis="x", ls=":", alpha=.4)
    axb.set_axisbelow(True)
    for sp in ("top", "right"):
        axb.spines[sp].set_visible(False)

    handles = [Patch(facecolor=c, label=lb) for c, lb in zip(cols, labels)]
    handles += [Patch(facecolor="#c9ccd4", label="semua penduduk"),
                Patch(facecolor="#b5121b", label="balita + lansia")]
    fig.legend(handles=handles, fontsize=8.5, frameon=False, ncol=7,
               loc="lower center", bbox_to_anchor=(.5, .003))
    fig.suptitle(
        f"Paparan asap — {name}, {meta['season'][0]} → {meta['season'][1]}\n"
        f"{tot['population']:,} jiwa · "
        f"{tot['person_days_unhealthy']/1e6:,.0f} juta person-day pada "
        f"Tidak Sehat atau lebih buruk, "
        f"{tot['vulnerable_person_days_unhealthy']/1e6:,.0f} juta di antaranya "
        f"balita/lansia",
        fontsize=13.5, fontweight="bold", x=.008, ha="left", y=.985)
    fig.text(.008, .045,
             "PM2.5: CAMS (~44 km), rerata harian per kabupaten. Penduduk: "
             "WorldPop 100 m, struktur umur 2020. Kelas ISPU PermenLHK "
             "P.14/2020. Person-day = satu orang, satu hari — konsentrasi luar "
             "ruangan, bukan luaran kesehatan.",
             fontsize=7.5, color="#777")
    fig.tight_layout(rect=[0, .075, 1, .945])
    out = os.path.join(run_dir, f"{name}_exposure.png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def run(backend, lat, lon, radius, name, run_dir, run_id, config_key=None,
        season=None, admin=None, bbox=None, pop_year=None, lang="id"):
    """Retrospective smoke exposure by district."""
    if backend == "mpc":
        raise SystemExit("smoke-exposure needs --backend gee (CAMS + WorldPop).")
    if not season or ":" not in season:
        raise SystemExit("smoke-exposure needs --season START:END, e.g. "
                         "--season 2019-08-01:2019-11-30")
    s0, s1 = (dt.date.fromisoformat(x) for x in season.split(":"))
    if s1 <= s0:
        raise SystemExit(f"--season end must follow start (got {season})")
    if s0 < CAMS_START:
        raise SystemExit(
            f"CAMS in Earth Engine starts {CAMS_START}; {s0} is before it. "
            f"The 2015 season cannot be computed from this source.")

    import ee
    from .gee_utils import initialize_ee
    from .fire_history import _resolve_aoi
    initialize_ee(config_key)

    aoi = _resolve_aoi(admin, bbox, lon, lat, radius)
    days = [s0 + dt.timedelta(days=i) for i in range((s1 - s0).days + 1)]
    year = pop_year or min(max(s0.year, 2000), 2020)
    districts = _districts(aoi)
    n_d = districts.size().getInfo()
    if not n_d:
        raise SystemExit("No GAUL level-2 districts intersect this area.")
    print(f"  {name}: {s0} → {s1} ({len(days)} days) · {n_d} districts · "
          f"population {year}")

    # Two reductions, whatever the season length: population once, and the
    # whole daily stack as one multi-band image.
    print("  summing population at native resolution ...", flush=True)
    pop = _population(year)
    pop_rows = pop.reduceRegions(
        collection=districts, reducer=ee.Reducer.sum(), scale=POP_SCALE,
        tileScale=4).select(["ADM1_NAME", "ADM2_NAME", "total", "under5",
                             "over65"], None, False).getInfo()["features"]

    print(f"  sampling {len(days)} days of CAMS ...", flush=True)
    pm = _daily_pm25(aoi, days)
    pm_rows = pm.reduceRegions(
        collection=districts, reducer=ee.Reducer.mean(), scale=CAMS_SCALE,
        tileScale=4).getInfo()["features"]

    recs, labels = _accumulate(pop_rows, pm_rows, days, lang)
    order, tot = _summarise(recs, labels, lang)

    meta = {"name": name, "season": [s0.isoformat(), s1.isoformat()],
            "days": len(days), "pop_year": year}
    md = _write_report(os.path.join(run_dir, f"{name}_exposure.md"),
                       order, tot, labels, meta)
    png = _render(run_dir, name, order, tot, labels, days, meta)
    stats = {"run_id": run_id, "scenario": "smoke-exposure", "name": name,
             **meta, "ispu_breaks": BREAKS, "totals": tot,
             "districts": recs,
             "sources": {"pm25": f"CAMS {CAMS_IC} daily mean, {CAMS_SCALE} m",
                         "population": f"WorldPop {WORLDPOP} {year} totals with "
                                       f"{WORLDPOP_AGE} 2020 age structure",
                         "boundaries": GAUL2},
             "outputs": {"report": os.path.basename(md),
                         "figure": os.path.basename(png) if png else None},
             "note": ("Person-days of outdoor concentration, not a health "
                      "outcome. A whole district is counted in one ISPU class "
                      "per day because CAMS at 44 km is coarser than most "
                      "districts. CAMS begins 2016-06-22, so the 2015 season "
                      "cannot be computed.")}
    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n{name} — {s0} → {s1}")
    print(f"  {tot['population']:,} people · {tot['under5']:,} under 5 · "
          f"{tot['over65']:,} over 65")
    for lb in labels:
        v = tot["person_days_by_class"][lb]
        if v:
            print(f"  {lb:20s} {v:>15,} person-days")
    print(f"\n  {'kabupaten/kota':28s} {'hari≥TS':>8s} {'person-day≥TS':>16s} "
          f"{'PM2.5 puncak':>13s}")
    for nm, r in order[:12]:
        print(f"  {nm[:28]:28s} {r['days_unhealthy']:8d} "
              f"{r['person_days_unhealthy']:16,} "
              f"{r['worst_pm25'] or 0:12.0f}")
    print(f"\n  laporan: {os.path.basename(md)}")
    return stats
    tot = {
        "districts": len(recs),
        "population": sum(r["population"] for r in recs.values()),
        "under5": sum(r["under5"] for r in recs.values()),
        "over65": sum(r["over65"] for r in recs.values()),
        "person_days_by_class": {
            lb: sum(r["person_days_by_class"][lb] for r in recs.values())
            for lb in labels},
        "person_days_unhealthy": sum(
            r["person_days_unhealthy"] for r in recs.values()),
        "vulnerable_person_days_unhealthy": sum(
            r["vulnerable_person_days_unhealthy"] for r in recs.values()),
    }
    return order, tot
