"""Pure-function tests for earthchange.embeddings."""
import json

import numpy as np
import pytest

from earthchange import embeddings as em


def test_cosine_change_is_zero_for_same_direction_and_one_for_orthogonal():
    a = np.array([[[1.0, 0.0]], [[0.0, 2.0]]])
    b = np.array([[[3.0, 0.0]], [[5.0, 0.0]]])
    c = em.cosine_change(a, b)
    assert c[0, 0] == pytest.approx(0.0)
    assert c[1, 0] == pytest.approx(1.0)


def test_first_crossing_takes_the_earliest_year():
    series = np.array([[[0.1, 0.5]], [[0.6, 0.2]], [[0.7, 0.9]]])   # years 2019..2021
    out = em.first_crossing(series, [2019, 2020, 2021], 0.4)
    assert out.tolist() == [[2020, 2019]]
    assert em.first_crossing(np.zeros((2, 1, 1)), [2020, 2021], 0.4)[0, 0] == 0


def test_similarity_ignores_vector_length():
    arr = np.array([[[2.0, 0.0], [0.0, 1.0]]])
    s = em.similarity(arr, [5.0, 0.0])
    assert s[0, 0] == pytest.approx(1.0) and s[0, 1] == pytest.approx(0.0)


def test_folds_never_split_a_polygon_and_cover_every_class():
    pid = np.array([0, 0, 1, 1, 2, 3, 3, 4])
    cls = np.array([0, 0, 0, 0, 0, 1, 1, 1])
    f = em.folds_by_polygon(pid, cls)
    for p in set(pid):
        assert len(set(f[pid == p])) == 1
    for c in set(cls):
        assert set(f[cls == c]) == {0, 1}


def test_fold_accuracy_on_separable_classes():
    rng = np.random.default_rng(0)
    X = np.concatenate([rng.normal(0, 0.1, (200, 4)) + [1, 0, 0, 0],
                        rng.normal(0, 0.1, (200, 4)) + [0, 1, 0, 0]]).astype("f4")
    y = np.array([0] * 200 + [1] * 200)
    pid = np.array([0] * 100 + [1] * 100 + [2] * 100 + [3] * 100)
    acc, rec, cm = em.fold_accuracy(X, y, pid, ["a", "b"])
    assert acc > 0.95 and rec["a"] > 0.9 and rec["b"] > 0.9


def test_tess_predict_keeps_nodata():
    class M:
        def predict(self, X):
            return (X[:, 0] > 0).astype(int)
    arr = np.array([[[1.0, 0.0], [np.nan, np.nan]], [[-1.0, 0.0], [2.0, 1.0]]], "f4")
    out = em.tess_predict(M(), arr)
    assert out.tolist() == [[1, 255], [0, 1]]


def test_load_labels(tmp_path):
    p = tmp_path / "l.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"class": "water"}, "geometry": None},
        {"type": "Feature", "properties": {"class": "bare"}, "geometry": None},
        {"type": "Feature", "properties": {}, "geometry": None}]}))
    feats, names = em.load_labels(str(p))
    assert names == ["bare", "water"] and len(feats) == 2


def test_class_colors_known_and_fallback():
    assert em.class_colors(["bare", "mystery"])[0] == em.PALETTE["bare"]
    assert em.class_colors(["bare", "mystery"])[1].startswith("#")


def test_expansion_table_counts_targets_by_first_change_year():
    cls = np.array([[0, 0, 1], [2, 0, 1]])           # 0 bare, 1 built, 2 forest
    first = np.array([[0, 2021, 2023], [2021, 2023, 0]])
    t = em.expansion_table(cls, first, [0, 1], [2017, 2021, 2022, 2023], px_ha=1.0)
    assert t["before_or_unchanged"] == 2.0             # bare@0 and built@0
    assert t["2021"] == 1.0 and t["2023"] == 2.0 and t["2022"] == 0.0
    assert sum(t.values()) == pytest.approx(5.0)       # the forest pixel is never counted


def test_stable_threshold_is_a_high_percentile_and_ignores_nan():
    v = np.concatenate([np.linspace(0, 0.1, 99), [0.9, np.nan]])
    assert 0.1 <= em.stable_threshold(v) < 0.9
    with pytest.raises(ValueError):
        em.stable_threshold([np.nan])
