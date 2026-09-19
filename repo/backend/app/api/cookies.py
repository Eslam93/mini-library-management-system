"""The cookies the API sets.

session: the sign-in token. HttpOnly, so page scripts cannot read it; SameSite=Lax, so other
sites' pages cannot send it with their requests; Secure in production, so it travels only over
HTTPS. It lasts as long as the session can (the absolute expiry).

oauth_state: a short-lived signed cookie that carries a Google sign-in's state, nonce and PKCE
verifier from the redirect to Google back to the callback.
"""

from fastapi import Response

from app.core.config import Settings

SESSION_COOKIE = "session"
OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60
# The browser sends the OAuth state cookie only to the Google sign-in routes.
OAUTH_STATE_COOKIE_PATH = "/api/auth/google"


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(settings.session_lifetime.total_seconds()),
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.is_production, httponly=True, samesite="lax"
    )
