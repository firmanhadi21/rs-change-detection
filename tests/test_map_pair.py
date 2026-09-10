"""The SIRAD | ΔNDVI side-by-side sheet is drawn only for a real pair.

A mining run writes a SIRAD composite (RGB) and an NDVI change (one band) over
the same AOI; those two go side by side. Anything else -- a single product, two
change layers, or products from different runs that happen to share a folder --
must not be forced onto that sheet.
"""

from earthchange.mapmaker import find_pair


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
