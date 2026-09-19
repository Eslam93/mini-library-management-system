"""Validated field types for request bodies.

Text is trimmed. Optional text that is blank after trimming becomes null, so an emptied form
field clears the value. Rule failures carry their own error type, such as isbn_checksum, so
clients can show a precise message next to the field.
"""

import re
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints
from pydantic_core import PydanticCustomError

from app.models.book import MIN_PUBLISHED_YEAR
from app.services.isbn import check_digit_matches, has_isbn_shape, normalize_isbn

# One @, no spaces, and a dot in the domain: enough to catch typing mistakes.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


def _valid_isbn(value: str) -> str:
    isbn = normalize_isbn(value)
    if not has_isbn_shape(isbn):
        raise PydanticCustomError(
            "isbn_format", "Enter a 10-digit or 13-digit ISBN (an ISBN-10 may end in X)."
        )
    if not check_digit_matches(isbn):
        raise PydanticCustomError(
            "isbn_checksum", "This ISBN is not valid: its check digit does not match."
        )
    return isbn


def latest_published_year() -> int:
    return datetime.now(UTC).year + 1


def _valid_published_year(value: int) -> int:
    latest = latest_published_year()
    if not MIN_PUBLISHED_YEAR <= value <= latest:
        raise PydanticCustomError(
            "year_out_of_range",
            "Enter a year between {earliest} and {latest}.",
            {"earliest": MIN_PUBLISHED_YEAR, "latest": latest},
        )
    return value


def _valid_email(value: str) -> str:
    if not _EMAIL.fullmatch(value):
        raise PydanticCustomError("email_format", "Enter a valid email address.")
    return value


def _required_text(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


BookTitle = Annotated[str, _required_text(300)]
AuthorName = Annotated[str, _required_text(200)]
FullName = Annotated[str, _required_text(200)]

Category = Annotated[
    Annotated[str, StringConstraints(max_length=100)] | None, BeforeValidator(_blank_to_none)
]
Description = Annotated[
    Annotated[str, StringConstraints(max_length=5000)] | None, BeforeValidator(_blank_to_none)
]
# Accepts hyphens and spaces; the value is stored as digits (and a final X).
ValidIsbn = Annotated[str, StringConstraints(max_length=32), AfterValidator(_valid_isbn)]
Isbn = Annotated[ValidIsbn | None, BeforeValidator(_blank_to_none)]
Email = Annotated[
    Annotated[str, StringConstraints(max_length=254), AfterValidator(_valid_email)] | None,
    BeforeValidator(_blank_to_none),
]
PublishedYear = Annotated[int, AfterValidator(_valid_published_year)] | None
