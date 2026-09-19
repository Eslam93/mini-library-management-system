"""Google sign-in against a fake provider.

The rules for turning a verified profile into a user are tested on the service. The routes run
the real authlib client with Google's configuration preloaded and the two network steps of the
callback replaced: the code exchange and the ID token check. The state check, the PKCE verifier
and the nonce still go through authlib.
"""

import time
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

from app.api.google import OAuthError
from app.models import ActivityEvent, Member, User
from app.services.auth import GoogleSignInRefused, complete_google_login

pytestmark = pytest.mark.integration

STAFF_EMAILS = ["ada@library.example"]
GOOGLE_METADATA = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
}


def profile(**claims):
    return {
        "sub": "google-subject-1",
        "email": "lina@mail.example",
        "email_verified": True,
        "name": "Lina Haddad",
        **claims,
    }


async def count(session, model, *conditions):
    return await session.scalar(select(func.count()).select_from(model).where(*conditions))


# Turning a Google profile into a user


@pytest.mark.parametrize(
    "claims",
    [
        {"email_verified": False},
        {"email_verified": None},
        {"email": None},
        {"sub": ""},
    ],
    ids=["unverified", "verification-missing", "no-email", "no-subject"],
)
async def test_profiles_without_a_verified_email_are_refused(empty_db, claims):
    with pytest.raises(GoogleSignInRefused):
        await complete_google_login(empty_db, profile(**claims), staff_emails=STAFF_EMAILS)

    assert await count(empty_db, User) == 0
    assert await count(empty_db, Member) == 0


async def test_a_new_user_becomes_a_member_with_a_member_record(empty_db):
    user = await complete_google_login(empty_db, profile(), staff_emails=STAFF_EMAILS)

    member = await empty_db.get(Member, user.member_id)
    assert (user.role, user.display_name, user.email) == (
        "member",
        "Lina Haddad",
        "lina@mail.example",
    )
    assert (user.google_sub, user.is_demo) == ("google-subject-1", False)
    assert (member.full_name, member.email) == ("Lina Haddad", "lina@mail.example")
    event = await empty_db.scalar(select(ActivityEvent))
    assert event.action == "member.created"
    assert event.summary == "Lina Haddad joined by signing in with Google"
    assert (event.actor, event.actor_user_id, event.via) == ("Lina Haddad", user.id, "ui")


async def test_an_address_on_the_staff_list_becomes_staff_whatever_its_case(empty_db):
    user = await complete_google_login(
        empty_db, profile(email="Ada@Library.Example", name="Ada"), staff_emails=STAFF_EMAILS
    )

    assert (user.role, user.member_id, user.email) == ("staff", None, "Ada@Library.Example")
    assert await count(empty_db, Member) == 0


async def test_without_a_name_the_address_is_the_display_name(empty_db):
    user = await complete_google_login(empty_db, profile(name=None), staff_emails=[])

    assert user.display_name == "lina@mail.example"


async def test_a_returning_user_is_found_by_google_subject_first(empty_db):
    first = await complete_google_login(empty_db, profile(), staff_emails=STAFF_EMAILS)

    again = await complete_google_login(
        empty_db, profile(email="lina.new@mail.example"), staff_emails=STAFF_EMAILS
    )

    assert again.id == first.id
    assert await count(empty_db, User) == 1
    assert await count(empty_db, Member) == 1


async def test_an_existing_user_is_found_by_address_and_linked(empty_db):
    existing = User(email="Grace@Library.example", display_name="Grace", role="staff")
    empty_db.add(existing)
    await empty_db.commit()

    user = await complete_google_login(
        empty_db, profile(email="grace@library.example", sub="google-subject-2"), staff_emails=[]
    )

    assert user.id == existing.id
    assert (user.role, user.google_sub) == ("staff", "google-subject-2")
    assert await count(empty_db, User) == 1


async def test_an_address_linked_to_another_google_account_is_refused(empty_db):
    await complete_google_login(empty_db, profile(), staff_emails=[])

    with pytest.raises(GoogleSignInRefused):
        await complete_google_login(empty_db, profile(sub="google-subject-9"), staff_emails=[])


async def test_a_new_member_user_takes_over_the_member_record_with_that_address(
    make_member, empty_db
):
    member = await make_member("Lina H.", "LINA@mail.example")

    user = await complete_google_login(empty_db, profile(), staff_emails=[])

    assert str(user.member_id) == member["id"]
    assert user.display_name == "Lina H."
    assert await count(empty_db, Member) == 1


# The routes


@pytest.fixture
def google():
    """What the fake provider saw and what it answers with."""

    class FakeGoogle:
        def __init__(self):
            self.claims = profile()
            self.exchange_error = None
            self.exchanged = {}
            self.nonce = None

        async def fetch_access_token(self, **params):
            self.exchanged = params
            if self.exchange_error is not None:
                raise self.exchange_error
            return {"access_token": "access-1", "token_type": "Bearer", "id_token": "id-token-1"}

        async def parse_id_token(self, token, nonce, **_):
            self.nonce = nonce
            return self.claims

    return FakeGoogle()


@pytest.fixture
def app(make_db_app, google, monkeypatch):
    app = make_db_app(
        google_client_id="client-1",
        google_client_secret="secret-1",
        staff_emails=STAFF_EMAILS,
        public_base_url="https://library.example",
    )
    client = app.state.google
    client.server_metadata.update({**GOOGLE_METADATA, "_loaded_at": time.time()})
    monkeypatch.setattr(client, "fetch_access_token", google.fetch_access_token)
    monkeypatch.setattr(client, "parse_id_token", google.parse_id_token)
    return app


async def start_login(http, next_path="/my-loans"):
    response = await http.get("/api/auth/google/login", params={"next": next_path})
    assert response.status_code == 302, response.text
    return response


def query_of(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


async def test_login_redirects_to_google_with_state_nonce_and_pkce(anonymous):
    response = await start_login(anonymous)

    location = urlsplit(response.headers["location"])
    params = query_of(response.headers["location"])
    authorize_url = f"{location.scheme}://{location.netloc}{location.path}"
    assert authorize_url == GOOGLE_METADATA["authorization_endpoint"]
    assert params["response_type"] == "code"
    assert params["client_id"] == "client-1"
    assert params["redirect_uri"] == "https://library.example/api/auth/google/callback"
    assert params["scope"] == "openid email profile"
    assert params["code_challenge_method"] == "S256"
    assert params["state"] and params["nonce"] and params["code_challenge"]
    state_cookie = response.headers["set-cookie"].lower()
    assert state_cookie.startswith("oauth_state=")
    assert "path=/api/auth/google" in state_cookie
    assert "max-age=600" in state_cookie
    assert "httponly" in state_cookie
    assert "samesite=lax" in state_cookie


async def test_callback_signs_in_and_returns_to_next(anonymous, google):
    login = query_of((await start_login(anonymous, "/my-loans")).headers["location"])

    response = await anonymous.get(
        "/api/auth/google/callback", params={"code": "code-1", "state": login["state"]}
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/my-loans"
    assert google.exchanged["code"] == "code-1"
    assert google.exchanged["code_verifier"]
    assert google.exchanged["redirect_uri"] == "https://library.example/api/auth/google/callback"
    assert google.nonce == login["nonce"]
    me = (await anonymous.get("/api/auth/me")).json()
    assert (me["display_name"], me["role"], me["is_demo"]) == ("Lina Haddad", "member", False)


async def test_callback_makes_staff_list_addresses_staff(anonymous, google):
    google.claims = profile(email="ada@library.example", name="Ada")
    login = query_of((await start_login(anonymous)).headers["location"])

    await anonymous.get("/api/auth/google/callback", params={"code": "c", "state": login["state"]})

    assert (await anonymous.get("/api/auth/me")).json()["role"] == "staff"


@pytest.mark.parametrize(
    "next_path", ["//evil.example", "https://evil.example/", "/\\evil.example", "sign-in"]
)
async def test_callback_ignores_a_next_that_leaves_the_site(anonymous, next_path):
    login = query_of((await start_login(anonymous, next_path)).headers["location"])

    response = await anonymous.get(
        "/api/auth/google/callback", params={"code": "c", "state": login["state"]}
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/"


async def test_provider_failure_returns_to_the_sign_in_page(anonymous, google):
    google.exchange_error = OAuthError(error="invalid_grant")
    login = query_of((await start_login(anonymous)).headers["location"])

    response = await anonymous.get(
        "/api/auth/google/callback", params={"code": "c", "state": login["state"]}
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/sign-in?error=google"
    assert "session=" not in response.headers.get("set-cookie", "")
    assert (await anonymous.get("/api/auth/me")).status_code == 401


async def test_declined_consent_returns_to_the_sign_in_page(anonymous):
    login = query_of((await start_login(anonymous)).headers["location"])

    response = await anonymous.get(
        "/api/auth/google/callback", params={"error": "access_denied", "state": login["state"]}
    )

    assert response.headers["location"] == "/sign-in?error=google"


async def test_callback_without_a_matching_state_is_refused(anonymous, google):
    await start_login(anonymous)

    response = await anonymous.get(
        "/api/auth/google/callback", params={"code": "c", "state": "forged-state"}
    )

    assert response.headers["location"] == "/sign-in?error=google"
    assert google.exchanged == {}


async def test_callback_without_a_login_first_is_refused(anonymous):
    response = await anonymous.get(
        "/api/auth/google/callback", params={"code": "c", "state": "any-state"}
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/sign-in?error=google"


async def test_unverified_email_returns_to_the_sign_in_page(anonymous, google, empty_db):
    google.claims = profile(email_verified=False)
    login = query_of((await start_login(anonymous)).headers["location"])

    response = await anonymous.get(
        "/api/auth/google/callback", params={"code": "c", "state": login["state"]}
    )

    assert response.headers["location"] == "/sign-in?error=google"
    assert await count(empty_db, User) == 0


async def test_state_is_single_use(anonymous):
    login = query_of((await start_login(anonymous)).headers["location"])
    params = {"code": "c", "state": login["state"]}
    await anonymous.get("/api/auth/google/callback", params=params)

    replay = await anonymous.get("/api/auth/google/callback", params=params)

    assert replay.headers["location"] == "/sign-in?error=google"
