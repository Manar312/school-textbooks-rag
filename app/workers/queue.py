"""Job queue abstraction: services enqueue work through this interface, Celery is just one implementation."""
from abc import ABC, abstractmethod

from app.core.errors import AppError


class JobQueue(ABC):
    @abstractmethod
    def enqueue_ingest(self, book_id: str, *, reindex_only: bool = False) -> None: ...


class CeleryJobQueue(JobQueue):
    def enqueue_ingest(self, book_id: str, *, reindex_only: bool = False) -> None:
        from app.workers.tasks import ingest_book
        try:
            ingest_book.delay(book_id, reindex_only=reindex_only)
        except Exception as e:
            raise AppError("Job queue unavailable, try again shortly.", code="queue_unavailable",
                           status_code=503) from e
