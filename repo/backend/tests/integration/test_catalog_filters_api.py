"""The catalog's filters and orders: availability, category and the four sorts, alone and with the
search box, and the categories the filter offers.

| Book | Author | Category | Year | Copies | Added |
|---|---|---|---|---|---|
| A Game of Thrones | George R. R. Martin | Fantasy | 1996 | 1, on loan | 1 Mar 2026 |
| Dune | Frank Herbert | Science Fiction | 1965 | 1, on loan | 1 Jun 2025 |
| Middlemarch | George Eliot | none | none | 1 | 1 Jan 2026 |
| Mistborn | Brandon Sanderson | Fantasy | 2006 | 1 | 1 Mar 2026 |
| The Hobbit | J.R.R. Tolkien | Fantasy | 1937 | 2 | 1 Jan 2024 |
| Old Atlas | Ann Mapper | Travel | 1990 | 1 | archived |
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.models import Book

pytestmark = pytest.mark.integration

ADDED = {
    "A Game of Thrones": datetime(2026, 3, 1, tzinfo=UTC),
    "Dune": datetime(2025, 6, 1, tzinfo=UTC),
    "Middlemarch": datetime(2026, 1, 1, tzinfo=UTC),
    "Mistborn": datetime(2026, 3, 1, tzinfo=UTC),
    "The Hobbit": datetime(2024, 1, 1, tzinfo=UTC),
}


@pytest.fixture
async def shelves(make_book, make_member, borrow, empty_db):
    thrones = await make_book(
        title="A Game of Thrones",
        author="George R. R. Martin",
        category="Fantasy",
        published_year=1996,
    )
    dune = await make_book(
        title="Dune", author="Frank Herbert", category="Science Fiction", published_year=1965
    )
    await make_book(title="Middlemarch", author="George Eliot")
    await make_book(
        title="Mistborn", author="Brandon Sanderson", category="Fantasy", published_year=2006
    )
    await make_book(
        title="The Hobbit",
        author="J.R.R. Tolkien",
        category="Fantasy",
        published_year=1937,
        copies=2,
    )
    await make_book(title="Old Atlas", author="Ann Mapper", category="Travel", published_year=1990)
    member = await make_member()
    for book in (thrones, dune):
        response = await borrow(book["copies"][0]["id"], member["id"])
        assert response.status_code == 201, response.text
    # Books added in one test transaction share its clock, so each gets its own day here.
    for title, added in ADDED.items():
        await empty_db.execute(update(Book).where(Book.title == title).values(created_at=added))
    await empty_db.execute(
        update(Book).where(Book.title == "Old Atlas").values(archived_at=datetime.now(UTC))
    )
    await empty_db.commit()


async def titles(client, **params) -> list[str]:
    response = await client.get("/api/books", params=params)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == len(page["items"])
    return [item["title"] for item in page["items"]]


@pytest.mark.usefixtures("shelves")
async def test_category_matches_the_whole_name_in_any_letter_case(client):
    assert await titles(client, category="fantasy") == [
        "A Game of Thrones",
        "Mistborn",
        "The Hobbit",
    ]
    assert await titles(client, category="Fan") == []
    assert await titles(client, category="Travel") == []


@pytest.mark.usefixtures("shelves")
async def test_available_only_keeps_books_with_a_copy_on_the_shelf(client):
    assert await titles(client, available_only="true") == ["Middlemarch", "Mistborn", "The Hobbit"]
    assert await titles(client, available_only="false") == [
        "A Game of Thrones",
        "Dune",
        "Middlemarch",
        "Mistborn",
        "The Hobbit",
    ]


@pytest.mark.usefixtures("shelves")
@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("title", ["A Game of Thrones", "Dune", "Middlemarch", "Mistborn", "The Hobbit"]),
        # By the author's name as written, first name first.
        ("author", ["Mistborn", "Dune", "Middlemarch", "A Game of Thrones", "The Hobbit"]),
        # Newest publication year first, a book without one last.
        ("year_desc", ["Mistborn", "A Game of Thrones", "Dune", "The Hobbit", "Middlemarch"]),
        # Most recently added first; the two added on 1 Mar 2026 by title.
        ("recent", ["A Game of Thrones", "Mistborn", "Middlemarch", "Dune", "The Hobbit"]),
    ],
)
async def test_each_sort_order(client, sort, expected):
    assert await titles(client, sort=sort) == expected


@pytest.mark.usefixtures("shelves")
async def test_filters_sort_and_search_work_together(client):
    assert await titles(client, category="Fantasy", available_only="true", sort="recent") == [
        "Mistborn",
        "The Hobbit",
    ]
    assert await titles(client, q="george", sort="year_desc") == [
        "A Game of Thrones",
        "Middlemarch",
    ]
    assert await titles(client, q="the", category="Fantasy", available_only="true") == [
        "The Hobbit"
    ]


@pytest.mark.usefixtures("shelves")
async def test_a_book_added_now_comes_first_in_recently_added(client, make_book):
    await make_book(title="Piranesi", author="Susanna Clarke", category="Fantasy")

    assert (await titles(client, sort="recent"))[:2] == ["Piranesi", "A Game of Thrones"]


@pytest.mark.usefixtures("shelves")
async def test_an_unknown_sort_is_422(client):
    response = await client.get("/api/books", params={"sort": "popular"})

    assert response.status_code == 422
    [error] = response.json()["error"]["details"]["errors"]
    assert error["location"] == ["query", "sort"]


@pytest.mark.usefixtures("shelves")
async def test_the_categories_are_those_of_the_books_in_the_catalog(client, member_client):
    staff = await client.get("/api/books/categories")
    member = await member_client.get("/api/books/categories")

    # No archived book's category, and no empty one.
    assert staff.status_code == 200
    assert staff.json() == ["Fantasy", "Science Fiction"]
    assert member.json() == ["Fantasy", "Science Fiction"]


async def test_categories_need_a_sign_in(anonymous):
    response = await anonymous.get("/api/books/categories")

    assert response.status_code == 401
