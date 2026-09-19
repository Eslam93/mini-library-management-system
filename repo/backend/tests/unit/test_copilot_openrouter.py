"""The OpenRouter client over a mock transport: the request it sends, the reply it reads, the one
retry on 429 and 5xx, timeouts and refusals. Nothing reaches the network.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.copilot.model import ModelError, ModelUnavailableError
from app.copilot.openrouter import DEFAULT_RETRY_WAIT_SECONDS, OpenRouterClient

API_KEY = "test-key-never-shown"
MESSAGES = [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]
TOOLS = [{"type": "function", "function": {"name": "list_categories", "parameters": {}}}]


def completion(message: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        **extra,
    }


class Server:
    """Answers each request with the next response and records the requests."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(server: Server, waits: list[float] | None = None) -> OpenRouterClient:
    async def record_wait(seconds: float) -> None:
        if waits is not None:
            waits.append(seconds)

    return OpenRouterClient(
        http=httpx.AsyncClient(transport=httpx.MockTransport(server)),
        api_key=API_KEY,
        base_url="https://models.test/api/v1/",
        model="some/model",
        max_output_tokens=500,
        sleep=record_wait,
    )


async def complete(client: OpenRouterClient, timeout: float = 30.0):
    return await client.complete(MESSAGES, tools=TOOLS, tool_choice="auto", timeout=timeout)


async def test_sends_an_openai_compatible_request_and_reads_tool_calls():
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "list_categories", "arguments": "{}"},
    }
    server = Server(
        httpx.Response(
            200,
            json=completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                    "reasoning_details": [{"type": "reasoning.encrypted", "data": "x"}],
                }
            ),
        )
    )

    reply = await complete(make_client(server))

    [request] = server.requests
    assert str(request.url) == "https://models.test/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {
        "model": "some/model",
        "messages": MESSAGES,
        "max_tokens": 500,
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    assert reply.text == ""
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("call_1", "list_categories", "{}")
    ]
    assert (reply.usage.prompt_tokens, reply.usage.completion_tokens) == (12, 3)
    # Sent back in the next request as it came, so the model keeps its reasoning.
    assert reply.message == {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call],
        "reasoning_details": [{"type": "reasoning.encrypted", "data": "x"}],
    }


async def test_reads_a_text_reply_and_arguments_given_as_an_object():
    call = {"id": "c", "type": "function", "function": {"name": "get_book", "arguments": {"a": 1}}}
    server = Server(
        httpx.Response(200, json=completion({"content": "Hello.", "tool_calls": [call]}))
    )

    reply = await complete(make_client(server))

    assert reply.text == "Hello."
    assert reply.tool_calls[0].arguments == '{"a": 1}'


@pytest.mark.parametrize(
    ("status", "headers", "expected_wait"),
    [
        (429, {"Retry-After": "2"}, 2.0),
        (429, {}, DEFAULT_RETRY_WAIT_SECONDS),
        (503, {"Retry-After": "0.5"}, 0.5),
        (502, {"Retry-After": "not a number"}, DEFAULT_RETRY_WAIT_SECONDS),
    ],
)
async def test_a_429_or_5xx_gets_one_retry_after_the_wait_it_asks_for(
    status, headers, expected_wait
):
    server = Server(
        httpx.Response(status, headers=headers),
        httpx.Response(200, json=completion({"content": "Hello."})),
    )
    waits: list[float] = []

    reply = await complete(make_client(server, waits))

    assert reply.text == "Hello."
    assert len(server.requests) == 2
    assert waits == [expected_wait]


async def test_retry_after_may_be_an_http_date():
    moment = format_datetime(datetime.now(UTC) + timedelta(seconds=3), usegmt=True)
    server = Server(
        httpx.Response(429, headers={"Retry-After": moment}),
        httpx.Response(200, json=completion({"content": "Hello."})),
    )
    waits: list[float] = []

    await complete(make_client(server, waits))

    [wait] = waits
    assert 1 < wait <= 3


async def test_only_one_retry():
    server = Server(httpx.Response(503), httpx.Response(503), httpx.Response(200))

    with pytest.raises(ModelError, match="503"):
        await complete(make_client(server))

    assert len(server.requests) == 2


async def test_no_retry_when_the_wait_does_not_fit_in_the_time_left():
    server = Server(httpx.Response(429, headers={"Retry-After": "30"}), httpx.Response(200))
    waits: list[float] = []

    with pytest.raises(ModelError, match="429"):
        await complete(make_client(server, waits), timeout=10)

    assert (len(server.requests), waits) == (1, [])


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_other_client_errors_are_not_retried(status):
    server = Server(httpx.Response(status), httpx.Response(200))

    with pytest.raises(ModelError):
        await complete(make_client(server))

    assert len(server.requests) == 1


@pytest.mark.parametrize("status", [401, 402, 403])
async def test_a_refused_key_or_account_makes_the_copilot_unavailable(status):
    server = Server(httpx.Response(status, json={"error": {"message": f"bad key {API_KEY}"}}))

    with capture_logs() as logs, pytest.raises(ModelUnavailableError) as caught:
        await complete(make_client(server))

    assert API_KEY not in str(caught.value)
    assert API_KEY not in repr(logs)
    assert [(log["event"], log["status"]) for log in logs] == [("copilot_model_error", status)]


async def test_a_refusal_logs_the_providers_reason_without_any_key():
    # OpenRouter wraps an upstream refusal; its text is what makes a rare 400 traceable.
    raw = json.dumps({"error": {"message": "Function call is missing a thought signature"}})
    body = {
        "error": {
            "message": f"Provider returned error for {API_KEY}",
            "code": 400,
            "metadata": {"provider_name": "Google", "raw": f"{raw} sk-or-v1-0123456789abcdef"},
        }
    }
    server = Server(httpx.Response(400, json=body))

    with capture_logs() as logs, pytest.raises(ModelError):
        await complete(make_client(server))

    [entry] = logs
    assert (entry["event"], entry["status"], entry["provider"]) == (
        "copilot_model_error",
        400,
        "Google",
    )
    assert "missing a thought signature" in entry["reason"]
    assert API_KEY not in repr(logs)
    assert "sk-or-v1-0123456789abcdef" not in repr(logs)


async def test_a_refusal_without_a_readable_body_logs_the_status_only():
    server = Server(httpx.Response(400, content=b"<html>Bad request</html>"))

    with capture_logs() as logs, pytest.raises(ModelError):
        await complete(make_client(server))

    [entry] = logs
    assert (entry["status"], entry["provider"], entry["reason"]) == (400, None, None)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps({"error": {"code": 502, "message": "upstream failed"}}).encode(),
        json.dumps({"choices": []}).encode(),
    ],
)
async def test_a_200_without_a_usable_reply_is_a_model_error(body):
    server = Server(httpx.Response(200, content=body))

    with pytest.raises(ModelError):
        await complete(make_client(server))


async def test_a_network_failure_is_a_model_error():
    server = Server(httpx.ConnectError("refused"))

    with pytest.raises(ModelError, match="ConnectError"):
        await complete(make_client(server))


async def test_an_httpx_timeout_is_a_timeout():
    server = Server(httpx.ReadTimeout("slow"))

    with pytest.raises(TimeoutError):
        await complete(make_client(server))


async def test_the_call_as_a_whole_is_bounded_by_its_timeout():
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    client = OpenRouterClient(
        http=httpx.AsyncClient(transport=httpx.MockTransport(slow)),
        api_key=API_KEY,
        base_url="https://models.test/api/v1",
        model="some/model",
        max_output_tokens=500,
    )

    with pytest.raises(TimeoutError):
        await complete(client, timeout=0.1)
