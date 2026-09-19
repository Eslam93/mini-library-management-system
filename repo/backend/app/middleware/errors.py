"""Turns exceptions that escape a route into the standard 500 error response."""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import unhandled_exception_handler


class UnhandledErrorMiddleware:
    """Handles errors inside the request id, logging and security header middleware.

    Starlette runs a handler registered for Exception outside all middleware, so its response
    would miss the request id and security headers. Catching here keeps 500 responses like any
    other response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_and_track(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_and_track)
        except Exception as exc:
            if response_started:
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)
