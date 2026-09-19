"""The curated catalog the generator shelves: real, well-known books.

data/catalog.csv has one row per title: category, title, author, year, isbn. Within a category,
rows run roughly from the most to the least borrowed, and the generator weights demand by that
position. The year is the original publication year, or the edition's year for technical books
that are read in a later edition; it is empty for works older than printing (the catalog accepts
years from 1450). An ISBN is given only where it is certain, and one that fails its checksum is
dropped when the file is read.
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.services.isbn import check_digit_matches, has_isbn_shape, normalize_isbn

CATALOG_FILE = Path(__file__).parent / "data" / "catalog.csv"


@dataclass(frozen=True)
class CatalogEntry:
    title: str
    author: str
    category: str
    published_year: int | None
    isbn: str | None
    # Position within the category in the file: 0 is the most borrowed.
    rank: int


@dataclass(frozen=True)
class Catalog:
    entries: list[CatalogEntry]
    isbns_kept: int
    isbns_dropped: int


def valid_isbn(raw: str) -> str | None:
    """The normalized ISBN when it has the right shape and passes its checksum."""
    isbn = normalize_isbn(raw)
    return isbn if has_isbn_shape(isbn) and check_digit_matches(isbn) else None


def load_catalog(path: Path = CATALOG_FILE) -> Catalog:
    entries: list[CatalogEntry] = []
    ranks: dict[str, int] = {}
    seen_isbns: set[str] = set()
    dropped = 0
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            raw_isbn = row["isbn"].strip()
            isbn = valid_isbn(raw_isbn) if raw_isbn else None
            # Two books in the catalog cannot share an ISBN.
            if isbn in seen_isbns:
                isbn = None
            if raw_isbn and isbn is None:
                dropped += 1
            if isbn is not None:
                seen_isbns.add(isbn)
            category = row["category"].strip()
            rank = ranks.get(category, 0)
            ranks[category] = rank + 1
            year = row["year"].strip()
            entries.append(
                CatalogEntry(
                    title=row["title"].strip(),
                    author=row["author"].strip(),
                    category=category,
                    published_year=int(year) if year else None,
                    isbn=isbn,
                    rank=rank,
                )
            )
    return Catalog(entries=entries, isbns_kept=len(seen_isbns), isbns_dropped=dropped)


def pick_titles(entries: Sequence[CatalogEntry], count: int | None) -> list[CatalogEntry]:
    """count titles, taking each category's most borrowed in turn so that a small library still
    has every category, in file order. None keeps them all.
    """
    if count is None or count >= len(entries):
        return list(entries)
    by_rank = sorted(range(len(entries)), key=lambda i: (entries[i].rank, i))
    return [entries[i] for i in sorted(by_rank[:count])]
