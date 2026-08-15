"""Pruning HyP3 products down to the bands that are actually read.

A single interferogram is ~73 MB and more than half of that is bands this
package never opens. At 700 pairs the difference decides whether the stack fits
on the disk at all, so the keep-list is worth pinning: dropping _corr.tif or
_unw_phase.tif by accident would break every run, silently, only at analysis
time.
"""

import os

from earthchange.insar import KEEP_SUFFIXES, prune

STEM = "S1DD_20260713T101602_20260725T101603_VVP012_INT80_G_weF_77B9"

# Sizes from a real product, rounded; the ratio is what matters.
FILES = {
    f"{STEM}_amp.tif": 30_632_350,
    f"{STEM}_corr.tif": 30_558_525,
    f"{STEM}_unw_phase.tif": 6_531_581,
    f"{STEM}_color_phase.kmz": 5_444_651,
    f"{STEM}_color_phase.png": 1_814_373,
    f"{STEM}_unw_phase.kmz": 1_178_080,
    f"{STEM}_unw_phase.png": 320_790,
    f"{STEM}_water_mask.tif": 266_707,
    f"{STEM}.txt": 4_000,
    f"{STEM}.README.md.txt": 30_883,
    f"{STEM}_corr.tif.xml": 14_472,
}


def build(tmp_path):
    d = tmp_path / "product"
    d.mkdir()
    for name, size in FILES.items():
        (d / name).write_bytes(b"\0" * min(size, 4096))
    return str(d)


def test_keeps_every_band_the_analysis_opens(tmp_path):
    d = build(tmp_path)
    prune(d)
    left = set(os.listdir(d))
    # These two are read by coherence_change and velocity; losing either turns
    # a run into a "no *_corr.tif in ..." failure after the download is spent.
    assert f"{STEM}_corr.tif" in left
    assert f"{STEM}_unw_phase.tif" in left
    # baselines() parses this.
    assert f"{STEM}.txt" in left


def test_drops_the_bulk_that_is_never_read(tmp_path):
    d = build(tmp_path)
    prune(d)
    left = set(os.listdir(d))
    assert f"{STEM}_amp.tif" not in left        # 30 MB, unused
    assert f"{STEM}_color_phase.kmz" not in left
    assert f"{STEM}_unw_phase.png" not in left


def test_is_idempotent(tmp_path):
    """Collection re-runs over products already on disk; the second pass must
    not fail on files the first removed."""
    d = build(tmp_path)
    first = prune(d)
    second = prune(d)
    assert first > 0
    assert second == 0


def test_saves_about_half_of_a_real_product():
    kept = sum(s for n, s in FILES.items()
               if n.endswith(KEEP_SUFFIXES) or n.endswith(".xml"))
    total = sum(FILES.values())
    assert kept / total < 0.55, "pruning no longer halves a product"
