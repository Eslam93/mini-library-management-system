"""The staff dashboard: counts of the library as it is now, the loans that need attention, and
the latest activity. Four queries, whatever the size of the library.
"""

from datetime import timedelta

from sqlalchemy import ColumnElement, ScalarSelect, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.models import Book, Copy, Loan, Member
from app.schemas.dashboard import DashboardCounts, DashboardOut
from app.services import activity, circulation

# How many loans each list shows; the counts give the full numbers.
LIST_SIZE = 8
DUE_SOON_DAYS = 3
RECENT_ACTIVITY_SIZE = 10
ACTIVE_MEMBER_DAYS = 90


def _count(entity: type[Base], *conditions: ColumnElement[bool]) -> ScalarSelect[int]:
    return select(func.count()).select_from(entity).where(*conditions).scalar_subquery()


async def _counts(session: AsyncSession) -> DashboardCounts:
    """Every count in one query. Archived books and copies are out of circulation."""
    in_circulation = Copy.archived_at.is_(None)
    on_loan = exists().where(Loan.copy_id == Copy.id, Loan.returned_at.is_(None))
    since = func.now() - timedelta(days=ACTIVE_MEMBER_DAYS)
    active_members = (
        select(func.count(distinct(Loan.member_id))).where(Loan.borrowed_at >= since)
    ).scalar_subquery()

    row = (
        await session.execute(
            select(
                _count(Book, Book.archived_at.is_(None)).label("titles"),
                _count(Copy, in_circulation).label("copies"),
                _count(Copy, in_circulation, ~on_loan).label("available"),
                _count(Copy, in_circulation, on_loan).label("on_loan"),
                _count(Loan, circulation.is_overdue()).label("overdue"),
                _count(Member, Member.archived_at.is_(None)).label("members"),
                active_members.label("active_members_90d"),
            )
        )
    ).one()
    return DashboardCounts(**row._asdict())


async def get_dashboard(session: AsyncSession) -> DashboardOut:
    return DashboardOut(
        counts=await _counts(session),
        overdue=await circulation.overdue_loans(session, limit=LIST_SIZE),
        due_soon=await circulation.loans_due_soon(session, days=DUE_SOON_DAYS, limit=LIST_SIZE),
        recent_activity=await activity.list_recent(session, limit=RECENT_ACTIVITY_SIZE),
    )
