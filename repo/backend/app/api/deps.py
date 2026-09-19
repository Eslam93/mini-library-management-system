"""Dependencies and query parameters shared by the routers."""

from typing import Annotated

from fastapi import Depends, Query, Request

from app.api.cookies import SESSION_COOKIE
from app.core.config import Settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.session import DbSession
from app.models import User
from app.services import auth


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(_settings)]

SearchQuery = Annotated[
    str | None, Query(max_length=200, description="Case-insensitive text to search for")
]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


async def current_user(request: Request, session: DbSession, settings: AppSettings) -> User:
    """The signed-in user, from the session cookie. 401 unauthorized without a live session."""
    token = request.cookies.get(SESSION_COOKIE)
    user = None
    if token:
        user = await auth.user_for_token(session, token, idle_timeout=settings.session_idle_timeout)
    if user is None:
        raise UnauthorizedError()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_staff(user: CurrentUser) -> User:
    """The signed-in user when they are staff. 403 forbidden for members."""
    if not user.is_staff:
        raise ForbiddenError("This is available to staff only.")
    return user


StaffUser = Annotated[User, Depends(require_staff)]
