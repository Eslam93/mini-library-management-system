"""State-changing requests from other sites are refused before any route runs.

POST /api/auth/logout is the probe: without a session cookie it answers 204 without touching
the database.
"""

import pytest

from app.middleware.origin_check import normalize_origin

LOGOUT = "/api/auth/logout"


async def test_foreign_origin_is_refused_with_the_error_envelope(client):
    response = await client.post(
        LOGOUT, headers={"Origin": "https://evil.example", "X-Request-ID": "origin-check-1"}
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "origin_not_allowed",
            "message": "This request came from a site that is not allowed to make changes here.",
            "details": {},
        },
        "meta": {"request_id": "origin-check-1"},
    }
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_every_state_changing_method_is_checked(client, method):
    response = await client.request(
        method, "/api/books", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


@pytest.mark.parametrize(
    "origin", ["http://localhost:8000", "http://localhost:5173", "HTTP://LOCALHOST:8000/"]
)
async def test_allowed_origins_pass(client, origin):
    response = await client.post(LOGOUT, headers={"Origin": origin})

    assert response.status_code == 204


async def test_requests_without_an_origin_pass(client):
    response = await client.post(LOGOUT)

    assert response.status_code == 204


async def test_reading_is_not_checked(client):
    response = await client.get("/api/auth/config", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200


async def test_opaque_origin_is_refused(client):
    response = await client.post(LOGOUT, headers={"Origin": "null"})

    assert response.status_code == 403


async def test_production_does_not_allow_the_development_server(make_app, serve):
    app = make_app(
        app_env="production", session_secret="p" * 40, public_base_url="https://library.example"
    )

    async with serve(app) as http:
        own = await http.post(LOGOUT, headers={"Origin": "https://library.example"})
        dev = await http.post(LOGOUT, headers={"Origin": "http://localhost:5173"})

    assert own.status_code == 204
    assert dev.status_code == 403


async def test_allowed_origins_come_from_settings(make_app, serve):
    app = make_app(allowed_origins=["https://library.example"])

    async with serve(app) as http:
        listed = await http.post(LOGOUT, headers={"Origin": "https://library.example"})
        default = await http.post(LOGOUT, headers={"Origin": "http://localhost:8000"})

    assert listed.status_code == 204
    assert default.status_code == 403


async def test_the_servers_own_origin_passes_even_when_not_listed(make_app, serve):
    # Opening the app by IP address instead of the configured host name must still work.
    app = make_app(allowed_origins=["https://library.example"])

    async with serve(app) as http:
        own = await http.post(
            LOGOUT, headers={"Origin": "http://127.0.0.1:8000", "Host": "127.0.0.1:8000"}
        )
        foreign = await http.post(
            LOGOUT, headers={"Origin": "https://evil.example", "Host": "127.0.0.1:8000"}
        )

    assert own.status_code == 204
    assert foreign.status_code == 403


@pytest.mark.parametrize(
    ("origin", "normalized"),
    [
        ("https://Library.Example/", "https://library.example"),
        ("https://library.example:443", "https://library.example"),
        ("http://localhost:80", "http://localhost"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("https://library.example:8443", "https://library.example:8443"),
    ],
)
def test_origins_compare_without_case_trailing_slash_or_default_port(origin, normalized):
    assert normalize_origin(origin) == normalized
