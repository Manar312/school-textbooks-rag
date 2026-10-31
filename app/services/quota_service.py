import logging
import time
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import QuotaExceeded, RateLimited
from app.repositories import UsageRepository

log = logging.getLogger(__name__)


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


class QuotaService:
    def __init__(self, repo_factory, redis: Redis):
        self.repo_factory = repo_factory
        self.redis = redis

    async def enforce(self, user_id: uuid.UUID, request_limit: int, token_limit: int) -> None:
        """Burst limit (Redis, fails open) + daily limits (Postgres, source of truth)."""
        if self.redis is not None:
            try:
                key = f"rl:{user_id}:{int(time.time() // 60)}"
                n = await self.redis.incr(key)
                if n == 1:
                    await self.redis.expire(key, 90)
                if n > settings.rate_limit_per_minute:
                    raise RateLimited("Too many questions in a minute, slow down a little.")
            except RedisError:
                log.warning("redis unavailable: per-minute rate limit skipped")
        async with self.repo_factory() as repo:
            row = await repo.get(user_id, today())
        if row and row.requests >= request_limit:
            raise QuotaExceeded("Daily question limit reached. It resets at midnight (Cairo time).")
        if row and (row.tokens_in + row.tokens_out) >= token_limit:
            raise QuotaExceeded("Daily usage limit reached. It resets at midnight (Cairo time).")

    async def record(self, user_id: uuid.UUID, tokens_in: int, tokens_out: int) -> None:
        async with self.repo_factory() as repo:
            await repo.increment(user_id, today(), tokens_in, tokens_out)

    async def usage_today(self, user_id: uuid.UUID) -> dict:
        async with self.repo_factory() as repo:
            row = await repo.get(user_id, today())
        return {"day": today().isoformat(), "requests": row.requests if row else 0,
                "tokens_in": row.tokens_in if row else 0, "tokens_out": row.tokens_out if row else 0}
