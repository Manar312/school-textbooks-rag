import logging

from celery import Celery

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

celery_app = Celery("school_rag", broker=settings.redis_url, backend=settings.redis_url,
                    include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,                # redeliver if the worker dies mid-task (ingestion is resumable)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="ingest",
    task_soft_time_limit=60 * 60 * 3,
    task_time_limit=60 * 60 * 3 + 300,
    broker_transport_options={"visibility_timeout": 60 * 60 * 4},
)
