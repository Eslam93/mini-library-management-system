"""One physical copy of a book, labelled on the shelf with a code such as CP-0001."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Sequence, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Copy codes are numbered from this sequence, so a number is never handed out twice.
COPY_CODE_SEQUENCE = Sequence("copy_code_seq", metadata=Base.metadata)


def format_copy_code(number: int) -> str:
    """CP- followed by the number, padded to at least four digits."""
    return f"CP-{number:04d}"


class Copy(TimestampMixin, Base):
    __tablename__ = "copies"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
