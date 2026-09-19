"""The analyst's tools for the staff face: the metric catalogue, typed metric queries and
forecasts, each shown as a table with, where it helps, a chart.

The model never writes SQL. It picks a metric, a grouping, filters, a period and a comparison
from the catalogue (app.services.metrics), and the server runs fixed statements. Every figure a
reply may quote is in the result, shares, changes and forecast ranges included, so the number
check holds for analyst answers as for any other.
"""

from dataclasses import asdict
from typing import Any, Literal

from app.copilot.tools import Data, Tool, ToolContext, ToolOutput, ToolParams
from app.schemas.copilot import (
    ChartBand,
    ChartSeries,
    TableChart,
    TableColumn,
    TableDisplay,
    TableFormat,
)
from app.services import circulation, metrics
from app.services.activity import format_day, format_month
from app.services.metrics.forecast import MIN_MONTHS

# How a grouping reads in a title ("Loans by category") and as its column's header.
_GROUPING_TITLES: dict[metrics.Grouping, str] = {
    "category": "category",
    "book": "book",
    "author": "author",
    "month": "month",
    "year": "year",
    "weekday": "weekday",
    "member_joined_year": "year the member joined",
}
_GROUPING_HEADERS: dict[metrics.Grouping, str] = {
    "category": "Category",
    "book": "Book",
    "author": "Author",
    "month": "Month",
    "year": "Year",
    "weekday": "Weekday",
    "member_joined_year": "Member joined",
}
_EARLIER_HEADERS = {"previous_period": "Previous period", "same_period_last_year": "A year earlier"}
# Groupings shown as a line when their rows are in time order.
_LINE_GROUPINGS: tuple[metrics.Grouping, ...] = ("month", "year")
_MIN_LINE_POINTS = 3
_MIN_BARS, _MAX_BARS = 2, 12


# describe_metrics


class DescribeMetrics(ToolParams):
    pass


async def _describe_metrics(_: ToolContext, __: DescribeMetrics) -> ToolOutput:
    catalogue = [
        {
            "name": metric.name,
            "meaning": metric.meaning,
            "measured": metric.measured,
            "value": metric.unit,
            "group_by": list(metric.groupings),
            "filters": list(metric.filters),
            "share_of_total": metric.shares,
        }
        for metric in metrics.CATALOGUE.values()
    ]
    data = {
        "today": format_day(circulation.today_utc()),
        "metrics": catalogue,
        "group_by": metrics.GROUPINGS,
        "filters": metrics.FILTERS,
        "periods": {
            "presets": metrics.PRESETS,
            "dates": "Instead of a preset, from and to as dates, from not after to and to not "
            "after today.",
            "default": metrics.DEFAULT_PRESET,
            "measured_now": "Metrics measured now take no period and no comparison.",
        },
        "compare_to": metrics.COMPARISONS,
    }
    return ToolOutput(data)


def _render_catalogue(data: Data) -> str:
    lines = [f"- {metric['name']}: {metric['meaning']}" for metric in data["metrics"]]
    return "\n".join(["The figures I can give:", *lines])


# query_metrics


class QueryMetrics(metrics.MetricQuery, ToolParams):
    pass


def _period_data(period: metrics.Period) -> Data:
    return {
        "from": format_day(period.start),
        "to": format_day(period.end),
        "label": period.label,
        "partial": period.partial,
    }


def _comparison_data(comparison: metrics.Comparison) -> Data:
    return {
        "kind": comparison.kind,
        "from": format_day(comparison.start),
        "to": format_day(comparison.end),
        "label": comparison.label,
    }


def _compared_fields(result: metrics.MetricResult, item: Any, *, shares: bool) -> Data:
    """The comparison figures of a row or the total: none without a comparison, and no
    relative change for a percentage metric, whose change is already in points.
    """
    if result.comparison is None:
        return {}
    data: Data = {"previous_value": item.previous_value}
    if shares:
        data["previous_share_pct"] = item.previous_share_pct
    data["change"] = item.change
    if result.metric.unit != "percent":
        data["change_pct"] = item.change_pct
    return data


def _row_data(result: metrics.MetricResult, row: metrics.Row) -> Data:
    shares = result.metric.shares
    # A book's key is its id. Under an id's name its digits cannot vouch for a number in the
    # reply (app.copilot.numbers).
    key_name = "book_id" if result.group_by == "book" else "key"
    data: Data = {key_name: row.key, "label": row.label, "value": row.value}
    if shares:
        data["share_pct"] = row.share_pct
    return {**data, **_compared_fields(result, row, shares=shares)}


def result_data(result: metrics.MetricResult) -> Data:
    """The result as the model reads it: every figure a reply may use, dates written out."""
    return {
        "metric": result.metric.name,
        "label": result.metric.label,
        "measured": result.metric.measured,
        "period": _period_data(result.period) if result.period is not None else None,
        "comparison": (
            _comparison_data(result.comparison) if result.comparison is not None else None
        ),
        "group_by": result.group_by,
        "sort": result.sort,
        "rows": [_row_data(result, row) for row in result.rows],
        "rows_total": result.rows_total,
        "total": {
            "value": result.total.value,
            **_compared_fields(result, result.total, shares=False),
        },
    }


def _title(result: metrics.MetricResult) -> str:
    if result.group_by == "none":
        return result.metric.label
    return f"{result.metric.label} by {_GROUPING_TITLES[result.group_by]}"


def _subtitle(result: metrics.MetricResult) -> str:
    """The period (or "Now"), the comparison and the filters."""
    period = result.period
    if period is None:
        parts = ["Now"]
    else:
        # A label that names its days already, such as "Q2 2026", needs no dates after it.
        named = period.label == metrics.range_label(period.start, period.end)
        days = f"{format_day(period.start)} to {format_day(period.end)}"
        parts = [period.label if named else f"{period.label} ({days})"]
    if result.comparison is not None:
        parts.append(f"compared with {result.comparison.label}")
    return " · ".join([*parts, *result.scope])


def _columns(result: metrics.MetricResult) -> list[TableColumn]:
    metric, grouped = result.metric, result.group_by != "none"
    unit: TableFormat = metric.unit
    columns = []
    if grouped:
        columns.append(
            TableColumn(key="label", label=_GROUPING_HEADERS[result.group_by], format="text")
        )
    columns.append(TableColumn(key="value", label=metric.label, format=unit))
    shares = metric.shares and grouped
    if shares:
        columns.append(TableColumn(key="share_pct", label="Share", format="percent"))
    if result.comparison is not None:
        earlier = _EARLIER_HEADERS[result.comparison.kind]
        columns.append(TableColumn(key="previous_value", label=earlier, format=unit))
        if shares:
            columns.append(
                TableColumn(key="previous_share_pct", label="Share before", format="percent")
            )
        change: TableFormat = "points" if metric.unit == "percent" else unit
        columns.append(TableColumn(key="change", label="Change", format=change))
        if metric.unit != "percent":
            columns.append(TableColumn(key="change_pct", label="Change %", format="change_percent"))
    return columns


def _cells(columns: list[TableColumn], values: dict[str, Any]) -> dict[str, Any]:
    return {column.key: values.get(column.key) for column in columns}


def _chart(result: metrics.MetricResult) -> TableChart | None:
    """A line for months or years in time order with at least three points; bars for other
    groupings with two to twelve rows; otherwise none. A list of books not borrowed is a list,
    not a chart.
    """
    rows, grouping = len(result.rows), result.group_by
    if grouping == "none" or (result.metric.name == "titles_not_borrowed" and grouping == "book"):
        return None
    if grouping in _LINE_GROUPINGS and result.sort == "key":
        if rows < _MIN_LINE_POINTS:
            return None
        chart_type: Literal["bar", "line"] = "line"
    elif _MIN_BARS <= rows <= _MAX_BARS:
        chart_type = "bar"
    else:
        return None
    series = [ChartSeries(key="value", label=result.metric.label)]
    if result.comparison is not None:
        earlier = _EARLIER_HEADERS[result.comparison.kind]
        series.append(ChartSeries(key="previous_value", label=earlier))
    return TableChart(type=chart_type, x="label", series=series)


def table_display(result: metrics.MetricResult) -> TableDisplay:
    columns = _columns(result)
    total = {
        "label": "Total",
        "value": result.total.value,
        "previous_value": result.total.previous_value,
        "change": result.total.change,
        "change_pct": result.total.change_pct,
    }
    if result.group_by == "none":
        # A single figure: one row, and no total row under it.
        rows, total_row = [_cells(columns, total)], None
    else:
        rows = [_cells(columns, asdict(row)) for row in result.rows]
        total_row = _cells(columns, total)
    return TableDisplay(
        title=_title(result),
        subtitle=_subtitle(result),
        columns=columns,
        rows=rows,
        total=total_row,
        chart=_chart(result),
    )


async def _query_metrics(context: ToolContext, params: QueryMetrics) -> ToolOutput:
    result = await metrics.run_query(context.session, params, today=circulation.today_utc())
    return ToolOutput(result_data(result), table_display(result))


def _figure(value: Any, unit: metrics.Unit) -> str:
    if value is None:
        return "no figure"
    if unit == "count":
        return f"{value:,}"
    return f"{value}%" if unit == "percent" else f"{value} days"


def _change_text(item: Data, unit: metrics.Unit) -> str:
    text = f"{_figure(item['value'], unit)}"
    if item.get("share_pct") is not None:
        text += f" ({item['share_pct']}% of the total)"
    if "previous_value" not in item:
        return text
    text += f", against {_figure(item['previous_value'], unit)}"
    if item.get("previous_share_pct") is not None:
        text += f" ({item['previous_share_pct']}%)"
    change = item.get("change")
    if change is not None:
        signed = f"{change:+,}" if unit == "count" else f"{change:+}"
        text += (
            f", a change of {signed}" + {"count": "", "percent": " points", "days": " days"}[unit]
        )
        if item.get("change_pct") is not None:
            text += f" ({item['change_pct']:+}%)"
    return text


def _render_query(data: Data) -> str:
    unit = metrics.CATALOGUE[data["metric"]].unit
    heading = data["label"]
    if data["group_by"] != "none":
        heading += f" by {_GROUPING_TITLES[data['group_by']]}"
    period = data["period"]
    heading += (
        " now" if period is None else f", {period['label']} ({period['from']} to {period['to']})"
    )
    if data["comparison"] is not None:
        heading += f", compared with {data['comparison']['label']}"
    total = _change_text(data["total"], unit)
    if data["group_by"] == "none":
        return f"{heading}: {total}."
    if not data["rows"]:
        return f"{heading}: nothing to show."
    lines = [f"- {row['label']}: {_change_text(row, unit)}" for row in data["rows"]]
    return "\n".join([f"{heading}:", *lines, f"Total: {total}."])


# forecast_metric


class ForecastMetric(metrics.ForecastQuery, ToolParams):
    pass


FORECAST_METHOD = (
    "Each month is forecast as the same month a year earlier times the trend (the last 12 "
    "months against the 12 before, held between 0.5 and 2.0), then corrected by how far the "
    "same method typically missed when it was tested on past months. The likely range comes "
    "from those same tests: about 8 past months in 10 fell inside it."
)
_REFUSAL_ALTERNATIVE = "the trend: the last 12 months against the 12 before"


def _months_text(months: float) -> str:
    return f"{months:g} full month" + ("" if months == 1 else "s")


def _refusal_data(result: metrics.ForecastResult, refusal: metrics.Refusal) -> Data:
    """What the records have and what a forecast would need, in words with their figures."""
    noun = result.metric.label.lower()
    if refusal.reason == "short_history":
        have = f"{_months_text(refusal.have or 0)} of history"
        need = (
            f"{_months_text(refusal.need)}: {MIN_MONTHS} to forecast from, and "
            f"{refusal.need - MIN_MONTHS:g} more to test the method against"
        )
    elif refusal.reason == "too_sparse":
        have = f"an average of {refusal.have} {noun} a month over the last 12 months"
        need = f"an average of at least {refusal.need:g} {noun} a month"
    else:
        have = (
            f"a typical error of {refusal.have}% when the method was tested on past months"
            if refusal.have is not None
            else f"past forecasts of no {noun} for months that had some"
        )
        need = f"a typical error of at most {refusal.need:g}%"
    return {
        "reason": refusal.reason,
        "have": have,
        "need": need,
        "alternative": _REFUSAL_ALTERNATIVE,
    }


def _trend_data(trend: metrics.Trend) -> Data:
    return {
        "period": metrics.range_label(trend.start, trend.end),
        "value": trend.value,
        "previous_period": metrics.range_label(trend.previous_start, trend.previous_end),
        "previous_value": trend.previous_value,
        "change": trend.change,
        "change_pct": trend.change_pct,
    }


def forecast_data(result: metrics.ForecastResult) -> Data:
    """The forecast as the model reads it: months written out, counts as whole numbers."""
    refusal = result.refusal
    return {
        "metric": result.metric.name,
        "label": result.metric.label,
        "method": FORECAST_METHOD,
        "basis": f"{result.months} months of history",
        "typical_error_pct": result.typical_error_pct,
        "history": [
            {"month": format_month(month.month), "value": month.value} for month in result.history
        ],
        "forecast": [
            {
                "month": format_month(month.month),
                "value": month.value,
                "low": month.low,
                "high": month.high,
            }
            for month in result.forecast
        ],
        "refusal": _refusal_data(result, refusal) if refusal is not None else None,
        "trend": _trend_data(result.trend) if result.trend is not None else None,
    }


def _forecast_span(result: metrics.ForecastResult) -> str:
    first, last = (format_month(month.month) for month in (result.forecast[0], result.forecast[-1]))
    return first if first == last else f"{first} to {last}"


def _forecast_display(result: metrics.ForecastResult) -> TableDisplay:
    """The last 12 months as counted and the forecast months with their ranges, as a line with
    the range shaded.
    """
    label = result.metric.label
    columns = [
        TableColumn(key="label", label="Month", format="text"),
        TableColumn(key="actual", label=label, format="count"),
        TableColumn(key="forecast", label="Forecast", format="count"),
        TableColumn(key="low", label="Low", format="count"),
        TableColumn(key="high", label="High", format="count"),
    ]
    rows: list[dict[str, Any]] = [
        {"label": format_month(month.month), "actual": month.value} for month in result.history
    ]
    rows += [
        {
            "label": format_month(month.month),
            "forecast": month.value,
            "low": month.low,
            "high": month.high,
        }
        for month in result.forecast
    ]
    history = f"from {result.months} months of history"
    if result.first_month is not None:
        history += f", {format_month(result.first_month)} to {format_month(result.last_month)}"
    subtitle = [_forecast_span(result), history, f"typical error {result.typical_error_pct}%"]
    return TableDisplay(
        title=f"{label} forecast",
        subtitle=" · ".join([*subtitle, *result.scope]),
        columns=columns,
        rows=[_cells(columns, row) for row in rows],
        total=None,
        chart=TableChart(
            type="line",
            x="label",
            series=[
                ChartSeries(key="actual", label=label),
                ChartSeries(key="forecast", label="Forecast"),
            ],
            band=ChartBand(low="low", high="high", label="Likely range"),
        ),
    )


def _trend_display(result: metrics.ForecastResult, trend: metrics.Trend) -> TableDisplay:
    """A refused forecast's trend: one row, the last 12 months against the 12 before."""
    columns = [
        TableColumn(key="value", label="Last 12 months", format="count"),
        TableColumn(key="previous_value", label="12 months before", format="count"),
        TableColumn(key="change", label="Change", format="count"),
        TableColumn(key="change_pct", label="Change %", format="change_percent"),
    ]
    data = _trend_data(trend)
    compared = f"{data['period']} compared with {data['previous_period']}"
    return TableDisplay(
        title=f"{result.metric.label} trend",
        subtitle=" · ".join([compared, *result.scope]),
        columns=columns,
        rows=[_cells(columns, data)],
        total=None,
        chart=None,
    )


async def _forecast_metric(context: ToolContext, params: ForecastMetric) -> ToolOutput:
    result = await metrics.run_forecast(context.session, params, today=circulation.today_utc())
    if result.trend is not None:
        display = _trend_display(result, result.trend)
    else:
        display = _forecast_display(result)
    return ToolOutput(forecast_data(result), display)


def _render_forecast(data: Data) -> str:
    label, refusal = data["label"], data["refusal"]
    if refusal is not None:
        trend = data["trend"]
        text = (
            f"No forecast of {label.lower()}: the records have {refusal['have']}, and a forecast "
            f"would need {refusal['need']}. The trend instead: {trend['value']:,} in "
            f"{trend['period']}, against {trend['previous_value']:,} in "
            f"{trend['previous_period']}, a change of {trend['change']:+,}"
        )
        if trend["change_pct"] is not None:
            text += f" ({trend['change_pct']:+}%)"
        return text + "."
    lines = [
        f"- {month['month']}: {month['value']:,}, likely {month['low']:,} to {month['high']:,}"
        for month in data["forecast"]
    ]
    heading = (
        f"{label} forecast from {data['basis']}, with a typical error of "
        f"{data['typical_error_pct']}%:"
    )
    return "\n".join([heading, *lines])


FORECAST_METRIC = Tool(
    name="forecast_metric",
    description="Forecast a monthly count, loans, returns or new members, for the coming months "
    "starting with this one, from the full months of history. Returns each month's forecast "
    "with its likely range, how the range was measured (by testing the same method on past "
    "months) and the typical error. When the history is too short, too sparse or too erratic, "
    "it returns a refusal saying what the records have and what a forecast would need, with the "
    "trend of the last twelve months against the twelve before instead. The panel shows the "
    "forecast as a chart with the range shaded, or the trend as a table.",
    params=ForecastMetric,
    status="Working out the forecast",
    run=_forecast_metric,
    render=_render_forecast,
)

DESCRIBE_METRICS = Tool(
    name="describe_metrics",
    description="The catalogue of figures about how the library is used: each metric with its "
    "meaning, whether it is measured over a period or now, the groupings and filters it accepts "
    "and whether rows get a share of the total; the period presets, the comparisons and today's "
    "date.",
    params=DescribeMetrics,
    status="Looking at the figures available",
    run=_describe_metrics,
    render=_render_catalogue,
)

QUERY_METRICS = Tool(
    name="query_metrics",
    description="Answer a question about how the library is used with one typed query: a "
    "metric, optionally grouped, filtered, over a period and compared with an earlier period. "
    "Returns the period covered, the rows, and the total over the whole filtered scope (not a "
    "sum of the rows); rows get their share of the total where shares apply, and with a "
    "comparison the earlier values and the changes. late_return_rate and copies_on_loan_share "
    "are percentages, and their changes are percentage points; average_loan_days is in days. "
    "The panel shows the result as a table, with a chart where it helps. A combination the "
    "metric does not accept comes back as an error that lists what it accepts.",
    params=QueryMetrics,
    status="Counting the figures",
    run=_query_metrics,
    render=_render_query,
)
