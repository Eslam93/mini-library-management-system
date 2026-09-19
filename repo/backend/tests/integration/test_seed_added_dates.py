"""The demo library records when each title entered it: a book's created_at is the moment the
generated history added it, in the opening week or later, which the catalog's "recently added"
order and the titles-not-borrowed figure read.

A small library over two years ending today keeps this fast while leaving room for titles that
arrive after the opening week.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Book
from app.seed import GeneratorOptions, seed
from app.seed.simulation import simulate
from app.services import catalog
from app.services.circulation import today_utc

pytestmark = pytest.mark.integration


def two_years() -> GeneratorOptions:
    today = today_utc()
    return GeneratorOptions(today=today, start=today - timedelta(days=730), titles=60, members=30)


async def test_each_book_is_dated_the_day_it_entered_the_library(empty_db):
    options = two_years()
    history = simulate(options)
    await seed(empty_db, options)

    stored = dict((await empty_db.execute(select(Book.id, Book.created_at))).tuples().all())
    opening_week_ends = options.start + timedelta(days=7)
    later = [book for book in history.books if book.added_at.date() > opening_week_ends]

    assert stored == {book.id: book.added_at for book in history.books}
    assert later, "some titles should arrive after the opening week"
    assert all(book.added_at.date() >= options.start for book in history.books)


async def test_recently_added_lists_the_latest_arrivals_first(empty_db):
    options = two_years()
    history = simulate(options)
    await seed(empty_db, options)

    page = await catalog.list_books(empty_db, q=None, sort="recent", limit=5, offset=0)

    newest = sorted(
        history.books, key=lambda book: (-book.added_at.timestamp(), book.entry.title.lower())
    )
    assert [book.title for book in page.items] == [book.entry.title for book in newest[:5]]
