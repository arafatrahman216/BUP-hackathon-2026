"""Async SQLAlchemy engine, session factory and the `get_db` dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Base

settings = get_settings()

_url = settings.database_url
# Supabase's session pooler caps connections per project, so keep the pool small.
_pool = {} if _url.startswith("sqlite") else {"pool_size": 5, "max_overflow": 5}
engine = create_async_engine(_url, echo=settings.DB_ECHO, pool_pre_ping=True, **_pool)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Repositories commit their own writes."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables for all models (no migrations, see design.md)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
