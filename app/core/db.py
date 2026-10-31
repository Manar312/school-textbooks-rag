from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def make_engine(null_pool: bool = False) -> AsyncEngine:
    if null_pool:  # Celery tasks: fresh event loop per task, so no pooled connections
        return create_async_engine(settings.database_url, poolclass=NullPool)
    return create_async_engine(settings.database_url, pool_size=10, max_overflow=20, pool_pre_ping=True)


engine = make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def scoped(repo_cls, sm=None):
    """Returns `open()` -> async context manager yielding repo_cls(fresh_session).
    Used by long-lived services (streaming answers, ingestion tasks) that must not hold one request session."""
    sm = sm or SessionLocal

    @asynccontextmanager
    async def open_repo():
        async with sm() as s:
            yield repo_cls(s)
    return open_repo
