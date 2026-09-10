"""The SIRAD | ΔNDVI side-by-side sheet is drawn only for a real pair.

A mining run writes a SIRAD composite (RGB) and an NDVI change (one band) over
the same AOI; those two go side by side. Anything else -- a single product, two
change layers, or products from different runs that happen to share a folder --
must not be forced onto that sheet.
"""

from earthchange.mapmaker import _stats_lines, _title, find_pair


def _meta(key, rgb, run="r1", name="konawe"):
    return {"product_key": key, "is_rgb": rgb, "run_id": run, "name": name}


def test_mining_run_pairs_sirad_with_ndvi_change():
    sirad, dndvi = _meta("sirad", True), _meta("dndvi", False)
    assert find_pair([dndvi, sirad]) == (sirad, dndvi)   # order-independent


def test_single_product_has_no_pair():
    assert find_pair([_meta("dndvi", False)]) is None
    assert find_pair([]) is None


def test_two_change_layers_are_not_a_radar_optical_pair():
    assert find_pair([_meta("dndvi", False), _meta("dndbi", False)]) is None


def test_extra_product_makes_the_pairing_ambiguous():
    metas = [_meta("sirad", True), _meta("dndvi", False), _meta("dnbr", False)]
    assert find_pair(metas) is None


def test_products_from_different_runs_are_not_paired():
    assert find_pair([_meta("sirad", True, run="r1"),
                      _meta("dndvi", False, run="r2")]) is None


# Trimmed from a real Konawe mining run: both legs live in one stats dict.
MINING_STATS = {
    "sirad": {"method": "SIRAD", "orbit": "DESCENDING",
              "images_per_period": [30, 29, 30]},
    "ndvi": {"metric": "dNDVI", "direction": "loss", "mean": -0.0301,
             "pct_affected": 4.07, "pct_severe": 1.98,
             "scenes_pre": 26, "scenes_post": 22},
}


def _text(meta, **kw):
    return "\n".join(_stats_lines({"stats": MINING_STATS, **meta}, **kw))


def test_sirad_sheet_does_not_show_the_ndvi_numbers():
    t = _text({"is_rgb": True})
    assert "SIRAD orbit: DESCENDING" in t
    for ndvi in ("dNDVI", "Rerata", "Area terdampak", "Scene pre/post"):
        assert ndvi not in t


def test_ndvi_sheet_does_not_show_the_radar_numbers():
    t = _text({"is_rgb": False})
    assert "Metrik: dNDVI" in t and "Area terdampak: 4.1%" in t
    assert "SIRAD" not in t and "Citra/periode" not in t


def test_side_by_side_sheet_shows_both_legs():
    t = _text({"is_rgb": True}, both=True)
    assert "SIRAD orbit: DESCENDING" in t and "Metrik: dNDVI" in t


MINING_LABEL = "Mining — radar temporal (SIRAD) + NDVI loss (S1 + S2)"


def _title_of(is_rgb, sensor="Sentinel-2"):
    stats = {**MINING_STATS, "ndvi": {**MINING_STATS["ndvi"], "sensor": sensor}}
    return _title({"label": MINING_LABEL, "stats": stats, "is_rgb": is_rgb})


def test_each_mining_sheet_is_titled_for_its_own_method():
    assert _title_of(True) == "Mining — radar temporal (SIRAD, Sentinel-1 VH)"
    assert _title_of(False) == "Mining — NDVI loss (Sentinel-2)"


def test_landsat_run_says_landsat_not_its_archive_note():
    assert _title_of(False, "Landsat (archive to 1984)") == "Mining — NDVI loss (Landsat)"


def test_single_product_scenarios_keep_their_label():
    label = "Burn severity — dNBR (Sentinel-2)"
    assert _title({"label": label, "stats": {"metric": "dNBR"}}) == label
