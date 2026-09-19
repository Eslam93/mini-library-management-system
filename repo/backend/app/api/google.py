"""The Google OpenID Connect client used by the Google sign-in routes.

authlib does the protocol work: the redirect with state, nonce and a PKCE challenge, then at the
callback the state check, the code exchange and the ID token check (signature, issuer, audience,
expiry and nonce). It keeps a sign-in's state in request.session, which the oauth_state cookie
carries; the app adds that cookie's middleware only when Google is configured.
"""

import warnings
from collections.abc import Mapping
from typing import Any, Protocol

import authlib.deprecate
from fastapi import Request, Response

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.services.auth import GoogleSignInRefused

# authlib prefers the httpx2 package and warns on import when it falls back to httpx, which it
# supports and this app uses. authlib.deprecate (imported above) installs a filter that always
# shows authlib warnings; this ignore filter goes in after it, so it wins for that one message.
# The rest of the app imports authlib through this module.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="The httpx module is deprecated",
        category=authlib.deprecate.AuthlibDeprecationWarning,
    )
    from authlib.integrations.starlette_client import OAuth, OAuthError

__all__ = ["OAuthError"]

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_SCOPE = "openid email profile"


class GoogleClient(Protocol):
    """The part of authlib's Starlette OAuth client the routes use."""

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response: ...

    async def authorize_access_token(self, request: Request) -> dict[str, Any]: ...


def create_google_client(settings: Settings) -> GoogleClient | None:
    """The client, or None when Google sign-in is not configured."""
    if not settings.google_enabled or settings.google_client_secret is None:
        return None
    oauth = OAuth()
    client: GoogleClient = oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url=GOOGLE_METADATA_URL,
        client_kwargs={"scope": GOOGLE_SCOPE, "code_challenge_method": "S256"},
    )
    return client


def google_client(request: Request) -> GoogleClient:
    """Dependency: the app's Google client, or 404 when Google sign-in is not configured."""
    client: GoogleClient | None = request.app.state.google
    if client is None:
        raise NotFoundError("Google sign-in is not configured.")
    return client


async def google_userinfo(client: GoogleClient, request: Request) -> Mapping[str, Any]:
    """The checked ID token claims of the sign-in this callback completes."""
    token = await client.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not isinstance(userinfo, Mapping):
        raise GoogleSignInRefused("Google returned no ID token")
    return userinfo
