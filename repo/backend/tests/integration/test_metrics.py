"""The metric engine against a small library built for the test, with exact expected figures.

Today is fixed at 19 Sep 2026 for the periods. The loans (borrowed, due, returned, all UTC):

| Loan | Book, copy | Member | Borrowed | Due | Returned |
|---|---|---|---|---|---|
| L1 | Dune, copy 1 | Maya | 3 Jul 2026 10:00 | 17 Jul | 20 Jul 12:00, late |
| L2 | Clean Code | Omar | 10 Jul 2026 09:00 | 24 Jul | 15 Jul 09:00 |
| L3 | Clean Code | Lina | 1 Aug 2026 12:00 | 15 Aug | 11 Aug 12:00 |
| L4 | Emma (no category) | Maya | 5 Sep 2026 15:00 | 2099 | active |
| L5 | Dune, copy 2 | Lina | 20 Aug 2026 11:00 | 3 Sep | active, overdue |
| L6 | Old Atlas (archived) | Omar | 15 Apr 2026 10:00 | 29 Apr | 5 May 10:00, late |
| L7 | Dune, copy 1 | Omar | 2 May 2026 10:00 | 16 May | 12 May 10:00 |
| L8 | Clean Code | Maya | 25 Jun 2026 10:00 | 9 Jul | 28 Jun 10:00 |
| L9 | Dune, copy 1 | Maya | 7 Jul 2025 10:00 | 21 Jul | 14 Jul 10:00 |

Maya joined in 2024, Omar in Nov 2025, Lina in Feb 2026 and Sami (no loans) in Aug 2026.
Children of Dune has one copy and was never borrowed. Every book was added on 2 Jan 2024.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.models import Book, Copy, Loan, Member
from app.services.metrics import MetricQuery, run_query

pytestmark = pytest.mark.integration

TODAY = date(2026, 9, 19)
THIS_QUARTER = {"preset": "this_quarter"}


def at(day: str, hour: int = 10) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(hour, tzinfo=UTC))


def end_of(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(23, 59, 59, tzinfo=UTC))


@pytest.fixture
async def library(empty_db: AsyncSession) -> dict[str, uuid.UUID]:
    session = empty_db
    archived = at("2026-06-01")
    books = {
        "dune": Book(title="Dune", author="Frank Herbert", category="Science Fiction"),
        "clean": Book(title="Clean Code", author="Robert C. Martin", category="Technology"),
        "emma": Book(title="Emma", author="Jane Austen", category=None),
        "atlas": Book(
            title="Old Atlas", author="Ann Mapper", category="Technology", archived_at=archived
        ),
        "children": Book(
            title="Children of Dune", author="Frank Herbert", category="Science Fiction"
        ),
    }
    for book in books.values():
        book.created_at = at("2024-01-02")
    session.add_all(books.values())
    await session.flush()
    copies = {
        "dune1": Copy(book_id=books["dune"].id, code="CP-9001"),
        "dune2": Copy(book_id=books["dune"].id, code="CP-9002"),
        "clean": Copy(book_id=books["clean"].id, code="CP-9003"),
        "emma": Copy(book_id=books["emma"].id, code="CP-9004"),
        "atlas": Copy(book_id=books["atlas"].id, code="CP-9005", archived_at=archived),
        "children": Copy(book_id=books["children"].id, code="CP-9006"),
    }
    members = {
        "maya": Member(full_name="Maya Hassan", joined_on=date(2024, 3, 10)),
        "omar": Member(full_name="Omar Farouk", joined_on=date(2025, 11, 2)),
        "lina": Member(full_name="Lina Saad", joined_on=date(2026, 2, 14)),
        "sami": Member(full_name="Sami Nour", joined_on=date(2026, 8, 20)),
    }
    session.add_all([*copies.values(), *members.values()])
    await session.flush()
    loans = [
        ("dune1", "maya", at("2026-07-03"), end_of("2026-07-17"), at("2026-07-20", 12)),
        ("clean", "omar", at("2026-07-10", 9), end_of("2026-07-24"), at("2026-07-15", 9)),
        ("clean", "lina", at("2026-08-01", 12), end_of("2026-08-15"), at("2026-08-11", 12)),
        ("emma", "maya", at("2026-09-05", 15), end_of("2099-01-01"), None),
        ("dune2", "lina", at("2026-08-20", 11), end_of("2026-09-03"), None),
        ("atlas", "omar", at("2026-04-15"), end_of("2026-04-29"), at("2026-05-05")),
        ("dune1", "omar", at("2026-05-02"), end_of("2026-05-16"), at("2026-05-12")),
        ("clean", "maya", at("2026-06-25"), end_of("2026-07-09"), at("2026-06-28")),
        ("dune1", "maya", at("2025-07-07"), end_of("2025-07-21"), at("2025-07-14")),
    ]
    session.add_all(
        Loan(
            copy_id=copies[copy].id,
            member_id=members[member].id,
            borrowed_at=borrowed,
            due_at=due,
            returned_at=returned,
        )
        for copy, member, borrowed, due, returned in loans
    )
    await session.commit()
    return {name: book.id for name, book in books.items()}


async def run(session: AsyncSession, **query):
    return await run_query(session, MetricQuery.model_validate(query), today=TODAY)


def rows(result) -> list[tuple]:
    return [(row.label, row.value) for row in result.rows]


def figures(result, *fields: str) -> list[tuple]:
    return [tuple(getattr(row, name) for name in ("label", *fields)) for row in result.rows]


# Loans, groupings and totals


async def test_loans_this_quarter_by_category_with_shares(library, empty_db):
    result = await run(empty_db, metric="loans", group_by="category", period=THIS_QUARTER)

    assert (result.period.label, result.period.partial) == ("Q3 2026 so far", True)
    assert figures(result, "value", "share_pct") == [
        ("Science Fiction", 2, 40.0),
        ("Technology", 2, 40.0),
        ("Uncategorised", 1, 20.0),
    ]
    assert (result.total.value, result.rows_total, result.sort) == (5, 3, "value_desc")
    assert result.comparison is None


async def test_compared_with_the_previous_period_cut_at_the_same_point(library, empty_db):
    result = await run(
        empty_db,
        metric="loans",
        group_by="category",
        period=THIS_QUARTER,
        compare_to="previous_period",
    )

    # 1 Apr to 19 Jun holds L6 (an archived book, still counted) and L7, not L8 on 25 Jun.
    assert (result.comparison.start, result.comparison.end) == (date(2026, 4, 1), date(2026, 6, 19))
    assert figures(
        result, "value", "share_pct", "previous_value", "previous_share_pct", "change", "change_pct"
    ) == [
        ("Science Fiction", 2, 40.0, 1, 50.0, 1, 100.0),
        ("Technology", 2, 40.0, 1, 50.0, 1, 100.0),
        ("Uncategorised", 1, 20.0, 0, 0.0, 1, None),
    ]
    assert asdict(result.total) == {
        "value": 5,
        "previous_value": 2,
        "change": 3,
        "change_pct": 150.0,
    }


async def test_a_follow_up_filter_on_the_year_members_joined(library, empty_db):
    result = await run(
        empty_db,
        metric="loans",
        group_by="category",
        period=THIS_QUARTER,
        compare_to="previous_period",
        filters={"member_joined_year": {"from": 2026, "to": 2026}},
    )

    # Only Lina joined in 2026: L3 and L5 this quarter, nothing before.
    assert figures(result, "value", "share_pct", "previous_value", "change_pct") == [
        ("Science Fiction", 1, 50.0, 0, None),
        ("Technology", 1, 50.0, 0, None),
    ]
    assert (result.total.value, result.total.previous_value) == (2, 0)
    assert result.scope == ["members who joined in 2026"]


async def test_the_same_period_last_year(library, empty_db):
    result = await run(
        empty_db,
        metric="loans",
        group_by="category",
        period=THIS_QUARTER,
        compare_to="same_period_last_year",
    )

    assert figures(result, "value", "previous_value", "change", "change_pct") == [
        ("Science Fiction", 2, 1, 1, 100.0),
        ("Technology", 2, 0, 2, None),
        ("Uncategorised", 1, 0, 1, None),
    ]
    assert (result.total.previous_value, result.total.change_pct) == (1, 400.0)


async def test_a_group_seen_only_in_the_earlier_period_is_a_row_with_nothing_now(library, empty_db):
    result = await run(
        empty_db,
        metric="loans",
        group_by="author",
        period=THIS_QUARTER,
        compare_to="previous_period",
    )

    # Ann Mapper's Old Atlas was borrowed in April (L6) and not since.
    assert figures(result, "value", "share_pct", "previous_value", "change", "change_pct") == [
        ("Frank Herbert", 2, 40.0, 1, 1, 100.0),
        ("Robert C. Martin", 2, 40.0, 0, 2, None),
        ("Jane Austen", 1, 20.0, 0, 1, None),
        ("Ann Mapper", 0, 0.0, 1, -1, -100.0),
    ]
    assert result.rows_total == 4


async def test_each_grouping_of_loans(library, empty_db):
    by = {}
    for grouping in ("book", "author", "member_joined_year", "weekday"):
        by[grouping] = await run(empty_db, metric="loans", group_by=grouping, period=THIS_QUARTER)

    assert rows(by["book"]) == [
        ("Clean Code by Robert C. Martin", 2),
        ("Dune by Frank Herbert", 2),
        ("Emma by Jane Austen", 1),
    ]
    assert [row.key for row in by["book"].rows] == [
        str(library["clean"]),
        str(library["dune"]),
        str(library["emma"]),
    ]
    assert rows(by["author"]) == [("Frank Herbert", 2), ("Robert C. Martin", 2), ("Jane Austen", 1)]
    assert rows(by["member_joined_year"]) == [("2024", 2), ("2026", 2), ("2025", 1)]
    # Every weekday is listed, in week order: two Fridays, two Saturdays and a Thursday.
    assert rows(by["weekday"]) == [
        ("Monday", 0),
        ("Tuesday", 0),
        ("Wednesday", 0),
        ("Thursday", 1),
        ("Friday", 2),
        ("Saturday", 2),
        ("Sunday", 0),
    ]
    assert by["weekday"].sort == "key"


async def test_empty_months_and_years_are_listed(library, empty_db):
    by_month = await run(empty_db, metric="loans", group_by="month", period={"preset": "this_year"})
    by_year = await run(empty_db, metric="loans", group_by="year", period={"preset": "all_time"})

    assert [(row.key, row.label, row.value) for row in by_month.rows] == [
        ("2026-01", "Jan 2026", 0),
        ("2026-02", "Feb 2026", 0),
        ("2026-03", "Mar 2026", 0),
        ("2026-04", "Apr 2026", 1),
        ("2026-05", "May 2026", 1),
        ("2026-06", "Jun 2026", 1),
        ("2026-07", "Jul 2026", 2),
        ("2026-08", "Aug 2026", 2),
        ("2026-09", "Sep 2026", 1),
    ]
    assert by_month.total.value == 8
    # all_time starts at the first loan, 7 Jul 2025.
    assert by_year.period.start == date(2025, 7, 7)
    assert rows(by_year) == [("2025", 1), ("2026", 8)]


async def test_months_compare_with_the_earlier_period_month_by_month(library, empty_db):
    result = await run(
        empty_db,
        metric="loans",
        group_by="month",
        period={"preset": "this_quarter"},
        compare_to="previous_period",
    )

    # Jul against Apr, Aug against May, and Sep so far against Jun until the 19th.
    assert figures(result, "value", "previous_value", "change") == [
        ("Jul 2026", 2, 1, 1),
        ("Aug 2026", 2, 1, 1),
        ("Sep 2026", 1, 0, 1),
    ]


async def test_sorting_and_the_limit(library, empty_db):
    ascending = await run(
        empty_db, metric="loans", group_by="category", period=THIS_QUARTER, sort="value_asc"
    )
    by_key = await run(
        empty_db, metric="loans", group_by="category", period=THIS_QUARTER, sort="key"
    )
    first = await run(empty_db, metric="loans", group_by="category", period=THIS_QUARTER, limit=1)

    assert rows(ascending) == [("Uncategorised", 1), ("Science Fiction", 2), ("Technology", 2)]
    assert [label for label, _ in rows(by_key)] == [
        "Science Fiction",
        "Technology",
        "Uncategorised",
    ]
    assert (rows(first), first.rows_total, first.total.value) == ([("Science Fiction", 2)], 3, 5)


async def test_filters_narrow_the_scope(library, empty_db):
    async def total(**filters) -> int:
        return (
            await run(empty_db, metric="loans", period=THIS_QUARTER, filters=filters)
        ).total.value

    assert await total(book_id=str(library["dune"])) == 2
    assert await total(author="robert c. martin") == 2
    assert await total(categories=["technology", "Uncategorised"]) == 3
    assert await total(member_joined_year={"from": 2024, "to": 2025}) == 3
    assert await total(categories=["Science Fiction"], author="Frank Herbert") == 2


async def test_the_default_period_is_the_last_twelve_months(library, empty_db):
    result = await run(empty_db, metric="loans")

    # 1 Sep 2025 to 31 Aug 2026: everything but L4 (September) and L9 (July 2025).
    assert (result.period.label, result.total.value, result.rows) == ("Sep 2025 to Aug 2026", 7, [])


# The other metrics


async def test_unique_borrowers_total_is_not_the_sum_of_its_rows(library, empty_db):
    result = await run(
        empty_db, metric="unique_borrowers", group_by="category", period=THIS_QUARTER
    )

    assert figures(result, "value", "share_pct") == [
        ("Science Fiction", 2, None),
        ("Technology", 2, None),
        ("Uncategorised", 1, None),
    ]
    assert result.total.value == 3


async def test_returns_count_by_the_day_they_came_back(library, empty_db):
    result = await run(empty_db, metric="returns", group_by="month", period=THIS_QUARTER)

    assert rows(result) == [("Jul 2026", 2), ("Aug 2026", 1), ("Sep 2026", 0)]
    assert [row.share_pct for row in result.rows] == [66.7, 33.3, 0.0]


async def test_late_return_rate_in_points_with_empty_months_as_no_figure(library, empty_db):
    compared = await run(
        empty_db,
        metric="late_return_rate",
        group_by="category",
        period=THIS_QUARTER,
        compare_to="previous_period",
    )
    by_month = await run(empty_db, metric="late_return_rate", group_by="month", period=THIS_QUARTER)

    # L1 of three returns came back late; before, L6 of two.
    assert asdict(compared.total) == {
        "value": 33.3,
        "previous_value": 50.0,
        "change": -16.7,
        "change_pct": None,
    }
    assert figures(compared, "value", "previous_value", "change", "change_pct") == [
        ("Science Fiction", 100.0, 0.0, 100.0, None),
        ("Technology", 0.0, 100.0, -100.0, None),
    ]
    assert rows(by_month) == [("Jul 2026", 50.0), ("Aug 2026", 0.0), ("Sep 2026", None)]


async def test_average_loan_days(library, empty_db):
    result = await run(
        empty_db, metric="average_loan_days", period=THIS_QUARTER, compare_to="previous_period"
    )

    # (17 days 2 hours + 5 days + 10 days) / 3 against (20 + 10) / 2.
    assert asdict(result.total) == {
        "value": 10.7,
        "previous_value": 15.0,
        "change": -4.3,
        "change_pct": -28.7,
    }


async def test_active_and_overdue_loans_now(library, empty_db):
    active = await run(empty_db, metric="active_loans", group_by="category")
    by_year = await run(empty_db, metric="active_loans", group_by="member_joined_year", sort="key")
    overdue = await run(empty_db, metric="overdue_loans", group_by="book")

    assert (active.period, active.comparison, active.total.value) == (None, None, 2)
    assert figures(active, "value", "share_pct") == [
        ("Science Fiction", 1, 50.0),
        ("Uncategorised", 1, 50.0),
    ]
    assert rows(by_year) == [("2024", 1), ("2026", 1)]
    assert figures(overdue, "key", "value", "share_pct") == [
        ("Dune by Frank Herbert", str(library["dune"]), 1, 100.0)
    ]


async def test_copies_on_loan_share_counts_copies_in_circulation(library, empty_db):
    result = await run(empty_db, metric="copies_on_loan_share", group_by="category")
    herbert = await run(
        empty_db, metric="copies_on_loan_share", filters={"author": "Frank Herbert"}
    )

    # Five copies in circulation (the archived one is not), two of them on loan.
    assert result.total.value == 40.0
    assert rows(result) == [
        ("Uncategorised", 100.0),
        ("Science Fiction", 33.3),
        ("Technology", 0.0),
    ]
    assert herbert.total.value == 33.3


async def test_new_members_by_month_and_year(library, empty_db):
    by_month = await run(
        empty_db, metric="new_members", group_by="month", period={"preset": "this_year"}
    )
    by_year = await run(
        empty_db, metric="new_members", group_by="year", period={"preset": "all_time"}
    )
    default = await run(empty_db, metric="new_members")

    assert [value for _, value in rows(by_month)] == [0, 1, 0, 0, 0, 0, 0, 1, 0]
    assert (by_month.rows[1].share_pct, by_month.total.value) == (50.0, 2)
    assert by_year.period.start == date(2024, 3, 10)
    assert figures(by_year, "value", "share_pct") == [
        ("2024", 1, 25.0),
        ("2025", 1, 25.0),
        ("2026", 2, 50.0),
    ]
    assert default.total.value == 3


async def test_titles_not_borrowed_lists_the_books(library, empty_db):
    quarter = await run(empty_db, metric="titles_not_borrowed", period=THIS_QUARTER)
    listed = await run(
        empty_db, metric="titles_not_borrowed", group_by="book", period={"preset": "last_quarter"}
    )
    science_fiction = await run(
        empty_db,
        metric="titles_not_borrowed",
        period={"preset": "last_quarter"},
        filters={"categories": ["Science Fiction"]},
    )

    # The archived Old Atlas is not in the catalog, so it is never listed.
    assert quarter.total.value == 1
    assert figures(listed, "value", "share_pct") == [
        ("Children of Dune by Frank Herbert", 1, 50.0),
        ("Emma by Jane Austen", 1, 50.0),
    ]
    assert science_fiction.total.value == 1


async def test_titles_not_borrowed_leaves_out_books_added_after_the_period(library, empty_db):
    empty_db.add_all(
        [
            # The last second of Q2, and the first of Q3.
            Book(title="Circe", author="Madeline Miller", created_at=end_of("2026-06-30")),
            Book(title="Piranesi", author="Susanna Clarke", created_at=at("2026-07-01", 0)),
        ]
    )
    await empty_db.commit()

    last_quarter = await run(
        empty_db, metric="titles_not_borrowed", group_by="book", period={"preset": "last_quarter"}
    )
    this_quarter = await run(empty_db, metric="titles_not_borrowed", period=THIS_QUARTER)

    assert [row.label for row in last_quarter.rows] == [
        "Children of Dune by Frank Herbert",
        "Circe by Madeline Miller",
        "Emma by Jane Austen",
    ]
    assert this_quarter.total.value == 3


# Refusals that need the database


async def test_filters_must_name_what_exists(library, empty_db):
    with pytest.raises(ValidationFailedError) as category:
        await run(empty_db, metric="loans", filters={"categories": ["Sci-fi"]})
    with pytest.raises(ValidationFailedError) as author:
        await run(empty_db, metric="loans", filters={"author": "Frank"})
    with pytest.raises(NotFoundError):
        await run(empty_db, metric="loans", filters={"book_id": str(uuid.uuid4())})

    assert category.value.code == "unknown_category"
    assert category.value.message == (
        "No category is named Sci-fi. The categories are: Science Fiction, Technology, "
        "Uncategorised."
    )
    assert author.value.code == "unknown_author"


async def test_refusals_come_before_any_figure(library, empty_db):
    future = {"from": "2026-09-01", "to": "2026-09-30"}
    backwards = {"from": "2026-09-02", "to": "2026-09-01"}
    for query, code in (
        ({"metric": "active_loans", "group_by": "month"}, "grouping_not_accepted"),
        ({"metric": "new_members", "filters": {"author": "Frank Herbert"}}, "filter_not_accepted"),
        ({"metric": "overdue_loans", "period": THIS_QUARTER}, "measured_now"),
        (
            {"metric": "loans", "period": {"preset": "all_time"}, "compare_to": "previous_period"},
            "comparison_not_accepted",
        ),
        ({"metric": "loans", "period": future}, "invalid_period"),
        ({"metric": "loans", "period": backwards}, "invalid_period"),
    ):
        with pytest.raises(ValidationFailedError) as refused:
            await run(empty_db, **query)
        assert refused.value.code == code
