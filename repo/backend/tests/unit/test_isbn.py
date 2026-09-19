import pytest

from app.services.isbn import (
    check_digit_matches,
    has_isbn_shape,
    isbn_search_fragment,
    normalize_isbn,
)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("978-0-441-17271-9", "9780441172719"),
        (" 0 441 17271 7 ", "0441172717"),
        ("0-8044-2957-x", "080442957X"),
    ],
)
def test_normalize_removes_spaces_and_hyphens(raw, normalized):
    assert normalize_isbn(raw) == normalized


@pytest.mark.parametrize("isbn", ["9780441172719", "9780547928227", "0441172717", "080442957X"])
def test_valid_isbn_10_and_13_pass_the_checksum(isbn):
    assert has_isbn_shape(isbn)
    assert check_digit_matches(isbn)


@pytest.mark.parametrize("isbn", ["9780441172710", "9780441172718", "0441172718", "0804429571"])
def test_wrong_check_digit_fails(isbn):
    assert has_isbn_shape(isbn)
    assert not check_digit_matches(isbn)


@pytest.mark.parametrize("isbn", ["", "12345", "97804411727190", "X441172717", "978044117271X"])
def test_wrong_shape_is_rejected(isbn):
    assert not has_isbn_shape(isbn)
    assert not check_digit_matches(isbn)


@pytest.mark.parametrize(
    ("term", "fragment"),
    [
        ("978-0441", "9780441"),
        ("0 441 172", "0441172"),
        ("2957-x", "2957X"),
        ("herb", None),
        ("1984 edition", None),
    ],
)
def test_search_fragment_is_the_digits_of_an_isbn_like_term(term, fragment):
    assert isbn_search_fragment(term) == fragment
