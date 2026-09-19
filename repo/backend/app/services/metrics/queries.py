"""The statements behind the metrics, and a query's result.

Each metric has one fixed statement. A grouping is a key and a label from a fixed map of column
expressions, and a filter is a condition from another; the values a query brings reach the
database only as bound parameters.
"""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import (
    ColumnElement,
    DateTime,
    FromClause,
    Select,
    Text,
    and_,
    cast,
    distinct,
    extract,
    func,
    null,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Book, Copy, Loan, Member
from app.services.circulation import is_overdue
from app.services.metrics.catalogue import (
    CATALOGUE,
    DEFAULT_PRESET,
    DEFAULT_ROWS,
    MAX_ROWS,
    TIME_GROUPINGS,
    UNCATEGORISED,
    Grouping,
    Metric,
    MetricFilters,
    MetricQuery,
    PeriodSpec,
    SortOrder,
    check_query,
    refusal,
)
from app.services.metrics.periods import (
    Comparison,
    Period,
    bucket_label,
    buckets,
    resolve_comparison,
    resolve_period,
)

Value = int | float
Span = tuple[date, date]

_TENTH = Decimal("0.1")
_SECONDS_PER_DAY = 86400
_CATEGORY = func.coalesce(Book.category, UNCATEGORISED)
# A day as a timestamp without a time zone, so formatting it never depends on the connection.
_JOINED_ON = cast(Member.joined_on, DateTime())


# The statements


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _within(moment: Any, span: Span) -> ColumnElement[bool]:
    start, end = span
    return and_(moment >= _day_start(start), moment < _day_start(end + timedelta(days=1)))


def _group_columns(grouping: Grouping, event: Any) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    """A grouping's key and label. event is the UTC time (or day) that places a row in time."""
    if grouping == "category":
        return _CATEGORY, _CATEGORY
    if grouping == "author":
        return Book.author.expression, Book.author.expression
    if grouping == "book":
        return cast(Book.id, Text), func.concat(Book.title, " by ", Book.author)
    # Time buckets and joining years: the label is made from the key afterwards.
    formats = {"month": "YYYY-MM", "year": "YYYY", "weekday": "ID"}
    key = (
        func.to_char(_JOINED_ON, "YYYY")
        if grouping == "member_joined_year"
        else func.to_char(event, formats[grouping])
    )
    return key, key


def _filter_conditions(filters: MetricFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.categories is not None:
        names = [name.lower() for name in filters.categories]
        conditions.append(func.lower(_CATEGORY).in_(names))
    if filters.author is not None:
        conditions.append(func.lower(Book.author) == filters.author.strip().lower())
    if filters.book_id is not None:
        conditions.append(Book.id == filters.book_id)
    if filters.member_joined_year is not None:
        years = filters.member_joined_year
        conditions.append(extract("year", Member.joined_on).between(years.from_, years.to))
    return conditions


@dataclass(frozen=True)
class _Source:
    """What a metric counts: the rows it reads, which of them are in scope, the moment that
    places a row in time, and how the rows add up (the denominator is null for counts).
    """

    rows: FromClause | type[Any]
    conditions: list[ColumnElement[bool]]
    event: Any
    numerator: ColumnElement[Any]
    denominator: ColumnElement[Any]


def _loan_rows() -> FromClause:
    return (
        Loan.__table__.join(Copy, Copy.id == Loan.copy_id)
        .join(Book, Book.id == Copy.book_id)
        .join(Member, Member.id == Loan.member_id)
    )


def _source(metric: Metric, span: Span | None) -> _Source:
    name, count = metric.name, func.count()
    if name == "active_loans":
        return _Source(_loan_rows(), [Loan.returned_at.is_(None)], None, count, null())
    if name == "overdue_loans":
        return _Source(_loan_rows(), [is_overdue()], None, count, null())
    if name == "copies_on_loan_share":
        # A copy has at most one active loan, so the joined loans count the copies on loan.
        rows = Copy.__table__.join(Book, Book.id == Copy.book_id).outerjoin(
            Loan, and_(Loan.copy_id == Copy.id, Loan.returned_at.is_(None))
        )
        in_circulation: list[ColumnElement[bool]] = [
            Copy.archived_at.is_(None),
            Book.archived_at.is_(None),
        ]
        return _Source(rows, in_circulation, None, func.count(Loan.id), count)

    if span is None:
        raise ValueError(f"{name} is measured over a period")
    if name == "new_members":
        start, end = span
        return _Source(Member, [Member.joined_on.between(start, end)], _JOINED_ON, count, null())
    if name == "titles_not_borrowed":
        borrowed = (
            select(Loan.id)
            .join(Copy, Copy.id == Loan.copy_id)
            .where(Copy.book_id == Book.id, _within(Loan.borrowed_at, span))
            .exists()
        )
        # A book added after the period could not have been borrowed in it.
        added_by_then = Book.created_at < _day_start(span[1] + timedelta(days=1))
        conditions = [Book.archived_at.is_(None), added_by_then, ~borrowed]
        return _Source(Book, conditions, None, count, null())

    # Loans started in the period, or returned in it.
    moment = Loan.borrowed_at if name in ("loans", "unique_borrowers") else Loan.returned_at
    event = func.timezone("UTC", moment)
    numerator: ColumnElement[Any] = count
    denominator: ColumnElement[Any] = null()
    if name == "unique_borrowers":
        numerator = func.count(distinct(Loan.member_id))
    elif name == "late_return_rate":
        numerator, denominator = count.filter(Loan.returned_at > Loan.due_at), func.count()
    elif name == "average_loan_days":
        duration = extract("epoch", Loan.returned_at - Loan.borrowed_at)
        numerator, denominator = func.sum(duration), func.count()
    return _Source(_loan_rows(), [_within(moment, span)], event, numerator, denominator)


def statement(
    metric: Metric, grouping: Grouping, filters: MetricFilters, span: Span | None
) -> Select[Any]:
    """The metric's statement: a numerator and a denominator per group, or one row without a
    grouping.
    """
    source = _source(metric, span)
    conditions = [*source.conditions, *_filter_conditions(filters)]
    measures = (source.numerator.label("numerator"), source.denominator.label("denominator"))
    if grouping == "none":
        return select(*measures).select_from(source.rows).where(*conditions)
    key, label = _group_columns(grouping, source.event)
    # Grouped by the output names, so an expression holding a bound value matches itself.
    return (
        select(key.label("group_key"), label.label("group_label"), *measures)
        .select_from(source.rows)
        .where(*conditions)
        .group_by("group_key", "group_label")
    )


# Results


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    value: Value | None
    share_pct: float | None = None
    previous_value: Value | None = None
    previous_share_pct: float | None = None
    change: Value | None = None
    change_pct: float | None = None


@dataclass(frozen=True)
class Total:
    value: Value | None
    previous_value: Value | None = None
    change: Value | None = None
    change_pct: float | None = None


@dataclass(frozen=True)
class MetricResult:
    metric: Metric
    period: Period | None
    comparison: Comparison | None
    group_by: Grouping
    sort: SortOrder
    rows: list[Row]
    # The number of groups before the limit.
    rows_total: int
    total: Total
    # The filters in words, such as "category: Technology" or "members who joined in 2026".
    scope: list[str]


def round_one(value: float) -> float:
    """Rounded to one decimal with halves away from zero, as people round by hand."""
    return float(Decimal(repr(float(value))).quantize(_TENTH, rounding=ROUND_HALF_UP))


def _value(metric: Metric, numerator: Any, denominator: Any) -> Value | None:
    if metric.unit == "count":
        return int(numerator or 0)
    if not denominator:
        return None
    if metric.unit == "percent":
        return round_one(100 * float(numerator) / denominator)
    return round_one(float(numerator) / denominator / _SECONDS_PER_DAY)


def _empty(metric: Metric) -> Value | None:
    """The value of a group with nothing in it: zero for counts, none for rates and averages."""
    return 0 if metric.unit == "count" else None


def _share(value: Value | None, total: Value | None) -> float | None:
    if value is None or not total:
        return None
    return round_one(100 * value / total)


def _change(metric: Metric, value: Value | None, previous: Value | None) -> Value | None:
    """The current value less the previous one, from the rounded values the result shows, so
    the three figures agree. For a percentage metric it is in percentage points.
    """
    if value is None or previous is None:
        return None
    if metric.unit == "count":
        return int(value) - int(previous)
    return round_one(value - previous)


def _change_pct(metric: Metric, value: Value | None, previous: Value | None) -> float | None:
    """The relative change. None for percentage metrics, and when there is nothing before."""
    if metric.unit == "percent" or value is None or not previous:
        return None
    return round_one(100 * (value - previous) / previous)


Groups = dict[str, tuple[str, Value | None]]


async def _measure(
    session: AsyncSession,
    metric: Metric,
    grouping: Grouping,
    filters: MetricFilters,
    span: Span | None,
) -> tuple[Groups, Value | None]:
    """The metric per group, and over the whole scope: never the sum of the groups."""
    total_row = (await session.execute(statement(metric, "none", filters, span))).one()
    total = _value(metric, total_row.numerator, total_row.denominator)
    groups: Groups = {}
    if grouping != "none":
        rows = await session.execute(statement(metric, grouping, filters, span))
        for row in rows:
            value = _value(metric, row.numerator, row.denominator)
            groups[row.group_key] = (row.group_label, value)
    if grouping in TIME_GROUPINGS and span is not None:
        # Every bucket of the period, the empty ones too.
        return {
            key: (bucket_label(grouping, key), groups.get(key, (key, _empty(metric)))[1])
            for key in buckets(grouping, *span)
        }, total
    return groups, total


def _sorted(rows: list[Row], order: SortOrder, grouping: Grouping) -> list[Row]:
    by_label = sorted(rows, key=lambda row: (row.label.casefold(), row.key))
    if order == "key":
        return sorted(rows, key=lambda row: row.key) if grouping in TIME_GROUPINGS else by_label
    # Rows without a value go last either way; ties keep the alphabetical order.
    valued = [row for row in by_label if row.value is not None]
    valued.sort(key=lambda row: row.value or 0, reverse=order == "value_desc")
    return valued + [row for row in by_label if row.value is None]


def _earlier_groups(grouping: Grouping, current: Groups, earlier: Groups) -> Groups:
    """The earlier period's group for each key. Months and years line up by position, the
    first with the first, because the two periods cover different calendar dates.
    """
    if grouping in ("month", "year"):
        return {key: group for key, group in zip(current, earlier.values(), strict=False)}
    return earlier


def _compared(metric: Metric, row: Row, earlier: Groups, earlier_total: Value | None) -> Row:
    before = earlier.get(row.key, (row.label, _empty(metric)))[1]
    return replace(
        row,
        previous_value=before,
        previous_share_pct=_share(before, earlier_total) if metric.shares else None,
        change=_change(metric, row.value, before),
        change_pct=_change_pct(metric, row.value, before),
    )


async def describe_filters(session: AsyncSession, filters: MetricFilters) -> list[str]:
    """Checks that the filters name things that exist, so a misspelt name is not read as a
    zero, and puts them in words.
    """
    scope = []
    if filters.categories is not None:
        known = set(await session.scalars(select(distinct(_CATEGORY)).select_from(Book)))
        by_lower = {name.lower(): name for name in known}
        unknown = [name for name in filters.categories if name.lower() not in by_lower]
        if unknown:
            raise refusal(
                f"No category is named {', '.join(unknown)}. The categories are: "
                f"{', '.join(sorted(known))}.",
                "unknown_category",
            )
        names = [by_lower[name.lower()] for name in filters.categories]
        noun = "category" if len(names) == 1 else "categories"
        scope.append(f"{noun}: {', '.join(names)}")
    if filters.author is not None:
        author = await session.scalar(
            select(Book.author)
            .where(func.lower(Book.author) == filters.author.strip().lower())
            .limit(1)
        )
        if author is None:
            raise refusal(
                f"No book in the catalog is by {filters.author}. Give the author's name exactly "
                "as the results give it.",
                "unknown_author",
            )
        scope.append(f"by {author}")
    if filters.book_id is not None:
        title = await session.scalar(select(Book.title).where(Book.id == filters.book_id))
        if title is None:
            raise NotFoundError("Book not found.")
        scope.append(f"book: {title}")
    if filters.member_joined_year is not None:
        years = filters.member_joined_year
        joined = str(years.from_) if years.from_ == years.to else f"{years.from_} to {years.to}"
        scope.append(f"members who joined in {joined}")
    return scope


async def _first_day(session: AsyncSession, metric: Metric) -> date | None:
    """Where all_time starts: the first member's joining day, or the first loan's day."""
    if metric.name == "new_members":
        joined: date | None = await session.scalar(select(func.min(Member.joined_on)))
        return joined
    first: datetime | None = await session.scalar(select(func.min(Loan.borrowed_at)))
    return first.astimezone(UTC).date() if first is not None else None


async def first_event_day(
    session: AsyncSession, metric: Metric, filters: MetricFilters
) -> date | None:
    """The UTC day of the first loan, return or joining in the filtered scope, or None when
    there is none. Members joining take no filters.
    """
    if metric.name == "new_members":
        joined: date | None = await session.scalar(select(func.min(Member.joined_on)))
        return joined
    moment = Loan.returned_at if metric.name == "returns" else Loan.borrowed_at
    first: datetime | None = await session.scalar(
        select(func.min(moment)).select_from(_loan_rows()).where(*_filter_conditions(filters))
    )
    return first.astimezone(UTC).date() if first is not None else None


async def run_query(session: AsyncSession, query: MetricQuery, *, today: date) -> MetricResult:
    """Runs one metric query. A combination the metric does not accept is refused with a
    ValidationFailedError whose message lists what it accepts; a book that does not exist is a
    NotFoundError.
    """
    metric = CATALOGUE[query.metric]
    check_query(metric, query)
    period = comparison = None
    if metric.measured == "period":
        spec = query.period or PeriodSpec(preset=DEFAULT_PRESET)
        first_day = await _first_day(session, metric) if spec.preset == "all_time" else None
        period = resolve_period(spec, today=today, first_day=first_day)
        comparison = resolve_comparison(period, query.compare_to)
    scope = await describe_filters(session, query.filters)

    grouping, filters = query.group_by, query.filters
    span = (period.start, period.end) if period is not None else None
    groups, value = await _measure(session, metric, grouping, filters, span)
    rows = [Row(key, label, row_value) for key, (label, row_value) in groups.items()]
    earlier: Groups = {}
    before: Value | None = None
    if comparison is not None:
        earlier_span = (comparison.start, comparison.end)
        earlier, before = await _measure(session, metric, grouping, filters, earlier_span)
        earlier = _earlier_groups(grouping, groups, earlier)
        # A group seen only in the earlier period is a row too, with nothing in it now.
        rows += [
            Row(key, label, _empty(metric))
            for key, (label, _) in earlier.items()
            if key not in groups
        ]
    if metric.shares:
        rows = [replace(row, share_pct=_share(row.value, value)) for row in rows]
    total = Total(value)
    if comparison is not None:
        rows = [_compared(metric, row, earlier, before) for row in rows]
        total = Total(
            value, before, _change(metric, value, before), _change_pct(metric, value, before)
        )

    time_grouping = grouping in TIME_GROUPINGS
    sort = query.sort or ("key" if time_grouping else "value_desc")
    limit = query.limit or (MAX_ROWS if time_grouping else DEFAULT_ROWS)
    ordered = _sorted(rows, sort, grouping)
    return MetricResult(
        metric, period, comparison, grouping, sort, ordered[:limit], len(ordered), total, scope
    )
