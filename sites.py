#!/usr/bin/env python3
"""Site definitions for the change-detection pipeline.

Every data-collection script targets a *site* — an area of interest plus the
time periods to analyse. Pick one with `--site <name>` or the `SITE` env var
(default: capkala). Add a new location by copying an entry below.

    python3 data-collection/02_sirad_gee.py --site konawe
    SITE=konawe python3 data-collection/01_sentinel2_download.py
"""

import os
import sys

SITES = {
    "capkala": {
        "label": "Capkala, Bengkayang, Kalimantan Barat",
        "lat": 0.6784,
        "lon": 109.0836,
        "radius_km": 1.5,
        "sentinel2_date": "2026-06-19",  # low-cloud acquisition
        "sirad_periods": {
            "R_2024": ("2024-01-01", "2024-12-31"),
            "G_2025": ("2025-01-01", "2025-12-31"),
            "B_2026": ("2026-03-01", "2026-06-30"),  # post police raid
        },
    },
    "konawe": {
        # Approximate centroid of the documented Mandiodo / Molawe illegal
        # nickel block, Konawe Utara, Sulawesi Tenggara (~3°20'S 122°15'E).
        # Verify / refine the AOI for your exact area of interest.
        "label": "Mandiodo (Konawe Utara), Sulawesi Tenggara",
        "lat": -3.333,
        "lon": 122.25,
        "radius_km": 6.0,
        "sentinel2_date": "2026-06-19",
        "sirad_periods": {
            "R_2024": ("2024-01-01", "2024-12-31"),
            "G_2025": ("2025-01-01", "2025-12-31"),
            "B_2026": ("2026-03-01", "2026-06-30"),
        },
    },
}

DEFAULT_SITE = "capkala"


def get_site(argv=None):
    """Resolve the target site from `--site NAME`, `--site=NAME`, or $SITE."""
    argv = sys.argv if argv is None else argv
    name = os.environ.get("SITE", DEFAULT_SITE)
    for i, arg in enumerate(argv):
        if arg == "--site" and i + 1 < len(argv):
            name = argv[i + 1]
        elif arg.startswith("--site="):
            name = arg.split("=", 1)[1]

    name = name.lower()
    if name not in SITES:
        raise SystemExit(
            f"Unknown site '{name}'. Available: {', '.join(sorted(SITES))}"
        )
    site = dict(SITES[name])
    site["key"] = name
    return site
