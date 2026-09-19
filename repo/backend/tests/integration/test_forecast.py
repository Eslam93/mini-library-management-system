"""Forecasts against a small library built for the test, with exact expected figures.

Fantasy is lent the same number of times in the same month every year: 20 in January, then two
more each month, 42 in December. The method fits such a series exactly (a trend of 1 and no past
misses), so each forecast is the count of the same month a year earlier, with a range of no
width. Poetry is lent twice a month, too few to forecast. Today is 19 Sep 2026 unless a test
says otherwise:

- Fantasy: one loan on 15 Dec 2023 (a partial first month, left out), then every month from Jan
  2024 to Aug 2026 on the 10th, and five loans on 5 Sep 2026 (the current month, left out).
- Poetry: two loans on the 1st of every month from Jan 2024 to Aug 2026, so January is full.

Every loan comes back a week later, in the month it started.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from copilot_stream import chat, data_of, tool_results
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.copilot.fake import call, reply
from app.core.exceptions import ValidationFailedError
from app.models import Book, Copy, Loan, Member
from app.services.activity import format_month
from app.services.circulation import today_utc
from app.services.metrics import ForecastQuery, run_forecast
from app.services.metrics.periods import add_months

pytestmark = pytest.mark.integration

TODAY = date(2026, 9, 19)
FIRST_MONTH = date(2024, 1, 1)


def fantasy_count(month: date) -> int:
    return 20 + 2 * (month.month - 1)


def months_between(first: date, last: date) -> list[date]:
    months, month = [], first
    while month <= last:
        months.append(month)
        month = add_months(month, 1)
    return months


async def lend(session: AsyncSession, copy_id, member_id, day: date, count: int) -> None:
    """count loans started on the day, a minute apart, each returned a week later."""
    start = datetime.combine(day, time(10, tzinfo=UTC))
    await session.execute(
        insert(Loan),
        [
            {
                "id": uuid.uuid4(),
                "copy_id": copy_id,
                "member_id": member_id,
                "borrowed_at": start + timedelta(minutes=n),
                "due_at": start + timedelta(days=14),
                "returned_at": start + timedelta(days=7, minutes=n),
            }
            for n in range(count)
        ],
    )


async def shelve(session: AsyncSession) -> dict[str, uuid.UUID]:
    books = [
        Book(title="The Hobbit", author="J.R.R. Tolkien", category="Fantasy"),
        Book(title="Leaves of Grass", author="Walt Whitman", category="Poetry"),
    ]
    session.add_all(books)
    await session.flush()
    copies = [
        Copy(book_id=books[0].id, code="CP-8001"),
        Copy(book_id=books[1].id, code="CP-8002"),
    ]
    member = Member(full_name="Maya Hassan", joined_on=date(2023, 11, 1))
    session.add_all([*copies, member])
    await session.flush()
    return {"fantasy": copies[0].id, "poetry": copies[1].id, "member": member.id}


async def fill(session: AsyncSession, this_month: date) -> None:
    """The library above, for the 32 full months before this_month."""
    ids = await shelve(session)
    fantasy, poetry, member = ids["fantasy"], ids["poetry"], ids["member"]
    first = add_months(this_month, -32)
    await lend(session, fantasy, member, add_months(first, -1).replace(day=15), 1)
    for month in months_between(first, add_months(this_month, -1)):
        await lend(session, fantasy, member, month.replace(day=10), fantasy_count(month))
        await lend(session, poetry, member, month, 2)
    await lend(session, fantasy, member, this_month.replace(day=5), 5)
    await session.commit()


@pytest.fixture
async def library(empty_db: AsyncSession) -> None:
    await fill(empty_db, TODAY.replace(day=1))


async def forecast(session: AsyncSession, **query):
    return await run_forecast(session, ForecastQuery.model_validate(query), today=TODAY)


FANTASY = {"categories": ["fantasy"]}


async def test_a_forecast_from_full_months_is_the_same_month_a_year_earlier(library, empty_db):
    result = await forecast(empty_db, metric="loans", filters=FANTASY)

    # December 2023 is partial and September 2026 is not over: Jan 2024 to Aug 2026.
    assert (result.months, result.first_month, result.last_month) == (
        32,
        FIRST_MONTH,
        date(2026, 8, 1),
    )
    assert [(format_month(m.month), m.value) for m in result.history] == [
        ("Sep 2025", 36),
        ("Oct 2025", 38),
        ("Nov 2025", 40),
        ("Dec 2025", 42),
        ("Jan 2026", 20),
        ("Feb 2026", 22),
        ("Mar 2026", 24),
        ("Apr 2026", 26),
        ("May 2026", 28),
        ("Jun 2026", 30),
        ("Jul 2026", 32),
        ("Aug 2026", 34),
    ]
    assert [(format_month(m.month), m.value, m.low, m.high) for m in result.forecast] == [
        ("Sep 2026", 36, 36, 36),
        ("Oct 2026", 38, 38, 38),
        ("Nov 2026", 40, 40, 40),
    ]
    assert (result.trend_factor, result.typical_error_pct) == (1.0, 0.0)
    assert (result.refusal, result.trend) == (None, None)
    assert result.scope == ["category: Fantasy"]


async def test_the_whole_library_and_returns_count_every_category(library, empty_db):
    loans = await forecast(empty_db, metric="loans", horizon_months=1)
    returns = await forecast(empty_db, metric="returns", horizon_months=1)

    # Fantasy's 36 and Poetry's 2 in September 2025.
    assert [(m.value, m.low, m.high) for m in loans.forecast] == [(38, 38, 38)]
    assert returns.months == 32
    assert [(m.value, m.low, m.high) for m in returns.forecast] == [(38, 38, 38)]


async def test_a_sparse_category_is_refused_with_the_trend_instead(library, empty_db):
    result = await forecast(empty_db, metric="loans", filters={"categories": ["Poetry"]})

    # Poetry starts on 1 Jan 2024, so January is a full month.
    assert (result.months, result.first_month) == (32, FIRST_MONTH)
    assert result.forecast == []
    assert (result.refusal.reason, result.refusal.have, result.refusal.need) == (
        "too_sparse",
        2.0,
        10,
    )
    trend = result.trend
    assert (trend.start, trend.end, trend.previous_start, trend.previous_end) == (
        date(2025, 9, 1),
        date(2026, 8, 31),
        date(2024, 9, 1),
        date(2025, 8, 31),
    )
    assert (trend.value, trend.previous_value, trend.change, trend.change_pct) == (24, 24, 0, 0.0)


async def test_six_months_ahead_needs_more_history_than_there_is(library, empty_db):
    result = await forecast(empty_db, metric="loans", filters=FANTASY, horizon_months=6)

    assert (result.refusal.reason, result.refusal.have, result.refusal.need) == (
        "short_history",
        32,
        35,
    )
    # Twelve months of 20 to 42 each year: 372 against 372.
    assert (result.trend.value, result.trend.previous_value, result.trend.change) == (372, 372, 0)


async def test_the_trend_counts_the_months_before_the_records_started_as_nothing(library, empty_db):
    """On 19 Mar 2025 the records hold 14 full months, Jan 2024 to Feb 2025."""
    early = await run_forecast(
        empty_db, ForecastQuery(metric="loans", filters=FANTASY), today=date(2025, 3, 19)
    )

    assert (early.months, early.refusal.reason, early.refusal.have) == (14, "short_history", 14)
    # Mar 2024 to Feb 2025 holds every month once: 372. Mar 2023 to Feb 2024 holds the partial
    # December's 1, January's 20 and February's 22: 43.
    trend = early.trend
    assert (trend.value, trend.previous_value, trend.change, trend.change_pct) == (
        372,
        43,
        329,
        765.1,
    )


async def test_no_records_is_a_short_history_of_no_months(empty_db):
    result = await forecast(empty_db, metric="loans")

    assert (result.months, result.first_month, result.history) == (0, None, [])
    assert (result.refusal.reason, result.refusal.have, result.refusal.need) == (
        "short_history",
        0,
        32,
    )
    assert (result.trend.value, result.trend.previous_value, result.trend.change_pct) == (
        0,
        0,
        None,
    )


async def test_filters_that_do_not_apply_or_do_not_exist_are_refused(library, empty_db):
    with pytest.raises(ValidationFailedError) as members:
        await forecast(empty_db, metric="new_members", filters=FANTASY)
    with pytest.raises(ValidationFailedError) as category:
        await forecast(empty_db, metric="loans", filters={"categories": ["Sci-fi"]})

    assert members.value.code == "filter_not_accepted"
    assert members.value.message == (
        "new_members is forecast for the whole library, with no filters."
    )
    assert category.value.code == "unknown_category"


# The tool in a Copilot turn, against today's date


@pytest.fixture
async def library_until_now(empty_db: AsyncSession) -> date:
    this_month = today_utc().replace(day=1)
    await fill(empty_db, this_month)
    return this_month


async def test_a_forecast_streams_a_line_with_the_likely_range_shaded(library_until_now, copilot):
    this_month = library_until_now
    expected = fantasy_count(this_month)
    answer = f"About {expected} loans are likely this month, the same as a year ago."
    http, model = await copilot(
        call("forecast_metric", metric="loans", filters={"categories": ["Fantasy"]}),
        reply(answer),
        role="staff",
    )

    events = await chat(http, "Forecast Fantasy borrowing for the next three months")

    data = tool_results(model, 1)[0]
    assert data["basis"] == "32 months of history"
    assert data["typical_error_pct"] == 0.0
    assert data["forecast"][0] == {
        "month": format_month(this_month),
        "value": expected,
        "low": expected,
        "high": expected,
    }
    assert data["refusal"] is None
    assert data_of(events, "status") == [{"text": "Working out the forecast"}]
    assert data_of(events, "message") == [{"text": answer}]
    [result] = data_of(events, "result")
    display = result["display"]
    assert result["tool"] == "forecast_metric"
    assert display["title"] == "Loans forecast"
    assert len(display["rows"]) == 15
    assert display["chart"]["band"] == {"low": "low", "high": "high", "label": "Likely range"}


async def test_a_refused_forecast_streams_the_trend_as_a_table_without_a_chart(
    library_until_now, copilot
):
    http, model = await copilot(
        call("forecast_metric", metric="loans", filters={"categories": ["Poetry"]}),
        reply("Poetry has 24 loans in the last 12 months, too few to forecast."),
        role="staff",
    )

    events = await chat(http, "Forecast Poetry borrowing")

    refusal = tool_results(model, 1)[0]["refusal"]
    assert refusal["reason"] == "too_sparse"
    [result] = data_of(events, "result")
    assert result["display"]["title"] == "Loans trend"
    assert result["display"]["rows"] == [
        {"value": 24, "previous_value": 24, "change": 0, "change_pct": 0.0}
    ]
    assert result["display"]["chart"] is None
    assert data_of(events, "message") == [
        {"text": "Poetry has 24 loans in the last 12 months, too few to forecast."}
    ]
