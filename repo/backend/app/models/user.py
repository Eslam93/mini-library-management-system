"""Someone who can sign in: staff, or a member linked to their member record."""

import uuid
from datetime import datetime
from typing import Literal, get_args

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

UserRole = Literal["staff", "member"]
_ROLE_SQL_LIST = ", ".join(f"'{value}'" for value in get_args(UserRole))

# Two users cannot share an email address, whatever its letter case.
USER_EMAIL_INDEX = "uq_users_email_lower"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({_ROLE_SQL_LIST})", name="role_allowed"),
        # A member signs in as their member record, so their loans are theirs.
        CheckConstraint("role <> 'member' OR member_id IS NOT NULL", name="member_has_record"),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_not_blank"),
        Index(USER_EMAIL_INDEX, func.lower(text("email")), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    member_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("members.id"), unique=True)
    # The Google account's stable subject id, once the user has signed in with Google.
    google_sub: Mapped[str | None] = mapped_column(Text, unique=True)
    # The demo sign-in accounts, one per role.
    is_demo: Mapped[bool] = mapped_column(default=False, server_default=false())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_staff(self) -> bool:
        return self.role == "staff"
