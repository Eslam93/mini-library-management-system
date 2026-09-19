"""Members: the people who borrow. Staff only."""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import PageLimit, PageOffset, SearchQuery, StaffUser, require_staff
from app.db.session import DbSession
from app.schemas.common import Page, error_responses
from app.schemas.members import MemberCreate, MemberDetail, MemberOut
from app.services import members

router = APIRouter(prefix="/members", tags=["members"], dependencies=[Depends(require_staff)])


@router.get("", responses=error_responses(staff=True))
async def list_members(
    session: DbSession, q: SearchQuery = None, limit: PageLimit = 20, offset: PageOffset = 0
) -> Page[MemberOut]:
    """Members ordered by name. q matches part of the name or the email address."""
    return await members.list_members(session, q=q, limit=limit, offset=offset)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(staff=True, conflicts=["member_email_taken"]),
)
async def create_member(session: DbSession, user: StaffUser, body: MemberCreate) -> MemberOut:
    return await members.create_member(session, body, actor=user)


@router.get("/{member_id}", responses=error_responses(staff=True, not_found=True))
async def get_member(session: DbSession, member_id: uuid.UUID) -> MemberDetail:
    """The member, with how many loans they have now and have had in total. Their loans come
    from GET /api/loans?member_id=.
    """
    return await members.get_member_detail(session, member_id)
