import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.s.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return (await self.s.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return (await self.s.execute(select(User.id).where(User.email == email.lower()))).first() is not None

    async def add(self, user: User) -> User:
        self.s.add(user)
        await self.s.commit()
        await self.s.refresh(user)
        return user

    async def list_students(self, grade: str | None = None) -> list[User]:
        q = select(User).where(User.role == "student").order_by(User.full_name)
        if grade:
            q = q.where(User.grade == grade)
        return list((await self.s.execute(q)).scalars().all())

    async def save(self, user: User) -> User:
        await self.s.commit()
        await self.s.refresh(user)
        return user
