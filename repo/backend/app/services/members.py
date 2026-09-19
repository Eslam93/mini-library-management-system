"""Members: search, detail and add."""

import uuid

from sqlalchemy import ColumnElement, Label, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.db.errors import flush_or_raise
from app.models import ActivityVia, Loan, Member, User
from app.models.member import MEMBER_EMAIL_INDEX
from app.schemas.common import Page
from app.schemas.members import MemberCreate, MemberDetail, MemberOut
from app.services import activity
from app.services.text_search import contains, search_term


def _email_taken() -> ConflictError:
    return ConflictError(
        "Another member already uses this email address.", code="member_email_taken"
    )


def _active_loans_column() -> Label[int]:
    return (
        select(func.count())
        .where(Loan.member_id == Member.id, Loan.returned_at.is_(None))
        .correlate(Member)
        .scalar_subquery()
        .label("active_loans")
    )


def _search_condition(q: str | None) -> ColumnElement[bool] | None:
    """Case-insensitive substring match on the name or the email address."""
    term = search_term(q)
    if term is None:
        return None
    return or_(contains(Member.full_name, term), contains(Member.email, term))


def _member_out(member: Member, active_loans: int) -> MemberOut:
    return MemberOut(
        id=member.id,
        full_name=member.full_name,
        email=member.email,
        joined_on=member.joined_on,
        active_loans=active_loans,
    )


async def list_members(
    session: AsyncSession, *, q: str | None, limit: int, offset: int
) -> Page[MemberOut]:
    conditions: list[ColumnElement[bool]] = [Member.archived_at.is_(None)]
    search = _search_condition(q)
    if search is not None:
        conditions.append(search)

    total = await session.scalar(select(func.count()).select_from(Member).where(*conditions))
    rows = await session.execute(
        select(Member, _active_loans_column())
        .where(*conditions)
        .order_by(func.lower(Member.full_name), Member.id)
        .limit(limit)
        .offset(offset)
        .execution_options(populate_existing=True)
    )
    items = [_member_out(*row._tuple()) for row in rows]
    return Page(items=items, total=total or 0, limit=limit, offset=offset)


async def get_member(session: AsyncSession, member_id: uuid.UUID) -> MemberOut:
    found = (
        await session.execute(
            select(Member, _active_loans_column())
            .where(Member.id == member_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if found is None:
        raise NotFoundError("Member not found.")
    return _member_out(*found._tuple())


async def get_member_detail(session: AsyncSession, member_id: uuid.UUID) -> MemberDetail:
    """The member with counts of their loans now and ever. Their loans themselves come from the
    loans list, filtered by member.
    """
    loans_total = (
        select(func.count())
        .where(Loan.member_id == Member.id)
        .correlate(Member)
        .scalar_subquery()
        .label("loans_total")
    )
    found = (
        await session.execute(
            select(Member, _active_loans_column(), loans_total)
            .where(Member.id == member_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if found is None:
        raise NotFoundError("Member not found.")
    member, active_loans, total = found._tuple()
    return MemberDetail(**_member_out(member, active_loans).model_dump(), loans_total=total)


async def create_member(
    session: AsyncSession,
    data: MemberCreate,
    *,
    via: ActivityVia = "ui",
    actor: User | None,
) -> MemberOut:
    if data.email is not None:
        taken = exists().where(func.lower(Member.email) == data.email.lower())
        if await session.scalar(select(taken)):
            raise _email_taken()

    member = Member(full_name=data.full_name, email=data.email)
    session.add(member)
    await flush_or_raise(session, {MEMBER_EMAIL_INDEX: _email_taken()})
    activity.record(
        session,
        action="member.created",
        entity_type="member",
        entity_id=member.id,
        summary=activity.member_created(member.full_name),
        details={"email": member.email},
        via=via,
        actor=actor,
    )
    await session.commit()
    return await get_member(session, member.id)
