"""Shapes shared by several endpoints: paging and the error envelope."""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorMeta(BaseModel):
    request_id: str | None


class ErrorResponse(BaseModel):
    """The envelope every error response uses."""

    error: ErrorBody
    meta: ErrorMeta


def error_responses(
    *,
    signed_in: bool = False,
    staff: bool = False,
    not_found: bool = False,
    conflicts: Sequence[str] = (),
) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries for a route's error responses: whether it needs a signed-in user or staff,
    and the conflict codes it can return.
    """
    responses: dict[int | str, dict[str, Any]] = {
        422: {
            "model": ErrorResponse,
            "description": "validation_failed: details.errors lists each field "
            "as {location, message, type}",
        }
    }
    if signed_in or staff:
        responses[401] = {"model": ErrorResponse, "description": "unauthorized: not signed in"}
    if staff:
        responses[403] = {"model": ErrorResponse, "description": "forbidden: staff only"}
    if not_found:
        responses[404] = {"model": ErrorResponse, "description": "not_found"}
    if conflicts:
        responses[409] = {"model": ErrorResponse, "description": ", ".join(conflicts)}
    return responses
