"""Water adequacy, uniformity and reliability, to the Paper 3 definitions.

The numbers here are the ones the irrigation work already settled
(paper3/reference/irrigation_performance_dynamic.py): SI = min(1.2 ETa/CWR, 1),
Christiansen CU as a percentage, RI = share of weeks at SI >= 0.80, and a Kc
curve stretched onto the season the field actually had.
"""
import numpy as np
import pytest

from earthchange.paddy_water import (ADEQUACY_CLASSES, adequacy,
                                     adequacy_class, christiansen_uniformity,
                                     delay_class, delay_days,
                                     equity_percentile, kc, kc_curve110,
                                     kc_stage, puso_candidates, reliability,
                                     season_adequacy)


def test_kc_curve_matches_the_operational_110_day_table():
    """The published breakpoints: 1.05 flat, 1.15 at 40 d, peak 1.20, 0.95 end."""
    for day, want in ((1, 1.05), (10, 1.05), (40, 1.15), (80, 1.20), (110, 0.95)):
        assert kc_curve110(day, 110) == pytest.approx(want, abs=0.005)


def test_kc_is_stretched_onto_a_short_season_not_truncated():
    """A 75-day variety reaches peak demand at 75 days, not at 110.

    Truncating the 110-day curve would charge a short variety for a
    mid-season it never had -- the error that put harvest outside the
    farmers' window 13 times out of 13.
    """
    assert kc_curve110(75, 75) == pytest.approx(0.95, abs=0.01)   # at harvest
    assert kc_curve110(55, 75) == pytest.approx(1.20, abs=0.02)   # peak earlier
    assert kc_curve110(110, 75) == 0.0                            # season over


def test_kc_is_zero_outside_the_season():
    assert kc_curve110(0, 110) == 0.0 and kc_curve110(200, 110) == 0.0
    assert kc_stage(0, 90) == 0.0 and kc_stage(95, 90) == 0.0


def test_kc_stage_follows_the_s1_stage_clock():
    assert kc_stage(10, 90) == pytest.approx(1.05)          # flooded, no canopy
    assert kc_stage(36, 90) == pytest.approx(1.125, abs=0.01)   # mid dev ramp
    assert kc_stage(58, 90) == pytest.approx(1.20)          # reproductive
    assert kc_stage(89, 90) < 1.20                          # ripening, falling


def test_kc_mode_selection_and_a_clear_error():
    assert kc(50, 110, "curve110") == kc_curve110(50, 110)
    assert kc(50, 110, "stage") == kc_stage(50, 110)
    with pytest.raises(ValueError, match="curve110"):
        kc(50, 110, "fao56")


def test_adequacy_is_capped_and_scaled_by_the_free_water_term():
    assert adequacy(5.0, 6.0) == pytest.approx(1.0)      # 1.2*5/6 = 1.0
    assert adequacy(3.0, 6.0) == pytest.approx(0.6)
    assert adequacy(9.0, 6.0) == pytest.approx(1.0)      # capped


def test_no_demand_means_no_adequacy_not_full_adequacy():
    """Fallow land must not be reported as well watered."""
    assert np.isnan(adequacy(0.0, 0.0))


def test_adequacy_classes_follow_the_fao33_bands():
    got = adequacy_class(np.array([1.05, 0.90, 0.70, 0.30], dtype="float32"))
    assert list(got) == [0, 1, 2, 3]
    assert [c[3]["en"] for c in ADEQUACY_CLASSES][3] == "Severe deficit"


def test_christiansen_is_100_when_every_unit_gets_the_same():
    assert christiansen_uniformity([0.9, 0.9, 0.9]) == pytest.approx(100.0)
    # mean 0.75, mean absolute deviation 0.25 -> 100 * (1 - 1/3)
    assert christiansen_uniformity([1.0, 0.5, 1.0, 0.5]) == pytest.approx(66.67,
                                                                          abs=0.01)


def test_reliability_counts_weeks_at_or_above_the_080_threshold():
    assert reliability([0.9, 0.85, 0.7, 0.8]) == pytest.approx(0.75)
    assert np.isnan(reliability([np.nan, np.nan]))


def test_equity_percentile_reports_the_tail_not_the_mean():
    v = [1.0] * 8 + [0.2] * 2                  # a starved tail-end fifth
    assert equity_percentile(v) < 0.5          # the tail shows
    assert np.mean(v) > 0.8                    # the mean hides it


def test_season_adequacy_uses_each_pixels_own_planting_and_length():
    """Two pixels, same weather: the late one is scored on its own season."""
    periods, rows, cols = 12, 1, 2
    et0 = np.full((periods, rows, cols), 5.0, dtype="float32")
    eta = np.full((periods, rows, cols), 5.0, dtype="float32")
    plant = np.array([[0.0, 6.0]], dtype="float32")        # early and late
    length = np.array([[90.0, 90.0]], dtype="float32")
    si, supply, demand = season_adequacy(eta, et0, plant, length)
    assert demand[0, 0] > demand[0, 1]        # the late field demanded less
    assert si[0, 0] == pytest.approx(si[0, 1], abs=0.05)   # both fully supplied


def test_a_pixel_that_never_planted_has_no_adequacy():
    et0 = np.full((6, 1, 1), 5.0, dtype="float32")
    eta = np.full((6, 1, 1), 5.0, dtype="float32")
    si, _, _ = season_adequacy(eta, et0, np.array([[np.nan]], dtype="float32"),
                               np.array([[90.0]], dtype="float32"))
    assert np.isnan(si[0, 0])


def test_delay_is_measured_against_the_same_fields_own_baseline():
    d = delay_days(np.array([10.0]), np.array([8.0]))
    assert d[0] == pytest.approx(24.0)                     # two periods late
    # 24 d sits on the upper edge of "12-24 days late", as the label reads
    assert list(delay_class(d, planted=np.array([True]))) == [1]
    late = delay_days(np.array([12.0]), np.array([8.0]))   # four periods late
    assert list(delay_class(late, planted=np.array([True]))) == [3]


def test_unplanted_fields_get_their_own_class_not_zero_delay():
    cls = delay_class(np.array([np.nan]), planted=np.array([False]))
    assert cls[0] == 4                                     # "not planted"


def test_puso_flags_both_failures_and_only_where_planted():
    planted = np.array([True, True, True, False])
    gain = np.array([10.0, 1.0, 9.0, 1.0])                 # 2nd: no canopy
    si = np.array([0.9, 0.9, 0.3, 0.1])                    # 3rd: starved
    flag, no_canopy, starved = puso_candidates(planted, gain, si)
    assert list(flag) == [False, True, True, False]
    assert list(no_canopy) == [False, True, False, False]
    assert list(starved) == [False, False, True, False]


# --- the forecast leg: reference ET from temperature alone ---

def test_extraterrestrial_radiation_is_near_the_fao_table():
    """FAO-56 Table 2.6 at the equator: ~15.0 Jan, 15.3 Apr, 13.9 Jul, 15.3 Oct."""
    from earthchange.paddy_water import extraterrestrial_radiation
    for doy, want in ((15, 15.0), (105, 15.3), (196, 13.9), (288, 15.3)):
        ra = float(extraterrestrial_radiation(0.0, doy))
        assert abs(ra - want) < 0.5, f"doy {doy}: {ra:.2f} vs FAO {want}"
    # Java in July: the southern tropics get less than the equator
    assert float(extraterrestrial_radiation(-7.0, 196)) < \
        float(extraterrestrial_radiation(0.0, 196))


def test_hargreaves_lands_in_the_tropical_range():
    """Java dry season: reference ET of roughly 4-5 mm/day (WaPOR says 4.0)."""
    from earthchange.paddy_water import et0_hargreaves
    et0 = float(et0_hargreaves(23.0, 32.0, -6.95, 196))
    assert 3.5 <= et0 <= 5.5


def test_hargreaves_rises_with_the_diurnal_spread():
    """A clear day (wide spread) evaporates more than an overcast one."""
    from earthchange.paddy_water import et0_hargreaves
    clear = float(et0_hargreaves(22.0, 34.0, -6.95, 196))
    cloudy = float(et0_hargreaves(24.0, 28.0, -6.95, 196))
    assert clear > cloudy


def test_demand_is_not_charged_for_periods_whose_supply_is_unpublished():
    """WaPOR actual ET lags its reference by ~2 weeks.

    Counting those periods' demand against missing supply invents a deficit.
    Two pixels, same crop: one scored over all periods, one with the last two
    periods' ETa still unpublished. They must agree.
    """
    periods = 8
    et0 = np.full((periods, 1, 2), 5.0, dtype="float32")
    eta = np.full((periods, 1, 2), 4.0, dtype="float32")
    eta[-2:, 0, 1] = np.nan                        # not published yet
    plant = np.zeros((1, 2), dtype="float32")
    length = np.full((1, 2), 96.0, dtype="float32")
    si, supply, demand = season_adequacy(eta, et0, plant, length)
    # Not identical -- dropping late periods changes the Kc mix a little --
    # but nothing like the 25% collapse that charging 8 periods of demand
    # against 6 of supply would produce.
    assert abs(si[0, 1] - si[0, 0]) < 0.05
    assert si[0, 1] > 0.9 * si[0, 0]
    assert demand[0, 1] < demand[0, 0]             # fewer periods, not a deficit


def test_a_pixel_with_no_paired_periods_reports_nothing():
    eta = np.full((3, 1, 1), np.nan, dtype="float32")
    et0 = np.full((3, 1, 1), 5.0, dtype="float32")
    si, _, _ = season_adequacy(eta, et0, np.zeros((1, 1), dtype="float32"),
                               np.full((1, 1), 96.0, dtype="float32"))
    assert np.isnan(si[0, 0])
