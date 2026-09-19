"""The append-only record of actions: what happened, to which record, and through which
channel. Application code only inserts rows.
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

from app.db.base import Base

# ui: a person using the web app. copilot: the AI module, after the user confirmed.
# system: the development seed and background jobs.
ActivityVia = Literal["ui", "copilot", "system"]
_VIA_SQL_LIST = ", ".join(f"'{value}'" for value in get_args(ActivityVia))


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        CheckConstraint(f"via IN ({_VIA_SQL_LIST})", name="via_allowed"),
        Index("ix_activity_events_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Who acted: their display name at the time, and their user id while that user exists.
    # Both are empty for the development seed and other system work.
    actor: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None]
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    via: Mapped[str] = mapped_column(Text, server_default="ui")
