"""Two borrows of one copy, two confirms of one Copilot proposal, or a borrow and an archive of
its book, at the same moment, through separate database connections.

These tests cannot run inside the rolled-back test transaction, because each connection must
see the other's committed work. They commit their own data and remove it afterwards.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.copilot import proposals
from app.core.exceptions import ConflictError
from app.models import ActivityEvent, Book, Copy, Loan, Member, User
from app.services import catalog, circulation
from app.services.catalog import allocate_copy_codes

pytestmark = pytest.mark.integration

LOCK_WAIT_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def app(make_app, db_engine):
    """The real app: every request gets its own session and connection from the pool."""
    return make_app(database_url=db_engine.url.render_as_string(hide_password=False))


@pytest.fixture
async def client(app, serve, sign_in, db_engine):
    """Signed in as demo staff. The account is committed for real, so it is removed afterwards
    together with its sessions.
    """
    async with serve(app) as http:
        staff = await sign_in(http, "staff")
        yield http

    async with db_engine.begin() as connection:
        await connection.execute(delete(User).where(User.id == uuid.UUID(staff["id"])))


@pytest.fixture
async def shelf(db_engine):
    """One book with one copy and two members, committed so every connection sees them."""
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as session:
        book = Book(title="Concurrency probe", author="Test Suite")
        session.add(book)
        await session.flush()
        [code] = await allocate_copy_codes(session, 1)
        copy = Copy(book_id=book.id, code=code)
        members = [Member(full_name="Race First"), Member(full_name="Race Second")]
        session.add_all([copy, *members])
        await session.commit()

    yield SimpleNamespace(book=book, copy=copy, members=members)

    async with sessions() as session:
        loan_ids = select(Loan.id).where(Loan.copy_id == copy.id)
        await session.execute(delete(ActivityEvent).where(ActivityEvent.entity_id.in_(loan_ids)))
        await session.execute(delete(Loan).where(Loan.copy_id == copy.id))
        await session.execute(delete(Book).where(Book.id == book.id))
        await session.execute(delete(Member).where(Member.id.in_([m.id for m in members])))
        await session.commit()


async def active_loans(engine: AsyncEngine, copy_id) -> int:
    async with engine.connect() as connection:
        count = await connection.scalar(
            select(func.count())
            .select_from(Loan)
            .where(Loan.copy_id == copy_id, Loan.returned_at.is_(None))
        )
    return count or 0


async def wait_until_waiting_on_a_lock(engine: AsyncEngine, pid: int) -> None:
    query = text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid")
    async with asyncio.timeout(LOCK_WAIT_TIMEOUT_SECONDS), engine.connect() as connection:
        while await connection.scalar(query, {"pid": pid}) != "Lock":
            await asyncio.sleep(0.02)


async def test_two_simultaneous_borrows_of_one_copy_make_one_loan_and_one_409(
    client, shelf, db_engine
):
    responses = await asyncio.gather(
        *(
            client.post(
                "/api/loans", json={"copy_id": str(shelf.copy.id), "member_id": str(member.id)}
            )
            for member in shelf.members
        )
    )

    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "copy_unavailable"
    assert await active_loans(db_engine, shelf.copy.id) == 1


async def test_borrow_that_loses_the_race_at_the_database_is_copy_unavailable(shelf, db_engine):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    first, second = shelf.members
    async with sessions() as winner, sessions() as loser:
        # The winner's loan is written but not committed, so the loser's up-front check cannot
        # see it and the loser's insert has to wait on the unique index.
        winner.add(
            Loan(
                copy_id=shelf.copy.id,
                member_id=first.id,
                due_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await winner.flush()
        loser_pid = await loser.scalar(text("SELECT pg_backend_pid()"))
        attempt = asyncio.create_task(
            circulation.borrow(
                loser, copy_id=shelf.copy.id, member_id=second.id, loan_period_days=14, actor=None
            )
        )
        await wait_until_waiting_on_a_lock(db_engine, loser_pid)
        await winner.commit()

        with pytest.raises(ConflictError) as caught:
            await attempt

    assert caught.value.code == "copy_unavailable"
    assert await active_loans(db_engine, shelf.copy.id) == 1


async def test_two_simultaneous_confirms_of_one_proposal_make_one_loan(client, shelf, db_engine):
    """The Copilot's proposal is one-time: the second confirm waits for the first one's row
    lock, then finds the proposal already confirmed.
    """
    staff_id = uuid.UUID((await client.get("/api/auth/me")).json()["id"])
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as session:
        staff = await session.get(User, staff_id)
        proposal = await proposals.prepare_borrow(
            session,
            user=staff,
            conversation_id=None,
            member_id=shelf.members[0].id,
            book_id=shelf.book.id,
            loan_period_days=14,
        )
    confirm = f"/api/copilot/proposals/{proposal.id}/confirm"

    responses = await asyncio.gather(client.post(confirm), client.post(confirm))

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "proposal_resolved"
    assert await active_loans(db_engine, shelf.copy.id) == 1


async def test_a_borrow_waits_for_an_archive_in_progress_and_finds_the_book_archived(
    shelf, db_engine
):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as archiver, sessions() as borrower:
        # Archiving locks the book's row for update and marks it archived; not committed yet.
        book = await archiver.get(Book, shelf.book.id, with_for_update=True)
        assert book is not None
        book.archived_at = func.now()
        await archiver.flush()
        borrower_pid = await borrower.scalar(text("SELECT pg_backend_pid()"))
        attempt = asyncio.create_task(
            circulation.borrow(
                borrower,
                copy_id=shelf.copy.id,
                member_id=shelf.members[0].id,
                loan_period_days=14,
                actor=None,
            )
        )
        await wait_until_waiting_on_a_lock(db_engine, borrower_pid)
        await archiver.commit()

        with pytest.raises(ConflictError) as caught:
            await attempt

    assert caught.value.code == "book_archived"
    assert await active_loans(db_engine, shelf.copy.id) == 0


async def test_an_archive_waits_for_a_borrow_in_progress_and_finds_the_copy_on_loan(
    shelf, db_engine
):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as borrower, sessions() as archiver:
        # A borrow that has passed its checks, with the book share-locked, and written its loan;
        # not committed yet.
        await circulation.check_borrow(
            borrower,
            copy_id=shelf.copy.id,
            member_id=shelf.members[0].id,
            loan_period_days=14,
            lock_book=True,
        )
        borrower.add(
            Loan(
                copy_id=shelf.copy.id,
                member_id=shelf.members[0].id,
                due_at=datetime.now(UTC) + timedelta(days=14),
            )
        )
        await borrower.flush()
        archiver_pid = await archiver.scalar(text("SELECT pg_backend_pid()"))
        attempt = asyncio.create_task(catalog.delete_book(archiver, shelf.book.id, actor=None))
        await wait_until_waiting_on_a_lock(db_engine, archiver_pid)
        await borrower.commit()

        with pytest.raises(ConflictError) as caught:
            await attempt

    assert caught.value.code == "book_has_active_loans"
    assert await active_loans(db_engine, shelf.copy.id) == 1
