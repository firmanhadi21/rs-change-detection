"""earthchange.run(): Python calls map onto the command line (offline)."""

import json
import os
import sys

import pytest

import earthchange as ec
from earthchange import api


def test_cli_args_flags_lists_and_negative_numbers():
    argv = api.cli_args("flood", lat=-3.333, lon=122.25, radius=6,
                        pre="2022-07-01:2022-07-25", map=True, drive=False,
                        basemap=None, walk_dist=[500, 1000])
    assert argv == ["-s", "flood", "--lat=-3.333", "--lon=122.25", "--radius=6",
                    "--pre=2022-07-01:2022-07-25", "--map", "--walk-dist=500,1000"]


def test_run_passes_argv_and_reads_stats(tmp_path, monkeypatch):
    seen = {}

    def fake_main():
        seen["argv"] = list(sys.argv)
        out = sys.argv[-1].split("=", 1)[1]
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "stats.json"), "w") as f:
            json.dump({"results": {"pct_affected": 6.3}}, f)
        open(os.path.join(out, "deforestation_dndvi_x.tif"), "w").close()

    monkeypatch.setattr("earthchange.detect.main", fake_main)
    r = ec.run("deforestation", out_dir=tmp_path / "a", lat=-3.333, lon=122.25)
    assert seen["argv"][:4] == ["earthchange", "-s", "deforestation", "--lat=-3.333"]
    assert r.stats["results"]["pct_affected"] == 6.3
    assert r.tif().endswith("deforestation_dndvi_x.tif")
    assert r.command.startswith("earthchange -s deforestation --lat=-3.333")
    assert not os.path.isabs(r.command.split("--out-dir=")[1])
    assert sys.argv[0] != "earthchange" or len(sys.argv) == 1   # restored


def test_run_raises_on_error_exit(tmp_path, monkeypatch):
    def failing():
        raise SystemExit("needs --pre")
    monkeypatch.setattr("earthchange.detect.main", failing)
    with pytest.raises(RuntimeError, match="needs --pre"):
        ec.run("flood", out_dir=tmp_path)


def test_short_rejects_unknown_command():
    with pytest.raises(ValueError):
        ec.short("gempa", "Palu", "2018-09-28")
