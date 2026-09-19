"""Circulation: the loans list, borrowing and returning copies. Staff only."""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    AppSettings,
    PageLimit,
    PageOffset,
    SearchQuery,
    StaffUser,
    require_staff,
)
from app.db.session import DbSession
from app.schemas.common import Page, error_responses
from app.schemas.loans import LoanCreate, LoanListStatus, LoanOut
from app.services import circulation

router = APIRouter(prefix="/loans", tags=["loans"], dependencies=[Depends(require_staff)])


@router.get("", responses=error_responses(staff=True))
async def list_loans(
    session: DbSession,
    status: LoanListStatus = "active",
    q: SearchQuery = None,
    member_id: uuid.UUID | None = None,
    book_id: uuid.UUID | None = None,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> Page[LoanOut]:
    """active (the default) and overdue: due soonest first. returned: most recently returned
    first. all: most recently borrowed first. q matches the book's title or author, the member's
    name or the copy code. member_id and book_id narrow the list to one member or one book.
    """
    return await circulation.list_loans(
        session,
        status=status,
        q=q,
        member_id=member_id,
        book_id=book_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        staff=True, not_found=True, conflicts=["copy_unavailable", "book_archived"]
    ),
)
async def borrow(
    session: DbSession, settings: AppSettings, user: StaffUser, body: LoanCreate
) -> LoanOut:
    """Lends a copy to a member. Without due_date the loan is due after the loan period.
    due_date must be after today and at most 90 days ahead.
    """
    return await circulation.borrow(
        session,
        copy_id=body.copy_id,
        member_id=body.member_id,
        due_date=body.due_date,
        loan_period_days=settings.loan_period_days,
        actor=user,
    )


@router.post(
    "/{loan_id}/return",
    responses=error_responses(staff=True, not_found=True, conflicts=["loan_already_returned"]),
)
async def return_loan(session: DbSession, user: StaffUser, loan_id: uuid.UUID) -> LoanOut:
    return await circulation.return_loan(session, loan_id, actor=user)
