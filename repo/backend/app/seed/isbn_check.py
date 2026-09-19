"""Checks the demo catalog's ISBNs against Open Library, and corrects or drops the ones that do not
belong to their book.

Run with: python -m app.seed.isbn_check [--write]

For each row of data/catalog.csv it asks Open Library's search endpoint for the ISBN and compares
the answer with the row: titles after normalizing (letter case, accents, punctuation, a subtitle
after ":" or "(", a leading article and an edition statement), authors by surname. When the ISBN
is unknown or belongs to another book, it searches by title and author and takes the first
ISBN-13 whose record matches, whose edition is not dated well before the row's year, and whose
cover exists; otherwise the row is dropped. A row without an ISBN gets one the same way, and keeps
none when nothing is found. It prints a report; --write rewrites the file.

It reaches the network, so it is run by hand when the catalog changes, never by the app or the
tests. A row that cannot be checked because Open Library did not answer stays as it is.
"""

import argparse
import csv
import re
import sys
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from app.seed.catalog import CATALOG_FILE, valid_isbn

SEARCH_URL = "https://openlibrary.org/search.json"
COVER_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
USER_AGENT = "LibraryCatalog/0.1 (demo catalog ISBN check)"
TIMEOUT_SECONDS = 6.0
# One request a second keeps the load on Open Library small. Its cover service allows 100
# requests by ISBN per 5 minutes for each address, so cover checks are spaced further apart.
SEARCH_INTERVAL_SECONDS = 1.0
COVER_INTERVAL_SECONDS = 3.1
# Works to consider when searching by title and author; each comes with its best edition.
CANDIDATE_WORKS = 5
# The work's key is asked for too: without it the search leaves the editions out.
FIELDS = ",".join(
    [
        "key",
        "title",
        "author_name",
        "author_alternative_name",
        "editions",
        "editions.title",
        "editions.isbn",
        "editions.cover_i",
        "editions.publish_date",
    ]
)
COLUMNS = ["category", "title", "author", "year", "isbn"]

# Apostrophes join a word ("Sorcerer's" -> "sorcerers"); other punctuation separates words.
_APOSTROPHES = re.compile("['`\u2018\u2019]")
_SUBTITLE = re.compile(r"[:(]")
# Open Library names some works "Wager" for "The Wager", and some editions "Python Crash Course,
# 3rd Edition"; both still name the book.
_LEADING_ARTICLE = re.compile(r"^(the|a|an) ")
_EDITION_STATEMENT = re.compile(r" [0-9]+(st|nd|rd|th) edition$")
_YEAR = re.compile(r"[0-9]{4}")
# Several authors in one catalog cell: "Erich Gamma, Richard Helm and John Vlissides".
_AUTHOR_SEPARATOR = re.compile(r",|\band\b|&")


# Matching rules


def _fold(text: str) -> str:
    """Lower case, accents removed, punctuation turned into spaces, spaces collapsed."""
    decomposed = unicodedata.normalize("NFKD", _APOSTROPHES.sub("", text))
    kept = (
        " " if unicodedata.category(char).startswith(("P", "S")) else char
        for char in decomposed
        if not unicodedata.combining(char)
    )
    return " ".join("".join(kept).casefold().split())


def normalize_title(title: str) -> str:
    """The title folded, without a subtitle, a leading article or an edition statement:
    "The Selfish Gene: 40th Anniversary" -> "selfish gene".
    """
    folded = _fold(_SUBTITLE.split(title, maxsplit=1)[0])
    return _LEADING_ARTICLE.sub("", _EDITION_STATEMENT.sub("", folded))


def titles_match(ours: str, theirs: str) -> bool:
    ours_normal = normalize_title(ours)
    return bool(ours_normal) and ours_normal == normalize_title(theirs)


def surname(name: str) -> str:
    """The last word of a name, folded. An inverted name keeps the part before its comma:
    "Tolstoy, Leo" and "Leo Tolstoy" both give "tolstoy".
    """
    words = _fold(name.split(",", maxsplit=1)[0]).split()
    return words[-1] if words else ""


def catalog_surnames(author: str) -> set[str]:
    """The surnames in a catalog author cell, which may name several people."""
    return {surname(part) for part in _AUTHOR_SEPARATOR.split(author)} - {""}


def authors_match(ours: str, theirs: Iterable[str]) -> bool:
    """True when one of the catalog's authors shares a surname with one of the record's names
    (Open Library lists alternative spellings too: "Leo Tolstoy" for "Лев Толстой").
    """
    return not catalog_surnames(ours).isdisjoint(surname(name) for name in theirs)


# Open Library's records


@dataclass(frozen=True)
class Record:
    """A work in Open Library's search results, with the edition that best matched the query."""

    title: str
    authors: list[str]
    edition_title: str | None
    edition_isbns: list[str]
    edition_has_cover: bool
    edition_year: int | None = None

    @property
    def author(self) -> str:
        return self.authors[0] if self.authors else "an unknown author"


@dataclass(frozen=True)
class Row:
    category: str
    title: str
    author: str
    year: str
    isbn: str


def record_matches(row: Row, record: Record) -> bool:
    """The work's title or its edition's title matches the row's, and an author does. The
    edition's title counts because a work is named once: "Harry Potter and the Sorcerer's Stone"
    is an edition of the work "Harry Potter and the Philosopher's Stone".
    """
    titles = (record.title, record.edition_title or "")
    return authors_match(row.author, record.authors) and any(
        titles_match(row.title, title) for title in titles
    )


def edition_predates_book(row: Row, record: Record) -> bool:
    """An edition dated more than a year before the book's year is an earlier edition or a wrong
    record: one "Onyx Storm" (2025) edition is dated 2018. A year's margin allows for a book
    printed in December and published in January.
    """
    return bool(row.year and record.edition_year and record.edition_year < int(row.year) - 1)


class LookupUnavailable(Exception):
    """Open Library did not answer usefully, so the row cannot be checked now."""


class Lookup(Protocol):
    def by_isbn(self, isbn: str) -> Record | None: ...

    def search(self, title: str, author: str) -> list[Record]: ...

    def has_cover(self, isbn: str) -> bool: ...


# Deciding each row

Status = Literal["kept", "corrected", "filled", "no_isbn", "dropped", "unchecked"]


@dataclass(frozen=True)
class Outcome:
    row: Row
    status: Status
    # The ISBN the row has after the check; empty when it has none or is dropped.
    isbn: str
    reason: str = ""


def check_row(row: Row, lookup: Lookup, taken: set[str]) -> Outcome:
    """Keeps an ISBN whose record matches the row; otherwise looks for a replacement that is not
    already another row's. Raises LookupUnavailable when Open Library does not answer.
    """
    problem = ""
    if row.isbn:
        isbn = valid_isbn(row.isbn)
        record = lookup.by_isbn(isbn) if isbn is not None else None
        if record is not None and record_matches(row, record):
            return Outcome(row, "kept", row.isbn)
        if isbn is None:
            problem = "fails its checksum"
        elif record is None:
            problem = "is unknown to Open Library"
        else:
            problem = f'belongs to "{record.title}" by {record.author}'

    replacement = find_replacement(row, lookup, taken)
    if replacement is not None:
        status: Status = "corrected" if row.isbn else "filled"
        return Outcome(row, status, replacement, "" if not row.isbn else f"the ISBN {problem}")
    if not row.isbn:
        return Outcome(row, "no_isbn", "", "no matching edition with a cover")
    return Outcome(row, "dropped", "", f"the ISBN {problem}; no matching edition with a cover")


def find_replacement(row: Row, lookup: Lookup, taken: set[str]) -> str | None:
    """The first ISBN-13 of a matching edition that has a cover, is not dated well before the
    book, and belongs to no other row.
    """
    first_author = _AUTHOR_SEPARATOR.split(row.author, maxsplit=1)[0].strip()
    for record in lookup.search(row.title, first_author):
        # Open Library says whether an edition has a cover, which saves a limited cover request.
        usable_edition = record.edition_has_cover and not edition_predates_book(row, record)
        if not (usable_edition and record_matches(row, record)):
            continue
        for isbn in record.edition_isbns:
            usable = len(isbn) == 13 and valid_isbn(isbn) == isbn and isbn not in taken
            if usable and lookup.has_cover(isbn):
                return isbn
    return None


def check_catalog(
    rows: Sequence[Row], lookup: Lookup, progress: Callable[[int, Outcome], None] | None = None
) -> list[Outcome]:
    taken = {row.isbn for row in rows if row.isbn}
    outcomes: list[Outcome] = []
    for number, row in enumerate(rows, start=1):
        try:
            outcome = check_row(row, lookup, taken)
        except LookupUnavailable as error:
            outcome = Outcome(row, "unchecked", row.isbn, str(error))
        if outcome.isbn:
            taken.add(outcome.isbn)
        outcomes.append(outcome)
        if progress is not None:
            progress(number, outcome)
    return outcomes


# Open Library over HTTP


def _record(doc: dict[str, Any]) -> Record:
    editions = (doc.get("editions") or {}).get("docs") or [{}]
    edition = editions[0]
    return Record(
        title=str(doc.get("title") or ""),
        authors=[str(name) for name in (doc.get("author_name") or [])]
        + [str(name) for name in (doc.get("author_alternative_name") or [])],
        edition_title=str(edition["title"]) if edition.get("title") else None,
        edition_isbns=[str(isbn) for isbn in (edition.get("isbn") or [])],
        edition_has_cover=bool(edition.get("cover_i")),
        edition_year=_first_year(edition.get("publish_date") or []),
    )


def _first_year(dates: list[Any]) -> int | None:
    """The year in Open Library's free-text dates: "2025", "Jan 21, 2025" or "2025-01-21"."""
    for text in dates:
        found = _YEAR.search(str(text))
        if found:
            return int(found.group())
    return None


class OpenLibrary:
    """One request at a time, spaced out, each retried once when it times out or the connection
    fails.
    """

    def __init__(self, http: httpx.Client) -> None:
        self._http = http
        self._last_request = 0.0
        self._last_cover = 0.0

    def by_isbn(self, isbn: str) -> Record | None:
        docs = self._search({"isbn": isbn, "fields": FIELDS, "limit": 1})
        return _record(docs[0]) if docs else None

    def search(self, title: str, author: str) -> list[Record]:
        params: dict[str, str | int] = {
            "title": title,
            "author": author,
            "fields": FIELDS,
            "limit": CANDIDATE_WORKS,
        }
        return [_record(doc) for doc in self._search(params)]

    def has_cover(self, isbn: str) -> bool:
        self._last_cover = self._wait(self._last_cover, COVER_INTERVAL_SECONDS)
        # default=false answers 404 when there is no cover, instead of a blank image.
        response = self._get(COVER_URL.format(isbn=isbn), {"default": "false"})
        if response.status_code in (httpx.codes.OK, httpx.codes.NOT_FOUND):
            return response.status_code == httpx.codes.OK
        raise LookupUnavailable(f"the cover service answered {response.status_code}")

    def _search(self, params: dict[str, str | int]) -> list[dict[str, Any]]:
        response = self._get(SEARCH_URL, params)
        if response.status_code != httpx.codes.OK:
            raise LookupUnavailable(f"the search answered {response.status_code}")
        docs: list[dict[str, Any]] = response.json().get("docs") or []
        return docs

    def _get(self, url: str, params: dict[str, str | int]) -> httpx.Response:
        retried = False
        while True:
            self._last_request = self._wait(self._last_request, SEARCH_INTERVAL_SECONDS)
            try:
                return self._http.get(url, params=params)
            except httpx.TransportError as error:
                if retried:
                    raise LookupUnavailable(f"no answer twice ({type(error).__name__})") from error
                retried = True

    @staticmethod
    def _wait(last: float, interval: float) -> float:
        remaining = last + interval - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        return time.monotonic()


# The file and the report


def read_rows(path: Path) -> list[Row]:
    with path.open(encoding="utf-8", newline="") as file:
        return [
            Row(**{column: row[column].strip() for column in COLUMNS})
            for row in csv.DictReader(file)
        ]


def write_rows(path: Path, rows: Iterable[Row]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows([row.category, row.title, row.author, row.year, row.isbn] for row in rows)


def rows_after(outcomes: Iterable[Outcome]) -> list[Row]:
    return [replace(item.row, isbn=item.isbn) for item in outcomes if item.status != "dropped"]


def report(outcomes: Sequence[Outcome]) -> str:
    counts = Counter(item.status for item in outcomes)
    with_isbn = sum(1 for item in outcomes if item.row.isbn)
    lines = [
        f"Checked {len(outcomes)} rows, {with_isbn} with an ISBN, against Open Library.",
        f"Kept: {counts['kept']} (the ISBN belongs to the book)",
    ]
    sections: list[tuple[Status, str]] = [
        ("corrected", "Corrected"),
        ("filled", "Filled (no ISBN before)"),
        ("no_isbn", "Still without an ISBN"),
        ("dropped", "Dropped"),
        ("unchecked", "Not checked (left as they were)"),
    ]
    for status, heading in sections:
        lines.append(f"{heading}: {counts[status]}")
        for item in outcomes:
            if item.status != status:
                continue
            row = item.row
            change = {
                "corrected": f"{row.isbn} -> {item.isbn}",
                "filled": f"-> {item.isbn}",
            }.get(status, row.isbn or "no ISBN")
            reason = f" ({item.reason})" if item.reason else ""
            lines.append(f"  {row.category} | {row.title} | {row.author} | {change}{reason}")
    remaining = rows_after(outcomes)
    per_category = Counter(row.category for row in remaining)
    lines.append(f"Titles after the check: {len(remaining)} in {len(per_category)} categories")
    lines.extend(f"  {category}: {count}" for category, count in sorted(per_category.items()))
    return "\n".join(lines) + "\n"


def _progress(number: int, outcome: Outcome) -> None:
    sys.stderr.write(f"{number:>3} {outcome.status:<9} {outcome.row.title}\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed.isbn_check",
        description="Check every ISBN in the demo catalog against Open Library, and correct or "
        "drop the ones that do not belong to their book. Needs the network; takes minutes.",
    )
    parser.add_argument("--write", action="store_true", help="rewrite the catalog file")
    args = parser.parse_args(argv)

    rows = read_rows(CATALOG_FILE)
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as http:
        outcomes = check_catalog(rows, OpenLibrary(http), _progress)
    sys.stdout.write(report(outcomes))
    if args.write:
        write_rows(CATALOG_FILE, rows_after(outcomes))
        sys.stdout.write(f"Wrote {CATALOG_FILE.name}.\n")


if __name__ == "__main__":
    main()
