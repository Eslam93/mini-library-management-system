"""Server-sent events for the Copilot's chat stream.

A producer task runs the turn and puts events on a queue; the response writes each one as it
comes, as a named event with JSON data. When the stream has been quiet for a while it writes a
comment line, so proxies keep the connection open during long model calls. When the client goes
away the response stops and the producer is cancelled.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from fastapi.responses import StreamingResponse

KEEPALIVE_SECONDS = 15.0
# Proxies must pass events through as they come, and nothing may cache them.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_KEEPALIVE = ": keepalive\n\n"

Emit = Callable[[str, Mapping[str, Any]], Awaitable[None]]


def format_event(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def event_stream(
    produce: Callable[[Emit], Awaitable[None]], *, keepalive_seconds: float = KEEPALIVE_SECONDS
) -> StreamingResponse:
    """A text/event-stream response of the events produce emits. produce runs when the response
    starts, so request-scoped dependencies such as the database session are still open.
    """

    async def body() -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def emit(event: str, data: Mapping[str, Any]) -> None:
            await queue.put(format_event(event, data))

        async def run() -> None:
            try:
                await produce(emit)
            finally:
                await queue.put(None)

        producer = asyncio.create_task(run())
        try:
            while (item := await _next(queue, keepalive_seconds)) is not None:
                yield item
            # Finished: this raises anything the producer did not handle itself.
            await producer
        finally:
            producer.cancel()

    return StreamingResponse(body(), media_type="text/event-stream", headers=SSE_HEADERS)


async def _next(queue: asyncio.Queue[str | None], keepalive_seconds: float) -> str | None:
    try:
        return await asyncio.wait_for(queue.get(), keepalive_seconds)
    except TimeoutError:
        return _KEEPALIVE
