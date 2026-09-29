"""Async SQLAlchemy engine, session factory and the `get_db` dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Base

settings = get_settings()

_url = settings.database_url
if _url.startswith("sqlite"):
    _options: dict = {}
else:
    _options = {
        # small pool: also fits Supabase's session pooler, which caps connections per project
        "pool_size": 5, "max_overflow": 5,
        "pool_recycle": 300,  # replace idle connections before a network middlebox drops them
        # asyncpg: a query on a dead connection fails after N s instead of hanging forever
        "connect_args": {"command_timeout": settings.DB_COMMAND_TIMEOUT_SECONDS},
    }
engine = create_async_engine(_url, echo=settings.DB_ECHO, pool_pre_ping=True, **_options)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Repositories commit their own writes."""
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables for all models (no migrations, see design.md)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
