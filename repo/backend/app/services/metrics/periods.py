"""Periods and comparisons: the whole days in UTC a query covers, resolved against today, and
the time buckets of a period.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.activity import format_day, format_month
from app.services.metrics.catalogue import ComparisonKind, Grouping, PeriodSpec, refusal

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    partial: bool
    # The calendar unit in months, for calendar presets. None for rolling presets, all_time and
    # explicit dates, which compare with the same number of days just before.
    unit_months: int | None = None
    all_time: bool = False


@dataclass(frozen=True)
class Comparison:
    kind: ComparisonKind
    start: date
    end: date
    label: str


def add_months(day: date, months: int) -> date:
    """The same day `months` later, or earlier when negative, cut to the end of a shorter month:
    29 Feb less twelve months is 28 Feb.
    """
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def _month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _quarter(day: date) -> int:
    return (day.month - 1) // 3 + 1


def range_label(start: date, end: date) -> str:
    """A calendar year, quarter, month or run of months by name; any other range by its days."""
    if start.day == 1 and end == _month_end(end):
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        if months == 12 and start.month == 1:
            return str(start.year)
        if months == 3 and start.month % 3 == 1:
            return f"Q{_quarter(start)} {start.year}"
        if months == 1:
            return format_month(start)
        return f"{format_month(start)} to {format_month(end)}"
    return f"{format_day(start)} to {format_day(end)}"


def resolve_period(spec: PeriodSpec, *, today: date, first_day: date | None = None) -> Period:
    """The days a period covers. first_day is where all_time starts; without data it is today."""
    if spec.preset is None:
        start, end = spec.from_ or today, spec.to or today
        if start > end:
            raise refusal("The period's from date is after its to date.", "invalid_period")
        if end > today:
            raise refusal(
                f"The period cannot end after today, {format_day(today)}.", "invalid_period"
            )
        return Period(start, end, range_label(start, end), partial=False)

    month_start = today.replace(day=1)
    quarter_start = date(today.year, 3 * _quarter(today) - 2, 1)
    match spec.preset:
        case "last_30_days":
            return Period(today - timedelta(days=29), today, "Last 30 days", partial=False)
        case "last_90_days":
            return Period(today - timedelta(days=89), today, "Last 90 days", partial=False)
        case "this_month":
            return Period(month_start, today, f"{format_month(today)} so far", True, 1)
        case "this_quarter":
            label = f"Q{_quarter(today)} {today.year} so far"
            return Period(quarter_start, today, label, True, 3)
        case "this_year":
            return Period(date(today.year, 1, 1), today, f"{today.year} so far", True, 12)
        case "last_month":
            start, unit = add_months(month_start, -1), 1
            end = month_start - timedelta(days=1)
        case "last_quarter":
            start, unit = add_months(quarter_start, -3), 3
            end = quarter_start - timedelta(days=1)
        case "last_year":
            start, unit = date(today.year - 1, 1, 1), 12
            end = date(today.year - 1, 12, 31)
        case "last_12_months":
            start, unit = add_months(month_start, -12), 12
            end = month_start - timedelta(days=1)
        case "all_time":
            start = min(first_day or today, today)
            return Period(start, today, "All time", partial=False, all_time=True)
    return Period(start, end, range_label(start, end), partial=False, unit_months=unit)


def resolve_comparison(period: Period, kind: ComparisonKind) -> Comparison | None:
    """The earlier period to compare with, or None without a comparison."""
    if kind == "none":
        return None
    if period.all_time:
        raise refusal(
            "all_time has no earlier period to compare with. Choose another period, or leave "
            "compare_to out.",
            "comparison_not_accepted",
        )
    if kind == "same_period_last_year":
        start, end = add_months(period.start, -12), add_months(period.end, -12)
    elif period.unit_months is not None:
        # The previous calendar unit. A partial one is cut at the same point in its unit, so
        # this quarter until 19 Sep compares with 1 Apr to 19 Jun.
        start = add_months(period.start, -period.unit_months)
        if period.partial:
            end = add_months(period.end, -period.unit_months)
        else:
            end = period.start - timedelta(days=1)
    else:
        end = period.start - timedelta(days=1)
        start = end - (period.end - period.start)
    return Comparison(kind, start, end, range_label(start, end))


def buckets(grouping: Grouping, start: date, end: date) -> list[str]:
    """Every time bucket of the days start to end, in time order: months as "2026-07", years
    as "2026", and weekdays as "1" (Monday) to "7" (Sunday).
    """
    if grouping == "year":
        return [str(year) for year in range(start.year, end.year + 1)]
    if grouping == "weekday":
        days = min(7, (end - start).days + 1)
        return sorted(str((start + timedelta(days=n)).isoweekday()) for n in range(days))
    keys, month = [], start.replace(day=1)
    while month <= end:
        keys.append(f"{month.year}-{month.month:02d}")
        month = add_months(month, 1)
    return keys


def bucket_label(grouping: Grouping, key: str) -> str:
    """The month "2026-07" is Jul 2026 and the weekday "1" is Monday; a year is its own label."""
    if grouping == "month":
        return format_month(date(int(key[:4]), int(key[5:]), 1))
    if grouping == "weekday":
        return WEEKDAYS[int(key) - 1]
    return key
