"""The model client for OpenRouter: OpenAI-compatible chat completions with tools, over httpx.

Each call is bounded by the time its turn has left. httpx's timeouts bound each network step,
not the call, so the call as a whole also runs inside asyncio.timeout. A 429 or 5xx answer gets
one more try after the wait its Retry-After header asks for, when that wait still leaves time
for the call; nothing else is retried.

The key travels only in the Authorization header. Errors and log lines carry status codes and
error types, never the key or the text of a request. A refusal's log line also carries the
provider's stated reason, cut short and with anything shaped like a key removed, because a rare
refusal cannot be traced from its status alone.
"""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.copilot.model import (
    Message,
    ModelError,
    ModelReply,
    ModelUnavailableError,
    ToolCall,
    ToolChoice,
    Usage,
)
from app.core.logging import get_logger

log = get_logger(__name__)

# The wait before the second try when a 429 or 5xx names none.
DEFAULT_RETRY_WAIT_SECONDS = 1.0
# The second try must leave at least this long for the call itself.
MIN_CALL_SECONDS = 1.0
# The key is refused, or the account cannot pay: waiting will not help.
_UNAVAILABLE_STATUSES = frozenset({401, 402, 403})
# How much of a provider's stated reason a log line keeps.
MAX_REASON_CHARS = 300
_KEY_SHAPED = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


class _Function(BaseModel):
    name: str
    arguments: str | dict[str, Any] = "{}"


class _ToolCallIn(BaseModel):
    id: str
    function: _Function


class _MessageIn(BaseModel):
    content: str | None = None
    tool_calls: list[_ToolCallIn] | None = None
    # Some models return their reasoning in this field, and need it back with their tool calls
    # in the next request.
    reasoning_details: list[Any] | None = None


class _Choice(BaseModel):
    message: _MessageIn


class _Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _Completion(BaseModel):
    choices: list[_Choice]
    usage: _Usage | None = None


class OpenRouterClient:
    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        api_key: str,
        base_url: str,
        model: str,
        max_output_tokens: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._sleep = sleep

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Message],
        tool_choice: ToolChoice,
        timeout: float,
    ) -> ModelReply:
        deadline = time.monotonic() + timeout
        body: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "max_tokens": self._max_output_tokens,
        }
        if tools:
            body["tools"] = list(tools)
            body["tool_choice"] = tool_choice

        response = await self._post(body, deadline)
        wait = _retry_wait(response)
        if wait is not None and time.monotonic() + wait + MIN_CALL_SECONDS < deadline:
            log.warning(
                "copilot_model_retry", status=response.status_code, wait_seconds=round(wait, 2)
            )
            await self._sleep(wait)
            response = await self._post(body, deadline)
        if response.status_code != httpx.codes.OK:
            raise _error_for(response, api_key=self._api_key)
        return _reply(response)

    async def _post(self, body: dict[str, Any], deadline: float) -> httpx.Response:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("no time left for the model call")
        try:
            async with asyncio.timeout(remaining):
                return await self._http.post(
                    self._url, json=body, headers=self._headers, timeout=remaining
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError("the model call timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"the model call failed: {type(exc).__name__}") from exc


def _retry_wait(response: httpx.Response) -> float | None:
    """Seconds to wait before the second try, or None when this answer is not worth one."""
    status = response.status_code
    if status != httpx.codes.TOO_MANY_REQUESTS and status < httpx.codes.INTERNAL_SERVER_ERROR:
        return None
    value = response.headers.get("retry-after")
    if value is None:
        return DEFAULT_RETRY_WAIT_SECONDS
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    # Retry-After may also be an HTTP date.
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_WAIT_SECONDS
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - datetime.now(UTC)).total_seconds())


def _error_for(response: httpx.Response, *, api_key: str) -> ModelError:
    status = response.status_code
    provider, reason = _stated_reason(response, api_key=api_key)
    log.warning("copilot_model_error", status=status, provider=provider, reason=reason)
    if status in _UNAVAILABLE_STATUSES:
        return ModelUnavailableError(f"the model service refused the request ({status})")
    return ModelError(f"the model service answered {status}")


def _stated_reason(response: httpx.Response, *, api_key: str) -> tuple[str | None, str | None]:
    """The upstream provider's name and the reason given for a refusal, from OpenRouter's error
    body, or None for what the body does not hold. The key, and anything shaped like one, is
    removed before the reason goes anywhere.
    """
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return None, None
    if not isinstance(error, dict):
        return None, None
    found = error.get("metadata")
    metadata: dict[str, Any] = found if isinstance(found, dict) else {}
    provider = metadata.get("provider_name")
    parts = [str(part) for part in (error.get("message"), metadata.get("raw")) if part]
    if not parts:
        return (str(provider) if provider else None), None
    reason = " | ".join(parts)
    if api_key:
        reason = reason.replace(api_key, "[key]")
    reason = _KEY_SHAPED.sub("[key]", reason)[:MAX_REASON_CHARS]
    return (str(provider) if provider else None), reason


def _reply(response: httpx.Response) -> ModelReply:
    # A 200 can still carry an error object instead of choices; it fails validation here.
    try:
        completion = _Completion.model_validate_json(response.content)
    except ValidationError as exc:
        raise ModelError("the model service sent an unexpected response") from exc
    if not completion.choices:
        raise ModelError("the model service sent no choices")

    message = completion.choices[0].message
    calls = tuple(
        ToolCall(id=call.id, name=call.function.name, arguments=_arguments_text(call.function))
        for call in message.tool_calls or []
    )
    replay: Message = {"role": "assistant", "content": message.content}
    if calls:
        replay["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ]
    if message.reasoning_details:
        replay["reasoning_details"] = message.reasoning_details
    usage = completion.usage or _Usage()
    return ModelReply(
        text=message.content or "",
        tool_calls=calls,
        message=replay,
        usage=Usage(usage.prompt_tokens, usage.completion_tokens),
    )


def _arguments_text(function: _Function) -> str:
    arguments = function.arguments
    return arguments if isinstance(arguments, str) else json.dumps(arguments)
