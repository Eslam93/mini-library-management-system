"""Application errors and the handlers that render every error in one JSON envelope:
{"error": {"code", "message", "details"}, "meta": {"request_id"}}.
"""

from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from typing import Any, Self

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import get_request_id

log = get_logger(__name__)


class AppError(Exception):
    """Base for errors that map to a specific HTTP status and a stable error code."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.code = code or type(self).code
        self.details = dict(details or {})
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_failed"
    message = "The request is not valid."

    @classmethod
    def for_field(cls, field: str, message: str, error_type: str) -> Self:
        """A business rule rejected one body field. The details have the same shape as request
        validation errors, so clients show both next to the field.
        """
        error = {"location": ["body", field], "message": message, "type": error_type}
        return cls(details={"errors": [error]})


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Authentication is required."


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to perform this action."


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {"code": code, "message": message, "details": dict(details or {})},
        "meta": {"request_id": get_request_id()},
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    try:
        http_status = HTTPStatus(exc.status_code)
        code, phrase = http_status.name.lower(), http_status.phrase
    except ValueError:
        code, phrase = "http_error", "HTTP error"
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else phrase
    details = exc.detail if isinstance(exc.detail, dict) else None
    return error_response(exc.status_code, code, message, details, exc.headers)


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only the location, message and type of each error are returned, never the input value.
    errors = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return error_response(
        ValidationFailedError.status_code,
        ValidationFailedError.code,
        ValidationFailedError.message,
        {"errors": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_error", method=request.method, path=request.url.path, exc_info=exc)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, AppError.code, AppError.message)


_HANDLERS: dict[type[Exception], Callable[[Request, Any], Awaitable[JSONResponse]]] = {
    AppError: app_error_handler,
    RequestValidationError: validation_exception_handler,
    StarletteHTTPException: http_exception_handler,
    # Last resort for errors raised outside the error middleware.
    Exception: unhandled_exception_handler,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exc_class, handler in _HANDLERS.items():
        app.add_exception_handler(exc_class, handler)
