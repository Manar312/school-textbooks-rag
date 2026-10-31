import logging

from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import RateLimited, Unauthorized
from app.core.security import create_token, hash_password, verify_password
from app.repositories import UserRepository

log = logging.getLogger(__name__)
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class AuthService:
    def __init__(self, users: UserRepository, redis: Redis | None):
        self.users, self.redis = users, redis

    async def _throttle(self, ip: str) -> None:
        if self.redis is None:
            return
        try:
            key = f"login:{ip}"
            n = await self.redis.incr(key)
            if n == 1:
                await self.redis.expire(key, 300)
            if n > settings.login_attempts_per_5min:
                raise RateLimited("Too many login attempts, try again in a few minutes.")
        except RateLimited:
            raise
        except Exception:
            log.warning("redis unavailable: login throttle skipped")  # never block logins because redis is down

    async def login(self, email: str, password: str, ip: str) -> str:
        await self._throttle(ip)
        user = await self.users.get_by_email(email)
        ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)  # constant-ish time
        if not user or not ok or not user.is_active:
            raise Unauthorized("Wrong email or password")
        return create_token(user.id, user.role)
