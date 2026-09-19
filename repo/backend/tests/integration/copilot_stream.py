"""Reading the Copilot's chat stream in tests: its events, and what the fake model was shown."""

import json
from typing import Any

from app.copilot.fake import FakeModelClient

Event = tuple[str, dict[str, Any]]


def parse_events(text: str) -> list[Event]:
    """Named events with JSON data; comment lines (keep-alives) are skipped."""
    events = []
    for block in text.split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith(":")]
        if not lines:
            continue
        fields = dict(line.split(": ", 1) for line in lines)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


async def chat(http, message: str, conversation_id: str | None = None) -> list[Event]:
    body: dict[str, Any] = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    response = await http.post("/api/copilot/chat", json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    return parse_events(response.text)


def names(events: list[Event]) -> list[str]:
    return [name for name, _ in events]


def data_of(events: list[Event], name: str) -> list[dict[str, Any]]:
    return [data for event, data in events if event == name]


def tool_results(model: FakeModelClient, request: int) -> list[dict[str, Any]]:
    """The lookup results the model had received by its request number `request`."""
    messages = model.requests[request].messages
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
