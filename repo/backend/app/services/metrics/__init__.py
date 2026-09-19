"""The library's usage figures: typed metric queries, answered from fixed statements.

A query names a metric from a fixed catalogue (catalogue.py), and may add a grouping, filters, a
period and a comparison with an earlier period (periods.py). Each metric has one fixed statement
(queries.py); nothing in a query is ever written into SQL, and everything here is read-only. A
forecast (forecast.py) extends a monthly count into the next months, or refuses to.

Periods are whole days in UTC, resolved against today. A total is the metric over the whole
filtered scope, never a sum of rows, so distinct borrowers and rates stay right. Shares, changes
and rates are computed here and rounded to one decimal, so every figure an answer may quote is
in the result.
"""

from app.services.metrics.catalogue import (
    CATALOGUE,
    COMPARISONS,
    DEFAULT_PRESET,
    FILTERS,
    GROUPINGS,
    PRESETS,
    TIME_GROUPINGS,
    ForecastFilters,
    ForecastQuery,
    Grouping,
    Metric,
    MetricFilters,
    MetricName,
    MetricQuery,
    PeriodSpec,
    Unit,
    YearRange,
)
from app.services.metrics.forecast import (
    ForecastMonth,
    ForecastResult,
    MonthValue,
    Refusal,
    Trend,
    forecast_series,
    run_forecast,
)
from app.services.metrics.periods import (
    Comparison,
    Period,
    range_label,
    resolve_comparison,
    resolve_period,
)
from app.services.metrics.queries import MetricResult, Row, Total, round_one, run_query

__all__ = [
    "CATALOGUE",
    "COMPARISONS",
    "DEFAULT_PRESET",
    "FILTERS",
    "GROUPINGS",
    "PRESETS",
    "TIME_GROUPINGS",
    "Comparison",
    "ForecastFilters",
    "ForecastMonth",
    "ForecastQuery",
    "ForecastResult",
    "Grouping",
    "Metric",
    "MetricFilters",
    "MetricName",
    "MetricQuery",
    "MetricResult",
    "MonthValue",
    "Period",
    "PeriodSpec",
    "Refusal",
    "Row",
    "Total",
    "Trend",
    "Unit",
    "YearRange",
    "forecast_series",
    "range_label",
    "resolve_comparison",
    "resolve_period",
    "round_one",
    "run_forecast",
    "run_query",
]
