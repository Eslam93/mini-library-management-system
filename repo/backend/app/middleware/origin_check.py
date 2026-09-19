"""Refuses state-changing requests sent by pages on other sites.

The session cookie is SameSite=Lax, so browsers already leave it off most cross-site requests.
This check adds a second barrier: a POST, PUT, PATCH or DELETE whose Origin header names neither
this server's own origin (its scheme and Host header) nor a site in ALLOWED_ORIGINS gets 403
origin_not_allowed before any route runs. A browser always sets Host to the server it is talking
to, so a page on another site cannot make its Origin match. Requests without an Origin header
pass, because browsers always send one on these methods; clients that omit it are not browsers
and carry no ambient cookie.
"""

from collections.abc import Collection

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.exceptions import error_response
from app.core.logging import get_logger

log = get_logger(__name__)

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_DEFAULT_PORTS = {"http": ":80", "https": ":443"}


def normalize_origin(origin: str) -> str:
    """Lower case, without a trailing slash or the scheme's default port."""
    value = origin.strip().rstrip("/").lower()
    scheme = value.split("://", 1)[0]
    default_port = _DEFAULT_PORTS.get(scheme)
    if default_port and value.endswith(default_port):
        value = value.removesuffix(default_port)
    return value


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, *, allowed_origins: Collection[str]) -> None:
        self.app = app
        self.allowed = frozenset(normalize_origin(origin) for origin in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in STATE_CHANGING_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin is not None and not self._is_allowed(
                normalize_origin(origin), scope, headers
            ):
                log.warning(
                    "origin_not_allowed", method=scope["method"], path=scope["path"], origin=origin
                )
                response = error_response(
                    403,
                    "origin_not_allowed",
                    "This request came from a site that is not allowed to make changes here.",
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _is_allowed(self, origin: str, scope: Scope, headers: Headers) -> bool:
        if origin in self.allowed:
            return True
        host = headers.get("host")
        return host is not None and origin == normalize_origin(f"{scope['scheme']}://{host}")
