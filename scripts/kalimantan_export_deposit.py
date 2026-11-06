#!/usr/bin/env python3
"""Deposit tables for the ERL paper (Zenodo), with concessions identified by acronym only.

Company and group names in the working tables (per_concession_matched*.csv, from Global Forest Watch
attributes) are replaced by acronyms: initials of the name after dropping legal forms (PT, Tbk, CV ...)
and unit qualifiers. Unnamed units become "UNNAMED". The acronym is not unique by itself, so every row
also carries the concession type and the run's unit id. The full names stay in the gitignored working
files and are not deposited (author decision, 2026-11-07; the per-concession flag is descriptive, see
kalimantan_flag_calibration.py).

Writes output/deposit/ (gitignored):
  per_concession_drought_matched.csv   primary classification (peak-DC band in the strata)
  per_concession_land_strata.csv       land strata only (sensitivity)
  README.txt                           column notes

    python scripts/kalimantan_export_deposit.py
"""
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
from kalimantan_excess_burn import OUT  # noqa: E402

DEP = os.path.join(os.path.dirname(os.path.dirname(OUT)), "deposit")
DROP = {"PT", "PT.", "TBK", "TBK.", "CV", "CV.", "KUD", "INDONESIA", "UNIT", "THE", "DAN", "AND", "&", "-"}
KEEP = ["kind", "id", "acronym", "group_acronym", "cells", "area_km2", "burned_pct", "matched_ctl_pct", "ratio",
        "ci_lo", "ci_hi", "coverage", "p", "q_bh", "class_fdr", "viirs_ratio", "viirs_ci_lo", "viirs_ci_hi",
        "peat_share", "mean_depth_cm", "palm_share", "forest_share", "burned_km2"]


def acronym(name):
    if not isinstance(name, str) or not name.strip() or name.strip().lower() in ("noname", "nan", "none"):
        return "UNNAMED"
    words = re.split(r"[\s,/()]+", name.upper())
    words = [w for w in words if w and w not in DROP and not re.fullmatch(r"[IVX]+|\d+|P\.?", w)]
    a = "".join(w[0] for w in words if w[0].isalnum())
    return a or "UNNAMED"


def main():
    import pandas as pd
    os.makedirs(DEP, exist_ok=True)
    for src, dst in (("per_concession_matched_dc.csv", "per_concession_drought_matched.csv"),
                     ("per_concession_matched.csv", "per_concession_land_strata.csv")):
        P = pd.read_csv(os.path.join(OUT, src))
        P["acronym"] = P.label.map(acronym)
        P["group_acronym"] = P.group.map(lambda g: acronym(g) if isinstance(g, str) and g.strip().lower() not in ("no group", "unknown", "") else "")
        D = P[[c for c in KEEP if c in P.columns]].sort_values(["kind", "id"])
        names = set(P.label.dropna().astype(str)) | set(P.group.dropna().astype(str))
        text = D.to_csv(index=False)
        leaked = [n for n in names if len(n) > 5 and n in text]
        assert not leaked, f"full names leaked into {dst}: {leaked[:3]}"
        open(os.path.join(DEP, dst), "w").write(text)
        print(f"  {dst}: {len(D)} rows, {D.acronym.nunique()} distinct acronyms, no full names")
    open(os.path.join(DEP, "README.txt"), "w").write(
        "Per-concession matched burned-share ratios, Kalimantan 2026 (Sentinel-2 dNBR + VIIRS burned cells).\n"
        "Concessions are identified by acronym (initials of the company name without legal forms) plus type\n"
        "and unit id; full names are not included. ratio = concession burned share / stratum-weighted burned\n"
        "share of unpermitted land in the same CEM strata; ci_lo, ci_hi = 95% 5 km block-bootstrap interval;\n"
        "p = two-sided percentile p; q_bh = Benjamini-Hochberg q within type; class_fdr = excess / deficit /\n"
        "no difference at q <= 0.05. The class is descriptive: unpermitted patches of the same size and drought\n"
        "are flagged at similar rates (see paper, section 3.3). peat_share = BBSDLP; mean_depth_cm = PEATGRIDS.\n")
    print(f"Saved: {DEP}")


if __name__ == "__main__":
    main()
