"""A person who borrows. A member may or may not have a sign-in."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Two members cannot share an email address, whatever its letter case.
MEMBER_EMAIL_INDEX = "uq_members_email_lower"


class Member(TimestampMixin, Base):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint("length(btrim(full_name)) > 0", name="full_name_not_blank"),
        Index(MEMBER_EMAIL_INDEX, func.lower(text("email")), unique=True),
        Index(
            "ix_members_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    joined_on: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
