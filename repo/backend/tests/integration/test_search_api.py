import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog(make_book):
    await make_book(title="Dune", author="Frank Herbert", isbn="9780441172719")
    await make_book(title="Dune Messiah", author="Frank Herbert", isbn="9780441172696")
    await make_book(title="The Hobbit", author="J.R.R. Tolkien", isbn="9780547928227")
    await make_book(title="Neuromancer", author="William Gibson", isbn="0441569595")
    await make_book(title="100% Pure Code", author="Ana Lee")


async def titles(client, q, **params):
    response = await client.get("/api/books", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("herb", ["Dune", "Dune Messiah"]),
        ("HERBERT", ["Dune", "Dune Messiah"]),
        ("  hobb ", ["The Hobbit"]),
        ("romanc", ["Neuromancer"]),
        ("tolkien", ["The Hobbit"]),
        ("978-0441", ["Dune", "Dune Messiah"]),
        ("0441172719", ["Dune"]),
        ("928227", ["The Hobbit"]),
        ("0 441 569", ["Neuromancer"]),
    ],
)
async def test_search_matches_partial_title_author_and_isbn(client, q, expected):
    assert await titles(client, q) == expected


@pytest.mark.usefixtures("catalog")
async def test_no_match_is_an_empty_page(client):
    response = await client.get("/api/books", params={"q": "zzzz"})

    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.mark.usefixtures("catalog")
async def test_like_wildcards_in_the_query_match_literally(client):
    assert await titles(client, "%") == ["100% Pure Code"]
    assert await titles(client, "_") == []


@pytest.mark.usefixtures("catalog")
async def test_empty_query_lists_everything_ordered_by_title(client):
    assert await titles(client, "") == [
        "100% Pure Code",
        "Dune",
        "Dune Messiah",
        "Neuromancer",
        "The Hobbit",
    ]


@pytest.mark.usefixtures("catalog")
async def test_paging_returns_the_total_and_the_requested_slice(client):
    response = await client.get("/api/books", params={"limit": 2, "offset": 2})

    page = response.json()
    assert (page["total"], page["limit"], page["offset"]) == (5, 2, 2)
    assert [item["title"] for item in page["items"]] == ["Dune Messiah", "Neuromancer"]


@pytest.mark.usefixtures("catalog")
async def test_search_total_counts_all_matches_not_just_the_page(client):
    response = await client.get("/api/books", params={"q": "dune", "limit": 1})

    page = response.json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
