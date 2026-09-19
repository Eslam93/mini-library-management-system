"""Copilot conversations and their messages, and the borrows and returns the Copilot proposes.

A conversation belongs to one user and one face; the server keeps it so follow-up questions have
the earlier turns as context. A proposal is a change the Copilot prepared and only the user's
confirm makes (app.copilot.proposals).
"""

import uuid
from datetime import datetime
from typing import Any, Literal, get_args

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# The role decides the face: members get the member face, staff the staff face.
CopilotFace = Literal["member", "staff"]
# user: what the person typed. assistant: the model's reply, or its request for lookups.
# tool: the result of one lookup.
CopilotRole = Literal["user", "assistant", "tool"]
# The changes the Copilot may propose.
ProposalAction = Literal["borrow", "return"]
# pending: waiting for the user. confirmed: the change was made. cancelled: the user declined.
# failed: the change was refused when confirmed. expired: not confirmed in time.
ProposalStatus = Literal["pending", "confirmed", "cancelled", "failed", "expired"]
_FACE_SQL_LIST = ", ".join(f"'{value}'" for value in get_args(CopilotFace))
_ROLE_SQL_LIST = ", ".join(f"'{value}'" for value in get_args(CopilotRole))
_ACTION_SQL_LIST = ", ".join(f"'{value}'" for value in get_args(ProposalAction))
_STATUS_SQL_LIST = ", ".join(f"'{value}'" for value in get_args(ProposalStatus))


class CopilotConversation(TimestampMixin, Base):
    __tablename__ = "copilot_conversations"
    __table_args__ = (CheckConstraint(f"face IN ({_FACE_SQL_LIST})", name="face_allowed"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    face: Mapped[str] = mapped_column(Text)


class CopilotMessage(Base):
    """One message. content holds it in the shape the model reads it back (see
    app.copilot.conversations); the id orders messages within a conversation.
    """

    __tablename__ = "copilot_messages"
    __table_args__ = (
        CheckConstraint(f"role IN ({_ROLE_SQL_LIST})", name="role_allowed"),
        # The latest messages of a conversation, newest first.
        Index("ix_copilot_messages_conversation_id_id", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("copilot_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CopilotProposal(Base):
    """A borrow or a return the Copilot prepared for one user. The random id is the handle the
    panel confirms with. params hold what the change needs (borrow: copy_id, member_id,
    due_date; return: loan_id), summary what the card shows, and result the outcome (loan_id
    after a confirm, error {code, message} after a failure).
    """

    __tablename__ = "copilot_proposals"
    __table_args__ = (
        CheckConstraint(f"action IN ({_ACTION_SQL_LIST})", name="action_allowed"),
        CheckConstraint(f"status IN ({_STATUS_SQL_LIST})", name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The conversation that proposed it, told the outcome while it exists.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("copilot_conversations.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
