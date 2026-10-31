import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.container import Container
from app.core.db import make_engine
from app.repositories import BookRepository
from app.services.ingestion import IngestionService
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


async def _ingest(book_id: str, reindex_only: bool) -> None:
    # Fresh engine + providers per task: each asyncio.run() has its own event loop, and async SDK clients/DB
    # connections must not outlive it. Heavy local model weights are cached at module level inside the providers.
    engine = make_engine(null_pool=True)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    container = Container(settings, sessionmaker=sm)
    try:
        roles = ("vectors", "embedder") if reindex_only else ("vlm", "ocr", "vectors", "embedder")
        container.providers.validate(roles)
        async with sm() as s:
            svc = IngestionService(BookRepository(s), container.open_book_repo, container.providers)
            await svc.run(uuid.UUID(book_id), reindex_only=reindex_only)
    finally:
        await container.providers.aclose()
        await engine.dispose()


@celery_app.task(name="ingest_book", bind=True, max_retries=2, default_retry_delay=60)
def ingest_book(self, book_id: str, reindex_only: bool = False):
    try:
        asyncio.run(_ingest(book_id, reindex_only))
    except Exception as e:
        raise self.retry(exc=e)
