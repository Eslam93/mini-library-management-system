import uuid

import pytest


async def test_request_id_is_generated_when_missing(client):
    response = await client.get("/api/missing")

    request_id = response.headers["x-request-id"]
    assert uuid.UUID(request_id)
    assert response.json()["meta"]["request_id"] == request_id


async def test_valid_incoming_request_id_is_kept(client):
    response = await client.get("/api/missing", headers={"X-Request-ID": "edge-7f3a.01_b"})

    assert response.headers["x-request-id"] == "edge-7f3a.01_b"
    assert response.json()["meta"]["request_id"] == "edge-7f3a.01_b"


@pytest.mark.parametrize("incoming", ["has spaces", "line\tbreak", "x" * 129])
async def test_unsafe_incoming_request_id_is_replaced(client, incoming):
    response = await client.get("/api/missing", headers={"X-Request-ID": incoming})

    assert response.headers["x-request-id"] != incoming
    assert uuid.UUID(response.headers["x-request-id"])


async def test_each_request_gets_its_own_id(client):
    first = await client.get("/api/missing")
    second = await client.get("/api/missing")

    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_security_headers_are_set(client):
    response = await client.get("/api/missing")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self';" in csp
    assert "frame-ancestors 'none'" in csp
    assert "strict-transport-security" not in response.headers


async def test_hsts_is_sent_in_production(make_app, serve):
    async with serve(make_app(app_env="production", session_secret="s" * 40)) as http:
        response = await http.get("/api/missing")

    assert response.headers["strict-transport-security"].startswith("max-age=")


async def test_access_log_records_the_request(client, capsys):
    await client.get("/api/missing?q=private", headers={"X-Request-ID": "access-log-1"})

    lines = [line for line in capsys.readouterr().out.splitlines() if "access-log-1" in line]
    assert len(lines) == 1
    line = lines[0]
    for fragment in ("request", "GET", "/api/missing", "404", "duration_ms"):
        assert fragment in line
    assert "private" not in line


@pytest.mark.parametrize("app_env", ["local", "production"])
async def test_images_may_come_from_the_cover_hosts_and_nothing_else_may(make_app, serve, app_env):
    app = make_app(app_env=app_env, session_secret="s" * 40)

    async with serve(app) as http:
        response = await http.get("/api/missing")

    directives = dict(
        part.strip().split(" ", 1)
        for part in response.headers["content-security-policy"].split(";")
    )
    assert directives["img-src"] == (
        "'self' data: blob: https://covers.openlibrary.org https://archive.org "
        "https://*.archive.org"
    )
    assert directives["connect-src"] == "'self'"
    assert directives["script-src"] == "'self'"
