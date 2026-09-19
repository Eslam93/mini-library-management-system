"""Forecasts of a monthly count (loans, returns or new members) for the next one to six months,
each month with a likely range measured from the method's own past misses, or an honest refusal
that offers the trend instead.

The series is the count per calendar month in UTC, from the first full month with data to the
last full month. The current month is partial, so it is left out of the series and is the first
month forecast. The method is written here and needs no library: a month's forecast is the same
month a year earlier times the trend, which is the last 12 months' total over the total of the
12 before, held between 0.5 and 2.0. It needs 24 months.

The range is measured, not assumed. The same method is run from every past month that has 24
months before it, and each of its forecasts is compared with what happened: the miss is
actual / forecast - 1. For each month ahead, the 10th and 90th percentiles of those misses widen
the forecast, so about eight past months in ten fell inside the range, and the median miss moves
the forecast itself: a library whose growth slows makes "last year times the trend" run high
month after month, and the past tests measure by how much. The typical error is the median size
of the misses, over every month ahead.

A series is refused, with what it has and what it would need, when it is too short (each month
ahead needs six past tests), too sparse (under ten a month over the last 12 months) or too
erratic (a typical error over 35%). A refusal carries the trend instead: the last 12 calendar
months against the 12 before.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.metrics.catalogue import CATALOGUE, ForecastQuery, Metric, MetricFilters, refusal
from app.services.metrics.periods import add_months, buckets
from app.services.metrics.queries import describe_filters, first_event_day, round_one, statement

YEAR = 12
# The method looks back two years.
MIN_MONTHS = 2 * YEAR
# Each month ahead is tested at least this often before its range is trusted.
MIN_TESTS = 6
MIN_MONTHLY_AVERAGE = 10
MAX_TYPICAL_ERROR = 0.35
MIN_TREND, MAX_TREND = 0.5, 2.0
LOW_SHARE, HIGH_SHARE = 0.1, 0.9

RefusalReason = Literal["short_history", "too_sparse", "too_erratic"]


# The method, on a plain series of monthly counts, oldest first


def trend_factor(values: Sequence[int]) -> float:
    """The last 12 months' total over the 12 months' before, held between 0.5 and 2.0. Growth
    from nothing counts as the most growth, and nothing after nothing as no change.
    """
    recent, earlier = sum(values[-YEAR:]), sum(values[-MIN_MONTHS:-YEAR])
    if earlier == 0:
        return MAX_TREND if recent > 0 else 1.0
    return min(MAX_TREND, max(MIN_TREND, recent / earlier))


def seasonal_forecast(values: Sequence[int], horizon: int) -> list[float]:
    """The `horizon` months after the series, each the same month a year earlier times the
    trend. The series needs 24 months.
    """
    factor = trend_factor(values)
    start = len(values) - YEAR
    return [values[start + step] * factor for step in range(horizon)]


def miss(actual: int, forecast: float) -> float:
    """actual / forecast - 1. A forecast of nothing is exact when nothing happened, and misses
    without limit otherwise.
    """
    if forecast > 0:
        return actual / forecast - 1
    return 0.0 if actual == 0 else math.inf


def backtest(values: Sequence[int], horizon: int) -> list[list[float]]:
    """For each month ahead, the misses of the method run from every past month that has 24
    months before it, where what happened is known.
    """
    misses: list[list[float]] = [[] for _ in range(horizon)]
    for origin in range(MIN_MONTHS, len(values)):
        for step, forecast in enumerate(seasonal_forecast(values[:origin], horizon)):
            if origin + step < len(values):
                misses[step].append(miss(values[origin + step], forecast))
    return misses


def percentile(values: Sequence[float], share: float) -> float:
    """The value below which `share` of the values fall, interpolating linearly between the two
    nearest ranks: the 90th percentile of 1 to 11 is 10.
    """
    ordered = sorted(values)
    position = (len(ordered) - 1) * share
    below, above = ordered[math.floor(position)], ordered[math.ceil(position)]
    if below == above:
        return below
    return below + (above - below) * (position - math.floor(position))


def months_needed(horizon: int) -> int:
    """24 months to forecast from, and enough months after them to test each month ahead six
    times: 32 for three months ahead.
    """
    return MIN_MONTHS + MIN_TESTS + horizon - 1


@dataclass(frozen=True)
class Point:
    value: float
    low: float
    high: float


@dataclass(frozen=True)
class Refusal:
    reason: RefusalReason
    # What the series has and what a forecast would need: months (short_history), a monthly
    # average (too_sparse) or a typical error in percent (too_erratic; None when the past
    # forecasts missed without limit).
    have: float | None
    need: float


@dataclass(frozen=True)
class SeriesForecast:
    points: list[Point]
    trend: float | None
    # The median size of the past misses, as a fraction. None before the tests run, and when
    # they missed without limit.
    typical_error: float | None
    refusal: Refusal | None


def _refused(reason: RefusalReason, have: float | None, need: float) -> SeriesForecast:
    return SeriesForecast([], None, None, Refusal(reason, have, need))


def forecast_series(values: Sequence[int], horizon: int) -> SeriesForecast:
    """The months after the series with their likely ranges, or why they are not forecast."""
    needed = months_needed(horizon)
    if len(values) < needed:
        return _refused("short_history", len(values), needed)
    average = sum(values[-YEAR:]) / YEAR
    if average < MIN_MONTHLY_AVERAGE:
        return _refused("too_sparse", round_one(average), MIN_MONTHLY_AVERAGE)

    misses = backtest(values, horizon)
    typical = percentile([abs(value) for step in misses for value in step], 0.5)
    ranges = [
        (percentile(step, LOW_SHARE), percentile(step, 0.5), percentile(step, HIGH_SHARE))
        for step in misses
    ]
    bounded = math.isfinite(typical) and all(math.isfinite(high) for _, _, high in ranges)
    if not bounded or typical > MAX_TYPICAL_ERROR:
        have = round_one(100 * typical) if bounded else None
        return _refused("too_erratic", have, round_one(100 * MAX_TYPICAL_ERROR))

    forecasts = seasonal_forecast(values, horizon)
    points = [
        Point(value * (1 + median), value * (1 + low), value * (1 + high))
        for value, (low, median, high) in zip(forecasts, ranges, strict=True)
    ]
    return SeriesForecast(points, trend_factor(values), typical, None)


# The forecast of a metric from the database


@dataclass(frozen=True)
class MonthValue:
    # The month's first day.
    month: date
    value: int


@dataclass(frozen=True)
class ForecastMonth:
    month: date
    value: int
    low: int
    high: int


@dataclass(frozen=True)
class Trend:
    """The last 12 calendar months against the 12 before them. Months before the records start
    count as nothing.
    """

    start: date
    end: date
    value: int
    previous_start: date
    previous_end: date
    previous_value: int
    change: int
    change_pct: float | None


@dataclass(frozen=True)
class ForecastResult:
    metric: Metric
    # The full months of the series, and its first month (None without data).
    months: int
    first_month: date | None
    last_month: date
    # The series' last 12 months.
    history: list[MonthValue]
    trend_factor: float | None
    typical_error_pct: float | None
    forecast: list[ForecastMonth]
    refusal: Refusal | None
    # Only with a refusal.
    trend: Trend | None
    # The filters in words, such as "category: Fantasy".
    scope: list[str]


def _whole(value: float) -> int:
    """Rounded to a whole number with halves up, as people round by hand."""
    return int(Decimal(repr(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _hundredths(value: float) -> float:
    return float(Decimal(repr(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _monthly_counts(
    session: AsyncSession, metric: Metric, filters: MetricFilters, first: date, last: date
) -> list[int]:
    """The count in each month from the month `first` to the month `last`, empty ones as 0."""
    end = add_months(last, 1) - timedelta(days=1)
    rows = await session.execute(statement(metric, "month", filters, (first, end)))
    counts = {row.group_key: int(row.numerator or 0) for row in rows}
    return [counts.get(key, 0) for key in buckets("month", first, end)]


def _trend(counts: list[int], this_month: date) -> Trend:
    """counts run up to last month; earlier months count as nothing."""
    padded = [0] * max(0, 2 * YEAR - len(counts)) + counts
    value, previous = sum(padded[-YEAR:]), sum(padded[-2 * YEAR : -YEAR])
    start, previous_start = add_months(this_month, -YEAR), add_months(this_month, -2 * YEAR)
    change = value - previous
    return Trend(
        start=start,
        end=this_month - timedelta(days=1),
        value=value,
        previous_start=previous_start,
        previous_end=start - timedelta(days=1),
        previous_value=previous,
        change=change,
        change_pct=round_one(100 * change / previous) if previous else None,
    )


async def run_forecast(
    session: AsyncSession, query: ForecastQuery, *, today: date
) -> ForecastResult:
    """Forecasts the metric for the months from this one on. Filters the metric does not take,
    and names that do not exist, are refused with a ValidationFailedError.
    """
    metric = CATALOGUE[query.metric]
    if any(name not in metric.filters for name in query.filters.used()):
        raise refusal(
            f"{metric.name} is forecast for the whole library, with no filters.",
            "filter_not_accepted",
        )
    filters = query.filters.as_metric_filters()
    scope = await describe_filters(session, filters)

    this_month = today.replace(day=1)
    last_month = add_months(this_month, -1)
    first_day = await first_event_day(session, metric, filters)
    counts: list[int] = []
    if first_day is not None and first_day < this_month:
        counts = await _monthly_counts(
            session, metric, filters, first_day.replace(day=1), last_month
        )
    # The first month with data is full only when the data starts on its first day.
    partial = 1 if counts and first_day is not None and first_day.day > 1 else 0
    series = counts[partial:]
    first_month = add_months(last_month, 1 - len(series)) if series else None
    history = [
        MonthValue(add_months(last_month, index - len(series) + 1), value)
        for index, value in enumerate(series)
    ][-YEAR:]

    outcome = forecast_series(series, query.horizon_months)
    forecast = [
        ForecastMonth(add_months(this_month, step), _whole(p.value), _whole(p.low), _whole(p.high))
        for step, p in enumerate(outcome.points)
    ]
    typical = outcome.typical_error
    return ForecastResult(
        metric=metric,
        months=len(series),
        first_month=first_month,
        last_month=last_month,
        history=history,
        trend_factor=_hundredths(outcome.trend) if outcome.trend is not None else None,
        typical_error_pct=round_one(100 * typical) if typical is not None else None,
        forecast=forecast,
        refusal=outcome.refusal,
        trend=_trend(counts, this_month) if outcome.refusal is not None else None,
        scope=scope,
    )
