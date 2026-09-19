"""The catalog check's rules: when an ISBN belongs to its book, and what happens to a row when it
does not. The check calls Open Library; here a fake stands in for it, so nothing reaches the
network.
"""

from dataclasses import replace

import pytest

from app.seed.isbn_check import (
    LookupUnavailable,
    Record,
    Row,
    authors_match,
    catalog_surnames,
    check_catalog,
    check_row,
    normalize_title,
    read_rows,
    record_matches,
    rows_after,
    surname,
    titles_match,
    write_rows,
)

# Valid ISBN-13s; which book each belongs to only matters through the fake below.
DUNE = "9780441172719"
OTHER = "9780735219090"
FIRST = "9780525559474"
SECOND = "9780385547345"
THIRD = "9780593321201"


def row(title="Dune", author="Frank Herbert", isbn=DUNE, category="Science Fiction"):
    return Row(category=category, title=title, author=author, year="1965", isbn=isbn)


def record(
    title="Dune", authors=("Frank Herbert",), edition_title=None, isbns=(), cover=True, year=None
):
    return Record(
        title=title,
        authors=list(authors),
        edition_title=edition_title,
        edition_isbns=list(isbns),
        edition_has_cover=cover,
        edition_year=year,
    )


class FakeLibrary:
    """Answers from fixed records, and remembers what was asked."""

    def __init__(self, by_isbn=None, found=(), covers=(), unavailable=()):
        self.records = by_isbn or {}
        self.found = list(found)
        self.covers = set(covers)
        self.unavailable = set(unavailable)
        self.searches = []
        self.cover_checks = []

    def by_isbn(self, isbn):
        if isbn in self.unavailable:
            raise LookupUnavailable("the search answered 503")
        return self.records.get(isbn)

    def search(self, title, author):
        self.searches.append((title, author))
        return self.found

    def has_cover(self, isbn):
        self.cover_checks.append(isbn)
        return isbn in self.covers


# Titles and authors


@pytest.mark.parametrize(
    ("title", "normalized"),
    [
        ("Sapiens: A Brief History of Humankind", "sapiens"),
        ("Tao Te Ching (Penguin Classics)", "tao te ching"),
        ("Harry Potter and the Sorcerer\u2019s Stone", "harry potter and the sorcerers stone"),
        ("Nineteen Eighty-Four", "nineteen eighty four"),
        ("  THE   Hobbit ", "hobbit"),
        ("A Man Called Ove", "man called ove"),
        ("Python Crash Course, 3rd Edition", "python crash course"),
        ("Cien años de soledad", "cien anos de soledad"),
        ("Legends & Lattes", "legends lattes"),
    ],
)
def test_titles_are_compared_without_case_accents_punctuation_subtitle_article_or_edition(
    title, normalized
):
    assert normalize_title(title) == normalized


def test_titles_match_only_on_the_same_main_title():
    assert titles_match("The Martian", "The Martian: A Novel")
    assert titles_match("What If?", "What If? (Serious Scientific Answers)")
    assert titles_match(
        "Harry Potter and the Sorcerer's Stone", "harry potter and the sorcerers stone"
    )
    assert titles_match("The Wager", "Wager")
    assert not titles_match("The Road", "The Roads")
    assert not titles_match("Dune", "Dune Messiah")
    assert not titles_match("Dune", "Children of Dune")
    assert not titles_match("", "")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Leo Tolstoy", "tolstoy"),
        ("Tolstoy, Leo", "tolstoy"),
        ("J.R.R. Tolkien", "tolkien"),
        ("Gabriel García Márquez", "marquez"),
        ("Prince Harry, Duke of Sussex", "harry"),
        ("Malcolm X", "x"),
        ("", ""),
    ],
)
def test_the_surname_is_the_last_word_before_any_comma(name, expected):
    assert surname(name) == expected


def test_a_catalog_cell_can_name_several_authors():
    assert catalog_surnames("Erich Gamma, Richard Helm, Ralph Johnson and John Vlissides") == {
        "gamma",
        "helm",
        "johnson",
        "vlissides",
    }
    assert catalog_surnames("Terry Pratchett and Neil Gaiman") == {"pratchett", "gaiman"}
    assert catalog_surnames("Alexandra Anderson") == {"anderson"}


def test_authors_match_on_one_shared_surname_in_names_or_alternative_names():
    assert authors_match("Leo Tolstoy", ["Лев Толстой", "Tolstoy, Leo"])
    assert authors_match("Terry Pratchett and Neil Gaiman", ["Neil Gaiman"])
    assert authors_match("J.R.R. Tolkien", ["J. R. R. Tolkien"])
    assert not authors_match("Frank Herbert", ["Brian Herbertson"])
    assert not authors_match("Frank Herbert", [])


def test_a_record_matches_on_the_work_or_the_edition_title_and_an_author():
    philosophers_stone = record(
        title="Harry Potter and the Philosopher's Stone",
        authors=["J. K. Rowling"],
        edition_title="Harry Potter and the Sorcerer's Stone",
    )
    sorcerers_stone = row("Harry Potter and the Sorcerer's Stone", "J.K. Rowling")

    assert record_matches(sorcerers_stone, philosophers_stone)
    assert record_matches(row(), record(edition_title="Dune (Penguin Galaxy)"))
    assert not record_matches(row(), record(authors=["Brian Herbertson"]))
    assert not record_matches(row(), record(title="Dune Messiah", edition_title="Dune Messiah"))


# What happens to a row


def test_an_isbn_whose_record_matches_is_kept_without_a_search():
    library = FakeLibrary(by_isbn={DUNE: record()})

    outcome = check_row(row(), library, taken={DUNE})

    assert (outcome.status, outcome.isbn) == ("kept", DUNE)
    assert library.searches == []


def test_an_isbn_of_another_book_is_replaced_by_the_first_usable_matching_edition():
    library = FakeLibrary(
        by_isbn={DUNE: record(title="The Midnight Library", authors=["Matt Haig"])},
        found=[
            record(title="Dune Messiah", isbns=[OTHER]),
            record(isbns=[OTHER], cover=False),
            record(isbns=["0441172717", OTHER, FIRST, SECOND, THIRD]),
        ],
        covers={SECOND, THIRD},
    )

    outcome = check_row(row(), library, taken={DUNE, OTHER})

    # OTHER is another row's, FIRST has no cover, the ISBN-10 is skipped.
    assert (outcome.status, outcome.isbn) == ("corrected", SECOND)
    assert outcome.reason == 'the ISBN belongs to "The Midnight Library" by Matt Haig'
    assert library.searches == [("Dune", "Frank Herbert")]
    assert library.cover_checks == [FIRST, SECOND]


def test_an_edition_older_than_the_book_is_not_taken():
    library = FakeLibrary(
        found=[record(isbns=[FIRST], year=1963), record(isbns=[SECOND], year=1964)],
        covers={FIRST, SECOND},
    )
    no_year = FakeLibrary(found=[record(isbns=[FIRST], year=1960)], covers={FIRST})

    # The row's year is 1965; an edition a year earlier still counts.
    assert check_row(row(isbn=""), library, taken=set()).isbn == SECOND
    assert check_row(replace(row(isbn=""), year=""), no_year, taken=set()).isbn == FIRST


def test_a_row_is_dropped_when_no_matching_edition_has_a_cover():
    library = FakeLibrary(found=[record(isbns=[FIRST], cover=False), record(isbns=[SECOND])])

    outcome = check_row(row(author="Frank Herbert and Brian Herbert"), library, taken={DUNE})

    assert (outcome.status, outcome.isbn) == ("dropped", "")
    assert outcome.reason == (
        "the ISBN is unknown to Open Library; no matching edition with a cover"
    )
    # The search names the first author only.
    assert library.searches == [("Dune", "Frank Herbert")]


def test_an_isbn_that_fails_its_checksum_is_replaced_without_asking_for_it():
    library = FakeLibrary(found=[record(isbns=[FIRST])], covers={FIRST})

    outcome = check_row(row(isbn="9780441172710"), library, taken=set())

    assert (outcome.status, outcome.isbn) == ("corrected", FIRST)
    assert outcome.reason == "the ISBN fails its checksum"


def test_a_row_without_an_isbn_gets_one_or_keeps_none():
    found = FakeLibrary(found=[record(isbns=[FIRST])], covers={FIRST})
    nothing = FakeLibrary(found=[record(title="Dune Messiah", isbns=[FIRST])], covers={FIRST})

    filled = check_row(row(isbn=""), found, taken=set())
    still_without = check_row(row(isbn=""), nothing, taken=set())

    assert (filled.status, filled.isbn, filled.reason) == ("filled", FIRST, "")
    assert (still_without.status, still_without.isbn) == ("no_isbn", "")


def test_the_catalog_check_never_gives_two_rows_one_isbn_and_leaves_unanswered_rows():
    library = FakeLibrary(
        by_isbn={DUNE: record(title="Something Else")},
        found=[record(isbns=[FIRST, SECOND])],
        covers={FIRST, SECOND},
        unavailable={THIRD},
    )
    rows = [row(), row(isbn=""), row(title="Dune", isbn=THIRD), row(title="Dune", isbn="")]

    outcomes = check_catalog(rows, library)

    assert [(item.status, item.isbn) for item in outcomes] == [
        ("corrected", FIRST),
        ("filled", SECOND),
        ("unchecked", THIRD),
        ("no_isbn", ""),
    ]


def test_the_file_keeps_its_format_and_loses_only_dropped_rows(tmp_path):
    path = tmp_path / "catalog.csv"
    original = (
        "category,title,author,year,isbn\n"
        'Fiction,"Tomorrow, and Tomorrow, and Tomorrow",Gabrielle Zevin,2022,9780593321201\n'
        "Philosophy,Meditations,Marcus Aurelius,,9780812968255\n"
        "Science Fiction,Dune,Frank Herbert,1965,9780441172710\n"
    )
    path.write_text(original, encoding="utf-8")
    rows = read_rows(path)
    library = FakeLibrary(
        by_isbn={
            "9780593321201": record("Tomorrow, and Tomorrow, and Tomorrow", ["Gabrielle Zevin"]),
            "9780812968255": record("Meditations", ["Marcus Aurelius"]),
        }
    )

    write_rows(path, rows)
    assert path.read_text(encoding="utf-8") == original
    write_rows(path, rows_after(check_catalog(rows, library)))
    assert path.read_text(encoding="utf-8") == original.rsplit("Science Fiction", 1)[0]
