#!/usr/bin/env python3
"""Build the Supplementary Information for the ERL paper: every table is generated from the run files in
output/fire/ (no hand-copied numbers) and inserted into the prose template at its {{key}} marker.

    python scripts/si_build.py      # output/manuscript/SI_TEMPLATE.md -> output/manuscript/SUPPLEMENTARY.md
"""
import json
import math
import os
import re

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(R, "output", "fire", "kalimantan_excess")
LIN = os.path.join(R, "output", "fire", "kalimantan_lineage")
PRF = os.path.join(R, "output", "peat_rf")
MS = os.path.join(R, "output", "manuscript")
J = lambda *p: json.load(open(os.path.join(*p)))       # noqa: E731
KINDS = ("oil palm", "pulpwood")


def f2(x, d=2):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


def ci(c, d=2):
    return f"{f2(c[0], d)}–{f2(c[1], d)}"


def pv(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


TERM = {"depth_m_z": "peat depth, unit mean (per SD)", "peat_share_10pp": "peat share, BBSDLP (per 10 pp)",
        "gpm_share_10pp": "peat share, Greifswald (per 10 pp)", "depth_on_peat_cm_z": "depth on peat (per SD)",
        "edge_on_peat_km_z": "distance to peat edge on peat (per SD)"}


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def evalue(rr):
    rr = 1 / rr if rr < 1 else rr
    return rr + math.sqrt(rr * (rr - 1))


# ---------------------------------------------------------------- S2 balance and sensitivity
def t_balance():
    b = J(EX, "balance_sensitivity.json")["balance"]
    rows = []
    for k in KINDS:
        for x in b[k]:
            rows.append([k, x["covariate"], f2(x["treated"], 3), f2(x["control_raw"], 3), f2(x["control_cem"], 3),
                         f2(x["smd_raw"]), f2(x["smd_cem"])])
    return table(["Type", "Covariate", "Concession", "Unpermitted, raw", "Unpermitted, CEM", "SMD raw", "SMD CEM"], rows)


def t_evalues():
    s = J(EX, "balance_sensitivity.json")["sensitivity"]
    d = {r["treated"]: r for r in J(EX, "dc_stratum.json")["burned_share"] if r["matched_on"] == "all strata + peak-DC band"}
    rows = []
    for k in KINDS:
        rows.append([k, "land strata: move the deficit to 1", f2(s[k]["ratio"], 3), ci(s[k]["ci"], 3),
                     f2(s[k]["evalue_point"]), f2(s[k]["evalue_ci"]) if s[k]["ratio"] < 1 and s[k]["ci"][1] < 1 else "— (interval includes 1)"])
        r = d[k]
        pt = evalue(1.10 / r["ratio"])
        up = evalue(1.10 / r["ci"][1]) if r["ci"][1] < 1.10 else None
        rows.append([k, "drought-matched: hide a true 10% excess", f2(r["ratio"], 3), ci(r["ci"], 3), f2(pt),
                     f2(up) if up else "— (interval reaches 1.10)"])
    return table(["Type", "Target", "Ratio", "95% interval", "E-value, point", "E-value, interval bound"], rows)


def t_leaveout():
    loo = J(EX, "balance_sensitivity.json")["leave_one_out"]
    dc = {(r["treated"], r["variant"]): r for r in J(EX, "dc_robustness.json")}
    prim = {r["treated"]: r for r in J(EX, "dc_stratum.json")["burned_share"] if r["matched_on"] == "all strata + peak-DC band"}
    rows = []
    for k in KINDS:
        for x in loo[k]:
            name = x["dropped"]
            dcr = dc.get((k, f"without {name}")) if name != "none" else prim[k]    # primary run, as in the paper
            rows.append([k, "none (full strata)" if name == "none" else name, f"{f2(x['ratio'], 3)} ({ci(x['ci'], 3)})",
                         f"{f2(dcr['ratio'], 3)} ({ci(dcr['ci'], 3)})" if dcr else "—"])
    return table(["Type", "Covariate left out", "Land strata", "+ drought band"], rows)


# ---------------------------------------------------------------- S3 ladder
def t_ladder():
    a = J(EX, "balance_sensitivity.json")["attribution"]
    rows = []
    for k in KINDS:
        for order, seq in a[k]["ladder_orders"].items():
            rows.append([k, order, " → ".join(f"{s['added']} {f2(s['ratio'])}" for s in seq)])
    return table(["Type", "Order", "Ratio after each covariate is added"], rows)


def t_shapley():
    a = J(EX, "balance_sensitivity.json")["attribution"]
    covs = list(a["oil palm"]["shapley_share_of_change"].keys())
    rows = [[c] + [f"{100 * a[k]['shapley_share_of_change'][c]:.0f}%" for k in KINDS] for c in covs]
    rows.append(["raw → full ratio"] + [f"{f2(a[k]['raw_ratio'], 3)} → {f2(a[k]['full_ratio'], 3)}" for k in KINDS])
    return table(["Covariate", "Oil palm", "Pulpwood"], rows)


# ---------------------------------------------------------------- S4 outcomes, robustness, canopy
def t_outcomes():
    oc = J(EX, "concession_checks.json")["outcomes"]
    dc = {(r["treated"], r["variant"]): r for r in J(EX, "dc_robustness.json")}
    names = {"burned": ("S2 burned ≥ ½ cell (main)", "S2 burned >= 1/2 (main outcome)"),
             "burned25": ("S2 burned ≥ ¼ cell", "S2 burned >= 1/4 of the cell"),
             "viirs_cell": ("VIIRS fire within ~300 m, Jun–Oct", "any VIIRS fire within ~300 m, Jun-Oct"),
             "viirs_count": ("VIIRS detections per cell, Jun–Oct", "VIIRS detections per cell, Jun-Oct")}
    prim = {r["treated"]: r for r in J(EX, "dc_stratum.json")["burned_share"] if r["matched_on"] == "all strata + peak-DC band"}
    rows = []
    for k in KINDS:
        for o, (lab, dkey) in names.items():
            raw = next(x for x in oc if x["outcome"] == o and x["treated"] == k and x["matched_on"] == "raw")
            ls = next(x for x in oc if x["outcome"] == o and x["treated"] == k and x["matched_on"] != "raw")
            d = prim[k] if o == "burned" else dc[(k, dkey)]        # main outcome: the paper's primary run
            rows.append([k, lab, f2(raw["ratio"], 3), f"{f2(ls['ratio'], 3)} ({ci(ls['ci95'], 3)})",
                         f"{f2(d['ratio'], 3)} ({ci(d['ci'], 3)})"])
    return table(["Type", "Outcome", "Raw", "Land strata", "+ drought band"], rows) + \
        "\n\n*Land-strata column: outcome-check run (concession_checks); its main-outcome interval differs slightly " \
        "from the primary land-strata run in tables S2 and S5 (0.798–0.920 for oil palm) because the bootstrap draws " \
        "differ. + drought band: main outcome from the primary run (table S5.1), other outcomes from the robustness run.*"


def t_robust():
    rob = [r for r in J(EX, "robustness.json") if "ratio" in r and "check" in r]
    dc = {(r["treated"], r["variant"]): r for r in J(EX, "dc_robustness.json")}
    rows = []
    for r in rob:
        if r["check"] == "base":
            continue
        rows.append([r["treated"], r["check"], r["variant"], f"{f2(r['ratio'], 3)} ({ci(r['ci'], 3)})", "land strata"])
    for k in KINDS:
        for key in (("peat map", "Greifswald GPM 2.0 peat + depth bins"), ("interior", "controls >= 5 km out, treated >= 5 km in")):
            d = dc[(k, key[1])]
            rows.append([k, key[0], key[1], f"{f2(d['ratio'], 3)} ({ci(d['ci'], 3)})", "+ drought band"])
    return table(["Type", "Check", "Variant", "Ratio (95% interval)", "Strata"], rows)


def t_canopy():
    c = J(EX, "concession_checks.json")["canopy"]
    lc = {0: "oil palm, planted ≤ 2001", 1: "oil palm, 2002–2011", 2: "oil palm, 2012–2018 (incl. no year)",
          3: "oil palm, 2019 or later", 4: "forest standing since 2000", 5: "forest lost 2001–2015",
          6: "forest lost since 2016", 7: "non-forest"}
    rows = []
    for i, lab in lc.items():
        row = [lab]
        for w in ("oil palm", "pulpwood", "unpermitted"):
            s, n = c.get(f"s2_burned|{w}|{i}"), c.get(f"n|{w}|{i}")
            row.append(f"{100 * s:.0f}% (n {int(n):,})" if s is not None and n else "—")
        rows.append(row)
    return table(["Land cover", "Oil palm", "Pulpwood", "Unpermitted"], rows)


# ---------------------------------------------------------------- S5 drought stratum
def t_dc_stratum():
    d = J(EX, "dc_stratum.json")
    rows = [[r["treated"], r["matched_on"], f"{r['treated_pct']:.2f}%", f"{r['control_pct']:.2f}%",
             f"{f2(r['ratio'], 3)} ({ci(r['ci'], 3)})", f"{100 * r['coverage']:.1f}%"] for r in d["burned_share"]]
    return table(["Type", "Strata", "Concession burned", "Matched unpermitted", "Ratio (95% interval)", "Coverage"], rows)


def t_crosstab():
    x = J(EX, "dc_units_summary.json")["crosstab"]
    cls = ("excess", "no difference", "deficit")
    rows = []
    for k in KINDS:
        for a in cls:
            rows.append([k, a] + [x.get(f"{k}|{a}|{b}", 0) for b in cls])
    return table(["Type", "Land strata class ↓ / drought-matched class →", *cls], rows)


# ---------------------------------------------------------------- S6 concentration and calibration
def t_classes():
    s = J(EX, "dc_units_summary.json")["classes"]
    rows = []
    for key, r in s.items():
        k, spec = key.split("|")
        rows.append([k, "land strata" if spec == "island-wide" else "+ drought band", r["units"], r["excess"],
                     r["no_difference"], r["deficit"], f"{r['excess_burned_km2']:,.0f} of {r['burned_km2']:,.0f} km² ({r['excess_share_pct']:.0f}%)",
                     f"{r['excess_with_peat_pct']:.0f}%"])
    return table(["Type", "Strata", "Units", "Excess", "No difference", "Deficit", "Burned area in excess units",
                  "Excess units with ≥ 1% peat"], rows)


def t_benchmark():
    v1 = J(EX, "concentration_benchmark_v1_tiles.json")
    v2 = J(EX, "concentration_benchmark.json")
    rows = []
    for k in KINDS:
        c = v2["concessions"][k]
        rows.append([k, "concessions", "—", f"{c['excess_pct']:.1f}%", f"{c['excess_share_pct']:.0f}%",
                     c.get("zero_burn_units", "—"), f"{c['excess_pct_of_burning']:.1f}%" if "excess_pct_of_burning" in c else "—",
                     f"{c.get('median_cells', float('nan')):,.0f}"])
        for name, src in (("v1 square tiles", v1), ("v2 patches (size + drought)", v2)):
            for r in src["replicates"]:
                if r["kind_sizes"] != k:
                    continue
                rows.append([k, name, r["replicate"], f"{r['excess_pct']:.1f}%", f"{r['excess_share_pct']:.0f}%",
                             r["zero_burn_units"], f"{r['excess_pct_of_burning']:.1f}%" if "excess_pct_of_burning" in r else "—",
                             f"{r['median_cells']:,.0f}"])
    return table(["Sizes of", "Units", "Replicate", "In excess", "Their share of burned area", "Zero-burn units",
                  "Excess among units that burned", "Median analysable cells"], rows)


def t_calibration():
    import numpy as np
    import pandas as pd
    P = pd.read_csv(os.path.join(EX, "per_concession_matched_dc.csv"))
    T = pd.read_csv(os.path.join(EX, "concentration_benchmark_patches.csv"))
    rows = []
    for k in KINDS:
        g = P[P.kind == k]
        null = T[T.kind_sizes == k].ratio.to_numpy()
        for q in (90, 95, 99, 99.9):
            thr = np.percentile(null, q)
            rows.append([k, f"{q}th", f"×{thr:.2f}", int((g.ratio > thr).sum()), f"{len(g) * (100 - q) / 100:.1f}"])
        rows.append([k, "maximum", f"×{null.max():.2f}", int((g.ratio > null.max()).sum()), "—"])
    cf = J(EX, "flag_calibration.json")["calibrated_flag"]
    foot = "; ".join(f"{k}: highest concession ratio ×{P[P.kind == k].ratio.max():.2f}, flagged after BH against patches "
                     f"{cf[k]['flag_bh']}, empirical p ≤ 0.05 for {cf[k]['above_patch_p95']} (ties at the threshold count as not above)"
                     for k in KINDS)
    return table(["Type", "Patch-ratio percentile", "Threshold", "Concessions above", "Expected if like patches"], rows) + \
        f"\n\n*{foot}. Null: {', '.join(str(cf[k]['null_patches']) for k in KINDS)} patch ratios (5 replicates).*"


# ---------------------------------------------------------------- S7 heterogeneity
def t_firth():
    F = J(EX, "firth.json")["models"]
    M = J(EX, "dc_units_summary.json")["model"]
    lab = {"depth_m_z": "peat depth, unit mean (per SD)", "peat_share_10pp": "peat share, BBSDLP (per 10 pp)",
           "gpm_share_10pp": "peat share, Greifswald (per 10 pp)", "depth_on_peat_cm_z": "depth on peat (per SD)",
           "forest_share_z": "forest share (per SD)", "log_area_z": "area, log (per SD)",
           "ind_share_10pp": "industrial palm (per 10 pp)", "small_share_10pp": "smallholder palm (per 10 pp)",
           "recent_share_10pp": "planted 2016–21 (per 10 pp)", "st_in_process": "permit: title in process",
           "st_location_permit": "permit: location permit only", "st_unknown": "permit: unknown",
           "grouped": "member of a company group", "rspo_cert_share_10pp": "RSPO certified (per 10 pp)",
           "rspo_member_share_10pp": "RSPO member, uncertified (per 10 pp)",
           "other_permit_share_10pp": "overlap with pulpwood permit (per 10 pp)"}
    mlmap = {"main (depth)": "main (depth)", "BBSDLP share": "BBSDLP share", "GPM share": "GPM share"}
    rows = []
    for model, terms in F.items():
        for t, r in terms.items():
            if model != "main (depth)" and t not in ("peat_share_10pp", "gpm_share_10pp", "depth_on_peat_cm_z"):
                continue                      # control terms repeat the main model; shown once
            ml = M.get(mlmap.get(model, ""), {}).get("logit", {}).get(t)
            rows.append([model, lab.get(t, t), f"{f2(r['or'])} ({ci([r['lo'], r['hi']])})", pv(r["p"]),
                         f"{f2(ml['or'])} ({ci([ml['lo'], ml['hi']])})" if ml else "—"])
    return table(["Model", "Term", "Firth OR (95% profile interval)", "p (penalised LR)", "ML logit OR, HC1 (95%)"], rows)


def t_peatdecomp():
    P = J(EX, "peat_depth_checks_dc.json")
    rows = []
    for k in KINDS:
        for v, terms in P[k].items():
            for t, r in terms.items():
                lg, w = r.get("logit"), r.get("wls")
                rows.append([k + (" (14 events; unstable)" if k == "pulpwood" else ""), v, TERM.get(t, t),
                             f"{f2(lg['or'])} ({ci([lg['lo'], lg['hi']])}), p {pv(lg['p'])}" if lg else "failed",
                             f"{f2(w['x'])} ({ci([w['lo'], w['hi']])}), p {pv(w['p'])}" if w else "—"])
    return table(["Type", "Variant", "Term", "ML logit OR, HC1 (95%), p", "WLS ratio (95%), p"], rows)


def t_peat_tenure():
    pi = J(EX, "flag_calibration.json")["peat_interaction"]
    rows = []
    for rep, r in pi.items():
        rows.append([rep, f"{f2(r['ps10']['or'])} ({ci([r['ps10']['lo'], r['ps10']['hi']])})",
                     f"{f2(r['ps10_x_conc']['or'])} ({ci([r['ps10_x_conc']['lo'], r['ps10_x_conc']['hi']])}), p {f2(r['ps10_x_conc']['p'], 3)}",
                     f2(r["ps10_in_concessions_point"]),
                     f"{r['patch_excess_pct_peat_vs_not'][0]:.1f}% / {r['patch_excess_pct_peat_vs_not'][1]:.1f}%"])
    c = J(EX, "flag_calibration.json")["concession_excess_pct_peat_vs_not"]
    return table(["Replicate", "Peat OR on patches (per 10 pp)", "Concession × peat interaction",
                  "Peat OR in concessions (point)", "Patches in excess, with / without peat"], rows) + \
        f"\n\n*Oil-palm concessions in excess, with / without ≥ 1% peat: {c[0]:.1f}% / {c[1]:.1f}%.*"


def t_peatbins():
    b = J(EX, "dc_units_summary.json")["peat_bins"]
    labs = [x["bin"] for x in b["ps"]]
    rows = [[lab, f"{b['ps'][i]['excess_pct']:.1f}% (n {b['ps'][i]['units']})",
             f"{b['gpm_share'][i]['excess_pct']:.1f}% (n {b['gpm_share'][i]['units']})"] for i, lab in enumerate(labs)]
    return table(["Share of concession on peat (%)", "BBSDLP", "Greifswald GPM 2.0"], rows)


# ---------------------------------------------------------------- S8 lineage
def t_lineage():
    L = J(LIN, "summary.json")
    s = L["sensitivity"]
    rows = [[k, f"{v['ignitions_season']:,}", f"{100 * v['share_inside_from_same_concession']:.0f}%",
             ", ".join(f"K{i + 1} {100 * b:.0f}%" for i, b in enumerate(v["four"].values()))] for k, v in s.items()]
    t1 = table(["Parent rule", "Ignitions (season)", "Concession detections from the same concession (both types, edge roots included)",
                "Ketapang four (K1–K4)"], rows)
    e = L["entry"]
    rows = [[k, f"{v['detections']:,}", f"{100 * v['same_concession']:.1f}%", f"{100 * v['same_concession_edge_root']:.1f}%",
             f"{100 * v['other_concession']:.1f}%", f"{100 * v['open_land']:.1f}%", f"{100 * v['my_bn']:.2f}%",
             f"{100 * v['off_land']:.2f}%"] for k, v in e.items()]
    t2 = table(["Detections inside", "Detections", "Same concession, interior root", "Same concession, edge root",
                "Other concession", "Open land", "Malaysia/Brunei", "Off land"], rows)
    x = L["escape"]
    rows = [[k, f"{v['detections']:,}", f"{100 * v['from_oil_palm']:.1f}%", f"{100 * v['from_pulpwood']:.1f}%",
             f"{100 * v['from_edge_roots']:.1f}%"] for k, v in x.items()]
    t3 = table(["Detections on", "Detections", "From oil palm", "From pulpwood", "From concession-edge roots"], rows)
    d = L["density"]
    rows = [[k, f"{v['area_km2']:,.0f}", f"{v['ignitions']:,}", f"{v['per_1000km2']:.0f}", f"{v['isolated_per_1000km2']:.0f}",
             f"{v['detections_per_1000km2']:,.0f}"] for k, v in d.items()]
    t4 = table(["Tenure", "Area (km²)", "Ignitions", "Per 1,000 km²", "Isolated per 1,000 km²", "Detections per 1,000 km²"], rows)
    return "\n\n".join([t1, t2, t3, t4])


# ---------------------------------------------------------------- S9 land preparation
def t_landprep():
    a = J(EX, "landprep", "landprep_tests.json")
    b = J(EX, "landprep", "landprep_tests_dc.json")
    rows = []
    for y in ("2015", "2019"):
        for z, r in a["T1"][y].items():
            rows.append([f"T1 burned {y} → planted by 2021", z, f"{100 * r['treated']:.2f}%", f"{100 * r['control']:.2f}%",
                         f"{f2(r['ratio'])} ({ci(r['ci'])})", f"{r['burned_km2']:,.0f} km²"])
    for name, src in (("T2 cleared before the 2026 fire, land strata", a), ("T2 … + drought band", b)):
        for z in KINDS:
            r = src["T2"][z]
            rows.append([name, z, f"{100 * r['treated']:.2f}%", f"{100 * r['control']:.2f}%", f"{f2(r['ratio'])} ({ci(r['ci'])})",
                         f"{src['T2']['burned_cells_used']:,} burned cells, all zones"])
    t1 = table(["Test", "Zone", "Treated", "Matched control", "Ratio (95%)", "Base"], rows)
    rows = []
    for name, src in (("land-strata classes", a), ("drought-matched classes", b)):
        u = src["T1"]["per_unit_2015"]
        rows.append([name, u["units"], u["excess_units"], f"{100 * u['median_planted_excess']:.1f}%",
                     f"{100 * u['median_planted_rest']:.1f}%", f2(u["mannwhitney_p"], 3)])
    t2 = table(["Classification", "Units with ≥ 1 km² burned 2015", "Excess units", "Median planted, excess",
                "Median planted, rest", "Mann–Whitney p"], rows)
    rows = [[k, f"{v['ignitions']:,}", f"{100 * v['day_share_ignitions']:.1f}%", f"{100 * v['day_share_all']:.1f}%",
             f2(v["ratio"]), v["multi_ignition_passes"], f2(v["per_100km2"])] for k, v in a["T3"].items()]
    t3 = table(["Tenure", "Ignitions", "Day share, ignitions", "Day share, all detections", "Ratio",
                "Overpasses with ≥ 3 new ignitions", "Per 100 km²"], rows)
    return "\n\n".join([t1, t2, t3])


# ---------------------------------------------------------------- S10 fire weather
def t_w1():
    fw = J(EX, "fire_weather.json")
    rows = [[r["treated"], f"{r['dc_band'][0]}–{r['dc_band'][1] if r['dc_band'][1] < 2000 else 'max'}",
             f"{r['treated_pct']:.2f}%", f"{r['control_pct']:.2f}%", f"{f2(r['ratio'])} ({ci(r['ci'])})",
             f"{r['n_treated']:,}"] for r in fw["W1"]]
    return table(["Type", "Peak DC band", "Concession burned", "Matched unpermitted", "Ratio (95%)", "Concession cells"], rows)


def t_timing():
    t = J(EX, "dc_stratum.json")["timing"]
    rows = [[r["treated"], r["matched_on"], "first-fire day (day of year)" if r["variable"] == "day" else "Drought Code at first fire (index units)",
             f"{r['treated_mean']:.1f}", f"{r['control_mean']:.1f}", f"{r['gap']:+.2f} ({r['ci'][0]:+.2f} to {r['ci'][1]:+.2f})"]
            for r in t]
    return table(["Type", "Strata", "Variable", "Concession", "Matched unpermitted", "Gap (95%)"], rows)


def t_w3():
    w = J(EX, "fire_weather.json")["W3"]
    bands = []
    for r in w:
        if r["dc_band"] not in bands:
            bands.append(r["dc_band"])
    v = {(r["tenure"], r["dc_band"]): r["per_1000km2_day"] for r in w}
    rows = [[b.replace("-2000", "+")] + [f2(v.get((t, b)), 2) for t in ("oil palm", "pulpwood", "open")] +
            [f2(v[("oil palm", b)] / v[("open", b)]) if v.get(("open", b)) else "—"] for b in bands]
    return table(["Same-day DC", "Oil palm", "Pulpwood", "Open land", "Oil palm / open"], rows)


# ---------------------------------------------------------------- S11 two dry seasons
def t_seasons():
    s = J(EX, "two_seasons.json")
    rows = [[f"{x['lat'][0]}° to {x['lat'][1]}°", f2(x["idn_peak"], 0), f2(x["mys_peak"], 0)] for x in s["dc_by_latitude"]]
    t1 = table(["Latitude band", "Peak Jul–Oct DC, Indonesia", "Peak Jul–Oct DC, Malaysia"], rows)
    rows = [[x["iso"], f"{x['lat'][0]}° to {x['lat'][1]}°", f"{x['mm_2026']:.0f}", f"{x['mm_normal']:.0f}", f"{x['pct']:.0f}%"]
            for x in s["chirps"]]
    t2 = table(["Country", "Latitude band", "Rain 1 Jul–30 Sep 2026 (mm)", "2001–2025 mean (mm)", "Of normal"], rows)
    return t1 + "\n\n" + t2


def t_national():
    rows = []
    for f in ("national.json", "border.json"):
        for r in J(EX, f):
            rows.append([f.replace(".json", ""), r["label"].strip(), f"{r['treated_pct']:.3f}%", f"{r['control_pct']:.3f}%",
                         f"{f2(r['ratio'])} ({ci(r['ci'])})", f"{100 * r['coverage']:.0f}%"])
    return table(["Set", "Comparison", "Treated burned", "Control burned", "Ratio (95%)", "Coverage"], rows) + \
        "\n\n*Treated is Indonesian land and control Malaysian land, except the last three border rows, which compare " \
        "concession with unpermitted land within one country.*"


# ---------------------------------------------------------------- S12 peat maps
def t_peatmaps():          # helper: returns (field-point table, CV table)
    import pandas as pd
    S = pd.read_csv(os.path.join(PRF, "old_maps_field_scores.csv"))
    rows = [[r["map"], int(r["n_field"]), f"{r['peat_called_%']:.0f}%", f2(r["accuracy"]), f2(r["kappa"]),
             f"{100 * r['recall_peat']:.0f}%", f"{100 * r['false_peat_on_mineral']:.0f}%"] for _, r in S.iterrows()]
    t1 = table(["Map", "Field points", "Called peat", "Accuracy", "Kappa", "Peat found", "Mineral called peat"], rows)
    cv = J(PRF, "spatial_cv_all_field.json")
    rows = []
    for w, r in cv["results"].items():
        a = r["at_0.61"]
        rows.append([w, f2(r["auc_mean_over_repeats"]), ci(r["auc_ci95_block_bootstrap"]), f2(a["kappa"]),
                     f"{100 * a['recall_peat']:.0f}%", f"{100 * a['false_peat_on_mineral']:.0f}%"])
    t2 = table(["Field-point weight", "AUC (spatial CV)", "AUC 95% (block bootstrap)", "Kappa at 0.61", "Peat found",
                "Mineral called peat"], rows)
    return t1, t2


def t_peatfield():
    t1 = t_peatmaps()[0]
    for a, b in (("old RF (Kalimantan_3857)", "2019 RF + MaxEnt map"), ("MaxEnt max_90ci", "MaxEnt, 90% CI threshold"),
                 ("MaxEnt max_95ci", "MaxEnt, 95% CI threshold"), ("MaxEnt mean_95ci", "MaxEnt, mean 95% CI threshold"),
                 ("MaxEnt mean_mean+stdv", "MaxEnt, mean + 1 SD threshold")):
        t1 = t1.replace(a, b)
    return t1


def t_peatcv():
    return t_peatmaps()[1]


def t_detadj():
    d = J(EX, "detection_adjust.json")
    rows = [[r["treated"], r["outcome"], f"{f2(r['ratio'], 3)} ({ci(r['ci'], 3)})"] for r in d["ratios"]]
    return table(["Type", "Outcome", "Drought-matched ratio (95%)"], rows)


def t_reconcile():
    import pandas as pd
    P = pd.read_csv(os.path.join(EX, "per_concession_matched_dc.csv"))
    rows = []
    for k in KINDS:
        g = P[P.kind == k]
        w = g.cells * g.coverage
        rows.append([k, f"{g.ratio.median():.2f}", int((g.burned_km2 == 0).sum()),
                     f"{(g.burned_pct * w).sum() / (g.matched_ctl_pct * w).sum():.3f}"])
    return table(["Type", "Median concession ratio", "Concessions with no burned area",
                  "Summed burned / summed expected (cf. pooled)"], rows)


def t_ketapang():
    m = [r for r in J(EX, "matched.json") if r.get("treated") == "Ketapang 4" and r.get("test") == "burn"]
    rows = [[r["matched_on"], f"{r['treated_pct']:.2f}%", f"{r['control_pct']:.2f}%", f"{f2(r['ratio'], 3)} ({ci(r['ratio_ci95'], 3)})",
             f"{100 * r.get('coverage', 1):.1f}%"] for r in m]
    t1 = table(["Strata", "Ketapang four burned", "Matched unpermitted", "Ratio (95%)", "Coverage"], rows)
    rows = []
    for name, f in (("land strata", "concession_checks.json"), ("+ drought band", "concession_checks_dc.json")):
        for i, u in enumerate(J(EX, f)["ketapang_four"]):
            rows.append([f"K{i + 1}", name, f"{f2(u['ratio'])} ({ci([u['ci_lo'], u['ci_hi']])})", f"{u['q_bh']:.3f}",
                         f"{u['burned_km2']:.0f}"])
    t2 = table(["Concession", "Strata", "Ratio (95%)", "BH q", "Burned 2026 (km²)"], rows)
    return t1 + "\n\n" + t2


TABLES = {k[2:]: v for k, v in globals().items() if k.startswith("t_") and callable(v) and k != "t_peatmaps"}


def main():
    tpl = open(os.path.join(MS, "SI_TEMPLATE.md")).read()
    keys = re.findall(r"\{\{(\w+)\}\}", tpl)
    missing = [k for k in keys if k not in TABLES]
    assert not missing, f"unknown table keys: {missing}"
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: TABLES[m.group(1)](), tpl)
    open(os.path.join(MS, "SUPPLEMENTARY.md"), "w").write(out)
    print(f"SUPPLEMENTARY.md: {len(keys)} tables, {len(out.split()):,} words")


if __name__ == "__main__":
    main()
