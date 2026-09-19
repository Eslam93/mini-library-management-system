import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import ActivityEvent, User
from app.services.activity import format_day

pytestmark = pytest.mark.integration

ACTIVITY_FIELDS = {
    "id",
    "occurred_at",
    "action",
    "entity_type",
    "entity_id",
    "summary",
    "via",
    "actor",
}


async def events(client, **params):
    response = await client.get("/api/activity", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def new_events(client, before):
    """Events recorded after `before` were fetched, newest first."""
    seen = {event["id"] for event in before}
    return [event for event in await events(client) if event["id"] not in seen]


async def test_every_change_writes_exactly_one_event(make_member, borrow, client):
    steps = []

    async def step(action, call):
        before = await events(client)
        response = await call()
        assert response.status_code in {200, 201}, response.text
        [event] = await new_events(client, before)
        assert event["action"] == action
        steps.append(event)
        return response.json()

    book = await step(
        "book.created",
        lambda: client.post("/api/books", json={"title": "Dune", "author": "Frank Herbert"}),
    )
    await step(
        "book.updated", lambda: client.patch(f"/api/books/{book['id']}", json={"category": "SF"})
    )
    await step(
        "copy.added", lambda: client.post(f"/api/books/{book['id']}/copies", json={"count": 2})
    )
    member = await step(
        "member.created", lambda: client.post("/api/members", json={"full_name": "Maya Hassan"})
    )
    loan = await step("loan.borrowed", lambda: borrow(book["copies"][0]["id"], member["id"]))
    await step("loan.returned", lambda: client.post(f"/api/loans/{loan['id']}/return"))
    await step("book.archived", lambda: client.delete(f"/api/books/{book['id']}"))
    other = await step(
        "book.created",
        lambda: client.post("/api/books", json={"title": "Draft", "author": "Nobody"}),
    )
    await step("book.deleted", lambda: client.delete(f"/api/books/{other['id']}"))

    for event in steps:
        assert set(event) == ACTIVITY_FIELDS
        assert event["via"] == "ui"
        assert event["actor"] == "Demo Staff"
    assert [e["entity_type"] for e in steps] == [
        "book",
        "book",
        "book",
        "member",
        "loan",
        "loan",
        "book",
        "book",
        "book",
    ]


async def test_events_record_who_acted_by_name_and_user_id(make_book, empty_db):
    book = await make_book()

    [event] = (
        await empty_db.scalars(
            select(ActivityEvent).where(ActivityEvent.entity_id == uuid.UUID(book["id"]))
        )
    ).all()
    staff = await empty_db.scalar(select(User).where(User.email == "staff@demo.local"))

    assert event.actor == "Demo Staff"
    assert event.actor_user_id == staff.id
    assert event.via == "ui"


async def test_failed_changes_write_no_event(make_book, make_member, borrow, client):
    book = await make_book(isbn="9780441172719")
    member = await make_member()
    loan = (await borrow(book["copies"][0]["id"], member["id"])).json()
    before = await events(client)

    await client.post("/api/books", json={"title": "Dup", "author": "X", "isbn": "9780441172719"})
    await borrow(book["copies"][0]["id"], member["id"])
    await client.delete(f"/api/books/{book['id']}")
    await client.post("/api/books", json={"title": ""})
    await client.patch(f"/api/books/{book['id']}", json={"title": "Dune"})

    assert await new_events(client, before) == []
    assert loan["returned_at"] is None


async def test_summaries_read_as_sentences(make_book, make_member, borrow, client):
    book = await make_book(title="Dune", author="Frank Herbert")
    code = book["copies"][0]["code"]
    member = await make_member("Maya Hassan")
    due = datetime.now(UTC).date() + timedelta(days=20)
    loan = (await borrow(book["copies"][0]["id"], member["id"], due_date=due.isoformat())).json()
    await client.post(f"/api/loans/{loan['id']}/return")
    await client.patch(f"/api/books/{book['id']}", json={"isbn": "9780441172719", "title": "Dune"})

    summaries = [event["summary"] for event in await events(client)]

    assert summaries == [
        "Edited Dune: ISBN",
        f"Returned Dune ({code}) from Maya Hassan",
        f"Borrowed Dune ({code}) to Maya Hassan, due {format_day(due)}",
        "Added member Maya Hassan",
        f"Added Dune by Frank Herbert with 1 copy ({code})",
    ]


async def test_activity_is_newest_first_and_limited(make_member, client):
    for name in ("First", "Second", "Third"):
        await make_member(name)

    latest_two = await events(client, limit=2)

    assert [e["summary"] for e in latest_two] == ["Added member Third", "Added member Second"]


@pytest.mark.parametrize("limit", [0, 201])
async def test_activity_limit_must_be_1_to_200(client, limit):
    response = await client.get("/api/activity", params={"limit": limit})

    assert response.status_code == 422
