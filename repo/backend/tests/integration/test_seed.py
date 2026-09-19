"""The generator against the database: the stored library keeps the circulation rules, the same
inputs store the same rows, --reset starts over, and the demo sign-in accounts keep working.

A small library (40 titles, 30 members, six months) ending today keeps these fast, and makes the
demo member's overdue loan overdue by the database clock too.
"""

from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, text

from app.models import ActivityEvent, Book, Copy, Loan, Member, User
from app.seed import GeneratorOptions, seed
from app.seed.people import load_names
from app.services.auth import ensure_demo_user
from app.services.circulation import today_utc

pytestmark = pytest.mark.integration


def small_library(**changes):
    today = today_utc()
    return GeneratorOptions(
        today=today, start=today - timedelta(days=182), titles=40, members=30, **changes
    )


async def count(session, model, *conditions):
    return await session.scalar(select(func.count()).select_from(model).where(*conditions))


async def sql_count(session, query):
    return await session.scalar(text(query))


async def test_seed_fills_an_empty_library_once(empty_db):
    first = await seed(empty_db, small_library())
    second = await seed(empty_db, small_library())

    assert first is not None
    assert second is None
    assert await count(empty_db, Book) == first.titles
    assert await count(empty_db, Copy) == first.copies
    assert await count(empty_db, Member) == first.members
    assert await count(empty_db, Loan) == first.loans
    assert await count(empty_db, Loan, Loan.returned_at.is_(None)) == first.active
    assert first.overdue >= 1


async def test_stored_loans_keep_the_circulation_rules(empty_db):
    await seed(empty_db, small_library())

    # Two loans of one copy that overlap in time, at any moment.
    assert (
        await sql_count(
            empty_db,
            """
            SELECT count(*) FROM loans a JOIN loans b ON a.copy_id = b.copy_id AND a.id < b.id
            WHERE a.borrowed_at < coalesce(b.returned_at, 'infinity')
              AND b.borrowed_at < coalesce(a.returned_at, 'infinity')
            """,
        )
        == 0
    )
    assert (
        await sql_count(
            empty_db,
            """
            SELECT count(*) FROM loans l JOIN members m ON m.id = l.member_id
            WHERE (l.borrowed_at AT TIME ZONE 'UTC')::date < m.joined_on
               OR l.borrowed_at < m.created_at
            """,
        )
        == 0
    )
    assert (
        await sql_count(
            empty_db,
            "SELECT count(*) FROM loans l JOIN copies c ON c.id = l.copy_id "
            "WHERE l.borrowed_at < c.created_at",
        )
        == 0
    )
    assert (
        await sql_count(
            empty_db,
            "SELECT count(*) FROM loans WHERE due_at <= borrowed_at OR returned_at < borrowed_at "
            "OR borrowed_at > now() OR returned_at > now()",
        )
        == 0
    )


async def test_every_change_has_its_activity_event_from_the_desk(empty_db):
    summary = await seed(empty_db, small_library())

    counts = await empty_db.execute(
        select(ActivityEvent.action, func.count()).group_by(ActivityEvent.action)
    )
    returned = await count(empty_db, Loan, Loan.returned_at.is_not(None))
    actors = set(await empty_db.scalars(select(ActivityEvent.actor).distinct()))
    via = set(await empty_db.scalars(select(ActivityEvent.via).distinct()))

    assert dict(counts.tuples().all()) == {
        "book.created": summary.titles,
        "member.created": summary.members,
        "loan.borrowed": summary.loans,
        "loan.returned": returned,
    }
    assert via == {"ui"}
    assert len(actors) > 1
    assert actors <= set(load_names().staff)
    # Event ids follow the order in which things happened.
    assert (
        await sql_count(
            empty_db,
            """
            SELECT count(*) FROM (
                SELECT occurred_at < lag(occurred_at) OVER (ORDER BY id) AS out_of_order
                FROM activity_events
            ) events WHERE out_of_order
            """,
        )
        == 0
    )


async def snapshot(session):
    tables = ("books", "copies", "members", "loans", "activity_events")
    return {
        table: (await session.execute(text(f"SELECT * FROM {table} ORDER BY id"))).all()  # noqa: S608 (fixed names)
        for table in tables
    }


async def test_the_same_seed_and_date_store_the_same_rows(empty_db):
    await seed(empty_db, small_library(), reset=True)
    first = await snapshot(empty_db)
    await seed(empty_db, small_library(), reset=True)
    second = await snapshot(empty_db)
    await seed(empty_db, small_library(seed=2), reset=True)
    other_seed = await snapshot(empty_db)

    assert first["loans"]
    assert first == second
    assert other_seed["books"] != first["books"]


async def test_reset_starts_the_copy_codes_again_at_cp_0001(empty_db):
    await seed(empty_db, small_library())

    await seed(empty_db, small_library(seed=2), reset=True)

    codes = list(await empty_db.scalars(select(Copy.code).order_by(Copy.code)))
    first_event = await empty_db.scalar(select(ActivityEvent).order_by(ActivityEvent.id))
    assert codes == [f"CP-{number:04d}" for number in range(1, len(codes) + 1)]
    assert first_event.action == "book.created"


async def test_reset_keeps_users_and_their_sessions(empty_db, open_client):
    staff = await open_client("staff")
    member = await open_client("member")
    assert (await member.get("/api/auth/me")).json()["display_name"] == "Demo Member"

    summary = await seed(empty_db, small_library(), reset=True)

    assert (await staff.get("/api/auth/me")).json()["display_name"] == "Demo Staff"
    assert (await member.get("/api/auth/me")).json()["display_name"] == "Maya Hassan"
    assert await count(empty_db, User) == 2
    # The demo member account moved to the generated member; its own record went.
    assert await count(empty_db, Member) == summary.members
    assert await count(empty_db, Member, Member.full_name == "Demo Member") == 0


async def test_demo_member_has_books_out_one_overdue_and_a_history(empty_db, open_client):
    await seed(empty_db, small_library())
    http = await open_client("member")

    active = (await http.get("/api/me/loans")).json()["items"]
    returned = (await http.get("/api/me/loans", params={"status": "returned"})).json()

    assert len(active) >= 2
    assert any(loan["is_overdue"] for loan in active)
    assert not all(loan["is_overdue"] for loan in active)
    assert returned["total"] >= 5


async def test_demo_sign_in_before_the_seed_on_an_empty_database(empty_db, open_client):
    http = await open_client("member")
    assert (await http.get("/api/auth/me")).json()["display_name"] == "Demo Member"

    added = await seed(empty_db, small_library())

    assert added is not None
    assert (await http.get("/api/auth/me")).json()["display_name"] == "Maya Hassan"
    assert len((await http.get("/api/me/loans")).json()["items"]) >= 2


async def test_seed_again_moves_a_demo_member_created_since_onto_maya(empty_db, open_client):
    await seed(empty_db, small_library())
    # As after a seed that predates the demo accounts.
    await empty_db.execute(delete(User))
    await empty_db.commit()
    http = await open_client("member")

    added = await seed(empty_db, small_library())

    assert added is None
    assert (await http.get("/api/auth/me")).json()["display_name"] == "Maya Hassan"
    assert len((await http.get("/api/me/loans")).json()["items"]) >= 2


async def test_seed_on_existing_data_still_adds_the_demo_accounts(empty_db, make_member):
    await make_member("Someone Else")

    added = await seed(empty_db, small_library())

    member_account = await empty_db.scalar(select(User).where(User.email == "member@demo.local"))
    assert added is None
    assert await count(empty_db, User, User.is_demo) == 2
    member = await empty_db.get(Member, member_account.member_id)
    assert member.full_name == "Demo Member"


async def test_demo_accounts_are_created_on_first_sign_in_without_the_seed(empty_db):
    staff = await ensure_demo_user(empty_db, "staff")
    member_account = await ensure_demo_user(empty_db, "member")
    again = await ensure_demo_user(empty_db, "member")

    member = await empty_db.get(Member, member_account.member_id)
    assert (staff.role, staff.member_id, staff.is_demo) == ("staff", None, True)
    assert again.id == member_account.id
    assert (member.full_name, member.email) == ("Demo Member", "member@demo.local")
    event = await empty_db.scalar(select(ActivityEvent))
    assert (event.action, event.via, event.entity_id) == ("member.created", "system", member.id)
    assert await count(empty_db, Member) == 1
