#!/usr/bin/env python3
"""earthchain — the fire-and-smoke chain, in causal order, from anywhere.

There is no single scenario for a comprehensive fire-and-smoke assessment, and
there should not be: each step answers a different question, several are
expensive, and you usually want two or three of them. What was missing was the
ORDER, and the date arithmetic around it.

  1 drought        was it dry?                      precondition
  2 fire-danger    is it dangerous, on whose land?  FDRS, forward-looking
  3 smoke-track    where is the smoke going?        forward trajectories
  4 smoke-exposure who is breathing it?             person-days by ISPU class
  5 smoke-track    where did their air come from?   backward, HYSPLIT
  6 haze           what did it look like?           PM2.5 + fires + admin
  7 fire-record    what happened, per designation?  closed seasons only
  8 fire-brief     assemble it into one deliverable reads 1-7, no data

THE TRAP THIS EXISTS TO HANDLE is that the steps read six archives and they do
not end on the same day. Measured 2026-08-09:

  ERA5-Land daily     8 days behind   binds steps 1, 2, 7
  ERA5 hourly         6 days behind   step 3
  GDAS1 on S3         2 days behind   step 5
  FIRMS               1 day behind    seeds and hotspots
  CAMS               runs 3 days AHEAD -- it is a forecast
  MODIS burned area 100 days behind   step 7, see below
  WorldPop            2020 is the last year, age structure 2020 only

ERA5-Land binds, so --end takes its last day and every other date is derived
from it. One number to change instead of six.

Step 7 is not in the default step list. MODIS burned area lags about three
months, so a record for the current season would report near-zero hectares
burned and read as good news. Run it against a closed season.

This replaces scripts/fire_smoke_chain.sh, which only worked from a checkout.
Same flags.
"""

import argparse
import datetime as dt
import os
import subprocess
import sys

SEASON_DAYS = 90        # exposure and haze window
RECORD_DAYS = 210       # step 7 needs a longer run-up; see _steps()
HYSPLIT_LEAD = 4        # GDAS1 is fresher than ERA5, so step 5 can run later

DEFAULT_STEPS = "1,2,3,4,5,6,8"


def _iso(d, delta):
    return (dt.date.fromisoformat(d) + dt.timedelta(days=delta)).isoformat()


def _steps(a):
    """Every step as (number, label, argv), with the dates already derived."""
    season = _iso(a.end, -SEASON_DAYS)
    record = _iso(a.end, -RECORD_DAYS)
    hy_day = _iso(a.end, HYSPLIT_LEAD)

    area = ["--admin", a.admin] if a.admin else ["--bbox", a.bbox]
    area += ["-n", a.name]
    # A district-sized AOI under-reports which districts the smoke crossed, so
    # the smoke steps take a wider box when one is given -- and are labelled for
    # it. Naming them after the province produced "Di mana penduduk terpapar --
    # Kalteng" over a map whose only shaded districts were in Kalbar, which
    # reads as a bug in the analysis rather than a finding about it.
    wide = (["--bbox", a.wide, "-n", f"{a.name}-regional"] if a.wide
            else list(area))
    zone = (["--zones", a.zones, "--zone-field", a.zone_field]
            if a.zones else [])

    def out(sub):
        return ["-o", os.path.join(a.out, sub)]

    return [
        (1, "drought — was it dry?",
         ["-s", "drought", *area, "--drought-end", a.end, "--spi-months", "3",
          "--cdi", *out("1_drought")]),
        (2, "fire-danger — FDRS, and which designation is driest",
         ["-s", "fire-danger", *area, "--date", a.end, "--spinup", "60",
          *zone, *out("2_fire_danger")]),
        (3, "smoke-track forward — where the smoke goes",
         ["-s", "smoke-track", *area, "--date", a.end, "--track-hours", "48",
          "--track-parcels", "25", *out("3_track_fwd")]),
        (4, "smoke-exposure — who breathes it, person-days by ISPU class",
         ["-s", "smoke-exposure", *wide, "--season", f"{season}:{a.end}",
          "--pop-year", "2020", *out("4_exposure")]),
        # HYSPLIT because backward is refused on the kinematic engine: reversing
        # a single-level integrator looks like source attribution while being no
        # more defensible than the forward fan.
        (5, "smoke-track backward — where their air came from (HYSPLIT)",
         ["-s", "smoke-track", *wide, "--date", hy_day, "--engine", "hysplit",
          "--direction", "backward", "--track-hours", "48",
          "--track-parcels", "12", *out("5_track_back")]),
        (6, "haze — PM2.5 with fires and admin context",
         ["-s", "haze", *area, "--haze-start", season, "--haze-end", a.end,
          *out("6_haze")]),
        # A 90-day window opens after every zone has already crossed its
        # thresholds and reports them all crossing on day one -- the window's
        # left edge masquerading as a finding. DC has a ~52-day time lag.
        (7, "fire-record — per-designation accountability (closed seasons only)",
         ["-s", "fire-record", *area, "--season", f"{record}:{a.end}",
          *zone, *out("7_record")]),
    ]


def _run(argv, dry):
    """One step, as its own process, so a failure does not poison the next."""
    cmd = [sys.executable, "-m", "earthchange.detect", *argv]
    print("   $ earthchange " + " ".join(argv))
    if dry:
        return 0
    return subprocess.run(cmd).returncode


def _brief(a, dry):
    cmd = [sys.executable, "-m", "earthchange.brief", a.out, "--lang", a.lang]
    print(f"   $ earthbrief {a.out} --lang {a.lang}")
    if dry:
        return 0
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser(
        prog="earthchain",
        description="Run the fire-and-smoke chain in causal order.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--end", required=True, metavar="YYYY-MM-DD",
                    help="last day of the assessment. ERA5-Land binds the "
                         "chain, so use its last available day; every other "
                         "date is derived from this one")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--admin", help="admin area name (FAO GAUL)")
    g.add_argument("--bbox", help="w,s,e,n in lon/lat")
    ap.add_argument("--name", help="output label (defaults to --admin)")
    ap.add_argument("--zones", help="your own polygon layer for steps 2 and 7")
    ap.add_argument("--zone-field", help="attribute naming the responsible party")
    ap.add_argument("--wide", metavar="W,S,E,N",
                    help="wider box for the two smoke steps; a district-sized "
                         "AOI under-reports which districts the smoke crossed")
    ap.add_argument("--out", default="output/chain", help="output folder")
    ap.add_argument("--steps", default=DEFAULT_STEPS,
                    help=f"which steps to run (default {DEFAULT_STEPS}). This "
                         "REPLACES the list rather than adding to it: "
                         "--steps 7 runs only step 7")
    ap.add_argument("--lang", choices=("id", "en"), default="id",
                    help="language for the assembled brief")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the commands without running them")
    a = ap.parse_args()

    a.name = a.name or a.admin or "aoi"
    if a.zones and not a.zone_field:
        ap.error("--zones needs --zone-field")
    try:
        dt.date.fromisoformat(a.end)
    except ValueError:
        ap.error(f"--end must be YYYY-MM-DD, got {a.end!r}")
    wanted = {s.strip() for s in a.steps.split(",") if s.strip()}

    failed = []
    for num, label, argv in _steps(a):
        if str(num) not in wanted:
            continue
        print(f"\n── {num}. {label}")
        if _run(argv, a.dry_run) != 0:
            failed.append(num)
            print(f"   step {num} failed — continuing")

    if "8" in wanted:
        print("\n── 8. fire-brief — assemble the six claims into one deliverable")
        _brief(a, a.dry_run)

    print(f"\nAll outputs under {a.out}/")
    if failed:
        print(f"Steps that failed: {', '.join(str(f) for f in failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
