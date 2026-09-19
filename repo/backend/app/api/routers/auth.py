"""Signing in and out: demo accounts, Google, and the current user.

Every route here is public except /me. A new sign-in first revokes the session the browser
already had, if any.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.cookies import SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.api.deps import AppSettings, CurrentUser
from app.api.google import GoogleClient, OAuthError, google_client, google_userinfo
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.session import DbSession
from app.models import User
from app.schemas.auth import AuthConfigOut, DemoSignIn, UserOut
from app.schemas.common import error_responses
from app.services import auth

log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

SIGN_IN_FAILED_PATH = "/sign-in?error=google"
# Where the OAuth state cookie keeps the path to return to after Google sign-in.
_NEXT_KEY = "next"

Google = Annotated[GoogleClient, Depends(google_client)]
NextPath = Annotated[str | None, Query(alias="next", max_length=auth.MAX_NEXT_PATH_LENGTH)]


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


async def _sign_in(request: Request, session: DbSession, user: User, settings: AppSettings) -> str:
    """Ends the browser's previous session, if any, and starts one for the user."""
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        await auth.revoke_session(session, previous)
    return await auth.start_session(session, user, lifetime=settings.session_lifetime)


def _require_demo_login(settings: AppSettings) -> None:
    if not settings.demo_login_enabled:
        raise NotFoundError("Demo sign-in is not available.")


@router.get("/config")
async def auth_config(settings: AppSettings) -> AuthConfigOut:
    """Which ways to sign in are available."""
    return AuthConfigOut(demo_login=settings.demo_login_enabled, google=settings.google_enabled)


@router.post(
    "/demo",
    dependencies=[Depends(_require_demo_login)],
    responses=error_responses(not_found=True),
)
async def demo_sign_in(
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
    body: DemoSignIn,
) -> UserOut:
    """Signs in as the demo account for the role. 404 when demo sign-in is turned off."""
    user = await auth.ensure_demo_user(session, body.role)
    token = await _sign_in(request, session, user, settings)
    set_session_cookie(response, token, settings)
    return _user_out(user)


@router.get(
    "/google/login",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses=error_responses(not_found=True),
)
async def google_login(
    request: Request, settings: AppSettings, google: Google, next_path: NextPath = None
) -> Response:
    """Redirects to Google. After sign-in the browser returns to next, a path on this site.
    404 when Google sign-in is not configured.
    """
    request.session.clear()
    request.session[_NEXT_KEY] = auth.safe_next_path(next_path)
    try:
        return await google.authorize_redirect(request, settings.google_redirect_uri)
    except Exception as exc:
        # Google's configuration document could not be fetched.
        log.error("google_sign_in_unavailable", exc_info=exc)
        request.session.clear()
        return RedirectResponse(SIGN_IN_FAILED_PATH, status_code=status.HTTP_302_FOUND)


@router.get(
    "/google/callback",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses=error_responses(not_found=True),
)
async def google_callback(
    request: Request, session: DbSession, settings: AppSettings, google: Google
) -> Response:
    """Where Google sends the browser back. Signs in and redirects to the path chosen at login,
    or to the sign-in page with error=google when anything fails.
    """
    next_path = auth.safe_next_path(request.session.get(_NEXT_KEY))
    try:
        userinfo = await google_userinfo(google, request)
        user = await auth.complete_google_login(
            session, userinfo, staff_emails=settings.staff_emails
        )
    except (OAuthError, auth.GoogleSignInRefused) as exc:
        log.warning("google_sign_in_refused", error=type(exc).__name__, reason=str(exc))
        return _sign_in_failed(request)
    except Exception as exc:
        # The browser is navigating, so it gets the sign-in page rather than an error body.
        log.error("google_sign_in_failed", exc_info=exc)
        return _sign_in_failed(request)

    request.session.clear()
    token = await _sign_in(request, session, user, settings)
    response = RedirectResponse(next_path, status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, token, settings)
    return response


def _sign_in_failed(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(SIGN_IN_FAILED_PATH, status_code=status.HTTP_302_FOUND)


@router.get("/me", responses=error_responses(signed_in=True))
async def me(user: CurrentUser) -> UserOut:
    """The signed-in user."""
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, session: DbSession, settings: AppSettings) -> Response:
    """Ends the session and clears the cookie. Also 204 when already signed out."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await auth.revoke_session(session, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, settings)
    return response
