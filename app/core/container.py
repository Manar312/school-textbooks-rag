"""Composition root: the only place that knows which concrete classes are wired together.
Controllers/services receive what they need from here, so tests can build a Container with fake providers."""
from functools import cached_property

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.db import SessionLocal, scoped
from app.providers import Providers
from app.repositories import BookRepository, ChatRepository, UsageRepository
from app.services.quota_service import QuotaService
from app.services.rag_service import RagService
from app.services.retrieval import Retriever
from app.workers.queue import CeleryJobQueue, JobQueue


class Container:
    def __init__(self, settings: Settings, *, providers: Providers | None = None, redis: Redis | None = None,
                 jobs: JobQueue | None = None, sessionmaker=SessionLocal):
        self.settings = settings
        self.providers = providers or Providers(settings)
        self.redis = redis
        self.jobs = jobs or CeleryJobQueue()
        self.sessionmaker = sessionmaker

    # fresh-session repo openers for long-running work
    @cached_property
    def open_chat_repo(self):
        return scoped(ChatRepository, self.sessionmaker)

    @cached_property
    def open_usage_repo(self):
        return scoped(UsageRepository, self.sessionmaker)

    @cached_property
    def open_book_repo(self):
        return scoped(BookRepository, self.sessionmaker)

    @cached_property
    def quota(self) -> QuotaService:
        return QuotaService(self.open_usage_repo, self.redis)

    @cached_property
    def retriever(self) -> Retriever:
        p = self.providers
        return Retriever(p.embedder, p.vectors, p.reranker)

    @cached_property
    def rag(self) -> RagService:
        p = self.providers
        return RagService(llm=p.llm, condense_llm=p.condense_llm, retriever=self.retriever, quota=self.quota,
                          open_chat_repo=self.open_chat_repo, redis=self.redis)
