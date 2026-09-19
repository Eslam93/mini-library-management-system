"""The staff loans list: status, search, the member and book filters, order and paging."""

from datetime import UTC, datetime, time, timedelta

import pytest

pytestmark = pytest.mark.integration


def due_in(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def end_of_day(days_from_today: int) -> datetime:
    day = datetime.now(UTC).date() + timedelta(days=days_from_today)
    return datetime.combine(day, time(23, 59, 59, tzinfo=UTC))


@pytest.fixture
async def library(make_book, make_member, borrow, client, move_loan):
    """Five loans with distinct times, named by what they show:

    late: Dune to Maya, overdue since the end of the day five days ago
    soon: Dune to Maya, due in 2 days
    later: Emma to Omar, due in 10 days
    returned_recently: Dune to Omar, returned 2 days ago
    returned_long_ago: Kindred to Maya, returned late 30 days ago
    """
    now = datetime.now(UTC)
    dune = await make_book(title="Dune", author="Frank Herbert", copies=2)
    emma = await make_book(title="Emma", author="Jane Austen")
    kindred = await make_book(title="Kindred", author="Octavia E. Butler")
    maya = await make_member("Maya Hassan")
    omar = await make_member("Omar Farouk")

    async def lend(book, index, member, **fields):
        return (await borrow(book["copies"][index]["id"], member["id"], **fields)).json()

    async def give_back(loan):
        await client.post(f"/api/loans/{loan['id']}/return")

    returned_recently = await lend(dune, 1, omar)
    await give_back(returned_recently)
    await move_loan(
        returned_recently["id"],
        borrowed_at=now - timedelta(days=10),
        due_at=now + timedelta(days=4),
        returned_at=now - timedelta(days=2),
    )
    returned_long_ago = await lend(kindred, 0, maya)
    await give_back(returned_long_ago)
    await move_loan(
        returned_long_ago["id"],
        borrowed_at=now - timedelta(days=50),
        due_at=now - timedelta(days=36),
        returned_at=now - timedelta(days=30),
    )
    late = await lend(dune, 0, maya)
    await move_loan(late["id"], borrowed_at=now - timedelta(days=20), due_at=end_of_day(-5))
    soon = await lend(dune, 1, maya, due_date=due_in(2))
    await move_loan(soon["id"], borrowed_at=now - timedelta(hours=1))
    later = await lend(emma, 0, omar, due_date=due_in(10))
    await move_loan(later["id"], borrowed_at=now - timedelta(days=1))

    return {
        "books": {"dune": dune, "emma": emma, "kindred": kindred},
        "members": {"maya": maya, "omar": omar},
        "loans": {
            "late": late["id"],
            "soon": soon["id"],
            "later": later["id"],
            "returned_recently": returned_recently["id"],
            "returned_long_ago": returned_long_ago["id"],
        },
    }


async def loans(client, **params):
    response = await client.get("/api/loans", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def names(library, page):
    by_id = {loan_id: name for name, loan_id in library["loans"].items()}
    return [by_id[loan["id"]] for loan in page["items"]]


# Status and order


async def test_active_loans_are_listed_by_default_due_soonest_first(library, client):
    page = await loans(client)

    assert names(library, page) == ["late", "soon", "later"]
    assert (page["total"], page["limit"], page["offset"]) == (3, 20, 0)


async def test_overdue_lists_only_overdue_loans(library, client):
    page = await loans(client, status="overdue")

    assert names(library, page) == ["late"]
    assert page["items"][0]["is_overdue"] is True


async def test_returned_loans_are_most_recently_returned_first(library, client):
    page = await loans(client, status="returned")

    assert names(library, page) == ["returned_recently", "returned_long_ago"]
    assert all(loan["returned_at"] is not None for loan in page["items"])


async def test_all_loans_are_most_recently_borrowed_first(library, client):
    page = await loans(client, status="all")

    assert names(library, page) == [
        "soon",
        "later",
        "returned_recently",
        "late",
        "returned_long_ago",
    ]


async def test_status_must_be_one_of_the_four(client):
    response = await client.get("/api/loans", params={"status": "late"})

    assert response.status_code == 422
    [error] = response.json()["error"]["details"]["errors"]
    assert error["location"] == ["query", "status"]


# Days overdue


async def test_days_overdue_counts_whole_days_since_the_due_date(library, client):
    page = await loans(client, status="all")

    days = {
        name: loan["days_overdue"]
        for name, loan in zip(names(library, page), page["items"], strict=True)
    }
    # A loan returned late is no longer overdue.
    assert days == {
        "late": 5,
        "soon": 0,
        "later": 0,
        "returned_recently": 0,
        "returned_long_ago": 0,
    }


async def test_a_loan_overdue_by_minutes_is_one_day_overdue(
    make_book, make_member, borrow, client, move_loan
):
    now = datetime.now(UTC)
    book = await make_book()
    member = await make_member()
    loan = (await borrow(book["copies"][0]["id"], member["id"])).json()
    await move_loan(
        loan["id"], borrowed_at=now - timedelta(days=14), due_at=now - timedelta(minutes=5)
    )

    [listed] = (await loans(client, status="overdue"))["items"]

    assert (listed["is_overdue"], listed["days_overdue"]) == (True, 1)


# Search


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("dune", ["soon", "returned_recently", "late"]),
        ("AUSTEN", ["later"]),
        ("octavia", ["returned_long_ago"]),
        ("farouk", ["later", "returned_recently"]),
        ("  Maya Has ", ["soon", "late", "returned_long_ago"]),
        ("nothing like this", []),
    ],
)
async def test_search_matches_title_author_or_member(library, client, q, expected):
    page = await loans(client, status="all", q=q)

    assert names(library, page) == expected
    assert page["total"] == len(expected)


async def test_search_matches_the_copy_code_in_any_case(library, client):
    code = library["books"]["kindred"]["copies"][0]["code"]

    page = await loans(client, status="all", q=code.lower())

    assert names(library, page) == ["returned_long_ago"]


async def test_search_combines_with_the_status(library, client):
    page = await loans(client, status="active", q="maya")

    assert names(library, page) == ["late", "soon"]


async def test_search_wildcards_match_only_themselves(library, client):
    page = await loans(client, status="all", q="%")

    assert page["total"] == 0


# Member and book filters


async def test_member_filter_lists_one_members_loans(library, client):
    maya = library["members"]["maya"]["id"]

    page = await loans(client, status="all", member_id=maya)

    assert names(library, page) == ["soon", "late", "returned_long_ago"]


async def test_book_filter_lists_the_loan_history_of_one_book(library, client):
    dune = library["books"]["dune"]["id"]

    history = await loans(client, status="all", book_id=dune)
    returned = await loans(client, status="returned", book_id=dune)

    assert names(library, history) == ["soon", "returned_recently", "late"]
    assert names(library, returned) == ["returned_recently"]


async def test_filters_must_be_ids(client):
    response = await client.get("/api/loans", params={"member_id": "maya"})

    assert response.status_code == 422


# Paging


async def test_loans_list_pages(library, client):
    page = await loans(client, status="all", limit=2, offset=2)

    assert names(library, page) == ["returned_recently", "late"]
    assert (page["total"], page["limit"], page["offset"]) == (5, 2, 2)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_paging_is_validated(client, params):
    response = await client.get("/api/loans", params=params)

    assert response.status_code == 422
