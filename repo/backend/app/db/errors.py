"""Turns database constraint violations into the application's own errors."""

from collections.abc import Mapping

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError


def violated_constraint(error: IntegrityError) -> str | None:
    """The name of the constraint or unique index that rejected a write, when reported."""
    # SQLAlchemy wraps the asyncpg error; asyncpg names the constraint.
    driver_error = getattr(error.orig, "__cause__", None)
    name = getattr(driver_error, "constraint_name", None)
    return name if isinstance(name, str) else None


async def flush_or_raise(session: AsyncSession, errors: Mapping[str, AppError]) -> None:
    """Flushes pending writes. When one of the named constraints rejects them, the transaction
    is rolled back and the matching error is raised; any other violation is re-raised as is.
    """
    try:
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        known = errors.get(violated_constraint(error) or "")
        if known is None:
            raise
        raise known from error
