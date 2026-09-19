"""The constraints and indexes that the rules and search depend on exist as migrated."""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def index_definitions(session, table):
    rows = await session.execute(
        text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :table"),
        {"table": table},
    )
    return dict(rows.tuples().all())


async def test_one_active_loan_per_copy_is_a_partial_unique_index(db_session):
    definition = (await index_definitions(db_session, "loans"))["uq_loans_copy_id_active"]

    assert "CREATE UNIQUE INDEX" in definition
    assert "(copy_id) WHERE (returned_at IS NULL)" in definition


async def test_isbn_is_unique_among_books_not_archived(db_session):
    definition = (await index_definitions(db_session, "books"))["uq_books_isbn_active"]

    assert "CREATE UNIQUE INDEX" in definition
    assert "(isbn) WHERE (archived_at IS NULL)" in definition


async def test_member_email_is_unique_ignoring_case(db_session):
    definition = (await index_definitions(db_session, "members"))["uq_members_email_lower"]

    assert "CREATE UNIQUE INDEX" in definition
    assert "lower(email)" in definition


@pytest.mark.parametrize(
    ("table", "index", "column"),
    [
        ("books", "ix_books_title_trgm", "title"),
        ("books", "ix_books_author_trgm", "author"),
        ("members", "ix_members_full_name_trgm", "full_name"),
    ],
)
async def test_search_columns_have_trigram_indexes(db_session, table, index, column):
    definition = (await index_definitions(db_session, table))[index]

    assert f"USING gin ({column} gin_trgm_ops)" in definition


async def test_trigram_index_serves_substring_search(db_session):
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = await db_session.execute(text("EXPLAIN SELECT id FROM books WHERE title ILIKE '%herb%'"))

    assert "ix_books_title_trgm" in "\n".join(plan.scalars())


async def test_copy_codes_come_from_a_sequence(db_session):
    first = await db_session.scalar(text("SELECT nextval('copy_code_seq')"))
    second = await db_session.scalar(text("SELECT nextval('copy_code_seq')"))

    assert second == first + 1
