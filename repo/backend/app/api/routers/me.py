"""Member self-service: the signed-in member's own loans."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, PageLimit, PageOffset
from app.core.exceptions import NotFoundError
from app.db.session import DbSession
from app.schemas.common import Page, error_responses
from app.schemas.loans import LoanOut, LoanStatus
from app.services import circulation

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/loans", responses=error_responses(signed_in=True, not_found=True))
async def my_loans(
    session: DbSession,
    user: CurrentUser,
    status: LoanStatus = "active",
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> Page[LoanOut]:
    """active: loans not returned yet, due soonest first. returned: history, most recently
    returned first. 404 no_member_profile for an account without a member record.
    """
    if user.member_id is None:
        raise NotFoundError(
            "This account has no member record, so it has no loans.", code="no_member_profile"
        )
    return await circulation.list_loans(
        session, status=status, member_id=user.member_id, limit=limit, offset=offset
    )
