"""Pure-function tests for forest-account, timelapse and the S1 history test."""
import numpy as np
import pytest

from earthchange import forest_account as fa
from earthchange import s1_history as sh
from earthchange import timelapse as tl


# ----------------------------- forest-account -----------------------------
def test_split_driver_year_decodes_driver_and_year():
    groups = [{"c": 223, "sum": 1934.04}, {"c": 115, "sum": 16932.0}, {"c": 905, "sum": 1.0}]
    out = fa.split_driver_year(groups)
    assert out["Hard commodities (mining, energy)"] == {2023: 1934.0}
    assert out["Permanent agriculture"] == {2015: 16932.0}
    assert out["class 9"] == {2005: 1.0}


def test_driver_rates_show_a_small_driver_growing():
    # 18 early years at 100 ha mining + 900 ha other; 6 recent at 300 + 700
    dy = {"mining": {y: (100 if y < 2019 else 300) for y in range(2001, 2025)},
          "other": {y: (900 if y < 2019 else 700) for y in range(2001, 2025)}}
    r = fa.driver_rates(dy, last=2024, recent=6)
    assert r["early"] == "2001-2018" and r["recent"] == "2019-2024"
    m = r["drivers"]["mining"]
    assert m["early_ha_per_yr"] == 100 and m["recent_ha_per_yr"] == 300
    assert m["early_share_pct"] == 10.0 and m["recent_share_pct"] == 30.0


def test_parse_groups():
    assert fa.parse_groups([{"y": 1, "sum": 7377.44}]) == {2001: 7377.4}


# ----------------------------- timelapse -----------------------------
def test_tile_grid_covers_the_box_exactly():
    tiles, tw, th, n = tl.tile_grid((127.8, 0.3, 128.3, 0.75), 1600)
    assert n == 3 and len(tiles) == 9 and tw == 533
    assert th == round(533 * 0.45 / 0.5)
    ws = min(t[2][0] for t in tiles); es = max(t[2][2] for t in tiles)
    ss = min(t[2][1] for t in tiles); ns = max(t[2][3] for t in tiles)
    assert (ws, ss) == pytest.approx((127.8, 0.3)) and (es, ns) == pytest.approx((128.3, 0.75))
    top_left = [t for t in tiles if t[0] == 0 and t[1] == 0][0][2]
    assert top_left[3] == pytest.approx(0.75)          # row 0 is the north edge


def test_small_box_is_one_tile():
    assert tl.tile_grid((0, 0, 1, 1), 500)[3] == 1


def test_frame_window():
    assert tl.frame_window(2024, 2) == ("2023-01-01", "2025-01-01")
    assert tl.frame_window(2024, 1) == ("2024-01-01", "2025-01-01")


# ----------------------------- S1 history -----------------------------
def _stack(T=12, H=40, W=40, seed=0):
    rng = np.random.default_rng(seed)
    vv = -10 + rng.normal(0, 0.8, (T, H, W))
    vh = -17 + rng.normal(0, 0.8, (T, H, W))
    return vv, vh


def test_history_flags_an_event_patch_and_not_noise():
    vv, vh = _stack()
    vv[-1, 10:20, 10:20] -= 6          # event: both polarisations drop 6 dB
    vh[-1, 10:20, 10:20] -= 6
    ev = sh.history_z(vv, vh)
    assert ev["n_control"] == 10
    g = sh.flag(ev, min_px=10)
    assert (g[10:20, 10:20] > 0).mean() > 0.9
    assert (g > 0).sum() - (g[10:20, 10:20] > 0).sum() < 10   # almost nothing outside
    ct = sh.flag(sh.control_z(vv, vh), min_px=10)
    assert (ct > 0).sum() < 10                             # control pair stays quiet


def test_history_needs_both_polarisations_to_drop():
    vv, vh = _stack()
    vv[-1, 5:15, 5:15] -= 6            # only VV drops (e.g. wet soil), VH unchanged
    assert sh.flag(sh.history_z(vv, vh), min_px=5).sum() == 0


def test_history_rejects_too_few_dates():
    vv, vh = _stack(T=4)
    with pytest.raises(ValueError):
        sh.history_z(vv, vh)


def test_noisy_pixel_needs_a_bigger_drop():
    vv, vh = _stack()
    rng = np.random.default_rng(1)
    vv[:-1, 0:10, 0:10] += rng.normal(0, 4, (vv.shape[0] - 1, 10, 10))   # paddy-like swings
    vh[:-1, 0:10, 0:10] += rng.normal(0, 4, (vh.shape[0] - 1, 10, 10))
    vv[-1, 0:10, 0:10] = vv[-2, 0:10, 0:10] - 3                            # 3 dB is ordinary there
    vh[-1, 0:10, 0:10] = vh[-2, 0:10, 0:10] - 3
    assert (sh.flag(sh.history_z(vv, vh), min_px=5)[0:10, 0:10] > 0).mean() < 0.2


def test_same_track_picks_newest_track():
    scenes = [{"date": "2026-11-06", "direction": "DESCENDING", "rel_orbit": 62},
              {"date": "2026-11-12", "direction": "DESCENDING", "rel_orbit": 62},
              {"date": "2026-11-09", "direction": "ASCENDING", "rel_orbit": 99},
              {"date": "2026-10-31", "direction": "DESCENDING", "rel_orbit": 62}]
    ref, dates = sh.same_track(scenes)
    assert ref["rel_orbit"] == 62
    assert dates == ["2026-10-31", "2026-11-06", "2026-11-12"]


def test_utm_epsg():
    assert sh.utm_epsg(97.59, 4.10) == 32647
    assert sh.utm_epsg(128.07, -0.5) == 32752


def test_valley_floor_and_terrain_split():
    x = np.arange(100)
    dem = np.tile(np.abs(x - 50) * 10.0, (100, 1))          # V-shaped valley along column 50
    dem[:, 45:56] = 0.0                                      # flat floor
    gy, gx = np.gradient(dem, 10.0)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    v = sh.valley_floor(dem, slope, 10.0)
    assert v[:, 50].all() and not v[:, 5].any()
    g_ev = np.zeros((100, 100), "uint8"); g_ev[:, 48:52] = 1
    g_ct = np.zeros((100, 100), "uint8"); g_ct[0:4, 0:4] = 1
    s = sh.terrain_split(g_ev, g_ct, v, ~v)
    assert s["valley_floor"]["event_pct"] > 10 and s["valley_floor"]["control_pct"] == 0
    assert s["hillside"]["control_pct"] > 0
