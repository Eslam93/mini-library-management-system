"""The generator without a database: the catalog file and the simulated history's rules.

These run without PostgreSQL; they sit beside the database tests of the generator.
"""

import csv
import itertools
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.seed import opening
from app.seed.catalog import CATALOG_FILE, load_catalog, pick_titles
from app.seed.people import load_names
from app.seed.simulation import DEMO_MEMBER, GeneratorOptions, History, simulate, years_before
from app.services.isbn import check_digit_matches, has_isbn_shape, normalize_isbn

TODAY = date(2026, 9, 19)
END = datetime.combine(TODAY, time(tzinfo=UTC))
SMALL = GeneratorOptions(today=TODAY, start=TODAY - timedelta(days=182), titles=40, members=30)


@pytest.fixture(scope="module")
def small() -> History:
    return simulate(SMALL)


@pytest.fixture(scope="module")
def full() -> History:
    return simulate(GeneratorOptions(today=TODAY, start=years_before(TODAY, 3)))


# The catalog file


def test_every_isbn_in_the_catalog_file_passes_the_checksum():
    with CATALOG_FILE.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    isbns = [normalize_isbn(row["isbn"]) for row in rows if row["isbn"].strip()]

    assert len(isbns) > len(rows) / 2
    assert [
        isbn for isbn in isbns if not (has_isbn_shape(isbn) and check_digit_matches(isbn))
    ] == []
    assert len(set(isbns)) == len(isbns)


def test_the_catalog_has_well_known_titles_across_a_dozen_categories():
    catalog = load_catalog()
    categories = {entry.category for entry in catalog.entries}

    assert 250 <= len(catalog.entries) <= 300
    assert 12 <= len(categories) <= 14
    assert len({(entry.title, entry.author) for entry in catalog.entries}) == len(catalog.entries)
    assert catalog.isbns_dropped == 0


def test_an_isbn_that_fails_its_checksum_is_dropped_and_the_title_kept(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text(
        "category,title,author,year,isbn\n"
        "Science Fiction,Dune,Frank Herbert,1965,9780441172710\n"
        "Science Fiction,Dune Messiah,Frank Herbert,1969,978-0-441-17269-6\n",
        encoding="utf-8",
    )

    catalog = load_catalog(path)

    assert [(entry.title, entry.isbn) for entry in catalog.entries] == [
        ("Dune", None),
        ("Dune Messiah", "9780441172696"),
    ]
    assert (catalog.isbns_kept, catalog.isbns_dropped) == (1, 1)


def test_a_small_library_takes_each_category_s_most_borrowed_first():
    entries = load_catalog().entries

    picked = pick_titles(entries, 14)

    assert {entry.category for entry in picked} == {entry.category for entry in entries}
    assert all(entry.rank == 0 for entry in picked)


# The simulated history


def test_the_same_seed_and_date_give_the_same_history(small):
    assert simulate(SMALL) == small
    assert simulate(replace(SMALL, seed=SMALL.seed + 1)) != small


def test_a_copy_is_never_on_two_loans_at_once(small):
    loans_by_copy = defaultdict(list)
    for loan in small.loans:
        loans_by_copy[loan.copy_id].append(loan)

    for loans in loans_by_copy.values():
        loans.sort(key=lambda loan: loan.borrowed_at)
        for earlier, later in itertools.pairwise(loans):
            assert earlier.returned_at is not None
            assert earlier.returned_at < later.borrowed_at


def test_loans_start_after_the_member_joined_and_the_copy_arrived(small):
    for loan in small.loans:
        assert loan.borrowed_at > loan.member.joined_at
        assert loan.borrowed_at > loan.book.added_at
        assert loan.copy_id in loan.book.copy_ids


def test_loans_are_due_after_the_loan_period_and_return_after_they_start(small):
    for loan in small.loans:
        assert loan.due_at.date() == loan.borrowed_at.date() + timedelta(
            days=SMALL.loan_period_days
        )
        assert loan.due_at > loan.borrowed_at
        assert loan.returned_at is None or loan.returned_at >= loan.borrowed_at


def test_everything_happens_before_today_during_opening_hours_at_the_desk(small):
    staff = set(load_names().staff)
    moments = [
        *((book.added_at, book.added_by) for book in small.books),
        *((member.joined_at, member.added_by) for member in small.members),
        *((loan.borrowed_at, loan.borrowed_by) for loan in small.loans),
        *((loan.returned_at, loan.returned_by) for loan in small.loans if loan.returned_at),
    ]

    for moment, actor in moments:
        opens, closes = opening.opening_hours(moment.date())
        assert moment < END
        assert opening.is_open(moment.date())
        assert opens <= moment.hour < closes
        assert actor in staff


def test_the_demo_member_has_a_history_and_two_books_out_one_overdue(small):
    loans = [loan for loan in small.loans if loan.member == small.demo_member]
    still_out = [loan for loan in loans if loan.returned_at is None]

    assert (small.demo_member.full_name, small.demo_member.email) == (
        DEMO_MEMBER.full_name,
        DEMO_MEMBER.email,
    )
    assert small.demo_member.joined_at == min(member.joined_at for member in small.members)
    assert len(loans) - len(still_out) >= 5
    assert any(loan.due_at < END for loan in still_out)
    assert any(loan.due_at > END for loan in still_out)


def test_three_years_look_like_a_working_library(full):
    copies = sum(len(book.copy_ids) for book in full.books)
    still_out = [loan for loan in full.loans if loan.returned_at is None]
    overdue = [loan for loan in still_out if loan.due_at < END]

    assert 250 <= len(full.books) <= 300
    assert 400 <= copies <= 600
    assert len(full.members) == 200
    assert 0.1 <= len(still_out) / copies <= 0.4
    assert 5 <= len(overdue) <= 25
    assert all(1 <= len(book.copy_ids) <= 3 for book in full.books)


def test_titles_published_during_the_history_arrive_in_their_year(full):
    start = years_before(TODAY, 3)
    arrived_later = [
        book for book in full.books if book.added_at.date() > start + timedelta(days=7)
    ]

    assert arrived_later
    for book in full.books:
        year = book.entry.published_year
        if year is not None and year > start.year:
            assert book.added_at.year == year


def test_the_software_professional_share_of_new_members_grows(full):
    third = len(full.members) // 3
    first, last = full.members[:third], full.members[-third:]

    def professionals(members):
        return sum(1 for member in members if member.persona == "software_professional")

    assert professionals(last) > professionals(first)
