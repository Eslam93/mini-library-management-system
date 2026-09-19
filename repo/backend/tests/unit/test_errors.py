import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationFailedError,
)

APP_ERRORS: dict[str, type[AppError]] = {
    "not-found": NotFoundError,
    "conflict": ConflictError,
    "validation-failed": ValidationFailedError,
    "unauthorized": UnauthorizedError,
    "forbidden": ForbiddenError,
}


class NewMember(BaseModel):
    name: str
    age: int


@pytest.fixture
def app(make_app) -> FastAPI:
    app = make_app()

    @app.get("/api/test/app-error/{kind}")
    async def raise_app_error(kind: str) -> None:
        raise APP_ERRORS[kind](details={"kind": kind})

    @app.get("/api/test/custom-error")
    async def raise_custom_error() -> None:
        raise ConflictError("That copy is already on loan.", code="copy_unavailable")

    @app.get("/api/test/http-error")
    async def raise_http_error() -> None:
        raise HTTPException(status_code=403, detail="No entry.")

    @app.post("/api/test/members")
    async def create_member(member: NewMember) -> NewMember:
        return member

    @app.get("/api/test/crash")
    async def crash() -> None:
        raise RuntimeError("database password is not-a-real-password")

    return app


def assert_envelope(body: dict[str, object], code: str, request_id: str) -> None:
    assert set(body) == {"error", "meta"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == code
    assert body["meta"] == {"request_id": request_id}


@pytest.mark.parametrize("kind", list(APP_ERRORS))
async def test_app_errors_use_their_status_and_code(client, kind):
    error_class = APP_ERRORS[kind]

    response = await client.get(f"/api/test/app-error/{kind}")

    assert response.status_code == error_class.status_code
    body = response.json()
    assert_envelope(body, error_class.code, response.headers["x-request-id"])
    assert body["error"]["message"] == error_class.message
    assert body["error"]["details"] == {"kind": kind}


async def test_app_error_message_and_code_can_be_overridden(client):
    response = await client.get("/api/test/custom-error")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "copy_unavailable",
        "message": "That copy is already on loan.",
        "details": {},
    }


async def test_http_exception_uses_the_envelope(client):
    response = await client.get("/api/test/http-error")

    assert response.status_code == 403
    assert_envelope(response.json(), "forbidden", response.headers["x-request-id"])
    assert response.json()["error"]["message"] == "No entry."


async def test_unknown_api_path_is_a_json_404(client):
    response = await client.get("/api/no-such-thing")

    assert response.status_code == 404
    assert_envelope(response.json(), "not_found", response.headers["x-request-id"])


async def test_wrong_method_is_a_json_405(client):
    response = await client.delete("/api/test/members")

    assert response.status_code == 405
    assert_envelope(response.json(), "method_not_allowed", response.headers["x-request-id"])
    assert response.headers["allow"] == "POST"


async def test_validation_error_lists_fields_without_echoing_input(client):
    response = await client.post("/api/test/members", json={"age": "secret-typed-value-123"})

    assert response.status_code == 422
    body = response.json()
    assert_envelope(body, "validation_failed", response.headers["x-request-id"])
    errors = {tuple(e["location"]): e for e in body["error"]["details"]["errors"]}
    assert set(errors) == {("body", "name"), ("body", "age")}
    assert all(set(e) == {"location", "message", "type"} for e in errors.values())
    assert "secret-typed-value-123" not in response.text


async def test_unhandled_error_is_a_generic_500_logged_with_the_request_id(client, capsys):
    response = await client.get("/api/test/crash", headers={"X-Request-ID": "crash-check-1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": {},
        },
        "meta": {"request_id": "crash-check-1"},
    }
    assert "not-a-real-password" not in response.text
    assert response.headers["x-request-id"] == "crash-check-1"
    assert response.headers["x-content-type-options"] == "nosniff"

    logged = capsys.readouterr().out
    unhandled_lines = [line for line in logged.splitlines() if "unhandled_error" in line]
    assert unhandled_lines
    assert "crash-check-1" in unhandled_lines[0]
