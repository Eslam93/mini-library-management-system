"""ISBN lookup for the add-book form. Staff only, like adding a book."""

from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.api.deps import StaffUser
from app.schemas.books import IsbnLookupOut
from app.schemas.common import ErrorResponse, error_responses
from app.schemas.fields import ValidIsbn
from app.services.isbn_lookup import IsbnLookup, IsbnLookupUnavailableError

router = APIRouter(prefix="/isbn", tags=["isbn"])

IsbnPath = Annotated[ValidIsbn, Path(description="An ISBN-10 or ISBN-13; hyphens are ignored")]


@router.get(
    "/{isbn}",
    responses={
        **error_responses(staff=True),
        404: {"model": ErrorResponse, "description": "isbn_not_found: no book has this ISBN"},
        503: {
            "model": ErrorResponse,
            "description": "isbn_lookup_unavailable: the lookup is turned off, or the service "
            "timed out, could not be reached or answered with an error",
        },
    },
)
async def lookup_isbn(request: Request, _: StaffUser, isbn: IsbnPath) -> IsbnLookupOut:
    """The title, first author and first publication year of the book with this ISBN, from Open
    Library. 422 when the ISBN's check digit does not match.
    """
    lookup: IsbnLookup | None = request.app.state.isbn_lookup
    if lookup is None:
        raise IsbnLookupUnavailableError()
    book = await lookup.find(isbn)
    return IsbnLookupOut(
        isbn=book.isbn, title=book.title, author=book.author, published_year=book.published_year
    )
