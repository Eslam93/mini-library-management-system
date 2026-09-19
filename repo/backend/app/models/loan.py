"""A copy lent to a member. The loan is active until returned_at is set.

Whether a loan is overdue is derived when reading (active and past due_at), never stored.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# The database guarantees at most one active loan per copy. The circulation service turns a
# violation of this index into a copy_unavailable conflict.
ACTIVE_LOAN_PER_COPY_INDEX = "uq_loans_copy_id_active"


class Loan(TimestampMixin, Base):
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint("due_at > borrowed_at", name="due_after_borrowed"),
        CheckConstraint("returned_at >= borrowed_at", name="returned_after_borrowed"),
        Index(
            ACTIVE_LOAN_PER_COPY_INDEX,
            "copy_id",
            unique=True,
            postgresql_where=text("returned_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    copy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("copies.id"), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    borrowed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
