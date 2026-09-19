"""A title in the catalog. Its physical items are copies."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Normalized form: digits only, with a final X allowed for ISBN-10.
ISBN_PATTERN = "^([0-9]{9}[0-9X]|[0-9]{13})$"
MIN_PUBLISHED_YEAR = 1450
# An ISBN is unique among the books still in the catalog; archiving a book frees its ISBN.
ACTIVE_ISBN_INDEX = "uq_books_isbn_active"


class Book(TimestampMixin, Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(btrim(author)) > 0", name="author_not_blank"),
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint(f"published_year >= {MIN_PUBLISHED_YEAR}", name="published_year_min"),
        Index(ACTIVE_ISBN_INDEX, "isbn", unique=True, postgresql_where=text("archived_at IS NULL")),
        # Trigram indexes serve case-insensitive substring search (ILIKE '%term%').
        Index(
            "ix_books_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_books_author_trgm",
            "author",
            postgresql_using="gin",
            postgresql_ops={"author": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    isbn: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    published_year: Mapped[int | None]
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
