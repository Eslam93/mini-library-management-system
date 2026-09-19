"""The metric engine's parts that need no database: the typed query, the rules for what each
metric accepts, and periods and comparisons against a fixed today.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationFailedError
from app.services.metrics import (
    CATALOGUE,
    MetricQuery,
    PeriodSpec,
    resolve_comparison,
    resolve_period,
    round_one,
)
from app.services.metrics.catalogue import check_query

TODAY = date(2026, 9, 19)


def period(preset: str | None = None, today: date = TODAY, **dates: str):
    spec = PeriodSpec.model_validate({"preset": preset} if preset else dates)
    return resolve_period(spec, today=today, first_day=date(2023, 9, 25))


def span(resolved) -> tuple[str, str]:
    return resolved.start.isoformat(), resolved.end.isoformat()


def refused(**query) -> ValidationFailedError:
    parsed = MetricQuery.model_validate(query)
    with pytest.raises(ValidationFailedError) as caught:
        check_query(CATALOGUE[parsed.metric], parsed)
    return caught.value


# Periods


@pytest.mark.parametrize(
    ("preset", "start", "end", "label", "partial"),
    [
        ("last_30_days", "2026-08-21", "2026-09-19", "Last 30 days", False),
        ("last_90_days", "2026-06-22", "2026-09-19", "Last 90 days", False),
        ("this_month", "2026-09-01", "2026-09-19", "Sep 2026 so far", True),
        ("this_quarter", "2026-07-01", "2026-09-19", "Q3 2026 so far", True),
        ("this_year", "2026-01-01", "2026-09-19", "2026 so far", True),
        ("last_month", "2026-08-01", "2026-08-31", "Aug 2026", False),
        ("last_quarter", "2026-04-01", "2026-06-30", "Q2 2026", False),
        ("last_year", "2025-01-01", "2025-12-31", "2025", False),
        ("last_12_months", "2025-09-01", "2026-08-31", "Sep 2025 to Aug 2026", False),
        ("all_time", "2023-09-25", "2026-09-19", "All time", False),
    ],
)
def test_every_preset_resolves_against_today(preset, start, end, label, partial):
    resolved = period(preset)

    assert span(resolved) == (start, end)
    assert (resolved.label, resolved.partial) == (label, partial)


def test_presets_at_the_turn_of_a_year():
    new_year = date(2026, 1, 1)

    assert span(period("last_month", new_year)) == ("2025-12-01", "2025-12-31")
    assert span(period("last_quarter", new_year)) == ("2025-10-01", "2025-12-31")
    assert span(period("last_12_months", new_year)) == ("2025-01-01", "2025-12-31")
    assert period("last_12_months", new_year).label == "2025"
    assert span(period("this_quarter", new_year)) == ("2026-01-01", "2026-01-01")


def test_all_time_without_data_is_today():
    spec = PeriodSpec.model_validate({"preset": "all_time"})

    assert span(resolve_period(spec, today=TODAY)) == ("2026-09-19", "2026-09-19")


def test_explicit_dates_are_labelled_by_name_or_by_days():
    assert period(**{"from": "2026-03-05", "to": "2026-04-10"}).label == (
        "5 Mar 2026 to 10 Apr 2026"
    )
    assert period(**{"from": "2026-04-01", "to": "2026-06-30"}).label == "Q2 2026"
    assert period(**{"from": "2026-09-01", "to": "2026-09-19"}).partial is False


def test_explicit_dates_must_be_in_order_and_not_after_today():
    for dates, message in (
        ({"from": "2026-05-02", "to": "2026-05-01"}, "from date is after its to date"),
        ({"from": "2026-09-01", "to": "2026-09-20"}, "cannot end after today, 19 Sep 2026"),
    ):
        with pytest.raises(ValidationFailedError, match=message) as caught:
            period(**dates)
        assert caught.value.code == "invalid_period"


# Comparisons


def compared(resolved, kind: str) -> tuple[str, str, str]:
    comparison = resolve_comparison(resolved, kind)
    assert comparison is not None
    assert comparison.kind == kind
    return comparison.start.isoformat(), comparison.end.isoformat(), comparison.label


def test_a_partial_quarter_compares_with_the_previous_quarter_cut_at_the_same_point():
    assert compared(period("this_quarter"), "previous_period") == (
        "2026-04-01",
        "2026-06-19",
        "1 Apr 2026 to 19 Jun 2026",
    )


@pytest.mark.parametrize(
    ("preset", "start", "end", "label"),
    [
        ("this_month", "2026-08-01", "2026-08-19", "1 Aug 2026 to 19 Aug 2026"),
        ("this_year", "2025-01-01", "2025-09-19", "1 Jan 2025 to 19 Sep 2025"),
        ("last_month", "2026-07-01", "2026-07-31", "Jul 2026"),
        ("last_quarter", "2026-01-01", "2026-03-31", "Q1 2026"),
        ("last_year", "2024-01-01", "2024-12-31", "2024"),
        ("last_12_months", "2024-09-01", "2025-08-31", "Sep 2024 to Aug 2025"),
        ("last_30_days", "2026-07-22", "2026-08-20", "22 Jul 2026 to 20 Aug 2026"),
        ("last_90_days", "2026-03-24", "2026-06-21", "24 Mar 2026 to 21 Jun 2026"),
    ],
)
def test_the_previous_period_of_each_preset(preset, start, end, label):
    assert compared(period(preset), "previous_period") == (start, end, label)


def test_explicit_dates_compare_with_as_many_days_just_before():
    # Thirty-seven days, 5 Mar to 10 Apr, against the thirty-seven days before 5 Mar.
    resolved = period(**{"from": "2026-03-05", "to": "2026-04-10"})

    assert compared(resolved, "previous_period")[:2] == ("2026-01-27", "2026-03-04")


def test_the_same_period_last_year_moves_both_dates_one_year():
    assert compared(period("this_quarter"), "same_period_last_year") == (
        "2025-07-01",
        "2025-09-19",
        "1 Jul 2025 to 19 Sep 2025",
    )
    assert compared(period("last_30_days"), "same_period_last_year")[:2] == (
        "2025-08-21",
        "2025-09-19",
    )


def test_the_29th_of_february_becomes_the_28th():
    leap_day = date(2028, 2, 29)

    assert compared(period("this_year", leap_day), "same_period_last_year")[:2] == (
        "2027-01-01",
        "2027-02-28",
    )
    assert compared(period("this_month", leap_day), "previous_period")[:2] == (
        "2028-01-01",
        "2028-01-29",
    )
    # The end of a longer month is cut to the end of the shorter one before it.
    assert compared(period("this_month", date(2028, 3, 31)), "previous_period")[:2] == (
        "2028-02-01",
        "2028-02-29",
    )


def test_no_comparison_and_all_time_has_none_to_compare_with():
    assert resolve_comparison(period("this_year"), "none") is None
    with pytest.raises(ValidationFailedError, match="all_time has no earlier period") as caught:
        resolve_comparison(period("all_time"), "previous_period")
    assert caught.value.code == "comparison_not_accepted"


# The typed query


@pytest.mark.parametrize(
    "query",
    [
        {"metric": "loans", "sql": "SELECT 1"},
        {"metric": "loans", "filters": {"member_id": "someone"}},
        {"metric": "loans", "period": {"preset": "this_year", "days": 3}},
        {"metric": "loans", "filters": {"member_joined_year": {"from": 2026, "to": 2026, "x": 1}}},
    ],
)
def test_unknown_fields_are_refused_at_every_level(query):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MetricQuery.model_validate(query)


@pytest.mark.parametrize(
    ("query", "problem"),
    [
        ({"metric": "visits"}, "Input should be"),
        ({"metric": "loans", "limit": 0}, "greater than or equal to 1"),
        ({"metric": "loans", "limit": 51}, "less than or equal to 50"),
        ({"metric": "loans", "period": {}}, "Give a preset, or both from and to"),
        ({"metric": "loans", "period": {"from": "2026-01-01"}}, "both from and to"),
        (
            {"metric": "loans", "period": {"preset": "this_year", "to": "2026-01-01"}},
            "not both",
        ),
        (
            {"metric": "loans", "filters": {"member_joined_year": {"from": 2026, "to": 2025}}},
            "from must not be after to",
        ),
        ({"metric": "loans", "filters": {"categories": []}}, "at least 1 item"),
    ],
)
def test_malformed_queries_are_refused(query, problem):
    with pytest.raises(ValidationError, match=problem):
        MetricQuery.model_validate(query)


def test_a_query_takes_from_as_the_name_of_its_first_day():
    query = MetricQuery.model_validate(
        {
            "metric": "loans",
            "period": {"from": "2026-01-01", "to": "2026-03-31"},
            "filters": {"member_joined_year": {"from": 2025, "to": 2026}},
        }
    )

    assert query.period is not None
    assert query.period.from_ == date(2026, 1, 1)
    assert query.filters.used() == ["member_joined_year"]
    assert (query.group_by, query.compare_to, query.sort, query.limit) == (
        "none",
        "none",
        None,
        None,
    )


# What each metric accepts


def test_a_grouping_the_metric_does_not_accept_lists_what_it_accepts():
    error = refused(metric="active_loans", group_by="month")

    assert error.code == "grouping_not_accepted"
    assert error.message == (
        "active_loans cannot be grouped by month. It accepts group_by: none, category, book, "
        "author, member_joined_year."
    )
    assert refused(metric="new_members", group_by="category").code == "grouping_not_accepted"
    assert refused(metric="titles_not_borrowed", group_by="weekday").code == (
        "grouping_not_accepted"
    )
    assert refused(metric="copies_on_loan_share", group_by="book").code == "grouping_not_accepted"


def test_a_filter_the_metric_does_not_accept_lists_what_it_accepts():
    joined = {"member_joined_year": {"from": 2026, "to": 2026}}

    none_taken = refused(metric="new_members", filters={"categories": ["Fiction"]})
    books_only = refused(metric="titles_not_borrowed", filters=joined)

    assert none_taken.code == books_only.code == "filter_not_accepted"
    assert (
        none_taken.message == "new_members cannot be filtered by categories. It takes no filters."
    )
    assert books_only.message == (
        "titles_not_borrowed cannot be filtered by member_joined_year. It accepts filters: "
        "categories, author."
    )
    assert refused(metric="copies_on_loan_share", filters=joined).code == "filter_not_accepted"


@pytest.mark.parametrize(
    "extra", [{"period": {"preset": "this_year"}}, {"compare_to": "previous_period"}]
)
@pytest.mark.parametrize("metric", ["active_loans", "overdue_loans", "copies_on_loan_share"])
def test_a_metric_measured_now_takes_no_period_or_comparison(metric, extra):
    error = refused(metric=metric, **extra)

    assert error.code == "measured_now"
    assert error.message.startswith(f"{metric} is measured now")


def test_accepted_combinations_pass():
    for query in (
        {"metric": "loans", "group_by": "weekday", "filters": {"author": "Frank Herbert"}},
        {"metric": "active_loans", "group_by": "member_joined_year"},
        {"metric": "new_members", "group_by": "month", "compare_to": "same_period_last_year"},
        {"metric": "titles_not_borrowed", "group_by": "book", "filters": {"categories": ["A"]}},
    ):
        parsed = MetricQuery.model_validate(query)
        check_query(CATALOGUE[parsed.metric], parsed)


def test_figures_round_to_one_decimal_with_halves_away_from_zero():
    assert [round_one(value) for value in (37.25, 37.24, -3.05, 100 / 3, 2 / 3 * 100)] == [
        37.3,
        37.2,
        -3.1,
        33.3,
        66.7,
    ]
