from datetime import UTC, date, datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

COUNT_FIELDS = {
    "titles",
    "copies",
    "available",
    "on_loan",
    "overdue",
    "members",
    "active_members_90d",
}


def due_in(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


async def dashboard(client):
    response = await client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    return response.json()


def ids(loans):
    return [loan["id"] for loan in loans]


async def test_counts_describe_the_library_now(make_book, make_member, borrow, client, move_loan):
    now = datetime.now(UTC)
    dune = await make_book(title="Dune", copies=3)
    emma = await make_book(title="Emma", author="Jane Austen", copies=2)
    old = await make_book(title="Old", author="Nobody", copies=2)
    maya = await make_member("Maya Hassan")
    omar = await make_member("Omar Farouk")
    lina = await make_member("Lina Haddad")
    await make_member("Sami Nour")
    overdue = (await borrow(dune["copies"][0]["id"], maya["id"])).json()
    await move_loan(
        overdue["id"], borrowed_at=now - timedelta(days=20), due_at=now - timedelta(days=2)
    )
    await borrow(dune["copies"][1]["id"], maya["id"], due_date=due_in(2))
    await borrow(emma["copies"][0]["id"], omar["id"], due_date=due_in(10))
    # Lina last borrowed 120 days ago, from a book that has since been archived.
    lina_loan = (await borrow(old["copies"][0]["id"], lina["id"])).json()
    await client.post(f"/api/loans/{lina_loan['id']}/return")
    await move_loan(
        lina_loan["id"],
        borrowed_at=now - timedelta(days=120),
        due_at=now - timedelta(days=106),
        returned_at=now - timedelta(days=110),
    )
    assert (await client.delete(f"/api/books/{old['id']}")).json() == {"outcome": "archived"}

    counts = (await dashboard(client))["counts"]

    assert set(counts) == COUNT_FIELDS
    assert counts == {
        "titles": 2,
        "copies": 5,
        "available": 2,
        "on_loan": 3,
        "overdue": 1,
        "members": 4,
        "active_members_90d": 2,
    }


async def test_an_empty_library_counts_zero(client):
    body = await dashboard(client)

    assert set(body["counts"].values()) == {0}
    assert (body["overdue"], body["due_soon"]) == ([], [])


async def test_overdue_and_due_soon_split_at_the_present(
    make_book, make_member, borrow, client, move_loan
):
    now = datetime.now(UTC)
    book = await make_book(copies=5)
    member = await make_member()
    copies = [copy["id"] for copy in book["copies"]]
    late_by_a_minute = (await borrow(copies[0], member["id"])).json()
    await move_loan(
        late_by_a_minute["id"],
        borrowed_at=now - timedelta(days=14),
        due_at=now - timedelta(minutes=1),
    )
    due_in_a_minute = (await borrow(copies[1], member["id"])).json()
    await move_loan(
        due_in_a_minute["id"],
        borrowed_at=now - timedelta(days=14),
        due_at=now + timedelta(minutes=1),
    )
    in_three_days = (await borrow(copies[2], member["id"], due_date=due_in(3))).json()
    await borrow(copies[3], member["id"], due_date=due_in(4))
    returned = (await borrow(copies[4], member["id"], due_date=due_in(1))).json()
    await client.post(f"/api/loans/{returned['id']}/return")

    body = await dashboard(client)

    assert ids(body["overdue"]) == [late_by_a_minute["id"]]
    assert ids(body["due_soon"]) == [due_in_a_minute["id"], in_three_days["id"]]
    assert body["overdue"][0]["is_overdue"] is True
    assert body["overdue"][0]["days_overdue"] >= 1
    assert all(loan["days_overdue"] == 0 for loan in body["due_soon"])


async def test_lists_show_at_most_eight_in_order(make_book, make_member, borrow, client, move_loan):
    now = datetime.now(UTC)
    book = await make_book(copies=19)
    member = await make_member()
    copies = [copy["id"] for copy in book["copies"]]
    for days_late, copy_id in enumerate(copies[:10], start=1):
        loan = (await borrow(copy_id, member["id"])).json()
        await move_loan(
            loan["id"],
            borrowed_at=now - timedelta(days=30),
            due_at=now - timedelta(days=days_late),
        )
    for days_ahead, copy_id in zip((3, 2, 1, 3, 2, 1, 3, 2, 1), copies[10:], strict=True):
        await borrow(copy_id, member["id"], due_date=due_in(days_ahead))

    body = await dashboard(client)

    assert body["counts"]["overdue"] == 10
    assert len(body["overdue"]) == 8
    assert [loan["days_overdue"] for loan in body["overdue"]] == [10, 9, 8, 7, 6, 5, 4, 3]
    assert len(body["due_soon"]) == 8
    due_dates = [loan["due_at"] for loan in body["due_soon"]]
    assert due_dates == sorted(due_dates)
    assert date.fromisoformat(due_dates[0][:10]) == datetime.now(UTC).date() + timedelta(days=1)


async def test_recent_activity_is_the_ten_latest_events(make_member, client):
    for number in range(12):
        await make_member(f"Member {number:02d}")

    recent = (await dashboard(client))["recent_activity"]
    latest = (await client.get("/api/activity", params={"limit": 10})).json()

    assert recent == latest
    assert [event["summary"] for event in recent[:2]] == [
        "Added member Member 11",
        "Added member Member 10",
    ]
