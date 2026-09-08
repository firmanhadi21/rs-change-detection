#!/usr/bin/env python3
"""HYSPLIT engine for smoke-track — real trajectories instead of a kinematic fan.

The kinematic engine in smoke_track carries parcels on a single level of ERA5
wind and says so loudly, because that is all it can honestly claim. This module
hands the same job to NOAA ARL's HYSPLIT, which does what the caveat says is
missing: vertical motion, the mixing depth, terrain, and -- the part that
actually matters for accountability -- backward trajectories from a receptor.

Two things make this practical rather than aspirational:

  * The public unregistered HYSPLIT build is not crippled for our purposes. Its
    one restriction is dispersion using *forecast* meteorology. Everything here
    is retrospective, so the restriction never binds.
  * The meteorology is on public S3 with no credentials -- GDAS1 at 1 degree,
    3-hourly, back to December 2004. No FTP account, no CDS registration.

What this module will not do is install HYSPLIT. ARL distributes it under a use
agreement that a person has to read and accept, and accepting a licence on
someone's behalf is not a thing a package should do. So this behaves the way
smoke-video behaves toward ffmpeg: find it, or explain exactly how to get it.

Registration is only needed for forecast dispersion or the source code:
  Mac    https://www.ready.noaa.gov/HYSPLIT_applehysp.php
  Linux  https://www.ready.noaa.gov/HYSPLIT_linuxtrial.php
"""

import calendar
import datetime as dt
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request

ARL_BUCKET = "https://noaa-oar-arl-hysplit-pds.s3.amazonaws.com"
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec")
GDAS1_START = dt.date(2004, 12, 1)

# Where the unregistered installers put things, in the order worth trying.
BIN_HINTS = ("/Applications/hysplit/exec", "~/hysplit/exec", "~/Hysplit/exec",
             "/opt/hysplit/exec", "/usr/local/hysplit/exec")

INSTALL_HELP = """\
smoke-track --engine hysplit needs the HYSPLIT executable `hyts_std`.

It is free and the public (unregistered) build is enough: its only limitation
is dispersion with *forecast* meteorology, and everything here is retrospective.

  Mac    https://www.ready.noaa.gov/HYSPLIT_applehysp.php
  Linux  https://www.ready.noaa.gov/HYSPLIT_linuxtrial.php

Then either put its exec/ directory on PATH, set HYSPLIT_DIR to the install
root, or pass --hysplit-bin /path/to/hyts_std.

The meteorology is fetched automatically from public S3 and needs no account.
Run without --engine hysplit for the kinematic fan, which needs no binary."""


# macOS kills unsigned quarantined binaries with SIGKILL and no message at all,
# which is a miserable thing to debug from the outside: no stdout, no stderr,
# exit -9. ARL ships HYSPLIT unsigned, so every Mac user who downloads it with a
# browser hits this. Name it precisely rather than let them guess.
_QUARANTINE_HELP = """\
HYSPLIT was killed by macOS before it ran (SIGKILL, no output).

This is not your run and not the model: ARL ships HYSPLIT unsigned, and macOS
refuses to launch unsigned binaries that carry a download quarantine flag.

Clear the flag on the install, once:

    xattr -dr com.apple.quarantine {root}

Then re-run. To confirm the flag is what is there:

    xattr -l {exe}"""


def _install_root(binary):
    """The HYSPLIT install root, given a path to something in its exec/."""
    exec_dir = os.path.dirname(os.path.abspath(binary))
    parent = os.path.dirname(exec_dir)
    return parent if os.path.basename(exec_dir) == "exec" else exec_dir


EXE = {"trajectory": "hyts_std", "concentration": "hycs_std"}


def find_binary(explicit=None, kind="trajectory"):
    """Locate the HYSPLIT executable: explicit, HYSPLIT_DIR, PATH, then hints.

    `kind` picks the model: trajectories are hyts_std, dispersion is hycs_std.
    They are separate executables in the same exec/ directory -- running a
    concentration CONTROL through hyts_std does not fail loudly, it reads the
    first eleven records and silently ignores the emission, grid and deposition
    blocks that make it a dispersion run.
    """
    exe = EXE.get(kind)
    if exe is None:
        raise ValueError(f"unknown HYSPLIT model kind: {kind!r}")

    if explicit:
        p = os.path.expanduser(explicit)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            # An explicit path for the wrong model is worth catching here: the
            # failure it causes downstream is an empty cdump with exit 0.
            if os.path.basename(p) != exe and kind == "concentration":
                sibling = os.path.join(os.path.dirname(p), exe)
                if os.access(sibling, os.X_OK):
                    return sibling
                raise SystemExit(
                    f"--hysplit-bin points at {os.path.basename(p)}, but a "
                    f"dispersion run needs {exe}, and it is not beside it.")
            return p
        raise SystemExit(f"--hysplit-bin: not an executable file: {p}")

    root = os.environ.get("HYSPLIT_DIR")
    if root:
        p = os.path.join(os.path.expanduser(root), "exec", exe)
        if os.access(p, os.X_OK):
            return p

    found = shutil.which(exe)
    if found:
        return found

    for hint in BIN_HINTS:
        p = os.path.join(os.path.expanduser(hint), exe)
        if os.access(p, os.X_OK):
            return p
    return None


# ARL publishes several meteorologies on the same public bucket, and which one
# a run can use is usually decided by the calendar rather than by preference.
# GDAS1 is weekly and lags about a week, so the last few days are simply not
# there; GFS 0.25 is written daily and reaches yesterday. That gap is exactly
# where an eruption or a fire that matters lands.
#
#   forecast=True marks a product ARL classes as forecast. The unregistered
#   HYSPLIT build refuses DISPERSION on forecast meteorology -- trajectories
#   are fine. Recorded here so the failure can be explained rather than
#   discovered as an unexplained exit.
MET_PRODUCTS = {
    "gdas1": {
        "cadence": "weekly", "res": "1 deg, 3-hourly", "size_mib": 571,
        "start": dt.date(2004, 12, 1), "forecast": False,
    },
    "gfs0p25": {
        "cadence": "daily", "res": "0.25 deg, 3-hourly", "size_mib": 3192,
        "start": dt.date(2019, 6, 13), "forecast": True,
    },
    "gdas0p5": {
        "cadence": "daily", "res": "0.5 deg, 3-hourly", "size_mib": 1100,
        "start": dt.date(2007, 9, 1), "forecast": False,
    },
}


def _daily_keys(start, hours, direction, product):
    """Day files spanning the run, for the products written one file per day."""
    span = dt.timedelta(hours=abs(hours))
    day1 = dt.timedelta(days=1)
    # No extra day of margin here, unlike the weekly path. A daily file covers
    # its own calendar day, so the days containing the two endpoints are
    # exactly what the run needs -- and at 3.1 GiB each an unnecessary margin
    # file is a third of the download for nothing.
    if direction == "backward":
        lo, hi = start - span, start
    else:
        lo, hi = start, start + span
    floor = MET_PRODUCTS[product]["start"]
    if lo.date() < floor:
        raise SystemExit(
            f"{product} on the ARL archive starts {floor}; this run reaches "
            f"back to {lo.date()}.")
    keys, day = [], lo.date()
    while day <= hi.date():
        name = f"{day:%Y%m%d}_{product}"
        keys.append((f"{product}/{day.year}/{day.month:02d}/{name}", name))
        day += day1
    return keys


def met_keys(start, hours, direction="forward", product="gdas1"):
    """Which met files a run spans, for the chosen product.

    GDAS1 is weekly and needs the week arithmetic below; gfs0p25 and gdas0p5
    are one file per day and need none of it, so they short-circuit.
    """
    if product not in MET_PRODUCTS:
        raise SystemExit(f"unknown meteorology {product!r}; have "
                         f"{', '.join(sorted(MET_PRODUCTS))}")
    if MET_PRODUCTS[product]["cadence"] == "daily":
        return _daily_keys(start, hours, direction, product)
    return _gdas1_keys(start, hours, direction)


def _gdas1_keys(start, hours, direction="forward"):
    """Which GDAS1 weekly files a run spans.

    ARL cuts GDAS1 into weeks w1=1-7, w2=8-14, w3=15-21, w4=22-28, w5=29-end,
    so a run that straddles the 21st needs two files and one near a month
    boundary needs two months. Backward runs reach into the past, which is the
    easy thing to get wrong: the span is [start-hours, start], not [start, +].
    """
    span = dt.timedelta(hours=abs(hours))
    day = dt.timedelta(days=1)
    # Margin goes in the direction of travel only. A symmetric margin looks
    # harmless and costs an extra 571 MiB download on every forward run that
    # starts early in a week, for meteorology the parcels never reach.
    if direction == "backward":
        lo, hi = start - span - day, start
    else:
        lo, hi = start, start + span + day
    if lo.date() < GDAS1_START:
        raise SystemExit(
            f"GDAS1 in the ARL archive starts {GDAS1_START}; this run reaches "
            f"back to {lo.date()}. For earlier dates the NCEP/NCAR reanalysis "
            "archive (1948-) is an option, but it is 2.5 degrees and this "
            "module does not wire it up yet.")

    keys, seen = [], set()
    day = lo.date()
    while day <= hi.date():
        week = min((day.day - 1) // 7 + 1, 5)
        name = f"gdas1.{MONTHS[day.month - 1]}{day.year % 100:02d}.w{week}"
        if name not in seen:
            seen.add(name)
            keys.append((f"gdas1/{day.year}/{name}", name))
        day += dt.timedelta(days=1)
    return keys


_NAME_RE = re.compile(r"gdas1\.([a-z]{3})(\d{2})\.w(\d)$")


def week_end(year, month, week):
    """Last day a GDAS1 weekly file covers.

    ARL cuts weeks as 1-7, 8-14, 15-21, 22-28 and then w5 for whatever is left,
    so the fifth file is three days long in February and four in August.
    """
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, last if week >= 5 else min(week * 7, last))


def _list_prefix(prefix):
    """Object keys under a prefix in the public ARL bucket."""
    url = f"{ARL_BUCKET}/?list-type=2&prefix={prefix}"
    with urllib.request.urlopen(url, timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    return re.findall(r"<Key>([^<]+)</Key>", body)


def archive_end():
    """Newest day GDAS1 actually covers, read from the bucket.

    Not a constant: ARL publishes a weekly file once its week has run, so the
    end of the archive moves and the current week is always absent.
    """
    today = dt.date.today()
    for year in (today.year, today.year - 1):
        best = None
        for key in _list_prefix(f"gdas1/{year}/"):
            m = _NAME_RE.search(key)
            if not m:
                continue
            mon = MONTHS.index(m.group(1)) + 1
            end = week_end(2000 + int(m.group(2)), mon, int(m.group(3)))
            if best is None or end > best:
                best = end
        if best:
            return best
    return None


def availability_message(missing, have_end, hours, direction):
    """A run the published archive cannot cover, said usefully.

    A bare 404 on a filename nobody recognises is not a usable error. Name the
    day the archive reaches and the dates that would work instead.
    """
    span = dt.timedelta(hours=abs(hours or 0))
    lines = [f"ARL has not published {missing} yet."]
    if have_end:
        lines.append(f"GDAS1 currently reaches {have_end}.")
        if hours:
            latest = have_end if direction == "backward" else have_end - span
            lines.append("")
            lines.append(f"With --track-hours {abs(hours)}, --date has to be "
                         f"{latest} or earlier.")
    lines.append("")
    lines.append("ARL writes each weekly file once its week has run, so the "
                 "current week is always missing.")
    lines.append("")
    lines.append("For the last few days, GFS 0.25 deg is written DAILY and "
                 "reaches yesterday:")
    lines.append("    --met-product gfs0p25")
    lines.append("It is finer than GDAS1 (0.25 deg vs 1 deg) but 3.1 GiB per "
                 "day rather than 571 MiB per week, and ARL classes it as a "
                 "forecast product -- see --met-product in the help.")
    lines.append("")
    lines.append("smoke-video reads live feeds and needs no archive at all.")
    return "\n".join(lines)


def fetch_met(keys, cache_dir, hours=None, direction="forward"):
    """Download the weekly met files, skipping any already cached.

    These are ~571 MiB each and are reused by every run in the same week, so
    they are cached outside the run directory on purpose -- re-downloading half
    a gigabyte per run would make the scenario unusable.
    """
    os.makedirs(cache_dir, exist_ok=True)
    out = []
    for key, name in keys:
        dest = os.path.join(cache_dir, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
            print(f"  met cached: {name} "
                  f"({os.path.getsize(dest) / 2**20:.0f} MiB)")
        else:
            _download(key, name, dest, hours, direction)
        out.append(dest)

    # HYSPLIT reads the met file list from CONTROL positionally and does not
    # sort it. Out-of-order days are not rejected -- the run just stops at the
    # first gap in time, silently producing a short plume that looks like a
    # calm day. Sorting by name works because every product here is named so
    # that lexical order is chronological.
    return sorted(out, key=os.path.basename)


def _download(key, name, dest, hours, direction):
    """One weekly file, streamed to a .part and renamed only when complete.

    A half-written file left at the real name would be treated as cached by the
    next run and handed to HYSPLIT as meteorology.
    """
    print(f"  fetching {name} from ARL public S3 …")
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(f"{ARL_BUCKET}/{key}") as r, \
                open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(1 << 22)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    print(f"\r    {got / 2**20:6.0f} / {total / 2**20:.0f} MiB",
                          end="", flush=True)
            print()
    except Exception as exc:                                       # noqa: BLE001
        if os.path.exists(tmp):
            os.remove(tmp)
        # A 404 is not a network problem: ARL writes each weekly file only once
        # its week has run, so the current week is simply not there yet.
        if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
            raise SystemExit(availability_message(name, archive_end(), hours,
                                                  direction))
        raise SystemExit(f"Could not fetch {key} from ARL S3: {exc}")
    os.replace(tmp, dest)


def write_control(path, start, points, hours, met_paths, out_dir, out_name,
                  vertical=0, model_top=10000.0):
    """Write a HYSPLIT trajectory CONTROL file.

    Record order is fixed and unforgiving -- HYSPLIT reads positionally and a
    missing line shifts everything after it into the wrong variable.
    Backward runs are a negative run time, not a flag.
    """
    lines = [f"{start.year % 100:02d} {start.month:02d} {start.day:02d} "
             f"{start.hour:02d}",
             f"{len(points)}"]
    for lat, lon, hgt in points:
        lines.append(f"{lat:.4f} {lon:.4f} {hgt:.1f}")
    lines += [f"{int(hours)}", f"{vertical}", f"{model_top:.1f}",
              f"{len(met_paths)}"]
    for m in met_paths:
        lines.append(os.path.dirname(os.path.abspath(m)) + os.sep)
        lines.append(os.path.basename(m))
    lines += [os.path.abspath(out_dir) + os.sep, out_name]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def read_tdump(path):
    """Parse a HYSPLIT endpoints file into per-trajectory point lists.

    Returns [[(datetime, lon, lat, height_m_agl), ...], ...] -- deliberately the
    same shape _advect produces, so the rest of smoke-track cannot tell which
    engine ran.

    Format (ARL user's guide S263):
      rec 1   ngrids, version
      rec 2   x ngrids: model id, start y m d h, forecast hour
      rec 3   ntraj, direction, vertical motion method
      rec 4   x ntraj: start y m d h, start lat lon, start height
      rec 5   nvars, variable labels
      rec 6+  traj#, grid#, y m d h min, forecast hour, age, lat, lon, height,
              then nvars diagnostics
    """
    with open(path) as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not lines:
        raise SystemExit(f"HYSPLIT wrote an empty endpoints file: {path}")

    i = 0
    ngrids = int(lines[i].split()[0])
    i += 1 + ngrids
    head = lines[i].split()
    ntraj = int(head[0])
    direction = head[1].upper() if len(head) > 1 else "FORWARD"
    i += 1 + ntraj
    i += 1                                    # record 5: nvars + labels

    paths = {}
    for ln in lines[i:]:
        p = ln.split()
        # traj grid y m d h min fcast age lat lon hgt  -> 12 minimum
        if len(p) < 12:
            raise SystemExit(
                f"Unparseable endpoint record in {path}:\n  {ln!r}\n"
                "Expected at least 12 whitespace-separated fields.")
        try:
            tid = int(p[0])
            yy, mm, dd, hh, mi = (int(p[2]), int(p[3]), int(p[4]),
                                  int(p[5]), int(p[6]))
            lat, lon, hgt = float(p[9]), float(p[10]), float(p[11])
        except ValueError as exc:
            raise SystemExit(f"Bad endpoint record in {path}: {ln!r} ({exc})")
        year = 2000 + yy if yy < 70 else 1900 + yy
        when = dt.datetime(year, mm, dd, hh, mi, tzinfo=dt.UTC)
        paths.setdefault(tid, []).append((when, lon, lat, hgt))

    out = []
    for tid in sorted(paths):
        pts = sorted(paths[tid], key=lambda r: r[0])
        # A backward run is emitted oldest-first once sorted, which is already
        # the direction the air travelled -- source first, receptor last. That
        # is what the figure wants, so both directions render identically.
        out.append(pts)
    return out, direction


def run_trajectories(binary, start, points, hours, met_paths, work_dir,
                     vertical=0):
    """Run hyts_std once for all start points and return the parsed endpoints."""
    os.makedirs(work_dir, exist_ok=True)
    out_name = "tdump"
    write_control(os.path.join(work_dir, "CONTROL"), start, points, hours,
                  met_paths, work_dir, out_name, vertical=vertical)

    # HYSPLIT reads ./CONTROL from the working directory and looks for
    # ASCDATA.CFG beside it; without the terrain/roughness defaults it warns and
    # substitutes its own, which is survivable but worth avoiding.
    root = os.path.dirname(os.path.dirname(os.path.abspath(binary)))
    for cfg in ("ASCDATA.CFG",):
        src = os.path.join(root, "bdyfiles", cfg)
        if os.path.exists(src) and not os.path.exists(
                os.path.join(work_dir, cfg)):
            shutil.copy(src, work_dir)

    print(f"  running {os.path.basename(binary)} "
          f"({len(points)} start points, {hours:+d} h) …")
    try:
        # stdin closed on purpose: HYSPLIT prompts interactively when CONTROL is
        # missing or malformed, so an inherited stdin turns a five-second
        # mistake into a thirty-minute hang.
        proc = subprocess.run([binary], cwd=work_dir, capture_output=True,
                              text=True, timeout=1800,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise SystemExit("HYSPLIT did not finish within 30 minutes.")

    if proc.returncode == -9 and sys.platform == "darwin":
        raise SystemExit(_QUARANTINE_HELP.format(exe=binary,
                                                 root=_install_root(binary)))
    tdump = os.path.join(work_dir, out_name)
    if not os.path.exists(tdump):
        tail = ((proc.stdout or "") + (proc.stderr or "")
                ).strip().splitlines()[-12:]
        raise SystemExit(
            f"HYSPLIT produced no endpoints file (exit {proc.returncode}).\n  "
            + "\n  ".join(tail or ["(no output)"]))
    return read_tdump(tdump)


# ---------------------------------------------------------------- dispersion
#
# A trajectory says where the air went. A dispersion run says how much of
# something is in it, which is the question anyone downwind is actually
# asking -- and the one smoke-track's caveat has been deferring to HYSPLIT all
# along. The model is the same; the CONTROL grows from 11 records to 31, and
# the output stops being text.
#
# The extra records, in the order HYSPLIT reads them positionally:
#
#   emission     pollutant id, rate per hour, duration, release start
#   grid         centre, spacing, span, output dir and file
#   levels       how many, and their heights in m AGL
#   sampling     start, stop, and the averaging interval
#   deposition   five records PER POLLUTANT: particle, dry, wet, decay, resusp
#
# Every one is mandatory even when zero. Omitting the deposition block does
# not disable deposition -- it shifts every later record into the wrong
# variable, and HYSPLIT reports nothing.

def write_concentration_control(
        path, start, points, hours, met_paths, out_dir, out_name,
        rate=1.0, duration=1.0, release_start=None, pollutant="AIR ",
        centre=None, spacing=(0.05, 0.05), span=(30.0, 30.0),
        levels=(0, 10000), sample_hours=1, sample_type=0,
        vertical=0, model_top=10000.0, deposition=None):
    """Write a HYSPLIT concentration CONTROL file.

    Defaults describe a unit-mass tracer with no deposition, which is the
    honest choice when the emission is unknown: the field is then relative and
    can be read as "where the plume goes", not "how many micrograms".
    Deposition is opt-in precisely so that nobody gets a settling velocity they
    did not ask for and cannot cite.

    levels are m AGL and MUST be ascending. A concentration level of 0 is a
    deposition accumulation surface, not a height -- so (0, 10000) means "one
    layer averaged 0-10000 m plus a deposition plane", which is what the plots
    that say "averaged between 0 m and 10000 m" are showing.

    sample_type: 0 average over the interval, 1 snapshot, 2 maximum.
    """
    if release_start is None:
        release_start = start
    if centre is None:
        # 0.0 0.0 tells HYSPLIT to centre the grid on the source, which keeps
        # the plume in frame without the caller computing a centroid.
        centre = (0.0, 0.0)
    levels = tuple(int(round(v)) for v in levels)
    if list(levels) != sorted(levels):
        raise SystemExit(f"concentration levels must ascend, got {levels}")

    L = [f"{start.year % 100:02d} {start.month:02d} {start.day:02d} "
         f"{start.hour:02d}",
         f"{len(points)}"]
    for lat, lon, hgt in points:
        L.append(f"{lat:.4f} {lon:.4f} {hgt:.1f}")
    L += [f"{int(hours)}", f"{vertical}", f"{model_top:.1f}",
          f"{len(met_paths)}"]
    for m in met_paths:
        L.append(os.path.dirname(os.path.abspath(m)) + os.sep)
        L.append(os.path.basename(m))

    # Emission. The id is CHAR*4 in the binary output, so it is padded here
    # rather than at read time; a 3-character name would otherwise come back
    # with a stray byte attached.
    L += ["1",
          f"{pollutant[:4]:<4}",
          f"{rate:g}",
          f"{duration:g}",
          f"{release_start.year % 100:02d} {release_start.month:02d} "
          f"{release_start.day:02d} {release_start.hour:02d} "
          f"{release_start.minute:02d}"]

    # Concentration grid.
    L += ["1",
          f"{centre[0]:.4f} {centre[1]:.4f}",
          f"{spacing[0]:g} {spacing[1]:g}",
          f"{span[0]:g} {span[1]:g}",
          os.path.abspath(out_dir) + os.sep,
          out_name,
          f"{len(levels)}",
          " ".join(str(v) for v in levels)]

    stop = start + dt.timedelta(hours=abs(int(hours)))
    lo, hi = (stop, start) if hours < 0 else (start, stop)
    L += [f"{lo.year % 100:02d} {lo.month:02d} {lo.day:02d} "
          f"{lo.hour:02d} {lo.minute:02d}",
          f"{hi.year % 100:02d} {hi.month:02d} {hi.day:02d} "
          f"{hi.hour:02d} {hi.minute:02d}",
          f"{sample_type:02d} {int(sample_hours):02d} 00"]

    # Deposition: five records, always present, zeros meaning "none".
    d = deposition or {}
    L += ["1",
          "{:g} {:g} {:g}".format(*d.get("particle", (0.0, 0.0, 0.0))),
          "{:g} {:g} {:g} {:g} {:g}".format(*d.get("dry",
                                                   (0.0,) * 5)),
          "{:g} {:g} {:g}".format(*d.get("wet", (0.0, 0.0, 0.0))),
          f"{d.get('half_life', 0.0):g}",
          f"{d.get('resuspension', 0.0):g}"]

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    return path


def _fortran_records(raw):
    """Yield the payload of each Fortran sequential unformatted record.

    HYSPLIT writes big-endian with a 4-byte length marker before and after
    every record. Reading the markers rather than assuming record sizes is
    what makes this robust to the packing flag and to variable pollutant and
    level counts.
    """
    i, n = 0, len(raw)
    while i + 4 <= n:
        (size,) = struct.unpack(">i", raw[i:i + 4])
        if size < 0 or i + 8 + size > n:
            break
        yield raw[i + 4:i + 4 + size]
        i += 8 + size


def read_cdump(path):
    """Parse a HYSPLIT binary concentration file.

    Returns (grids, meta) where grids is a list of
        {"start": datetime, "stop": datetime, "pollutant": str,
         "level": int, "data": 2-D list of float, nlat x nlon}
    and meta carries the grid geometry:
        {"nlat", "nlon", "dlat", "dlon", "lat0", "lon0", "levels", "pollutants"}

    lat0/lon0 are the LOWER-LEFT corner, so row 0 of data is the southernmost
    row. Anything that renders this with origin="upper" without flipping will
    put the plume on the wrong side of the source, which is the kind of error
    that looks plausible and is not.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if not raw:
        raise SystemExit(f"HYSPLIT wrote an empty concentration file: {path}")

    recs = list(_fortran_records(raw))
    if len(recs) < 5:
        raise SystemExit(
            f"{path}: only {len(recs)} Fortran records; expected at least 5. "
            "This does not look like a HYSPLIT cdump.")

    # Record 1: model id, met start, #locations, packing flag.
    r = recs[0]
    nloc, packed = struct.unpack(">ii", r[24:32])

    k = 1 + nloc                      # skip the per-release records

    nlat, nlon, dlat, dlon, lat0, lon0 = struct.unpack(">iiffff", recs[k][:24])
    k += 1

    nlev = struct.unpack(">i", recs[k][:4])[0]
    levels = list(struct.unpack(f">{nlev}i", recs[k][4:4 + 4 * nlev]))
    k += 1

    npol = struct.unpack(">i", recs[k][:4])[0]
    pollutants = [recs[k][4 + 4 * j:8 + 4 * j].decode("ascii", "replace")
                  .strip() for j in range(npol)]
    k += 1

    def _when(buf):
        yy, mo, da, hh, mi = struct.unpack(">5i", buf[:20])
        year = 2000 + yy if yy < 70 else 1900 + yy
        return dt.datetime(year, mo, da, hh, mi, tzinfo=dt.UTC)

    grids = []
    while k + 1 < len(recs):
        start, stop = _when(recs[k]), _when(recs[k + 1])
        k += 2
        for _ in range(npol * nlev):
            if k >= len(recs):
                break
            rec = recs[k]
            k += 1
            pol = rec[0:4].decode("ascii", "replace").strip()
            lev = struct.unpack(">i", rec[4:8])[0]
            plane = [[0.0] * nlon for _ in range(nlat)]
            if packed:
                (np_,) = struct.unpack(">i", rec[8:12])
                off = 12
                for _p in range(np_):
                    i_, j_ = struct.unpack(">hh", rec[off:off + 4])
                    (val,) = struct.unpack(">f", rec[off + 4:off + 8])
                    off += 8
                    # HYSPLIT indexes 1-based, i across longitude.
                    if 1 <= j_ <= nlat and 1 <= i_ <= nlon:
                        plane[j_ - 1][i_ - 1] = val
            else:
                vals = struct.unpack(f">{nlat * nlon}f",
                                     rec[8:8 + 4 * nlat * nlon])
                for jj in range(nlat):
                    plane[jj] = list(vals[jj * nlon:(jj + 1) * nlon])
            grids.append({"start": start, "stop": stop, "pollutant": pol,
                          "level": lev, "data": plane})

    if not grids:
        raise SystemExit(
            f"{path}: parsed the header but found no concentration planes. "
            "The run produced no sampled output -- check that the sampling "
            "window overlaps the run.")
    meta = {"nlat": nlat, "nlon": nlon, "dlat": dlat, "dlon": dlon,
            "lat0": lat0, "lon0": lon0, "levels": levels,
            "pollutants": pollutants, "packed": bool(packed)}
    return grids, meta


def run_concentration(binary, start, points, hours, met_paths, work_dir,
                      **kw):
    """Run hycs_std once and return (grids, meta) from the binary cdump."""
    os.makedirs(work_dir, exist_ok=True)
    out_name = kw.pop("out_name", "cdump")
    write_concentration_control(os.path.join(work_dir, "CONTROL"), start,
                                points, hours, met_paths, work_dir, out_name,
                                **kw)

    root = os.path.dirname(os.path.dirname(os.path.abspath(binary)))
    for cfg in ("ASCDATA.CFG",):
        src = os.path.join(root, "bdyfiles", cfg)
        if os.path.exists(src) and not os.path.exists(
                os.path.join(work_dir, cfg)):
            shutil.copy(src, work_dir)

    print(f"  running {os.path.basename(binary)} "
          f"({len(points)} source(s), {hours:+d} h dispersion) …")
    try:
        proc = subprocess.run([binary], cwd=work_dir, capture_output=True,
                              text=True, timeout=3600,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise SystemExit("HYSPLIT dispersion did not finish within an hour.")

    if proc.returncode == -9 and sys.platform == "darwin":
        raise SystemExit(_QUARANTINE_HELP.format(exe=binary,
                                                 root=_install_root(binary)))
    cdump = os.path.join(work_dir, out_name)
    if not os.path.exists(cdump) or os.path.getsize(cdump) == 0:
        tail = ((proc.stdout or "") + (proc.stderr or "")
                ).strip().splitlines()[-12:]
        raise SystemExit(
            f"HYSPLIT produced no concentration output (exit "
            f"{proc.returncode}).\n  " + "\n  ".join(tail or ["(no output)"]))
    return read_cdump(cdump)
