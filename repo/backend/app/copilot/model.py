"""The language model as the Copilot sees it: one chat completion with tools per call.

Messages and tool definitions use the OpenAI-compatible chat format, which OpenRouter speaks for
every model it serves. A call that runs out of time raises the built-in TimeoutError.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

# One chat message or tool definition in the OpenAI-compatible format.
Message = dict[str, Any]
# auto: the model may ask for lookups. none: it must answer in text.
ToolChoice = Literal["auto", "none"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    # The arguments as the model wrote them: JSON text, checked before any lookup runs.
    arguments: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True)
class ModelReply:
    text: str
    tool_calls: tuple[ToolCall, ...]
    # The assistant message to send back in later requests, as the model returned it.
    message: Message
    usage: Usage


class ModelError(Exception):
    """The model gave no usable answer. The message is for logs: it never holds the key or any
    message text.
    """


class ModelUnavailableError(ModelError):
    """The model service refused the key or the account, so no call can succeed until the
    configuration changes.
    """


class ModelClient(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Message],
        tool_choice: ToolChoice,
        timeout: float,
    ) -> ModelReply:
        """One model call, finished within timeout seconds or TimeoutError."""
        ...
