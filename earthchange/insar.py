"""InSAR from Sentinel-1 SLC, via ASF HyP3.

WHY THIS DOES NOT USE THE USUAL BACKENDS. Interferometry needs phase, and phase
only exists in SLC products. Earth Engine carries COPERNICUS/S1_GRD and
Planetary Computer carries sentinel-1-grd and sentinel-1-rtc -- all of them
*detected* amplitude, with the phase discarded at production. No amount of code
makes InSAR possible from either. SLC comes from ASF, so this scenario reaches a
third archive, and says so rather than pretending the backend flag applies.

WHY IT DOES NOT PROCESS LOCALLY. Coregistration, precise orbits, a DEM and phase
unwrapping mean ISCE2 or SNAP: multi-gigabyte installs and hours of compute, for
a package whose promise is `pip install` and one command. ASF HyP3 runs the
interferogram on demand and returns coherence and displacement as GeoTIFFs. What
happens here is what the rest of the package does -- threshold, cross with your
zones, report the number and its limits.

TWO PRODUCTS.

  --product coherence     Damage proxy. Compares a PRE-event interferometric
                          pair against a CO-event pair: ground that changed
                          between the two acquisitions loses coherence. Needs
                          three SLCs and two HyP3 jobs.

  --product displacement  Co-seismic ground motion along the satellite line of
                          sight, from unwrapped phase. One pair, one job.

JOBS ARE NOT INSTANT. A HyP3 job takes roughly 20-40 minutes, so a single
blocking call would be a poor fit for a CLI. The first run submits and records
the job names; a later run collects them. `--wait` blocks instead, for a script.
"""

import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request

ASF_SEARCH = "https://api.daac.asf.alaska.edu/services/search/param"

# A 12-day Sentinel-1 repeat is the shortest usable baseline; beyond about six
# weeks C-band coherence over vegetated ground is gone regardless of damage.
MAX_PAIR_DAYS = 48
COHERENCE_DROP = 0.30      # damage-proxy threshold on (pre - co) coherence
LOW_COH_FLOOR = 0.30       # below this, pre-event coherence carries no signal

NOTE_COHERENCE = (
    "Coherence loss is NOT damage. Coherence also falls with vegetation growth, "
    "cultivation, rainfall, and a longer temporal baseline, so the pre-event and "
    "co-event pairs are only comparable when their baselines are similar -- both "
    "are reported below. C-band decorrelates quickly over vegetation, and in "
    "humid tropical terrain coherence is already low outside built-up and bare "
    "ground: over Indonesia this method reads towns, not countryside. Treat the "
    "result as a list of places to verify, never as a damage count.")

NOTE_DISPLACEMENT = (
    "Displacement is along the satellite LINE OF SIGHT, not vertical and not "
    "horizontal; separating those needs both ascending and descending tracks. "
    "Unwrapped phase also carries an atmospheric delay that can reach several "
    "centimetres and mimics real motion, and unwrapping fails where coherence is "
    "low, leaving errors of whole fringes. Validate against GNSS before quoting "
    "a number.")


# --------------------------------------------------------------------------
# SLC search
# --------------------------------------------------------------------------
def _get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "earthchange/insar"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def search_slc(lat, lon, start, end):
    """Sentinel-1 SLC scenes over a point, newest first, InSAR-capable only."""
    q = urllib.parse.urlencode({
        "platform": "Sentinel-1", "processingLevel": "SLC",
        "intersectsWith": f"POINT({lon} {lat})",
        "start": f"{start}T00:00:00Z", "end": f"{end}T23:59:59Z",
        "output": "jsonlite",
    })
    res = _get(f"{ASF_SEARCH}?{q}")
    rows = res["results"] if isinstance(res, dict) and "results" in res else res
    out = []
    for r in rows:
        if r.get("canInSAR") is False:
            continue
        out.append({
            "granule": r.get("granuleName") or r.get("sceneName"),
            "date": r["startTime"][:10],
            "path": r.get("path"),
            "frame": r.get("frame"),
            "direction": (r.get("flightDirection") or "").lower(),
        })
    return sorted(out, key=lambda s: s["date"], reverse=True)


def tracks(scenes):
    """Group scenes by (path, frame). Interferometry only pairs within a track.

    Two scenes from different relative orbits view the ground from different
    geometries and cannot be interfered at all -- this is a harder constraint
    than the same-relative-orbit rule the amplitude scenarios follow.
    """
    by = {}
    for s in scenes:
        by.setdefault((s["path"], s["frame"], s["direction"]), []).append(s)
    for k in by:
        by[k].sort(key=lambda s: s["date"])
    return by


def _days(a, b):
    return abs((dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days)


def _next_pass(stack, today=None):
    """When this track is next acquired, projecting the 12-day repeat forward.

    Rolled forward past today rather than added once: where a frame's stack ends
    weeks ago -- the AOI clipping a neighbouring frame, say -- one increment
    lands in the past, and a refusal that tells you to wait for a date that has
    already gone is worse than one that offers no date at all.
    """
    today = today or dt.date.today()
    nxt = dt.date.fromisoformat(stack[-1]["date"])
    while nxt <= today:
        nxt += dt.timedelta(days=12)
    return nxt


def choose_pairs(scenes, event_date, product, direction=None, today=None):
    """Pick the SLCs to interfere, or explain precisely what is missing.

    For coherence change three scenes are needed on one track: two before the
    event and one after. Returning a half-usable selection would produce a map
    that looks fine and means nothing, so a track that cannot supply them is
    rejected by name.
    """
    ev = dt.date.fromisoformat(event_date)
    best, why = None, []

    for (path, frame, drn), stack in sorted(tracks(scenes).items()):
        if direction and direction != "auto" and drn != direction:
            continue
        pre = [s for s in stack if dt.date.fromisoformat(s["date"]) <= ev]
        post = [s for s in stack if dt.date.fromisoformat(s["date"]) > ev]
        label = f"path {path} frame {frame} {drn}"

        if not post:
            why.append(f"{label}: no post-event scene yet"
                       + (f" (next pass about {_next_pass(stack, today)})" if stack else ""))
            continue
        if not pre:
            why.append(f"{label}: no pre-event scene")
            continue

        co = (pre[-1], post[0])
        if _days(co[0]["date"], co[1]["date"]) > MAX_PAIR_DAYS:
            why.append(f"{label}: co-event baseline "
                       f"{_days(co[0]['date'], co[1]['date'])} days, over the "
                       f"{MAX_PAIR_DAYS}-day limit")
            continue

        pick = {"path": path, "frame": frame, "direction": drn,
                "co_pair": co,
                "co_days": _days(co[0]["date"], co[1]["date"])}

        if product == "coherence":
            if len(pre) < 2:
                why.append(f"{label}: only one pre-event scene; coherence "
                           f"change needs two")
                continue
            pre_pair = (pre[-2], pre[-1])
            pick["pre_pair"] = pre_pair
            pick["pre_days"] = _days(pre_pair[0]["date"], pre_pair[1]["date"])

        # Prefer the pair that straddles the event most tightly.
        if best is None or pick["co_days"] < best["co_days"]:
            best = pick

    return best, why


# --------------------------------------------------------------------------
# HyP3
# --------------------------------------------------------------------------
def _client():
    try:
        import hyp3_sdk
    except ImportError:
        raise SystemExit(
            "InSAR needs the hyp3_sdk package:\n"
            "  pip install 'earthchange[insar]'\n"
            "and a free NASA Earthdata login: https://urs.earthdata.nasa.gov/")
    user = os.environ.get("EARTHDATA_USERNAME")
    pwd = os.environ.get("EARTHDATA_PASSWORD")

    # hyp3_sdk requires both or neither: passing one and not the other fails
    # inside its session setup with a message about the missing half, which
    # reads like a credentials problem when it is really a typo in a shell rc.
    if bool(user) != bool(pwd):
        missing = "EARTHDATA_PASSWORD" if user else "EARTHDATA_USERNAME"
        raise SystemExit(
            f"{missing} is not set, but the other half is. Set both, or unset "
            "both and use ~/.netrc instead.")

    try:
        # With neither set these are None, and hyp3_sdk falls back to ~/.netrc.
        return hyp3_sdk.HyP3(username=user, password=pwd)
    except Exception as e:  # noqa: BLE001 -- give the actual next step
        raise SystemExit(
            f"Could not authenticate to ASF HyP3: {e}\n\n"
            "Put your NASA Earthdata credentials in ~/.netrc:\n"
            "    machine urs.earthdata.nasa.gov\n"
            "        login YOUR_USERNAME\n"
            "        password YOUR_PASSWORD\n"
            "then: chmod 600 ~/.netrc   (netrc is ignored if world-readable)\n\n"
            "or export EARTHDATA_USERNAME and EARTHDATA_PASSWORD.\n"
            "Register free at https://urs.earthdata.nasa.gov/\n"
            "First use also needs HyP3 authorised once at "
            "https://hyp3-api.asf.alaska.edu/")


def job_name(name, kind, pair, variant=""):
    """A deterministic name, so a later run can find the job it submitted.

    HyP3 has no notion of our run directory; the name is the only handle that
    survives between invocations, which is what makes this scenario resumable
    instead of forcing one 40-minute blocking call.

    Derived from the GRANULES ONLY -- not from --name, and not from whether the
    pair happens to be the pre- or co-event one. An interferogram is a function
    of its two granules and nothing else, so including the user's label meant
    the same pair submitted twice under two labels produced two identical jobs.
    That cost 10 credits when I hit it with one pair; on a 400-pair stack it
    would waste thousands. The short hash separates same-day pairs on different
    frames, which the dates alone would collide.

    `variant` covers the JOB PARAMETERS. Two runs over the same granules with
    different parameters are different products -- asking HyP3 for the DEM and
    incidence-angle bands produces a genuinely different result -- so they must
    not share a name. Without this, resubmitting for geometry would find the
    old geometry-less jobs and hand them back as if they were what was asked
    for, which is the worst kind of failure: silent, and it looks like success.
    """
    import hashlib

    del name, kind  # deliberately not part of the identity -- see above
    tag = f"{pair[0]['date']}_{pair[1]['date']}".replace("-", "")
    ident = "|".join(sorted(p["granule"] for p in pair))
    if variant:
        ident += f"|{variant}"
    digest = hashlib.sha1(ident.encode()).hexdigest()[:8]
    suffix = f"-{variant}" if variant else ""
    return f"earthchange-{tag}{suffix}-{digest}"


def submit_or_find(hyp3, name, kind, pair, product):
    """Return an existing job with this name, or submit a new one."""
    jn = job_name(name, kind, pair)
    existing = hyp3.find_jobs(name=jn)
    if len(existing) > 0:
        return jn, existing[0], False
    batch = hyp3.submit_insar_job(
        pair[0]["granule"], pair[1]["granule"], name=jn,
        include_displacement_maps=(product == "displacement"),
        apply_water_mask=True, looks="20x4")
    return jn, batch[0], True


def _state(job):
    return getattr(job, "status_code", "UNKNOWN")


# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
def fetch(job, dest):
    """Download and unpack a finished interferogram once; reuse it afterwards.

    Cached under the job NAME, not the job id. The name is derived from the two
    granules, so any job producing the same interferogram hits the same cache --
    which matters because HyP3 will happily run the identical pair twice under
    two job ids, and a product is ~70 MB. Keying on job id re-downloaded work
    already on disk the moment a pair was resubmitted.
    """
    import zipfile

    os.makedirs(dest, exist_ok=True)
    key = getattr(job, "name", None) or job.job_id
    stem = os.path.join(dest, key)
    if os.path.isdir(stem):
        return stem

    # Products fetched before the cache key changed are still valid; adopt one
    # rather than spending the download again.
    legacy = os.path.join(dest, job.job_id)
    if os.path.isdir(legacy):
        os.rename(legacy, stem)
        return stem

    for p in job.download_files(dest):
        p = str(p)
        if p.endswith(".zip"):
            with zipfile.ZipFile(p) as z:
                z.extractall(dest)
            os.remove(p)

    # HyP3 unpacks to a directory named after the product, not the job id.
    subs = [os.path.join(dest, d) for d in os.listdir(dest)
            if os.path.isdir(os.path.join(dest, d))
            and os.path.join(dest, d) != stem]
    if not subs:
        raise SystemExit(f"HyP3 product for job {job.job_id} unpacked no files")
    os.rename(max(subs, key=os.path.getmtime), stem)
    prune(stem)
    return stem


# Everything the analysis actually opens, plus the metadata the stats quote.
# A product is ~73 MB and _amp.tif alone is 30 MB of it, which nothing here
# reads; the browse images and KMZs are another 9 MB. Over a 700-pair stack
# that is the difference between 52 GB and 27 GB, on a disk with 65 GB free.
KEEP_SUFFIXES = ("_corr.tif", "_unw_phase.tif", "_water_mask.tif",
                 "_los_displacement.tif", "_dem.tif",
                 # Every geometry band HyP3 can emit, whichever flag produced
                 # it. Listing only _lv_theta.tif deleted the _inc_map.tif that
                 # 705 jobs had been resubmitted specifically to obtain -- the
                 # keep-list silently undid the reprocessing. A geometry raster
                 # is a few MB against a 70 MB product; there is no reason to be
                 # selective here.
                 "_lv_theta.tif", "_lv_phi.tif", "_inc_map.tif",
                 "_inc_map_ell.tif",
                 ".txt")


def prune(product_dir):
    """Drop the bands this package never opens. Returns bytes reclaimed.

    Deliberately conservative: it keeps the DEM and incidence-angle bands even
    though the built-in fit ignores them, because MintPy wants them, and a
    re-download costs far more than the disk they occupy.
    """
    freed = 0
    for f in os.listdir(product_dir):
        if f.endswith(KEEP_SUFFIXES) or f.endswith(".xml"):
            continue
        path = os.path.join(product_dir, f)
        if os.path.isfile(path):
            freed += os.path.getsize(path)
            os.remove(path)
    return freed


def band(product_dir, suffix):
    """One named GeoTIFF out of a HyP3 product directory."""
    hits = [os.path.join(product_dir, f) for f in sorted(os.listdir(product_dir))
            if f.endswith(suffix)]
    if not hits:
        have = sorted(f for f in os.listdir(product_dir) if f.endswith(".tif"))
        raise SystemExit(f"no *{suffix} in {os.path.basename(product_dir)}; "
                         f"it holds: {have}")
    return hits[0]


def baselines(product_dir, days=None):
    """Perpendicular baseline from the product metadata, temporal from the dates.

    HyP3 writes a single bare field, `Baseline: -95.6839`, and it is the
    PERPENDICULAR baseline in metres. Treating an unqualified "Baseline" as
    temporal reported two 12-day pairs as -95.7 and 86.1 days -- wrong, and
    wrong in the one field that exists to show whether the two pairs decorrelate
    comparably. Temporal baseline is not in the file at all; it is the
    difference between the two acquisition dates, which the caller already
    knows, so it is passed in rather than guessed at.
    """
    out = {}
    if days is not None:
        out["temporal_baseline_days"] = int(days)
    for f in sorted(os.listdir(product_dir)):
        if not f.endswith(".txt") or f.endswith(".README.md.txt"):
            continue
        for line in open(os.path.join(product_dir, f), errors="ignore"):
            m = re.match(r"\s*(?:Perpendicular\s+)?Baseline\s*:\s*(-?[\d.]+)",
                         line, re.I)
            if m:
                out["perp_baseline_m"] = round(float(m.group(1)), 1)
                break
    return out


def _open(path):
    import numpy as np
    import rasterio

    with rasterio.open(path) as s:
        a = s.read(1).astype("float32")
        if s.nodata is not None:
            a = np.where(a == s.nodata, np.nan, a)
        a = np.where(a == 0, np.nan, a)
        return a, s.transform, s.crs, s.bounds


def _pixel_ha(transform, crs, bounds):
    import numpy as np

    if crs and crs.is_projected:
        return abs(transform.a * transform.e) / 10_000.0
    lat = bounds.bottom + (bounds.top - bounds.bottom) / 2
    return (abs(transform.a * 111_320.0 * np.cos(np.radians(lat)))
            * abs(transform.e * 110_574.0) / 10_000.0)


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
def coherence_change(pre_dir, co_dir, pre_days=None, co_days=None):
    """Damage proxy: how far coherence fell from the pre-event pair to the
    co-event pair.

    Ground that was stable before the event and incoherent across it has
    changed. Where the pre-event pair was ALREADY incoherent -- vegetation,
    water, cultivated land -- the difference carries no information, so those
    pixels are excluded rather than counted as intact. In humid tropics that is
    most of the scene, and saying so is the point.
    """
    import numpy as np

    pre, transform, crs, bounds = _open(band(pre_dir, "_corr.tif"))
    co, _, _, _ = _open(band(co_dir, "_corr.tif"))

    if pre.shape != co.shape:
        n = (min(pre.shape[0], co.shape[0]), min(pre.shape[1], co.shape[1]))
        pre, co = pre[:n[0], :n[1]], co[:n[0], :n[1]]

    usable = np.isfinite(pre) & np.isfinite(co) & (pre >= LOW_COH_FLOOR)
    drop = np.where(usable, pre - co, np.nan)
    ha = _pixel_ha(transform, crs, bounds)

    flagged = usable & (drop >= COHERENCE_DROP)
    stats = {
        "metric": "coherence drop (pre-event pair minus co-event pair)",
        "threshold": COHERENCE_DROP,
        "low_coherence_floor": LOW_COH_FLOOR,
        "pixel_ha": round(ha, 4),
        "aoi_ha": round(float(np.isfinite(pre).sum() * ha), 1),
        "usable_ha": round(float(usable.sum() * ha), 1),
        "usable_pct_of_aoi": round(
            100 * float(usable.sum()) / max(1, int(np.isfinite(pre).sum())), 1),
        "flagged_ha": round(float(flagged.sum() * ha), 1),
        "flagged_pct_of_usable": round(
            100 * float(flagged.sum()) / max(1, int(usable.sum())), 2),
        "mean_drop_where_usable": round(float(np.nanmean(drop)), 3)
        if usable.any() else None,
        "pre_pair_baselines": baselines(pre_dir, pre_days),
        "co_pair_baselines": baselines(co_dir, co_days),
    }
    return drop, flagged, stats, (transform, crs, bounds)


def displacement(co_dir):
    """Line-of-sight motion, with coherence carried alongside as the mask."""
    import numpy as np

    for suffix in ("_los_displacement.tif", "_unw_phase.tif"):
        try:
            path = band(co_dir, suffix)
            break
        except SystemExit:
            continue
    else:
        raise SystemExit("no displacement or unwrapped-phase band in the product")

    disp, transform, crs, bounds = _open(path)
    coh, _, _, _ = _open(band(co_dir, "_corr.tif"))
    if coh.shape != disp.shape:
        n = (min(coh.shape[0], disp.shape[0]), min(coh.shape[1], disp.shape[1]))
        disp, coh = disp[:n[0], :n[1]], coh[:n[0], :n[1]]

    # Unwrapping is unreliable below the coherence floor; those pixels can be
    # wrong by whole fringes, so they are dropped rather than mapped.
    trusted = np.isfinite(disp) & np.isfinite(coh) & (coh >= LOW_COH_FLOOR)
    shown = np.where(trusted, disp, np.nan)
    ha = _pixel_ha(transform, crs, bounds)

    unit = "m" if suffix.endswith("displacement.tif") else "radians"
    stats = {
        "metric": f"line-of-sight displacement ({unit})",
        "band": os.path.basename(path),
        "coherence_floor": LOW_COH_FLOOR,
        "trusted_ha": round(float(trusted.sum() * ha), 1),
        "trusted_pct": round(
            100 * float(trusted.sum()) / max(1, int(np.isfinite(disp).sum())), 1),
        "min": round(float(np.nanmin(shown)), 4) if trusted.any() else None,
        "max": round(float(np.nanmax(shown)), 4) if trusted.any() else None,
        "p05": round(float(np.nanpercentile(shown, 5)), 4) if trusted.any() else None,
        "p95": round(float(np.nanpercentile(shown, 95)), 4) if trusted.any() else None,
        "pair_baselines": baselines(co_dir),
    }
    return shown, stats, (transform, crs, bounds)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def _write_tif(arr, geo, path):
    import numpy as np
    import rasterio

    transform, crs, _ = geo
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0],
                       width=arr.shape[1], count=1, dtype="float32",
                       crs=crs, transform=transform, nodata=np.nan,
                       compress="deflate") as d:
        d.write(arr.astype("float32"), 1)


def _render(arr, geo, product, title, subtitle, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    transform, _, bounds = geo
    ext = [bounds.left, bounds.right, bounds.bottom, bounds.top]

    fig, ax = plt.subplots(figsize=(11, 8.4))
    if product == "coherence":
        # Sequential: only loss is meaningful, and the floor is already applied.
        im = ax.imshow(np.ma.masked_invalid(arr), extent=ext, cmap="inferno_r",
                       vmin=0, vmax=0.8)
        label = "coherence drop (pre-event pair − co-event pair)"
    else:
        # Diverging and symmetric about zero: motion has a sign, and an
        # off-centre colour scale invents an apparent bias.
        lim = float(np.nanpercentile(np.abs(arr), 98)) if np.isfinite(arr).any() else 1
        im = ax.imshow(np.ma.masked_invalid(arr), extent=ext, cmap="RdBu_r",
                       vmin=-lim, vmax=lim)
        label = "line-of-sight displacement (m)  −away / +toward"

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=14, pad=10)
    fig.colorbar(im, ax=ax, shrink=0.72, label=label)
    fig.text(0.5, 0.02, subtitle, ha="center", fontsize=8.5, color="#555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=145, facecolor="white")
    plt.close(fig)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def _select(lat, lon, event_date, product, direction):
    """Find the track and the pairs, or refuse with the reason per track."""
    ev = dt.date.fromisoformat(event_date)
    scenes = search_slc(lat, lon,
                        (ev - dt.timedelta(days=120)).isoformat(),
                        (ev + dt.timedelta(days=60)).isoformat())
    if not scenes:
        raise SystemExit(f"no Sentinel-1 SLC over {lat}, {lon} in that window")

    pick, why = choose_pairs(scenes, event_date, product, direction)
    if pick is None:
        raise SystemExit("\n".join(
            ["no usable interferometric pair yet:"] + [f"  {w}" for w in why]
            + ["", "Sentinel-1 repeats every 12 days on a given track; a "
                   "post-event scene has to exist before anything can be "
                   "compared."]))

    print(f"track: path {pick['path']} frame {pick['frame']} {pick['direction']}")
    print(f"co-event pair : {pick['co_pair'][0]['date']} -> "
          f"{pick['co_pair'][1]['date']}  ({pick['co_days']} days)")
    if product == "coherence":
        print(f"pre-event pair: {pick['pre_pair'][0]['date']} -> "
              f"{pick['pre_pair'][1]['date']}  ({pick['pre_days']} days)")
    return pick


def _pairs_wanted(pick, product):
    wanted = [("co", pick["co_pair"])]
    if product == "coherence":
        wanted.insert(0, ("pre", pick["pre_pair"]))
    return wanted


def _get_jobs(hyp3, name, pick, product, run_dir, run_id, event_date, wait):
    """Submit or recover the HyP3 jobs. Returns None while any is unfinished."""
    wanted = _pairs_wanted(pick, product)
    jobs = {}
    for kind, pair in wanted:
        jn, job, is_new = submit_or_find(hyp3, name, kind, pair, product)
        jobs[kind] = job
        print(f"  {kind}-pair job {jn}: {_state(job)}"
              + ("  (submitted now)" if is_new else "  (already known)"))

    with open(os.path.join(run_dir, "jobs.json"), "w") as f:
        json.dump({"run_id": run_id, "product": product,
                   "event_date": event_date,
                   "track": {k: pick[k] for k in ("path", "frame", "direction")},
                   "jobs": {k: {"name": job_name(name, k, dict(wanted)[k]),
                                "id": j.job_id, "status": _state(j)}
                            for k, j in jobs.items()}}, f, indent=2)

    if wait:
        print("waiting for HyP3 (20-40 minutes is normal)...")
        jobs = {k: hyp3.watch(j) for k, j in jobs.items()}

    pending = {k: _state(j) for k, j in jobs.items() if _state(j) != "SUCCEEDED"}
    if pending:
        print("\nJobs are not finished: "
              + ", ".join(f"{k}={v}" for k, v in pending.items()))
        print("HyP3 takes roughly 20-40 minutes. Nothing is lost -- re-run the "
              "same command to collect, or add --wait to block here.")
        return None
    return jobs


def _analyse(product, prods, pick, name, run_dir):
    """Run the chosen analysis and write its GeoTIFF."""
    import numpy as np

    co = pick["co_pair"]
    if product == "coherence":
        arr, flagged, stats, geo = coherence_change(
            prods["pre"], prods["co"], pick["pre_days"], pick["co_days"])
        pre = pick["pre_pair"]
        _write_tif(np.where(flagged, arr, np.nan), geo,
                   os.path.join(run_dir, f"{name}_coherence_drop.tif"))
        return arr, stats, geo, NOTE_COHERENCE, (
            f"{name} — coherence change, around {pick['co_pair'][0]['date']}",
            f"pre {pre[0]['date']}→{pre[1]['date']} vs "
            f"co {co[0]['date']}→{co[1]['date']} · path {pick['path']} "
            f"{pick['direction']} · flagged where drop ≥ {COHERENCE_DROP}")

    arr, stats, geo = displacement(prods["co"])
    _write_tif(arr, geo, os.path.join(run_dir, f"{name}_los_displacement.tif"))
    return arr, stats, geo, NOTE_DISPLACEMENT, (
        f"{name} — line-of-sight displacement",
        f"{co[0]['date']}→{co[1]['date']} · path {pick['path']} "
        f"{pick['direction']} · masked below coherence {LOW_COH_FLOOR}")


def run(lat, lon, radius, name, run_dir, run_id, event_date=None,
        product="coherence", direction=None, wait=False, lang="id", **_):
    if not event_date:
        raise SystemExit(
            "insar needs --event-date YYYY-MM-DD: the pairs are chosen around "
            "it, and 'before' and 'after' are not defined without it.")

    print(f"InSAR ({product}) — SLC from ASF, interferograms from ASF HyP3.")
    print("Neither Earth Engine nor Planetary Computer carries SLC, so the "
          "--backend flag does not apply here.")

    pick = _select(lat, lon, event_date, product, direction)
    jobs = _get_jobs(_client(), name, pick, product, run_dir, run_id,
                     event_date, wait)
    if jobs is None:
        return

    prods = {k: fetch(j, os.path.join(run_dir, "hyp3")) for k, j in jobs.items()}
    arr, stats, geo, note, (title, sub) = _analyse(
        product, prods, pick, name, run_dir)

    fig = os.path.join(run_dir, f"{name}_insar_{product}.png")
    _render(arr, geo, product, title, sub, fig)

    pairs = {"co_event": [pick["co_pair"][0]["date"], pick["co_pair"][1]["date"]],
             "co_event_days": pick["co_days"]}
    if product == "coherence":
        pairs["pre_event"] = [pick["pre_pair"][0]["date"],
                              pick["pre_pair"][1]["date"]]
        pairs["pre_event_days"] = pick["pre_days"]

    with open(os.path.join(run_dir, "stats.json"), "w") as f:
        json.dump({
            "run_id": run_id, "scenario": "insar", "name": name,
            "product": product, "event_date": event_date,
            "track": {k: pick[k] for k in ("path", "frame", "direction")},
            "pairs": pairs,
            "granules": {k: [p["granule"] for p in pair]
                         for k, pair in _pairs_wanted(pick, product)},
            "sources": {
                "slc": "Sentinel-1 SLC via ASF DAAC",
                "processing": "ASF HyP3 INSAR_GAMMA, 20x4 looks, water masked"},
            "results": stats,
            "outputs": {"figure": os.path.basename(fig)},
            "note": note,
        }, f, indent=2)

    print(f"\n{os.path.basename(fig)}")
    if product == "coherence":
        print(f"  {stats['usable_pct_of_aoi']}% of the AOI had enough "
              f"pre-event coherence to judge")
        print(f"  {stats['flagged_ha']:,.0f} ha flagged "
              f"({stats['flagged_pct_of_usable']}% of that usable part)")
    else:
        print(f"  LOS {stats['p05']} to {stats['p95']}, "
              f"{stats['trusted_pct']}% trusted")
