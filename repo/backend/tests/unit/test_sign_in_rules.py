"""Pure sign-in rules: where to go after sign-in, and how tokens are stored."""

import hashlib

import pytest

from app.services.auth import hash_token, safe_next_path


@pytest.mark.parametrize(
    "path", ["/", "/my-loans", "/books/42?tab=copies", "/catalog?q=dune#top", "/history"]
)
def test_paths_on_this_site_are_kept(path):
    assert safe_next_path(path) == path


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "//evil.example",
        "//evil.example/path",
        "/\\evil.example",
        "/books\\..\\evil",
        "https://evil.example",
        "evil.example",
        "javascript:alert(1)",
        "/line\nbreak",
        "/tab\there",
        "/" + "x" * 2000,
    ],
)
def test_anything_else_falls_back_to_the_home_page(raw):
    assert safe_next_path(raw) == "/"


def test_tokens_are_stored_as_hex_sha256():
    token = "a-random-cookie-token"

    assert hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert len(hash_token(token)) == 64
    assert token not in hash_token(token)
