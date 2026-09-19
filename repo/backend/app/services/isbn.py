"""ISBN normalization and check-digit rules for ISBN-10 and ISBN-13."""

import re

_SEPARATORS = re.compile(r"[\s-]+")
_ISBN10 = re.compile(r"[0-9]{9}[0-9X]")
_ISBN13 = re.compile(r"[0-9]{13}")
# What a search term looks like once separators are removed, when it could be part of an ISBN.
_ISBN_FRAGMENT = re.compile(r"[0-9]+X?")


def normalize_isbn(raw: str) -> str:
    """Removes spaces and hyphens and upper-cases a final x: "0-441-17271-7" -> "0441172717"."""
    return _SEPARATORS.sub("", raw).upper()


def has_isbn_shape(isbn: str) -> bool:
    """True for 10 characters (digits, a final X allowed) or 13 digits."""
    return bool(_ISBN10.fullmatch(isbn) or _ISBN13.fullmatch(isbn))


def check_digit_matches(isbn: str) -> bool:
    """True when a normalized ISBN-10 or ISBN-13 passes its checksum."""
    if _ISBN10.fullmatch(isbn):
        # Weights 10 down to 1; X stands for 10.
        values = [10 if char == "X" else int(char) for char in isbn]
        return sum((10 - i) * value for i, value in enumerate(values)) % 11 == 0
    if _ISBN13.fullmatch(isbn):
        return sum(int(char) * (3 if i % 2 else 1) for i, char in enumerate(isbn)) % 10 == 0
    return False


def isbn_search_fragment(term: str) -> str | None:
    """The normalized digits of a search term that could be part of an ISBN, otherwise None."""
    fragment = normalize_isbn(term)
    return fragment if _ISBN_FRAGMENT.fullmatch(fragment) else None
