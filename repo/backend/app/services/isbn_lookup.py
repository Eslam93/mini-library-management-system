"""Finding a book's title, author and year by its ISBN, from Open Library's public catalog, so the
add-book form can fill them in.

The server asks, not the browser: one call to the search endpoint gives the title, the authors
and the first publication year. The service can take many seconds for an ISBN it does not know,
so each call has a short deadline, and a timeout, a network error or an answer other than 200 is
reported as the service being unavailable: the form still works by hand. Answers, "no such book"
included, are kept in memory for a day, up to a fixed number of ISBNs, oldest dropped first. The
memory is per process and starts empty on each restart.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from fastapi import status
from pydantic import BaseModel, ValidationError

from app.core.exceptions import AppError, NotFoundError
from app.core.logging import get_logger
from app.models.book import MIN_PUBLISHED_YEAR
from app.schemas.fields import latest_published_year

log = get_logger(__name__)

SEARCH_URL = "https://openlibrary.org/search.json"
USER_AGENT = "LibraryCatalog/0.1 (ISBN lookup for the add-book form)"
TIMEOUT_SECONDS = 6.0
CACHE_SECONDS = 24 * 3600
MAX_CACHED = 1000


class IsbnLookupUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "isbn_lookup_unavailable"
    message = "The ISBN lookup service is not available. Fill in the book's details by hand."


def isbn_not_found() -> NotFoundError:
    return NotFoundError("No book was found for this ISBN.", code="isbn_not_found")


@dataclass(frozen=True)
class IsbnBook:
    isbn: str
    title: str
    # The first author named.
    author: str
    # The first publication year, when the catalog accepts it.
    published_year: int | None


class _Doc(BaseModel):
    title: str | None = None
    author_name: list[str] | None = None
    first_publish_year: int | None = None


class _Search(BaseModel):
    docs: list[_Doc]


def _book(isbn: str, search: _Search) -> IsbnBook | None:
    """The first match, or None when there is none or it lacks a title or an author."""
    if not search.docs:
        return None
    doc = search.docs[0]
    title = (doc.title or "").strip()
    authors = [name.strip() for name in doc.author_name or [] if name.strip()]
    if not title or not authors:
        return None
    year = doc.first_publish_year
    if year is not None and not MIN_PUBLISHED_YEAR <= year <= latest_published_year():
        year = None
    return IsbnBook(isbn=isbn, title=title, author=authors[0], published_year=year)


class IsbnLookup:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        timeout: float = TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._timeout = timeout
        self._clock = clock
        # isbn -> (when it was asked, the book or None for no book). Oldest first.
        self._cache: dict[str, tuple[float, IsbnBook | None]] = {}

    async def find(self, isbn: str) -> IsbnBook:
        """The book with this normalized, valid ISBN. isbn_not_found when the service knows no
        book, isbn_lookup_unavailable when it cannot be asked.
        """
        now = self._clock()
        cached = self._cache.get(isbn)
        if cached is not None and now - cached[0] < CACHE_SECONDS:
            book = cached[1]
        else:
            book = _book(isbn, await self._search(isbn))
            self._remember(isbn, now, book)
        if book is None:
            raise isbn_not_found()
        return book

    async def _search(self, isbn: str) -> _Search:
        params = {"isbn": isbn, "fields": "title,author_name,first_publish_year", "limit": "1"}
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            # httpx's timeout bounds each network step, so the whole call has a deadline too.
            async with asyncio.timeout(self._timeout):
                response = await self._http.get(
                    SEARCH_URL, params=params, headers=headers, timeout=self._timeout
                )
        except (TimeoutError, httpx.HTTPError) as exc:
            log.warning("isbn_lookup_failed", reason=type(exc).__name__)
            raise IsbnLookupUnavailableError() from exc
        if response.status_code != httpx.codes.OK:
            log.warning("isbn_lookup_failed", reason="status", status=response.status_code)
            raise IsbnLookupUnavailableError()
        try:
            return _Search.model_validate_json(response.content)
        except ValidationError as exc:
            log.warning("isbn_lookup_failed", reason="unexpected_response")
            raise IsbnLookupUnavailableError() from exc

    def _remember(self, isbn: str, now: float, book: IsbnBook | None) -> None:
        self._cache.pop(isbn, None)
        while len(self._cache) >= MAX_CACHED:
            del self._cache[next(iter(self._cache))]
        self._cache[isbn] = (now, book)
