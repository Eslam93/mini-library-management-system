"""Copilot conversations as stored, and their messages as the model reads them back.

A message's content is the chat message without its role (a column of its own): a user
message is {"content": text}; an assistant message is what the model sent, its text and any
lookup requests; a lookup result is {"tool_call_id", "result"}, with the result as JSON rather
than as the text the model receives.
"""

import json
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.copilot.model import Message
from app.core.exceptions import NotFoundError
from app.models import CopilotConversation, CopilotFace, CopilotMessage, User

# How many of the latest messages the model gets as the conversation so far.
HISTORY_LIMIT = 20


async def find(
    session: AsyncSession, conversation_id: uuid.UUID, *, user: User, face: CopilotFace
) -> CopilotConversation:
    """The user's conversation with this face. Another user's is not found, like a missing one."""
    conversation = await session.scalar(
        select(CopilotConversation).where(
            CopilotConversation.id == conversation_id,
            CopilotConversation.user_id == user.id,
            CopilotConversation.face == face,
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


async def start(session: AsyncSession, *, user: User, face: CopilotFace) -> CopilotConversation:
    conversation = CopilotConversation(user_id=user.id, face=face)
    session.add(conversation)
    await session.flush()
    return conversation


async def add(
    session: AsyncSession, conversation_id: uuid.UUID, messages: Iterable[Message]
) -> None:
    """Adds the messages to the conversation, in order, and marks it updated. The caller
    commits.
    """
    session.add_all(
        CopilotMessage(conversation_id=conversation_id, role=m["role"], content=_stored(m))
        for m in messages
    )
    await session.execute(
        update(CopilotConversation)
        .where(CopilotConversation.id == conversation_id)
        .values(updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


async def history(
    session: AsyncSession, conversation_id: uuid.UUID, *, limit: int = HISTORY_LIMIT
) -> list[Message]:
    """The latest messages, oldest first, starting at a user message so that no lookup result
    is separated from the request that asked for it.
    """
    rows = await session.scalars(
        select(CopilotMessage)
        .where(CopilotMessage.conversation_id == conversation_id)
        .order_by(CopilotMessage.id.desc())
        .limit(limit)
    )
    messages = [_message(row) for row in reversed(rows.all())]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def _stored(message: Message) -> dict[str, Any]:
    content = {key: value for key, value in message.items() if key != "role"}
    if message["role"] == "tool":
        return {"tool_call_id": content["tool_call_id"], "result": json.loads(content["content"])}
    return content


def _message(row: CopilotMessage) -> Message:
    if row.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": row.content["tool_call_id"],
            "content": json.dumps(row.content["result"]),
        }
    return {"role": row.role, **row.content}
