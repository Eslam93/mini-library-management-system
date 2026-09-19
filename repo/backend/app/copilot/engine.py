"""One Copilot turn: the tool-calling loop, the number check and the fallback reply.

The model gets the face's prompt, the conversation so far and the new message. While it asks for
lookups, each call's arguments are checked against the tool's parameters and the tool runs as
the signed-in user; results, including argument errors, go back to the model, up to the round
limit. An empty reply gets one nudge, with the tools still on offer, because the model sometimes
stops between the steps of a task. The reply must pass the number check (app.copilot.numbers). A
reply that fails gets one
corrective retry, and if that fails too, the reply is the turn's lookup results in plain
sentences. The round limit ends the turn with that same plain reply.

The whole turn has one deadline; each model call gets the time left.
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.copilot.faces import Face
from app.copilot.model import (
    Message,
    ModelClient,
    ModelError,
    ModelReply,
    ModelUnavailableError,
    ToolCall,
    ToolChoice,
    Usage,
)
from app.copilot.numbers import allowed_runs, unsupported_numbers
from app.copilot.sse import Emit
from app.copilot.tools import Data, ToolContext
from app.core.exceptions import AppError
from app.core.logging import get_logger

log = get_logger(__name__)

TurnError = Literal["copilot_timeout", "copilot_unavailable", "copilot_failed"]

FALLBACK_INTRO = "Here is what I found:"
NOTHING_TO_SHOW = (
    "Sorry, I could not answer that from the library's records. Try asking in another way."
)
_UNSUPPORTED_NUMBERS_NOTE = (
    "Your reply contains numbers that are not in the lookup results or the user's messages: "
    "{numbers}. Rewrite the reply using only numbers from the lookup results or the user's "
    "messages, exactly as given. Do not calculate or estimate."
)
_EMPTY_REPLY_NOTE = (
    "Your reply was empty. Continue: make the next lookup if one is needed, or answer the "
    "user's last message."
)


@dataclass
class TurnResult:
    # Messages to keep, in order: each finished round's lookup requests and results, then the
    # reply. A round cut short by an error is left out.
    messages: list[Message] = field(default_factory=list)
    reply: str | None = None
    error: TurnError | None = None
    # How the turn ended, for the log: answered, corrected (after the retry), fallback,
    # round_limit, or the error without its prefix.
    outcome: str = "answered"
    rounds: int = 0
    model_calls: int = 0
    tools: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


async def run_turn(
    model: ModelClient,
    face: Face,
    context: ToolContext,
    *,
    history: Sequence[Message],
    user_text: str,
    timeout_seconds: float,
    max_tool_rounds: int,
    emit: Emit,
) -> TurnResult:
    """Runs the turn and reports how it ended. A timeout or model error ends it with an error;
    anything else, such as a database failure, propagates.
    """
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    turn = _Turn(model, face, context, emit, deadline, TurnResult())
    try:
        async with asyncio.timeout_at(deadline):
            await turn.converse(history, user_text, max_rounds=max_tool_rounds)
    except TimeoutError:
        turn.result.error = "copilot_timeout"
    except ModelUnavailableError:
        turn.result.error = "copilot_unavailable"
    except ModelError:
        turn.result.error = "copilot_failed"
    if turn.result.error is not None:
        turn.result.outcome = turn.result.error.removeprefix("copilot_")
    return turn.result


@dataclass
class _Turn:
    model: ModelClient
    face: Face
    context: ToolContext
    emit: Emit
    deadline: float
    result: TurnResult
    # This turn's successful lookups: their data for the number check, and their plain-text
    # rendering for the fallback reply.
    lookup_data: list[Data] = field(default_factory=list)
    renderings: list[str] = field(default_factory=list)

    async def converse(
        self, history: Sequence[Message], user_text: str, *, max_rounds: int
    ) -> None:
        messages: list[Message] = [
            {"role": "system", "content": self.face.prompt},
            *history,
            {"role": "user", "content": user_text},
        ]
        reply = await self._call(messages, "auto")
        nudged = False
        while True:
            while reply.tool_calls:
                if self.result.rounds == max_rounds:
                    self.result.outcome = "round_limit"
                    self._finish(self._fallback())
                    return
                self.result.rounds += 1
                round_messages: list[Message] = [reply.message]
                for call in reply.tool_calls:
                    data = await self._run_tool(call)
                    round_messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(data)}
                    )
                    self.result.tools.append(call.name)
                messages += round_messages
                self.result.messages += round_messages
                # Ends the lookups' read-only transaction, so no database connection waits on
                # the model.
                await self.context.session.commit()
                reply = await self._call(messages, "auto")
            if reply.text.strip() or nudged:
                break
            # The model sometimes stops between the steps of a task, with neither an answer nor
            # the next lookup. One nudge, with the tools still on offer, lets it continue. The
            # nudge is not stored: the conversation keeps only the lookups and the reply.
            nudged = True
            log.info("copilot_reply_rejected", reason="empty")
            messages = [*messages, {"role": "user", "content": _EMPTY_REPLY_NOTE}]
            reply = await self._call(messages, "auto")

        text = reply.text.strip()
        if not text:
            self.result.outcome = "fallback"
            self._finish(self._fallback())
            return

        user_texts = [m["content"] for m in history if m["role"] == "user"] + [user_text]
        earlier_data = [json.loads(m["content"]) for m in history if m["role"] == "tool"]
        allowed = allowed_runs([*earlier_data, *self.lookup_data], user_texts)

        note = _check(text, allowed)
        if note is None:
            self._finish(text)
            return
        log.info("copilot_reply_rejected", reason="numbers")
        retry_messages = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": note},
        ]
        retry = await self._call(retry_messages, "none")
        retry_text = retry.text.strip()
        if not retry.tool_calls and _check(retry_text, allowed) is None:
            self.result.outcome = "corrected"
            self._finish(retry_text)
        else:
            self.result.outcome = "fallback"
            self._finish(self._fallback())

    async def _call(self, messages: Sequence[Message], tool_choice: ToolChoice) -> ModelReply:
        remaining = self.deadline - asyncio.get_running_loop().time()
        reply = await self.model.complete(
            messages,
            tools=self.face.definitions(),
            tool_choice=tool_choice,
            timeout=remaining,
        )
        self.result.model_calls += 1
        self.result.usage += reply.usage
        return reply

    async def _run_tool(self, call: ToolCall) -> Data:
        """Runs one lookup and returns what the model reads: the tool's data, or an error that
        says what to fix.
        """
        tool = self.face.tool(call.name)
        if tool is None:
            return _tool_error(
                "unknown_tool", f"There is no tool named {call.name!r}. Use only the tools given."
            )
        try:
            arguments = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            arguments = None
        if not isinstance(arguments, dict):
            return _tool_error("invalid_arguments", "The arguments must be a JSON object.")
        try:
            params = tool.params.model_validate(arguments)
        except ValidationError as exc:
            problems = [
                {"field": ".".join(str(part) for part in error["loc"]), "problem": error["msg"]}
                for error in exc.errors()
            ]
            return _tool_error(
                "invalid_arguments",
                "The arguments do not match the tool's parameters.",
                problems=problems,
            )

        await self.emit("status", {"text": tool.status})
        try:
            output = await tool.run(self.context, params)
        except AppError as exc:
            return _tool_error(exc.code, exc.message)
        if output.display is not None:
            display = output.display.model_dump(mode="json", by_alias=True)
            await self.emit("result", {"tool": tool.name, "display": display})
        self.lookup_data.append(output.data)
        self.renderings.append(tool.render(output.data))
        return output.data

    def _fallback(self) -> str:
        unique = list(dict.fromkeys(self.renderings))
        return "\n\n".join([FALLBACK_INTRO, *unique]) if unique else NOTHING_TO_SHOW

    def _finish(self, reply: str) -> None:
        self.result.reply = reply
        self.result.messages.append({"role": "assistant", "content": reply})


def _check(text: str, allowed: set[str]) -> str | None:
    """None when the reply may be sent, otherwise the note that asks the model to fix it."""
    if not text:
        return _EMPTY_REPLY_NOTE
    unsupported = unsupported_numbers(text, allowed)
    if unsupported:
        return _UNSUPPORTED_NUMBERS_NOTE.format(numbers=", ".join(unsupported))
    return None


def _tool_error(code: str, message: str, **details: Any) -> Data:
    return {"error": code, "message": message, **details}
