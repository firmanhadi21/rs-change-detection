"""Time-series InSAR: line-of-sight velocity from a stack of interferograms.

WHAT THIS IS FOR. A single interferogram tells you what moved between two dates.
A stack tells you what has been moving steadily -- land subsidence, volcano
inflation, slope creep -- and, before an earthquake, it gives you the BASELINE
without which a co-seismic measurement cannot be read. If the coast was already
moving 8 mm/yr, an offset measured afterwards means nothing until you subtract
that.

WHAT THIS IS NOT FOR. It is not earthquake prediction. Reliably observed
precursory deformation is not an established phenomenon, and nothing here should
be presented as detecting one. Over a volcanic arc the dominant signal will be
volcanoes, not tectonic loading.

THE INVERSION IS DELIBERATELY SIMPLE. A least-squares linear velocity per pixel
over the unwrapped-phase stack, referenced to a stable point, masked by
coherence. It does NOT correct tropospheric delay, DEM error, or unwrapping
errors, and it does not separate seasonal from secular motion. Those are what
MintPy and StaMPS exist for, so this also writes a MintPy-ready directory: the
quick answer here, the defensible one there. `--export-mintpy` and see
docs/INSAR_TIMESERIES.md.

COST IS REAL. Every pair is a HyP3 job charged to your credits, and a four-year
stack is several hundred pairs. Nothing is submitted until you have seen the
network and its price and passed --confirm.
"""

import datetime as dt
import json
import os

from .insar import (LOW_COH_FLOOR, _client, _open, _pixel_ha, band, fetch,
                    job_name, search_slc, tracks)

# Fallback only. The real figure is read from HyP3's own cost table, because
# guessing it once cost real money: I inferred 5 from a 20-credit drop over what
# I believed were four jobs, having read the balance while only two had been
# charged. INSAR_GAMMA at 20x4 looks is 10, so a 348-pair estimate came out at
# half the true price.
CREDITS_PER_JOB = 10
DEFAULT_CONNECTIONS = 3      # each scene paired with the next N in time
MAX_TEMPORAL_DAYS = 60       # beyond this C-band coherence is gone in the wet tropics

NOTE = (
    "Linear line-of-sight velocity from a least-squares fit over unwrapped "
    "phase, referenced to the most coherent stable pixel. NOT corrected for "
    "tropospheric delay, DEM error, or unwrapping error, and seasonal motion is "
    "not separated from secular -- a wet-season signal can look like subsidence. "
    "LOS mixes vertical and east-west; separating them needs both ascending and "
    "descending tracks. Over a volcanic arc the largest signals are usually "
    "volcanoes, not tectonics. This is a reconnaissance velocity field: use it "
    "to find where to look, and MintPy or StaMPS to defend a number.")


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------
def pick_track(scenes, direction=None, frame=None):
    """The track with the most scenes, since depth is what a velocity needs."""
    best = None
    for (path, frm, drn), stack in tracks(scenes).items():
        if direction and direction != "auto" and drn != direction:
            continue
        if frame and frm != frame:
            continue
        if best is None or len(stack) > len(best[1]):
            best = ((path, frm, drn), stack)
    if best is None:
        raise SystemExit("no track matches that --orbit-pass / --frame")
    return best


def network(stack, connections=DEFAULT_CONNECTIONS,
            max_days=MAX_TEMPORAL_DAYS):
    """Small-baseline pairs: each scene against the next few in time.

    Pairs longer than max_days are dropped rather than submitted. In humid
    tropics they decorrelate to noise, and a noisy interferogram in the stack
    does not average out -- it drags the fit.
    """
    pairs, skipped = [], 0
    for i, a in enumerate(stack):
        for b in stack[i + 1:i + 1 + connections]:
            gap = (dt.date.fromisoformat(b["date"])
                   - dt.date.fromisoformat(a["date"])).days
            if gap > max_days:
                skipped += 1
                continue
            pairs.append((a, b))
    return pairs, skipped


def credits_per_job(hyp3=None, job_type="INSAR_GAMMA", looks="20x4"):
    """Per-job cost, from HyP3's own table rather than a constant.

    The table is authoritative and versioned server-side; a hardcoded number
    goes stale silently and the user only finds out from the balance. Falls back
    to the constant when offline, since a plan that cannot price itself is still
    better than no plan.
    """
    try:
        table = (hyp3 or _client()).costs()
        entry = table.get(job_type, {})
        if "cost" in entry:
            return int(entry["cost"])
        return int(entry.get("cost_table", {}).get(looks, CREDITS_PER_JOB))
    except Exception:  # noqa: BLE001 -- pricing must never block planning
        return CREDITS_PER_JOB


def plan(track_key, stack, pairs, skipped, per_job=CREDITS_PER_JOB):
    """Show the network and its price. Nothing is charged for looking."""
    path, frame, drn = track_key
    span = (dt.date.fromisoformat(stack[-1]["date"])
            - dt.date.fromisoformat(stack[0]["date"])).days
    print(f"track          : path {path} frame {frame} {drn}")
    print(f"scenes         : {len(stack)}  "
          f"{stack[0]['date']} → {stack[-1]['date']}  ({span} days)")
    print(f"pairs          : {len(pairs)}"
          + (f"  ({skipped} dropped over {MAX_TEMPORAL_DAYS} days)"
             if skipped else ""))
    print(f"HyP3 credits   : ~{len(pairs) * per_job} ({per_job} per pair, "
          f"INSAR_GAMMA at 20x4 looks)")
    print(f"                 INSAR_ISCE_BURST costs 1 credit per pair, but "
          f"covers a single burst\n                 (~20x5 km) rather than the "
          f"whole frame")
    return {"path": path, "frame": frame, "direction": drn,
            "scenes": len(stack), "span_days": span,
            "first": stack[0]["date"], "last": stack[-1]["date"],
            "pairs": len(pairs), "dropped_pairs": skipped,
            "credits_per_pair": per_job,
            "estimated_credits": len(pairs) * per_job}


# --------------------------------------------------------------------------
# Inversion
# --------------------------------------------------------------------------
def velocity(products, wavelength_m=0.055465):
    """Least-squares linear LOS velocity per pixel, in mm/yr.

    Solves d = v * dt for v across all pairs at once, so pairs that disagree
    pull against each other instead of the last one winning. Pixels are only
    fitted where enough pairs stayed coherent; the count is reported, because a
    velocity from three pairs and one from forty should not look alike on a map.
    """
    import numpy as np

    rows, phases, cohs, geo = [], [], [], None
    for pdir, (d1, d2) in products:
        unw, transform, crs, bounds = _open(band(pdir, "_unw_phase.tif"))
        coh, _, _, _ = _open(band(pdir, "_corr.tif"))
        geo = geo or (transform, crs, bounds)
        rows.append((dt.date.fromisoformat(d2)
                     - dt.date.fromisoformat(d1)).days / 365.25)
        phases.append(unw)
        cohs.append(coh)

    shape = min((p.shape for p in phases), key=lambda s: (s[0], s[1]))
    phases = np.stack([p[:shape[0], :shape[1]] for p in phases])
    cohs = np.stack([c[:shape[0], :shape[1]] for c in cohs])
    dt_yr = np.asarray(rows, dtype="float32")

    # Unwrapped phase to metres of range change, then to mm.
    disp = phases * (wavelength_m / (4 * np.pi)) * 1000.0
    good = np.isfinite(disp) & np.isfinite(cohs) & (cohs >= LOW_COH_FLOOR)
    n_good = good.sum(axis=0)

    w = np.where(good, 1.0, 0.0)
    x = dt_yr[:, None, None] * w
    y = np.where(good, disp, 0.0)
    # Least squares through the origin: velocity is a rate, and an intercept
    # here would absorb the reference offset we remove explicitly below.
    denom = (x * x).sum(axis=0)
    vel = np.where(denom > 0, (x * y).sum(axis=0) / np.where(denom > 0, denom, 1),
                   np.nan)
    vel = np.where(n_good >= max(3, len(products) // 4), vel, np.nan)

    # Reference to the most-observed coherent pixel: InSAR measures relative
    # motion, so an unreferenced velocity field has an arbitrary offset.
    if np.isfinite(vel).any():
        flat = np.where(np.isfinite(vel), n_good, -1)
        ref = np.unravel_index(np.argmax(flat), flat.shape)
        vel = vel - vel[ref]
    else:
        ref = (0, 0)

    # The span the fit ACTUALLY rests on, which is not the requested window.
    # A four-year request collected while later jobs were still processing fitted
    # only the two years already downloaded, and reported span_days 1447 beside
    # pairs_used 174 -- a velocity labelled with a baseline it never had.
    used_dates = sorted(d for _, pair in products for d in pair)
    span_used = (dt.date.fromisoformat(used_dates[-1])
                 - dt.date.fromisoformat(used_dates[0])).days

    stats = {
        "unit": "mm/yr, line of sight (negative = moving away from satellite)",
        "pairs_used": len(products),
        "pairs_first_date": used_dates[0],
        "pairs_last_date": used_dates[-1],
        "span_days_used": span_used,
        "reference_pixel_rowcol": [int(ref[0]), int(ref[1])],
        "min_pairs_per_pixel": int(max(3, len(products) // 4)),
        # Percent of pixels that HAD data, not of the whole array. The AOI is a
        # bounding box over an island: most of it is sea, so dividing by
        # vel.size reported 9.6% for a fit that actually covered most of the
        # land, and made a usable result look like a failed one.
        "fitted_pct_of_observed": round(
            100 * float(np.isfinite(vel).sum())
            / max(1, int((n_good > 0).sum())), 1),
        "fitted_pct_of_frame": round(
            100 * float(np.isfinite(vel).sum()) / vel.size, 1),
        "observed_pixels": int((n_good > 0).sum()),
        "median_pairs_per_fitted_pixel": int(np.median(n_good[np.isfinite(vel)]))
        if np.isfinite(vel).any() else 0,
        "p05": round(float(np.nanpercentile(vel, 5)), 2) if np.isfinite(vel).any() else None,
        "p95": round(float(np.nanpercentile(vel, 95)), 2) if np.isfinite(vel).any() else None,
    }
    return vel, n_good, stats, geo


# --------------------------------------------------------------------------
# MintPy hand-off
# --------------------------------------------------------------------------
def export_mintpy(products, run_dir, track):
    """Lay the downloaded products out the way MintPy's HyP3 loader expects.

    Not an attempt to run MintPy -- its dependency tree (gdal, isce2, cartopy)
    is conda-shaped and would break `pip install earthchange` for most people.
    What this removes is the tedious part: the directory layout and a config
    that already points at it, so the serious analysis starts from something
    correct rather than from scratch.
    """
    root = os.path.join(run_dir, "mintpy")
    os.makedirs(root, exist_ok=True)

    listing = []
    for pdir, (d1, d2) in products:
        listing.append({"product": os.path.basename(pdir),
                        "reference": d1, "secondary": d2,
                        "path": os.path.relpath(pdir, root)})

    cfg = f"""# Generated by earthchange -s insar-series.
# Run:  smallbaselineApp.py {os.path.join(root, 'earthchange.cfg')}
#
# The interferograms below are HyP3 INSAR_GAMMA products, already geocoded, so
# mintpy.load.processor must be hyp3 and NOT isce.
mintpy.load.processor        = hyp3
mintpy.load.unwFile          = ../hyp3/*/*_unw_phase.tif
mintpy.load.corFile          = ../hyp3/*/*_corr.tif
mintpy.load.demFile          = ../hyp3/*/*_dem.tif
mintpy.load.incAngleFile     = ../hyp3/*/*_lv_theta.tif

# Corrections this scenario does NOT apply, which is the reason to come here.
mintpy.troposphericDelay.method   = pyaps
mintpy.topographicResidual        = yes
mintpy.unwrapError.method         = bridging

mintpy.reference.minCoherence     = {LOW_COH_FLOOR}
mintpy.network.tempBaseMax        = {MAX_TEMPORAL_DAYS}
"""
    with open(os.path.join(root, "earthchange.cfg"), "w") as f:
        f.write(cfg)
    with open(os.path.join(root, "interferograms.json"), "w") as f:
        json.dump({"track": track, "count": len(listing),
                   "interferograms": listing}, f, indent=2)
    return root


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def _render(vel, n_good, geo, title, subtitle, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    _, _, bounds = geo
    ext = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    lim = float(np.nanpercentile(np.abs(vel), 98)) if np.isfinite(vel).any() else 10

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.6))
    im = axes[0].imshow(np.ma.masked_invalid(vel), extent=ext, cmap="RdBu_r",
                        vmin=-lim, vmax=lim)
    axes[0].set_title("LOS velocity", fontsize=12)
    fig.colorbar(im, ax=axes[0], shrink=0.8, label="mm/yr")

    # How many pairs each pixel was fitted from: a velocity from three
    # interferograms and one from forty must not look equally solid.
    im2 = axes[1].imshow(np.ma.masked_where(n_good == 0, n_good), extent=ext,
                         cmap="viridis")
    axes[1].set_title("coherent pairs per pixel", fontsize=12)
    fig.colorbar(im2, ax=axes[1], shrink=0.8, label="pairs")

    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(title, fontsize=14)
    fig.text(0.5, 0.02, subtitle, ha="center", fontsize=8.5, color="#555")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(path, dpi=145, facecolor="white")
    plt.close(fig)


def _collect(name, pairs, meta, run_dir, wait):
    """Submit or recover every pair, then download those that finished.

    Returns None when too few have finished to fit anything, which is the
    normal state for the first few hours of a large stack: the jobs keep
    running on ASF and the next run picks them up by name.
    """
    hyp3 = _client()

    # One listing, indexed by name -- not find_jobs() per pair. At 174 pairs a
    # lookup each was 174 round trips before a single job was submitted, and
    # two tracks doubled it.
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=180)
    known = {}
    for j in hyp3.find_jobs(start=since):
        if j.name:
            known.setdefault(j.name, j)

    want = {job_name(name, "ts", pair): pair for pair in pairs}
    missing = [(jn, p) for jn, p in want.items() if jn not in known]
    print(f"{len(want) - len(missing)} already submitted, "
          f"{len(missing)} to submit")

    # Price only what still has to be submitted. Charging for the whole network
    # made the guard refuse to COLLECT a stack that was already paid for: on the
    # four-year descending track it demanded 3540 credits to fetch 174 finished
    # interferograms, because it counted the 180 already bought.
    due = len(missing) * meta["credits_per_pair"]
    have = hyp3.check_credits()
    if missing and have is not None and have < due:
        raise SystemExit(
            f"{due} credits needed for the {len(missing)} pairs not yet "
            f"submitted, {have} available. Shorten the window or lower "
            "--connections. Pairs already submitted cost nothing to collect.")

    # Batch rather than one call each. The API caps a request, so chunk it.
    for i in range(0, len(missing), 100):
        chunk = missing[i:i + 100]
        prepared = [{
            "job_type": "INSAR_GAMMA",
            "name": jn,
            "job_parameters": {
                "granules": [p[0]["granule"], p[1]["granule"]],
                "apply_water_mask": True,
                "looks": "20x4",
            },
        } for jn, p in chunk]
        for j in hyp3.submit_prepared_jobs(prepared):
            known[j.name] = j
        print(f"  submitted {min(i + 100, len(missing))}/{len(missing)}")

    jobs = {jn: (known[jn], pair) for jn, pair in want.items() if jn in known}
    print(f"{len(jobs)} jobs tracked")

    if wait:
        print("waiting for HyP3 — hundreds of pairs takes hours...")
        jobs = {jn: (hyp3.watch(j), p) for jn, (j, p) in jobs.items()}

    done = {jn: (j, p) for jn, (j, p) in jobs.items()
            if getattr(j, "status_code", "") == "SUCCEEDED"}
    print(f"{len(done)}/{len(jobs)} finished")
    if len(done) < max(3, len(jobs) // 4):
        print("Too few finished to fit a velocity. Re-run to collect later.")
        return None

    return [(fetch(job, os.path.join(run_dir, "hyp3")),
             (pair[0]["date"], pair[1]["date"]))
            for _, (job, pair) in sorted(done.items())]


def run(lat, lon, radius, name, run_dir, run_id, start=None, end=None,
        direction=None, connections=DEFAULT_CONNECTIONS, confirm=False,
        wait=False, export_mintpy_only=False, **_):
    import numpy as np

    if not (start and end):
        raise SystemExit(
            "insar-series needs --series-start and --series-end. A velocity is "
            "a rate, and the window it is measured over is part of the answer.")

    print("Time-series InSAR — SLC from ASF, interferograms from ASF HyP3.")
    scenes = search_slc(lat, lon, start, end)
    if not scenes:
        raise SystemExit(f"no Sentinel-1 SLC over {lat}, {lon} in {start}..{end}")

    track_key, stack = pick_track(scenes, direction)
    pairs, skipped = network(stack, connections)
    if not pairs:
        raise SystemExit("no pair survives the temporal-baseline limit")

    meta = plan(track_key, stack, pairs, skipped, credits_per_job())
    with open(os.path.join(run_dir, "plan.json"), "w") as f:
        json.dump(meta, f, indent=2)

    if not confirm:
        print("\nNothing submitted. This would spend "
              f"~{meta['estimated_credits']} HyP3 credits.")
        print("Re-run with --confirm to submit, or narrow it with "
              "--series-start / --series-end / --connections.")
        return

    products = _collect(name, pairs, meta, run_dir, wait)
    if products is None:
        return

    mintpy_dir = export_mintpy(products, run_dir, meta)
    if export_mintpy_only:
        print(f"MintPy layout written to {mintpy_dir}")
        return

    vel, n_good, stats, geo = velocity(products)
    fig = os.path.join(run_dir, f"{name}_los_velocity.png")
    _render(vel, n_good, geo,
            f"{name} — line-of-sight velocity, {meta['first']} → {meta['last']}",
            f"path {meta['path']} {meta['direction']} · {stats['pairs_used']} "
            f"pairs · referenced to the most-observed coherent pixel · "
            f"NOT tropospheric-corrected", fig)

    from .insar import _write_tif
    _write_tif(vel, geo, os.path.join(run_dir, f"{name}_los_velocity.tif"))

    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump({"run_id": run_id, "scenario": "insar-series", "name": name,
                   "window": [start, end], "track": meta,
                   "sources": {"slc": "Sentinel-1 SLC via ASF DAAC",
                               "processing": "ASF HyP3 INSAR_GAMMA"},
                   "results": stats,
                   "outputs": {"figure": os.path.basename(fig),
                               "mintpy": os.path.relpath(mintpy_dir, run_dir)},
                   "note": NOTE}, f, indent=2)

    print(f"\n{os.path.basename(fig)}")
    if stats["span_days_used"] < meta["span_days"] - 60:
        print(f"  NOTE: fitted over {stats['pairs_first_date']} → "
              f"{stats['pairs_last_date']} ({stats['span_days_used']} days), "
              f"not the {meta['span_days']}-day window requested — "
              f"{stats['pairs_used']} of {meta['pairs']} pairs were ready. "
              f"Re-run to collect the rest.")
    print(f"  {stats['fitted_pct_of_observed']}% of observed pixels fitted, median "
          f"{stats['median_pairs_per_fitted_pixel']} pairs each")
    print(f"  LOS velocity p05..p95: {stats['p05']} .. {stats['p95']} mm/yr")
    print(f"  MintPy layout: {os.path.relpath(mintpy_dir, run_dir)}")
