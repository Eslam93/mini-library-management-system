"""What members see: the catalog without borrowers, and their own loans."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import Loan

pytestmark = pytest.mark.integration


def due_in(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


@pytest.fixture
async def member(member_client):
    """The demo member account's UserOut, signed in on member_client."""
    return (await member_client.get("/api/auth/me")).json()


# The catalog


async def test_members_see_when_a_copy_is_due_back_but_not_who_has_it(
    make_book, make_member, borrow, client, member_client
):
    book = await make_book(copies=2)
    maya = await make_member("Maya Hassan")
    loan = (await borrow(book["copies"][0]["id"], maya["id"], due_date=due_in(10))).json()

    as_member = (await member_client.get(f"/api/books/{book['id']}")).json()
    as_staff = (await client.get(f"/api/books/{book['id']}")).json()

    borrowed, available = as_member["copies"]
    assert borrowed["status"] == "borrowed"
    assert borrowed["due_at"] == loan["due_at"]
    assert borrowed["active_loan"] is None
    assert (available["status"], available["due_at"], available["active_loan"]) == (
        "available",
        None,
        None,
    )
    assert "Maya Hassan" not in str(as_member)
    staff_copy = as_staff["copies"][0]
    assert staff_copy["due_at"] == loan["due_at"]
    assert staff_copy["active_loan"]["member"] == {"id": maya["id"], "full_name": "Maya Hassan"}
    assert set(as_member) == set(as_staff)


async def test_members_can_list_and_search_the_catalog(make_book, member_client):
    await make_book(title="Dune")
    await make_book(title="Neuromancer", author="William Gibson")

    response = await member_client.get("/api/books", params={"q": "gibson"})

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["Neuromancer"]


# My loans


async def test_my_loans_lists_active_loans_due_soonest_first(
    make_book, make_member, borrow, member, member_client
):
    book = await make_book(copies=3)
    later, sooner, soonest = [
        (await borrow(copy["id"], member["member_id"], due_date=due_in(days))).json()
        for copy, days in zip(book["copies"], (20, 10, 5), strict=True)
    ]
    other = await make_member("Omar Farouk")
    other_book = await make_book(title="Not mine")
    await borrow(other_book["copies"][0]["id"], other["id"])

    response = await member_client.get("/api/me/loans")

    assert response.status_code == 200
    page = response.json()
    assert (page["total"], page["limit"], page["offset"]) == (3, 20, 0)
    assert [loan["id"] for loan in page["items"]] == [soonest["id"], sooner["id"], later["id"]]
    assert all(loan["member"]["id"] == member["member_id"] for loan in page["items"])
    assert all(loan["returned_at"] is None for loan in page["items"])


async def test_my_loans_shows_overdue_loans(make_book, borrow, member, member_client, empty_db):
    book = await make_book()
    loan = (await borrow(book["copies"][0]["id"], member["member_id"])).json()
    now = datetime.now(UTC)
    await empty_db.execute(
        update(Loan)
        .where(Loan.id == uuid.UUID(loan["id"]))
        .values(borrowed_at=now - timedelta(days=20), due_at=now - timedelta(days=6))
    )
    await empty_db.commit()

    [listed] = (await member_client.get("/api/me/loans")).json()["items"]

    assert listed["is_overdue"] is True


async def test_history_lists_returned_loans_most_recent_first(
    make_book, borrow, client, member, member_client, empty_db
):
    book = await make_book(copies=3)
    loans = [(await borrow(copy["id"], member["member_id"])).json() for copy in book["copies"]]
    for loan in loans[:2]:
        await client.post(f"/api/loans/{loan['id']}/return")
    # Returns in one test transaction share a timestamp, so the order is set here.
    now = datetime.now(UTC)
    for loan, minutes_ago in zip(loans[:2], (30, 5), strict=True):
        await empty_db.execute(
            update(Loan)
            .where(Loan.id == uuid.UUID(loan["id"]))
            .values(
                borrowed_at=now - timedelta(days=3),
                returned_at=now - timedelta(minutes=minutes_ago),
            )
        )
    await empty_db.commit()

    history = (await member_client.get("/api/me/loans", params={"status": "returned"})).json()
    active = (await member_client.get("/api/me/loans", params={"status": "active"})).json()

    assert [loan["id"] for loan in history["items"]] == [loans[1]["id"], loans[0]["id"]]
    assert all(loan["returned_at"] is not None for loan in history["items"])
    assert [loan["id"] for loan in active["items"]] == [loans[2]["id"]]


async def test_my_loans_pages(make_book, borrow, member, member_client):
    book = await make_book(copies=3)
    for copy in book["copies"]:
        await borrow(copy["id"], member["member_id"])

    page = (await member_client.get("/api/me/loans", params={"limit": 2, "offset": 2})).json()

    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (3, 2, 2, 1)


async def test_my_loans_without_loans_is_an_empty_page(member_client):
    response = await member_client.get("/api/me/loans")

    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_my_loans_for_an_account_without_a_member_record_is_404(client):
    response = await client.get("/api/me/loans")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_member_profile"


async def test_my_loans_status_must_be_active_or_returned(member_client):
    response = await member_client.get("/api/me/loans", params={"status": "overdue"})

    assert response.status_code == 422
