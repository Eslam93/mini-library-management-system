"""core catalog and circulation

Books and their copies, members, loans and the activity record, with the indexes that search
and the one-active-loan-per-copy rule depend on.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _trigram_index(name: str, table: str, column: str) -> None:
    op.create_index(
        name,
        table,
        [column],
        postgresql_using="gin",
        postgresql_ops={column: "gin_trgm_ops"},
    )


def upgrade() -> None:
    # Trigram matching makes case-insensitive substring search fast.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE SEQUENCE copy_code_seq")

    op.create_table(
        "books",
        _uuid_pk(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("isbn", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("published_year", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f("ck_books_title_not_blank")),
        sa.CheckConstraint("length(btrim(author)) > 0", name=op.f("ck_books_author_not_blank")),
        sa.CheckConstraint(
            "isbn ~ '^([0-9]{9}[0-9X]|[0-9]{13})$'", name=op.f("ck_books_isbn_format")
        ),
        sa.CheckConstraint("published_year >= 1450", name=op.f("ck_books_published_year_min")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_books")),
    )
    # An ISBN is unique among the books still in the catalog; archiving frees it.
    op.create_index(
        "uq_books_isbn_active",
        "books",
        ["isbn"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    _trigram_index("ix_books_title_trgm", "books", "title")
    _trigram_index("ix_books_author_trgm", "books", "author")

    op.create_table(
        "copies",
        _uuid_pk(),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_copies_book_id_books"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copies")),
        sa.UniqueConstraint("code", name=op.f("uq_copies_code")),
    )
    op.create_index(op.f("ix_copies_book_id"), "copies", ["book_id"])

    op.create_table(
        "members",
        _uuid_pk(),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("joined_on", sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "length(btrim(full_name)) > 0", name=op.f("ck_members_full_name_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_members")),
    )
    op.create_index(
        "uq_members_email_lower", "members", [sa.literal_column("lower(email)")], unique=True
    )
    _trigram_index("ix_members_full_name_trgm", "members", "full_name")

    op.create_table(
        "loans",
        _uuid_pk(),
        sa.Column("copy_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column(
            "borrowed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("due_at > borrowed_at", name=op.f("ck_loans_due_after_borrowed")),
        sa.CheckConstraint(
            "returned_at >= borrowed_at", name=op.f("ck_loans_returned_after_borrowed")
        ),
        sa.ForeignKeyConstraint(["copy_id"], ["copies.id"], name=op.f("fk_loans_copy_id_copies")),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_loans_member_id_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loans")),
    )
    op.create_index(op.f("ix_loans_copy_id"), "loans", ["copy_id"])
    op.create_index(op.f("ix_loans_member_id"), "loans", ["member_id"])
    # At most one active loan per copy: two simultaneous borrows cannot both succeed.
    op.create_index(
        "uq_loans_copy_id_active",
        "loans",
        ["copy_id"],
        unique=True,
        postgresql_where=sa.text("returned_at IS NULL"),
    )

    op.create_table(
        "activity_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("via", sa.Text(), server_default="ui", nullable=False),
        sa.CheckConstraint(
            "via IN ('ui', 'copilot', 'system')", name=op.f("ck_activity_events_via_allowed")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity_events")),
    )
    op.create_index("ix_activity_events_occurred_at", "activity_events", ["occurred_at"])


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints with it.
    op.drop_table("activity_events")
    op.drop_table("loans")
    op.drop_table("members")
    op.drop_table("copies")
    op.drop_table("books")
    op.execute("DROP SEQUENCE copy_code_seq")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
