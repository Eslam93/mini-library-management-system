"""Pure business rules: request fields, due dates, availability, copy codes and summary wording."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationFailedError
from app.models.copy import format_copy_code
from app.schemas.books import BookCreate, BookUpdate
from app.schemas.fields import latest_published_year
from app.schemas.members import MemberCreate
from app.services.activity import format_day, loan_borrowed
from app.services.catalog import availability_of
from app.services.circulation import due_at_for, normalize_copy_code

TODAY = date(2026, 9, 19)


def error_types(error: ValidationError) -> dict[str, str]:
    return {str(e["loc"][-1]): e["type"] for e in error.errors()}


def test_book_text_is_trimmed_and_blank_optional_text_is_null():
    book = BookCreate(
        title="  Dune ", author=" Frank Herbert", category="   ", description="", isbn=" "
    )

    assert (book.title, book.author) == ("Dune", "Frank Herbert")
    assert (book.category, book.description, book.isbn) == (None, None, None)
    assert book.copies == 1


@pytest.mark.parametrize("year", [1450, 1965, latest_published_year()])
def test_published_year_accepts_1450_to_next_year(year):
    assert BookCreate(title="t", author="a", published_year=year).published_year == year


@pytest.mark.parametrize("year", [1449, latest_published_year() + 1])
def test_published_year_outside_the_range_is_rejected(year):
    with pytest.raises(ValidationError) as caught:
        BookCreate(title="t", author="a", published_year=year)

    assert error_types(caught.value) == {"published_year": "year_out_of_range"}


def test_update_keeps_track_of_which_fields_were_sent():
    update = BookUpdate.model_validate({"category": "", "published_year": None})

    assert update.model_dump(exclude_unset=True) == {"category": None, "published_year": None}


def test_update_cannot_clear_title_or_author():
    with pytest.raises(ValidationError) as caught:
        BookUpdate.model_validate({"title": None, "author": None})

    assert error_types(caught.value) == {"title": "missing", "author": "missing"}


@pytest.mark.parametrize("email", ["maya@example.com", "Maya.Hassan+books@library.example.org"])
def test_valid_emails_are_accepted(email):
    assert MemberCreate(full_name="Maya", email=email).email == email


@pytest.mark.parametrize("email", ["maya", "maya@", "@example.com", "maya@example", "a b@c.de"])
def test_invalid_emails_are_rejected(email):
    with pytest.raises(ValidationError) as caught:
        MemberCreate(full_name="Maya", email=email)

    assert error_types(caught.value) == {"email": "email_format"}


def test_default_due_date_is_the_end_of_the_day_after_the_loan_period():
    due_at = due_at_for(None, today=TODAY, loan_period_days=14)

    assert due_at == datetime(2026, 10, 3, 23, 59, 59, tzinfo=UTC)


@pytest.mark.parametrize("chosen", [date(2026, 9, 20), date(2026, 12, 18)])
def test_chosen_due_date_from_tomorrow_to_90_days_is_kept(chosen):
    assert due_at_for(chosen, today=TODAY, loan_period_days=14).date() == chosen


@pytest.mark.parametrize(
    ("chosen", "error_type"),
    [
        (date(2026, 9, 19), "due_date_not_in_future"),
        (date(2026, 9, 1), "due_date_not_in_future"),
        (date(2026, 12, 19), "due_date_too_far"),
    ],
)
def test_due_date_outside_the_window_is_a_field_error(chosen, error_type):
    with pytest.raises(ValidationFailedError) as caught:
        due_at_for(chosen, today=TODAY, loan_period_days=14)

    [error] = caught.value.details["errors"]
    assert error["location"] == ["body", "due_date"]
    assert error["type"] == error_type
    assert caught.value.status_code == 422


@pytest.mark.parametrize(
    ("total", "available", "expected"),
    [(0, 0, "no_copies"), (3, 2, "available"), (3, 0, "all_borrowed")],
)
def test_availability_is_derived_from_copy_counts(total, available, expected):
    assert availability_of(total, available) == expected


@pytest.mark.parametrize(
    ("number", "code"), [(7, "CP-0007"), (1234, "CP-1234"), (12345, "CP-12345")]
)
def test_copy_codes_are_padded_to_four_digits(number, code):
    assert format_copy_code(number) == code


@pytest.mark.parametrize(
    ("typed", "code"),
    [
        ("CP-0012", "CP-0012"),
        ("cp-0012", "CP-0012"),
        ("12", "CP-0012"),
        (" 0012 ", "CP-0012"),
        ("cp12", "CP-0012"),
        ("CP-12", "CP-0012"),
        ("12345", "CP-12345"),
        ("CP-012345", "CP-12345"),
        ("0", "CP-0000"),
        ("cp-12-a", "CP-12-A"),
        ("1234567890", "1234567890"),
    ],
)
def test_typed_copy_codes_are_normalized(typed, code):
    assert normalize_copy_code(typed) == code


def test_borrow_summary_names_book_copy_member_and_due_date():
    summary = loan_borrowed("Dune", "CP-0007", "Maya Hassan", date(2026, 10, 3))

    assert summary == "Borrowed Dune (CP-0007) to Maya Hassan, due 3 Oct 2026"
    assert format_day(date(2027, 1, 12)) == "12 Jan 2027"
