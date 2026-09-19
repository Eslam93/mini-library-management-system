"""The forecast method on constructed series, with expected values worked out by hand from the
method's definition: the trend, the forecast, the misses of the past tests, the range and the
typical error, and each reason to refuse.
"""

import math

import pytest

from app.services.metrics.forecast import (
    backtest,
    forecast_series,
    miss,
    months_needed,
    percentile,
    seasonal_forecast,
    trend_factor,
)

FLAT = [100] * 24


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        # 12 x 12 over 12 x 10.
        ([10] * 12 + [12] * 12, 1.2),
        # 3.0 is held at 2.0, and 0.4 at 0.5.
        ([10] * 12 + [30] * 12, 2.0),
        ([10] * 12 + [4] * 12, 0.5),
        # Growth from nothing is the most growth; nothing after nothing is no change.
        ([0] * 12 + [5] * 12, 2.0),
        ([0] * 24, 1.0),
        # Only the last 24 months count.
        ([1000] * 6 + [10] * 12 + [12] * 12, 1.2),
    ],
)
def test_the_trend_is_the_last_year_over_the_year_before_held_between_half_and_double(
    values, expected
):
    assert trend_factor(values) == pytest.approx(expected)


def test_a_month_is_forecast_as_the_same_month_a_year_earlier_times_the_trend():
    year_before = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
    last_year = [2 * value for value in year_before[:6]] + year_before[6:]
    # Trend: (2 x 210 + 570) / 780 = 990 / 780.
    trend = 990 / 780

    forecast = seasonal_forecast(year_before + last_year, 3)

    assert forecast == pytest.approx([20 * trend, 40 * trend, 60 * trend])


def test_a_miss_is_actual_over_forecast_less_one():
    assert miss(110, 100) == pytest.approx(0.1)
    assert miss(90, 100) == pytest.approx(-0.1)
    assert miss(0, 0) == 0.0
    assert miss(5, 0) == math.inf


def test_percentiles_interpolate_between_the_nearest_ranks():
    values = [5, 1, 4, 2, 3]

    assert percentile(values, 0.5) == 3
    # Position 0.4, between 1 and 2; position 3.6, between 4 and 5.
    assert percentile(values, 0.1) == pytest.approx(1.4)
    assert percentile(values, 0.9) == pytest.approx(4.6)
    assert percentile(list(range(1, 12)), 0.9) == 10
    assert percentile([2, 7], 0.5) == pytest.approx(4.5)
    assert percentile([1, math.inf, math.inf], 0.9) == math.inf


def test_the_method_is_tested_from_every_month_with_two_years_before_it():
    # Two flat years, then 100 and 120.
    values = [*FLAT, 100, 120]

    misses = backtest(values, 2)

    # From month 24 (trend 1): 100 and 100 forecast, 100 and 120 happened.
    # From month 25 (trend 1200 / 1200): 100 forecast, 120 happened; its second month is unknown.
    assert misses[0] == pytest.approx([0.0, 0.2])
    assert misses[1] == pytest.approx([0.2])


def test_the_range_and_the_typical_error_come_from_the_past_misses():
    """Two flat years of 100, then six months tested one month ahead (horizon 1).

    From month 24 the trend is 1, so 100 is forecast; from month 25 the trend is
    (1100 + 106) / 1200, so 100.5 is forecast; and so on:

    | Month | Forecast | Happened | Miss |
    |---|---|---|---|
    | 24 | 100 | 106 | +0.06 |
    | 25 | 100.5 | 94 | 94 / 100.5 - 1 |
    | 26 | 100 | 112 | +0.12 |
    | 27 | 101 | 88 | 88 / 101 - 1 |
    | 28 | 100 | 100 | 0 |
    | 29 | 100 | 100 | 0 |
    """
    values = [*FLAT, 106, 94, 112, 88, 100, 100]
    miss_25, miss_27 = 94 / 100.5 - 1, 88 / 101 - 1

    outcome = forecast_series(values, 1)

    assert outcome.refusal is None
    # Month 30: the trend is back to 1, and month 18 was 100.
    assert outcome.trend == pytest.approx(1.0)
    [point] = outcome.points
    assert point.value == pytest.approx(100)
    # The 10th percentile of six misses lies halfway between the two lowest, the 90th halfway
    # between the two highest.
    assert point.low == pytest.approx(100 * (1 + (miss_27 + miss_25) / 2))
    assert point.high == pytest.approx(100 * (1 + (0.06 + 0.12) / 2))
    # The median size lies halfway between the third and fourth: 0.06 and 94 / 100.5 - 1.
    assert outcome.typical_error == pytest.approx((0.06 + abs(miss_25)) / 2)


def test_a_method_that_kept_forecasting_too_high_is_corrected_by_its_median_miss():
    """Two flat years of 100, then six months of 90, tested one month ahead (horizon 1).

    The trend falls a little each month, but the method keeps forecasting above 90:

    | Month | Forecast | Happened |
    |---|---|---|
    | 24 | 100 | 90 |
    | 25 | 100 x 1190 / 1200 | 90 |
    | 26 | 100 x 1180 / 1200 | 90 |
    | 27 | 100 x 1170 / 1200 | 90 |
    | 28 | 100 x 1160 / 1200 | 90 |
    | 29 | 100 x 1150 / 1200 | 90 |

    Month 30 is forecast as month 18 (100) times the trend 1140 / 1200, then moved by the median
    of those six misses, so the figure is not at the top of its own range.
    """
    values = [*FLAT, 90, 90, 90, 90, 90, 90]
    misses = [90 / (100 * (1200 - 10 * n) / 1200) - 1 for n in range(6)]
    median = (misses[2] + misses[3]) / 2
    raw = 100 * 1140 / 1200

    [point] = forecast_series(values, 1).points

    assert point.value == pytest.approx(raw * (1 + median))
    assert point.low == pytest.approx(raw * (1 + (misses[0] + misses[1]) / 2))
    assert point.high == pytest.approx(raw * (1 + (misses[4] + misses[5]) / 2))
    assert point.low <= point.value <= point.high


def test_a_series_the_method_fits_exactly_has_a_range_of_no_width():
    """Each month is one and a half times the same month a year earlier."""
    first_year = [40 + 4 * month for month in range(12)]
    values = (first_year + [v * 3 // 2 for v in first_year] + [v * 9 // 4 for v in first_year])[:34]

    outcome = forecast_series(values, 3)

    assert outcome.trend == pytest.approx(1.5)
    assert outcome.typical_error == pytest.approx(0)
    # Months 34 to 36 are the tenth to twelfth months of the third year.
    expected = [v * 9 / 4 for v in first_year[10:12]] + [first_year[0] * 27 / 8]
    assert [point.value for point in outcome.points] == pytest.approx(expected)
    assert [(point.low, point.high) for point in outcome.points] == pytest.approx(
        [(value, value) for value in expected]
    )


def test_each_month_ahead_needs_six_past_tests():
    assert [months_needed(horizon) for horizon in (1, 3, 6)] == [30, 32, 35]
    assert forecast_series([20] * 31, 3).refusal.need == 32
    assert forecast_series([20] * 32, 3).refusal is None


@pytest.mark.parametrize(
    ("values", "horizon", "reason", "have", "need"),
    [
        # Under two years: 20 months, and 32 are needed for three months ahead.
        ([100] * 20, 3, "short_history", 20, 32),
        # Two years is enough to forecast but not to test the forecast.
        ([100] * 26, 1, "short_history", 26, 30),
        # 5 a month over the last year.
        ([5] * 30, 1, "too_sparse", 5.0, 10),
        # Months that swing by half: misses of 0.5 and -0.52, a typical error of 51%.
        ([*FLAT, 150, 50, 150, 50, 150, 50], 1, "too_erratic", 51.0, 35.0),
    ],
)
def test_a_series_that_cannot_be_forecast_is_refused_with_what_it_has_and_needs(
    values, horizon, reason, have, need
):
    outcome = forecast_series(values, horizon)

    assert outcome.points == []
    assert outcome.refusal is not None
    assert (outcome.refusal.reason, outcome.refusal.have, outcome.refusal.need) == (
        reason,
        have,
        need,
    )


def test_ten_a_month_is_not_too_sparse():
    assert forecast_series([10] * 30, 1).refusal is None


def test_a_forecast_of_nothing_for_a_month_that_had_some_is_too_erratic():
    """Month 12 had nothing, so the test from month 24 forecasts nothing for a month of 100."""
    values = [100] * 12 + [0] + [100] * 17

    outcome = forecast_series(values, 1)

    assert outcome.refusal is not None
    assert (outcome.refusal.reason, outcome.refusal.have) == ("too_erratic", None)
