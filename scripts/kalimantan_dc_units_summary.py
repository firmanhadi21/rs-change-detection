#!/usr/bin/env python3
"""Compare per-concession classes with and without the peak-Drought-Code stratum (review M1), and refit
the oil-palm excess model (kalimantan_heterogeneity.fit, same covariates) on the drought-matched classes.

    python scripts/kalimantan_dc_units_summary.py
"""
import contextlib
import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import DATA, OUT  # noqa: E402
from kalimantan_heterogeneity import SHARE_STEP, fit  # noqa: E402

RES = os.path.join(OUT, "dc_units_summary.json")


def main():
    import pandas as pd
    A = pd.read_csv(os.path.join(OUT, "per_concession_matched.csv"))
    B = pd.read_csv(os.path.join(OUT, "per_concession_matched_dc.csv"))
    out = {"classes": {}, "peat_bins": {}, "model": {}}
    for kind in ("oil palm", "pulpwood"):
        for tag, P in (("island-wide", A), ("same drought", B)):
            g = P[P.kind == kind]
            ex = g[g.class_fdr == "excess"]
            r = {"units": int(len(g)), "excess": int(len(ex)),
                 "no_difference": int((g.class_fdr == "no difference").sum()),
                 "deficit": int((g.class_fdr == "deficit").sum()),
                 "excess_burned_km2": float(ex.burned_km2.sum()), "burned_km2": float(g.burned_km2.sum()),
                 "excess_share_pct": 100 * float(ex.burned_km2.sum() / g.burned_km2.sum()),
                 "excess_area_km2": float(ex.area_km2.sum()), "excess_peat_km2": float((ex.area_km2 * ex.peat_share).sum()),
                 "excess_with_peat_pct": 100 * float((ex.peat_share > 0.01).mean()) if len(ex) else None}
            out["classes"][f"{kind}|{tag}"] = r
            print(f"{kind:<9} {tag:<12} excess {r['excess']:>3}/{r['units']} ({100 * r['excess'] / r['units']:.1f}%), "
                  f"no diff {r['no_difference']}, deficit {r['deficit']}; excess hold {r['excess_burned_km2']:.0f} of "
                  f"{r['burned_km2']:.0f} km2 ({r['excess_share_pct']:.0f}%); excess units with peat {r['excess_with_peat_pct']:.0f}%")
    both = A.merge(B[["kind", "id", "class_fdr"]], on=["kind", "id"], suffixes=("", "_dc"))
    print(pd.crosstab([both.kind, both.class_fdr], both.class_fdr_dc).to_string())
    out["crosstab"] = {f"{k}|{a}|{b}": int(v) for (k, a), row in
                       pd.crosstab([both.kind, both.class_fdr], both.class_fdr_dc).iterrows() for b, v in row.items()}

    U = pd.read_csv(os.path.join(OUT, "heterogeneity_units.csv")).drop(columns=["excess"])
    C = pd.read_csv(os.path.join(DATA, "peat_check_covariates.csv"))[["kind", "id", "peat_share", "gpm_share"]]
    D = U.merge(B[["kind", "id", "class_fdr", "ratio", "ci_lo", "ci_hi"]].rename(
        columns={"class_fdr": "cls_dc", "ratio": "ratio_dc", "ci_lo": "lo_dc", "ci_hi": "hi_dc"}), on=["kind", "id"]) \
        .merge(C.rename(columns={"peat_share": "ps"}), on=["kind", "id"])
    O = D[D.kind == "oil palm"].copy()
    O["excess"] = O.cls_dc.eq("excess")
    for col in ("ps", "gpm_share"):
        v = O[col].fillna(0)
        bins = []
        for lo, hi, lab in ((-0.01, 0.01, "<1"), (0.01, 0.25, "1-25"), (0.25, 0.5, "25-50"), (0.5, 0.75, "50-75"), (0.75, 1.01, "75-100")):
            m = (v > lo) & (v <= hi)
            bins.append({"bin": lab, "units": int(m.sum()), "excess_pct": 100 * float(O[m].excess.mean())})
        out["peat_bins"][col] = bins
        print(col, [f"{b['bin']}: {b['excess_pct']:.1f}% (n={b['units']})" for b in bins])
    z = lambda x: (x - x.mean()) / x.std()      # noqa: E731
    for c in ("depth_m", "forest_share", "log_area"):
        O[c + "_z"] = z(O[c])
    O["ratio"], O["ci_lo"], O["ci_hi"] = O.ratio_dc, O.lo_dc, O.hi_dc
    O["peat_share_10pp"], O["gpm_share_10pp"] = O.ps / SHARE_STEP, O.gpm_share.fillna(0) / SHARE_STEP
    ctrl = ["forest_share_z", "log_area_z", "ind_share_10pp", "small_share_10pp", "recent_share_10pp", "st_in_process",
            "st_location_permit", "st_unknown", "grouped", "rspo_cert_share_10pp", "rspo_member_share_10pp",
            "other_permit_share_10pp"]
    for name, terms in (("main (depth)", ["depth_m_z"]), ("BBSDLP share", ["peat_share_10pp"]), ("GPM share", ["gpm_share_10pp"])):
        with contextlib.redirect_stdout(io.StringIO()):
            res = fit(O, terms + ctrl, name)
        out["model"][name] = res
        lg = res.get("logit", {})
        print(f"  {name:<14}" + "; ".join(f"{t} OR {lg[t]['or']:.2f} [{lg[t]['lo']:.2f}, {lg[t]['hi']:.2f}] p {lg[t]['p']:.3f}"
                                         for t in terms if t in lg) + (f"  (logit failed: {res.get('logit_error')})" if not lg else ""))
        if name == "main (depth)" and lg:
            for t in ("grouped", "st_location_permit", "rspo_cert_share_10pp", "log_area_z", "ind_share_10pp"):
                print(f"      {t:<22} OR {lg[t]['or']:.2f} [{lg[t]['lo']:.2f}, {lg[t]['hi']:.2f}] p {lg[t]['p']:.3f}")
    json.dump(out, open(RES, "w"), indent=1, default=float)
    print(f"Saved: {RES}")


if __name__ == "__main__":
    main()
