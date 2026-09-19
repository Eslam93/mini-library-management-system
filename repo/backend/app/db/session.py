"""Database engine, session factory, request-scoped session dependency and health probe."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.logging import get_logger

log = get_logger(__name__)


def create_engine(database_url: str) -> AsyncEngine:
    """Creates the connection pool. No connection is opened until first use."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yields one session per request. Work that is not committed is rolled back on close."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


async def ping_database(engine: AsyncEngine, *, timeout: float) -> bool:
    """Returns True when SELECT 1 succeeds within the timeout."""
    try:
        async with asyncio.timeout(timeout), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("database_unavailable", error=type(exc).__name__)
        return False
    return True
