import uuid
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageDaily


class UsageRepository:
    def __init__(self, s: AsyncSession):
        self.s = s

    async def get(self, user_id: uuid.UUID, day: date) -> UsageDaily | None:
        return await self.s.get(UsageDaily, (user_id, day))

    async def increment(self, user_id: uuid.UUID, day: date, tokens_in: int, tokens_out: int) -> None:
        stmt = pg_insert(UsageDaily).values(user_id=user_id, day=day, requests=1,
                                            tokens_in=tokens_in, tokens_out=tokens_out)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "day"],
            set_={"requests": UsageDaily.requests + 1, "tokens_in": UsageDaily.tokens_in + tokens_in,
                  "tokens_out": UsageDaily.tokens_out + tokens_out})
        await self.s.execute(stmt)
        await self.s.commit()
