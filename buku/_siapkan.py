"""Loaded by a hidden cell at the top of each chapter.

Every run the book shows is a real run. This only keeps each one in
buku/hasil/<folder>/ and, when the chapter is rendered again after an edit to
its prose, reads that folder back instead of downloading the same imagery a
second time. Set EC_ULANG=1 to run everything afresh.

A reader who copies a cell gets the plain earthchange behaviour: the run writes
to the folder named in out_dir, under their current directory.
"""

import os

import earthchange as ec
from earthchange import api

BUKU = os.path.dirname(os.path.abspath(__file__))
HASIL = os.path.join(BUKU, "hasil")
_ULANG = bool(os.environ.get("EC_ULANG"))
_run, _short = api.run, api.short


def _folder(out_dir):
    return os.path.join(HASIL, out_dir)


def run(scenario, out_dir, **opsi):
    folder = _folder(out_dir)
    if not _ULANG and os.path.exists(os.path.join(folder, "stats.json")):
        return api.Run(folder, api.cli_args(scenario, **opsi) + [f"--out-dir={folder}"])
    return _run(scenario, out_dir=folder, **opsi)


def short(command, place, *when, out_dir, **kw):
    folder = _folder(out_dir)
    if not _ULANG and os.path.exists(os.path.join(folder, "ringkasan.json")):
        r = api.Run(folder, [command, place, *map(str, when)])
        r.summary = api._read_json(os.path.join(folder, "ringkasan.json"))
        return r
    return _short(command, place, *when, out_dir=folder, **kw)


ec.run, ec.short = run, short
os.makedirs(HASIL, exist_ok=True)
