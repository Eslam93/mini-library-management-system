"""Service health, including whether the database answers."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import get_engine, ping_database

DATABASE_PROBE_TIMEOUT_SECONDS = 2.0

router = APIRouter(tags=["health"])


class HealthChecks(BaseModel):
    database: Literal["ok", "unavailable"]


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    checks: HealthChecks


@router.get(
    "/health",
    responses={503: {"model": HealthReport, "description": "A dependency is unavailable"}},
)
async def health(
    response: Response, engine: Annotated[AsyncEngine, Depends(get_engine)]
) -> HealthReport:
    database_ok = await ping_database(engine, timeout=DATABASE_PROBE_TIMEOUT_SECONDS)
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthReport(
        status="ok" if database_ok else "degraded",
        checks=HealthChecks(database="ok" if database_ok else "unavailable"),
    )
