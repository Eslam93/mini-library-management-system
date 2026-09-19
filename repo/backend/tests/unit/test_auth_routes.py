"""Sign-in routes that answer without touching the database."""

import pytest

PRODUCTION = {"app_env": "production", "session_secret": "p" * 40}


async def test_config_reports_the_ways_to_sign_in(client):
    response = await client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {"demo_login": True, "google": False}


async def test_config_reports_google_when_configured(make_app, serve):
    app = make_app(google_client_id="client-1", google_client_secret="secret-1")

    async with serve(app) as http:
        response = await http.get("/api/auth/config")

    assert response.json() == {"demo_login": True, "google": True}


@pytest.mark.parametrize(
    "settings",
    [{"demo_login_enabled": False}, PRODUCTION],
    ids=["turned-off", "production-default"],
)
async def test_demo_sign_in_is_404_when_turned_off(make_app, serve, settings):
    async with serve(make_app(**settings)) as http:
        config = (await http.get("/api/auth/config")).json()
        response = await http.post("/api/auth/demo", json={"role": "staff"})

    assert config["demo_login"] is False
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("path", ["/api/auth/google/login", "/api/auth/google/callback"])
async def test_google_routes_are_404_when_google_is_not_configured(client, path):
    response = await client.get(path, params={"next": "/my-loans"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_me_without_a_session_cookie_is_401(client):
    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_logout_without_a_session_is_204_and_clears_the_cookie(client):
    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert response.headers["set-cookie"].startswith('session=""')
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_demo_role_must_be_staff_or_member(client):
    response = await client.post("/api/auth/demo", json={"role": "admin"})

    assert response.status_code == 422
    [error] = response.json()["error"]["details"]["errors"]
    assert error["location"] == ["body", "role"]
