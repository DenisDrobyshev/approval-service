"""Async SQLAlchemy engine, session factory and FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()

_engine_kwargs: dict = {"future": True, "echo": False}
# SQLite connections are tied to the event loop that opened them; NullPool
# avoids reusing a pooled connection across loops (e.g. between async tests).
# The busy timeout lets a writer wait for a lock instead of failing fast,
# which otherwise shows up as intermittent "database is locked" errors.
if _settings.database_url.startswith("sqlite"):
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {"timeout": 30}

engine = create_async_engine(_settings.database_url, **_engine_kwargs)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session scoped to a single request."""
    async with SessionLocal() as session:
        yield session
