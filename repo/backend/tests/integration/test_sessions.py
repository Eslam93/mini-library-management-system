import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import User, UserSession

pytestmark = pytest.mark.integration

USER_FIELDS = {"id", "display_name", "email", "role", "member_id", "is_demo"}


def cookie_attributes(set_cookie: str) -> tuple[str, set[str]]:
    """The cookie's name=value and its attributes, lower case."""
    first, *attributes = [part.strip() for part in set_cookie.split(";")]
    return first, {attribute.lower() for attribute in attributes}


async def set_session_times(session, **values):
    await session.execute(update(UserSession).values(**values))
    await session.commit()


async def stored_sessions(session):
    return (await session.scalars(select(UserSession))).all()


# Demo sign-in


async def test_demo_staff_sign_in_returns_the_user_and_sets_the_session_cookie(anonymous):
    response = await anonymous.post("/api/auth/demo", json={"role": "staff"})

    assert response.status_code == 200
    user = response.json()
    assert set(user) == USER_FIELDS
    assert (user["display_name"], user["email"], user["role"]) == (
        "Demo Staff",
        "staff@demo.local",
        "staff",
    )
    assert (user["member_id"], user["is_demo"]) == (None, True)
    me = await anonymous.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == user


async def test_demo_member_signs_in_with_a_member_record(anonymous):
    user = (await anonymous.post("/api/auth/demo", json={"role": "member"})).json()

    assert (user["display_name"], user["role"], user["is_demo"]) == ("Demo Member", "member", True)
    assert user["member_id"] is not None


async def test_signing_in_again_reuses_the_demo_account(open_client):
    first = await open_client("staff")
    second = await open_client("staff")

    assert (await first.get("/api/auth/me")).json() == (await second.get("/api/auth/me")).json()


async def test_sign_in_records_when_the_user_last_signed_in(anonymous, empty_db):
    before = datetime.now(UTC)

    await anonymous.post("/api/auth/demo", json={"role": "staff"})

    user = await empty_db.scalar(select(User).where(User.email == "staff@demo.local"))
    assert user.last_login_at >= before - timedelta(seconds=1)


# Cookie and storage


async def test_session_cookie_is_http_only_lax_and_not_secure_outside_production(anonymous):
    response = await anonymous.post("/api/auth/demo", json={"role": "staff"})

    first, attributes = cookie_attributes(response.headers["set-cookie"])
    assert first.startswith("session=")
    assert {"httponly", "samesite=lax", "path=/", f"max-age={7 * 24 * 3600}"} <= attributes
    assert "secure" not in attributes


async def test_session_cookie_is_secure_in_production(make_db_app, serve):
    app = make_db_app(app_env="production", session_secret="p" * 40, demo_login_enabled=True)

    async with serve(app) as http:
        response = await http.post("/api/auth/demo", json={"role": "staff"})

    _, attributes = cookie_attributes(response.headers["set-cookie"])
    assert {"secure", "httponly", "samesite=lax", "path=/"} <= attributes


async def test_only_the_hash_of_the_token_is_stored(anonymous, empty_db):
    await anonymous.post("/api/auth/demo", json={"role": "staff"})
    token = anonymous.cookies["session"]

    [stored] = await stored_sessions(empty_db)

    assert len(token) >= 43
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert stored.expires_at - stored.created_at == timedelta(days=7)


async def test_a_new_sign_in_revokes_the_browsers_previous_session(anonymous, empty_db):
    await anonymous.post("/api/auth/demo", json={"role": "staff"})
    first_token = anonymous.cookies["session"]

    await anonymous.post("/api/auth/demo", json={"role": "member"})

    old = await anonymous.get("/api/auth/me", headers={"Cookie": f"session={first_token}"})
    assert old.status_code == 401
    assert (await anonymous.get("/api/auth/me")).json()["role"] == "member"


async def test_unknown_token_is_401(anonymous):
    response = await anonymous.get("/api/auth/me", headers={"Cookie": "session=not-a-real-token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# Expiry


async def test_session_ends_after_the_idle_timeout(client, empty_db):
    await set_session_times(empty_db, last_seen_at=datetime.now(UTC) - timedelta(minutes=721))

    response = await client.get("/api/auth/me")

    assert response.status_code == 401


async def test_session_within_the_idle_timeout_is_kept_alive(client, empty_db):
    await set_session_times(empty_db, last_seen_at=datetime.now(UTC) - timedelta(minutes=719))

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    [stored] = await stored_sessions(empty_db)
    assert datetime.now(UTC) - stored.last_seen_at < timedelta(minutes=1)


async def test_session_ends_at_its_absolute_expiry_even_when_active(client, empty_db):
    now = datetime.now(UTC)
    await set_session_times(empty_db, last_seen_at=now, expires_at=now - timedelta(seconds=1))

    response = await client.get("/api/auth/me")

    assert response.status_code == 401


async def test_idle_timeout_comes_from_settings(make_db_app, serve, sign_in, empty_db):
    async with serve(make_db_app(session_idle_minutes=5)) as http:
        await sign_in(http, "staff")
        await set_session_times(empty_db, last_seen_at=datetime.now(UTC) - timedelta(minutes=6))
        response = await http.get("/api/auth/me")

    assert response.status_code == 401


async def test_last_seen_is_written_at_most_once_a_minute(client, empty_db):
    recent = datetime.now(UTC) - timedelta(seconds=30)
    await set_session_times(empty_db, last_seen_at=recent)

    await client.get("/api/auth/me")

    [stored] = await stored_sessions(empty_db)
    assert stored.last_seen_at == recent


# Sign-out


async def test_logout_revokes_the_session_and_clears_the_cookie(client, anonymous, empty_db):
    token = client.cookies["session"]

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    first, attributes = cookie_attributes(response.headers["set-cookie"])
    assert first == 'session=""'
    assert {"max-age=0", "path=/", "httponly", "samesite=lax"} <= attributes
    [stored] = await stored_sessions(empty_db)
    assert stored.revoked_at is not None
    assert (await client.get("/api/auth/me")).status_code == 401
    # The token no longer works anywhere, even when sent again.
    reused = await anonymous.get("/api/auth/me", headers={"Cookie": f"session={token}"})
    assert reused.status_code == 401


async def test_logout_twice_is_still_204(client):
    await client.post("/api/auth/logout")

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204


async def test_signing_in_deletes_that_users_expired_sessions_only(open_client, empty_db):
    first, second = await open_client("staff"), await open_client("staff")
    member = await open_client("member")
    expired = [hash_of(first), hash_of(member)]
    await empty_db.execute(
        update(UserSession)
        .where(UserSession.token_hash.in_(expired))
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await empty_db.commit()

    third = await open_client("staff")

    # The staff account's expired session is gone; its live one and the member's stay.
    remaining = {stored.token_hash for stored in await stored_sessions(empty_db)}
    assert remaining == {hash_of(second), hash_of(member), hash_of(third)}


def hash_of(http) -> str:
    return hashlib.sha256(http.cookies["session"].encode()).hexdigest()
