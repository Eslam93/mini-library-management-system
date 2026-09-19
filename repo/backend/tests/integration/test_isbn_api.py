"""GET /api/isbn/{isbn}: the add-book form's lookup, with the service behind a mock transport.
Nothing here reaches the network.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack

import httpx
import pytest

from app.services.isbn_lookup import IsbnLookup

pytestmark = pytest.mark.integration

HOBBIT = "9780547928227"
HOBBIT_DOC = {"title": "The Hobbit", "author_name": ["J.R.R. Tolkien"], "first_publish_year": 1937}


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


@pytest.fixture
async def lookup_as(make_db_app, serve, sign_in) -> AsyncIterator[Callable]:
    """Opens a client of an app whose lookup asks this service, signed in as the role."""
    async with AsyncExitStack() as stack:

        async def _open(service: Service, role: str = "staff") -> httpx.AsyncClient:
            app = make_db_app()
            mock = httpx.AsyncClient(transport=httpx.MockTransport(service))
            app.state.isbn_lookup = IsbnLookup(mock)
            http = await stack.enter_async_context(serve(app))
            await sign_in(http, role)
            return http

        yield _open


async def test_a_known_isbn_gives_title_first_author_and_year(lookup_as):
    service = Service(httpx.Response(200, json={"numFound": 1, "docs": [HOBBIT_DOC]}))
    http = await lookup_as(service)

    response = await http.get("/api/isbn/978-0-547-92822-7")

    assert response.status_code == 200
    assert response.json() == {
        "isbn": HOBBIT,
        "title": "The Hobbit",
        "author": "J.R.R. Tolkien",
        "published_year": 1937,
    }
    # The ISBN is asked for as digits.
    assert service.requests[0].url.params["isbn"] == HOBBIT


async def test_the_same_isbn_again_is_answered_from_memory(lookup_as):
    service = Service(httpx.Response(200, json={"numFound": 1, "docs": [HOBBIT_DOC]}))
    http = await lookup_as(service)

    first = await http.get(f"/api/isbn/{HOBBIT}")
    second = await http.get(f"/api/isbn/{HOBBIT}")

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json() == first.json()
    assert len(service.requests) == 1


async def test_an_isbn_the_service_does_not_know_is_404(lookup_as):
    http = await lookup_as(Service(httpx.Response(200, json={"numFound": 0, "docs": []})))

    response = await http.get("/api/isbn/0441172717")

    assert response.status_code == 404
    error = response.json()["error"]
    assert (error["code"], error["message"]) == (
        "isbn_not_found",
        "No book was found for this ISBN.",
    )


@pytest.mark.parametrize(
    ("isbn", "error_type"),
    [("9780547928228", "isbn_checksum"), ("12345", "isbn_format")],
)
async def test_an_isbn_with_a_wrong_check_digit_or_shape_is_422_without_asking(
    lookup_as, isbn, error_type
):
    service = Service()
    http = await lookup_as(service)

    response = await http.get(f"/api/isbn/{isbn}")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_failed"
    [error] = body["details"]["errors"]
    assert (error["location"], error["type"]) == (["path", "isbn"], error_type)
    assert service.requests == []


@pytest.mark.parametrize(
    "failure",
    [httpx.ReadTimeout("slow"), httpx.ConnectError("unreachable"), httpx.Response(502)],
)
async def test_a_timeout_or_a_service_error_is_503(lookup_as, failure):
    http = await lookup_as(Service(failure))

    response = await http.get(f"/api/isbn/{HOBBIT}")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "isbn_lookup_unavailable"
    assert error["message"] == (
        "The ISBN lookup service is not available. Fill in the book's details by hand."
    )


async def test_the_lookup_turned_off_is_503(make_db_app, serve, sign_in):
    app = make_db_app(isbn_lookup_enabled=False)

    async with serve(app) as http:
        await sign_in(http, "staff")
        response = await http.get(f"/api/isbn/{HOBBIT}")

    assert app.state.isbn_lookup is None
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "isbn_lookup_unavailable"


async def test_turned_on_the_app_holds_a_lookup(make_db_app):
    assert isinstance(make_db_app(isbn_lookup_enabled=True).state.isbn_lookup, IsbnLookup)


async def test_members_cannot_look_up(lookup_as):
    service = Service()
    http = await lookup_as(service, role="member")

    response = await http.get(f"/api/isbn/{HOBBIT}")

    assert response.status_code == 403
    assert service.requests == []
