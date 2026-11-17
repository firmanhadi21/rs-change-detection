"""Run a scenario from Python, the same as from the terminal.

    import earthchange as ec
    run = ec.run("deforestation", lat=-3.333, lon=122.25, radius=6)
    run.stats["results"]["pct_affected"]
    run.tif()                       # path of the first GeoTIFF

Keyword arguments are the command-line options with dashes written as
underscores: ``ec.run("flood", pre="2022-07-01:2022-07-25", ee_key=...)`` is
``earthchange -s flood --pre 2022-07-01:2022-07-25 --ee-key ...``. ``True``
passes a bare flag (``map=True`` -> ``--map``); ``False`` and ``None`` leave
the option out; a list or tuple is joined with commas.

``ec.short("banjir", "Pining, Gayo Lues", "2026-11-08")`` runs one of the
short Indonesian commands the same way.
"""

import datetime as _dt
import glob
import json
import os
import sys
import uuid

__all__ = ["Run", "run", "short", "cli_args"]


class Run:
    """The folder one run wrote, with its statistics already read."""

    def __init__(self, run_dir, argv):
        self.run_dir = run_dir
        self.argv = list(argv)
        self.stats = _read_json(os.path.join(run_dir, "stats.json"))

    @property
    def files(self):
        return sorted(os.listdir(self.run_dir))

    def tifs(self, pattern="*.tif"):
        return sorted(glob.glob(os.path.join(self.run_dir, pattern)))

    def tif(self, pattern="*.tif"):
        """Path of the first GeoTIFF matching ``pattern``, or None."""
        found = self.tifs(pattern)
        return found[0] if found else None

    def find(self, pattern):
        """Path of the first file matching ``pattern`` (e.g. "*_map.png"), or None."""
        return self.tif(pattern)

    def path(self, name):
        return os.path.join(self.run_dir, name)

    @property
    def command(self):
        """The equivalent terminal command, with the output folder relative to
        the current directory (so it can be pasted, and shows no home path)."""
        def show(a):
            if a.startswith("--out-dir="):
                a = "--out-dir=" + os.path.relpath(a.split("=", 1)[1])
            return _quote(a)
        return "earthchange " + " ".join(show(a) for a in self.argv)

    def __repr__(self):
        return f"Run({self.run_dir!r})"


def cli_args(scenario, **options):
    """The argv list ``run`` passes to the command-line parser."""
    argv = ["-s", scenario]
    for key, value in options.items():
        if value is None or value is False:
            continue
        flag = "--" + key.replace("_", "-")
        if value is True:
            argv.append(flag)
        elif isinstance(value, (list, tuple)):
            argv.append(f"{flag}={','.join(str(v) for v in value)}")
        else:
            # --flag=value keeps a negative latitude from reading as an option
            argv.append(f"{flag}={value}")
    return argv


def run(scenario, out_dir=None, **options):
    """Run ``scenario`` and return a :class:`Run` for the folder it wrote.

    ``out_dir`` defaults to ``output/<timestamp>_<scenario>_<token>`` under the
    current directory, so runs never overwrite each other. Raises
    ``RuntimeError`` if the run stops with an error.
    """
    if out_dir is None:
        out_dir = os.path.join(
            "output", f"{_dt.datetime.now():%Y%m%d-%H%M%S}_{scenario}_{uuid.uuid4().hex[:6]}")
    out_dir = os.path.abspath(out_dir)
    argv = cli_args(scenario, **options) + [f"--out-dir={out_dir}"]
    _call_main(argv)
    return Run(out_dir, argv)


def short(command, place, *when, out_dir=None, force=False):
    """Run a short Indonesian command (banjir, kebakaran, hutan, kota, air)."""
    from .mudah import PERINTAH
    if command not in PERINTAH:
        raise ValueError(f"unknown short command {command!r}; one of {sorted(PERINTAH)}")
    argv = [command, str(place)] + [str(w) for w in when]
    if out_dir is not None:
        out_dir = os.path.abspath(out_dir)
        argv += ["--keluar", out_dir]
    if force:
        argv.append("--paksa")
    before = set(glob.glob(os.path.join("output", f"*_{command}_*")))
    _call_main(argv)
    if out_dir is None:
        new = sorted(set(glob.glob(os.path.join("output", f"*_{command}_*"))) - before)
        if not new:
            raise RuntimeError("the short command wrote no output folder")
        out_dir = os.path.abspath(new[-1])
    result = Run(out_dir, argv)
    result.summary = _read_json(os.path.join(out_dir, "ringkasan.json"))
    return result


def _call_main(argv):
    from .detect import main
    saved = sys.argv
    sys.argv = ["earthchange"] + list(argv)
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(f"earthchange {' '.join(argv)} stopped: {exc.code}") from None
    finally:
        sys.argv = saved


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _quote(arg):
    if any(c in arg for c in " \"'"):
        return "'" + arg.replace("'", "'\\''") + "'"
    return arg
