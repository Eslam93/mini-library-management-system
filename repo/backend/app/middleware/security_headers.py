"""Adds browser security headers to every HTTP response."""

from collections.abc import Collection

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Book covers come from Open Library. Its cover links redirect to the Internet Archive, which
# runs Open Library, so the archive's hosts are allowed for images too.
COVER_IMAGE_SOURCES = "https://covers.openlibrary.org https://archive.org https://*.archive.org"

# The web app is served from this origin and loads no third-party code. Only images, the book
# covers, come from elsewhere.
APP_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        f"img-src 'self' data: blob: {COVER_IMAGE_SOURCES}",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

# The interactive API docs page loads its script and styles from a CDN.
DOCS_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "object-src 'none'",
        "frame-ancestors 'none'",
    ]
)

_STATIC_HEADERS: dict[bytes, bytes] = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
}
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Sets each header unless the response already has it.

    HSTS is only sent when enabled, because browsers would otherwise force HTTPS on localhost.
    """

    def __init__(
        self, app: ASGIApp, *, hsts: bool = False, docs_paths: Collection[str] = ()
    ) -> None:
        self.app = app
        self.hsts = hsts
        self.docs_paths = frozenset(docs_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        csp = DOCS_CSP if scope["path"] in self.docs_paths else APP_CSP
        extra = {**_STATIC_HEADERS, b"content-security-policy": csp.encode("latin-1")}
        if self.hsts:
            extra[_HSTS[0]] = _HSTS[1]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers += [(name, value) for name, value in extra.items() if name not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
