from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers import Providers


class HealthController:
    def __init__(self, session: AsyncSession, redis, providers: Providers):
        self.session, self.redis, self.providers = session, redis, providers

    async def ready(self) -> tuple[bool, dict]:
        checks: dict = {}
        try:
            await self.session.execute(text("SELECT 1"))
            checks["postgres"] = True
        except Exception:
            checks["postgres"] = False
        try:
            checks["redis"] = bool(await self.redis.ping())
        except Exception:
            checks["redis"] = False
        checks["vectorstore"] = await self.providers.vectors.ping()
        ok = all(checks.values())
        return ok, {"status": "ok" if ok else "degraded", **checks, "providers": self.providers.describe()}
