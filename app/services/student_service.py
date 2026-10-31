import uuid

from app.core.config import settings
from app.core.errors import Conflict, NotFound
from app.core.security import hash_password
from app.models import User
from app.repositories import ChatRepository, UserRepository
from app.schemas import StudentCreate, StudentPatch
from app.services.quota_service import QuotaService


class StudentService:
    def __init__(self, users: UserRepository, chats: ChatRepository, quota: QuotaService):
        self.users, self.chats, self.quota = users, chats, quota

    async def create(self, body: StudentCreate) -> User:
        if await self.users.email_exists(body.email):
            raise Conflict("Email already registered.", code="email_taken")
        return await self.users.add(User(
            email=body.email.lower(), password_hash=hash_password(body.password), full_name=body.full_name,
            role="student", grade=body.grade,
            daily_request_limit=body.daily_request_limit if body.daily_request_limit is not None else settings.default_daily_requests,
            daily_token_limit=body.daily_token_limit if body.daily_token_limit is not None else settings.default_daily_tokens))

    async def _student(self, uid: uuid.UUID) -> User:
        u = await self.users.get(uid)
        if not u or u.role != "student":
            raise NotFound("Student not found")
        return u

    async def list_students(self, grade: str | None) -> list[User]:
        return await self.users.list_students(grade)

    async def patch(self, uid: uuid.UUID, body: StudentPatch) -> User:
        u = await self._student(uid)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(u, k, v)
        return await self.users.save(u)

    async def usage(self, uid: uuid.UUID) -> dict:
        u = await self._student(uid)
        chats, msgs = await self.chats.counts_for_user(uid)
        return {"today": await self.quota.usage_today(uid), "request_limit": u.daily_request_limit,
                "token_limit": u.daily_token_limit, "chats": chats, "messages": msgs}
