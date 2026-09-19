"""The ISBN lookup over a mock transport: the request it sends, the book it reads, the service
being unavailable in each way, and the memory of earlier answers. Nothing reaches the network.
"""

import asyncio
from typing import Any

import httpx
import pytest

from app.core.exceptions import NotFoundError
from app.services import isbn_lookup
from app.services.isbn_lookup import IsbnBook, IsbnLookup, IsbnLookupUnavailableError

HOBBIT = "9780547928227"


def found(**doc: Any) -> httpx.Response:
    fields = {"title": "The Hobbit", "author_name": ["J.R.R. Tolkien"], "first_publish_year": 1937}
    return httpx.Response(200, json={"numFound": 1, "docs": [{**fields, **doc}]})


NOTHING = httpx.Response(200, json={"numFound": 0, "docs": []})


class Service:
    """Answers each request with the next response, or raises it, and records the requests."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_lookup(service, clock: Clock | None = None, timeout: float = 6.0) -> IsbnLookup:
    http = httpx.AsyncClient(transport=httpx.MockTransport(service))
    return IsbnLookup(http, timeout=timeout, clock=clock or Clock())


async def test_it_asks_the_search_endpoint_for_one_book_naming_the_app():
    service = Service(found())

    book = await make_lookup(service).find(HOBBIT)

    assert book == IsbnBook(HOBBIT, "The Hobbit", "J.R.R. Tolkien", 1937)
    [request] = service.requests
    assert (request.url.host, request.url.path) == ("openlibrary.org", "/search.json")
    assert dict(request.url.params) == {
        "isbn": HOBBIT,
        "fields": "title,author_name,first_publish_year",
        "limit": "1",
    }
    assert request.headers["user-agent"].startswith("LibraryCatalog/")


async def test_the_first_author_is_kept_and_a_year_the_catalog_refuses_is_left_out():
    service = Service(
        found(author_name=["  ", "Terry Pratchett", "Neil Gaiman"], first_publish_year=1200),
        found(first_publish_year=None),
    )
    lookup = make_lookup(service)

    first = await lookup.find("9780060853983")
    second = await lookup.find(HOBBIT)

    assert (first.author, first.published_year) == ("Terry Pratchett", None)
    assert second.published_year is None


@pytest.mark.parametrize(
    "response",
    [
        NOTHING,
        found(title="  "),
        found(author_name=[]),
        httpx.Response(200, json={"docs": [{"title": "Untitled Pamphlet"}]}),
    ],
)
async def test_no_book_or_one_without_a_title_or_an_author_is_not_found(response):
    with pytest.raises(NotFoundError) as caught:
        await make_lookup(Service(response)).find(HOBBIT)

    assert caught.value.code == "isbn_not_found"


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("unreachable"),
        httpx.Response(500),
        httpx.Response(429),
        httpx.Response(200, content=b"<html>maintenance</html>"),
        httpx.Response(200, json={"error": "bad request"}),
    ],
)
async def test_a_timeout_a_network_error_or_an_unexpected_answer_is_unavailable(failure):
    with pytest.raises(IsbnLookupUnavailableError) as caught:
        await make_lookup(Service(failure)).find(HOBBIT)

    assert (caught.value.status_code, caught.value.code) == (503, "isbn_lookup_unavailable")


async def test_the_whole_call_has_a_deadline():
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return found()

    with pytest.raises(IsbnLookupUnavailableError):
        await make_lookup(slow, timeout=0.05).find(HOBBIT)


async def test_answers_are_remembered_for_a_day_not_found_included():
    clock = Clock()
    service = Service(found(), NOTHING, found(title="The Hobbit, or There and Back Again"))
    lookup = make_lookup(service, clock)
    unknown = "9780000000002"

    await lookup.find(HOBBIT)
    with pytest.raises(NotFoundError):
        await lookup.find(unknown)
    clock.now += 24 * 3600 - 1
    remembered = await lookup.find(HOBBIT)
    with pytest.raises(NotFoundError):
        await lookup.find(unknown)
    clock.now += 1
    asked_again = await lookup.find(HOBBIT)

    assert len(service.requests) == 3
    assert remembered.title == "The Hobbit"
    assert asked_again.title == "The Hobbit, or There and Back Again"


async def test_a_failure_is_not_remembered():
    service = Service(httpx.ReadTimeout("slow"), found())
    lookup = make_lookup(service)

    with pytest.raises(IsbnLookupUnavailableError):
        await lookup.find(HOBBIT)
    book = await lookup.find(HOBBIT)

    assert book.title == "The Hobbit"


async def test_the_oldest_answer_goes_when_the_memory_is_full(monkeypatch):
    monkeypatch.setattr(isbn_lookup, "MAX_CACHED", 2)
    isbns = ["9780547928227", "9780441172719", "9780060853983"]
    service = Service(*(found() for _ in range(4)))
    lookup = make_lookup(service)

    for isbn in isbns:
        await lookup.find(isbn)
    # The second and third are remembered; the first was dropped and is asked again.
    await lookup.find(isbns[2])
    await lookup.find(isbns[1])
    await lookup.find(isbns[0])

    asked = [request.url.params["isbn"] for request in service.requests]
    assert asked == [*isbns, isbns[0]]
