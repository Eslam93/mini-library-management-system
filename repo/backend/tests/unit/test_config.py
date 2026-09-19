from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_DIR, DEV_SESSION_SECRET, Settings, get_settings
from app.main import create_app


def make_settings(**values):
    return Settings(_env_file=None, **values)


@pytest.fixture
def no_settings_in_the_environment(monkeypatch):
    """Settings read the process environment as well as the file, and a runner may set some of
    them (CI sets APP_ENV and DATABASE_URL), so a test about the defaults clears them first.
    """
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_local_defaults(no_settings_in_the_environment):
    settings = make_settings()

    assert settings.app_env == "local"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.session_secret.get_secret_value() == DEV_SESSION_SECRET
    assert settings.frontend_dist_dir == BACKEND_DIR.parent / "frontend" / "dist"
    assert settings.loan_period_days == 14


@pytest.mark.parametrize("days", [0, 91])
def test_loan_period_must_be_1_to_90_days(days):
    with pytest.raises(ValidationError, match="loan_period_days"):
        make_settings(loan_period_days=days)


@pytest.mark.parametrize("secret", [DEV_SESSION_SECRET, "too-short-but-private"])
def test_production_rejects_weak_session_secret_without_printing_it(secret):
    with pytest.raises(ValidationError) as caught:
        make_settings(app_env="production", session_secret=secret)

    message = str(caught.value)
    assert "SESSION_SECRET" in message
    assert secret not in message


def test_production_accepts_a_long_session_secret():
    settings = make_settings(app_env="production", session_secret="k" * 32)

    assert settings.is_production


def test_sign_in_defaults():
    settings = make_settings()

    assert settings.demo_login_enabled is True
    assert settings.google_enabled is False
    assert settings.staff_emails == []
    assert settings.session_idle_timeout == timedelta(hours=12)
    assert settings.session_lifetime == timedelta(days=7)
    assert settings.google_redirect_uri == "http://localhost:8000/api/auth/google/callback"
    assert settings.allowed_origins == ["http://localhost:8000", "http://localhost:5173"]


def test_production_turns_demo_sign_in_off_and_allows_only_its_own_origin():
    settings = make_settings(
        app_env="production", session_secret="k" * 40, public_base_url="https://library.example/"
    )

    assert settings.demo_login_enabled is False
    assert settings.allowed_origins == ["https://library.example"]
    assert settings.google_redirect_uri == "https://library.example/api/auth/google/callback"


def test_demo_sign_in_can_be_turned_on_in_production(monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "true")

    settings = make_settings(app_env="production", session_secret="k" * 40)

    assert settings.demo_login_enabled is True


def test_demo_sign_in_can_be_turned_off_locally():
    assert make_settings(demo_login_enabled=False).demo_login_enabled is False


def test_list_settings_are_read_from_comma_separated_values(monkeypatch):
    monkeypatch.setenv("STAFF_EMAILS", " Ada@Library.example, grace@library.example,, ")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://library.example,https://staff.library.example")

    settings = make_settings()

    assert settings.staff_emails == ["Ada@Library.example", "grace@library.example"]
    assert settings.allowed_origins == ["https://library.example", "https://staff.library.example"]


@pytest.mark.parametrize(
    ("client_id", "client_secret", "enabled"),
    [("id-1", "secret-1", True), ("id-1", None, False), (None, "secret-1", False), ("", "", False)],
)
def test_google_is_enabled_only_with_client_id_and_secret(client_id, client_secret, enabled):
    settings = make_settings(google_client_id=client_id, google_client_secret=client_secret)

    assert settings.google_enabled is enabled


def test_google_client_secret_is_kept_out_of_the_settings_repr():
    settings = make_settings(google_client_id="id-1", google_client_secret="very-private-value")

    assert "very-private-value" not in repr(settings)


def test_app_refuses_to_start_in_production_with_the_dev_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", DEV_SESSION_SECRET)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="SESSION_SECRET"):
            create_app()
    finally:
        get_settings.cache_clear()
