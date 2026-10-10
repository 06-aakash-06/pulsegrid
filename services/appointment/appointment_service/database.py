"""Async SQLAlchemy pool and sessions owned exclusively by this service."""

from __future__ import annotations
import asyncio
from collections.abc import AsyncIterator
from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from .settings import Settings


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    async def start(self) -> None:
        if not self.settings.database_configured:
            return
        self.engine = create_async_engine(
            self.settings.database_url,
            isolation_level="READ COMMITTED",
            pool_size=self.settings.db_pool_size,
            max_overflow=self.settings.db_max_overflow,
            pool_timeout=self.settings.db_pool_timeout,
            pool_recycle=300,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args=self.settings.connection_options,
        )
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    async def readiness(self) -> str:
        if not self.settings.database_configured:
            return "unconfigured"
        if self.engine is None:
            return "unavailable"
        try:
            async with asyncio.timeout(self.settings.db_health_timeout):
                async with self.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            return "available"
        except (SQLAlchemyError, OSError, TimeoutError):
            return "unavailable"


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Future commands explicitly commit/transaction; uncommitted work rolls back."""
    database: Database = request.app.state.database
    if database.session_factory is None:
        raise HTTPException(status_code=503)
    async with database.session_factory() as session:
        yield session
