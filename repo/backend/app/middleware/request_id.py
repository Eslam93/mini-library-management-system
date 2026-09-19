"""Gives every HTTP request an id, exposed to logs and returned in the X-Request-ID header."""

import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
_HEADER_KEY = REQUEST_ID_HEADER.lower().encode("latin-1")
# A caller-supplied id is reused only when it is short and made of safe characters.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == _HEADER_KEY:
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or str(uuid.uuid4())
        token = request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                header = (_HEADER_KEY, request_id.encode("latin-1"))
                message["headers"] = [*message.get("headers", []), header]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
