"""The activity record, newest first. Staff only."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_staff
from app.db.session import DbSession
from app.schemas.activity import ActivityOut
from app.schemas.common import error_responses
from app.services import activity

router = APIRouter(prefix="/activity", tags=["activity"], dependencies=[Depends(require_staff)])


@router.get("", responses=error_responses(staff=True))
async def list_activity(
    session: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[ActivityOut]:
    return await activity.list_recent(session, limit=limit)
