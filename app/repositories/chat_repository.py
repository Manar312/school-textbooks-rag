import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatSession, Message


class ChatRepository:
    """Every read is scoped by user_id: a student can never reach another student's chat."""

    def __init__(self, s: AsyncSession):
        self.s = s

    async def create_session(self, user_id: uuid.UUID, title: str, subject: str | None) -> ChatSession:
        chat = ChatSession(user_id=user_id, title=title, subject=subject)
        self.s.add(chat)
        await self.s.commit()
        await self.s.refresh(chat)
        return chat

    async def get_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> ChatSession | None:
        return (await self.s.execute(select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id))).scalar_one_or_none()

    async def list_sessions(self, user_id: uuid.UUID, limit: int = 200) -> list[ChatSession]:
        rows = await self.s.execute(select(ChatSession).where(ChatSession.user_id == user_id)
                                    .order_by(ChatSession.updated_at.desc()).limit(limit))
        return list(rows.scalars().all())

    async def delete_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.s.execute(delete(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id))
        await self.s.commit()

    async def list_messages(self, session_id: uuid.UUID, user_id: uuid.UUID, limit: int = 200) -> list[Message]:
        rows = await self.s.execute(select(Message).where(Message.session_id == session_id, Message.user_id == user_id)
                                    .order_by(Message.id).limit(min(max(limit, 1), 500)))
        return list(rows.scalars().all())

    async def recent_history(self, session_id: uuid.UUID, user_id: uuid.UUID, limit: int) -> list[dict]:
        rows = (await self.s.execute(select(Message.role, Message.content).where(
            Message.session_id == session_id, Message.user_id == user_id)
            .order_by(Message.id.desc()).limit(limit))).all()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    async def add_message(self, *, session_id: uuid.UUID, user_id: uuid.UUID, role: str, content: str,
                          citations: list | None = None, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.s.add(Message(session_id=session_id, user_id=user_id, role=role, content=content,
                           citations=citations, tokens_in=tokens_in, tokens_out=tokens_out))
        await self.s.commit()

    async def set_title_if_default(self, session_id: uuid.UUID, user_id: uuid.UUID, title: str) -> None:
        chat = await self.get_session(session_id, user_id)
        if chat and chat.title == "New chat":
            chat.title = title
            await self.s.commit()

    async def counts_for_user(self, user_id: uuid.UUID) -> tuple[int, int]:
        chats = (await self.s.execute(select(func.count()).select_from(ChatSession)
                                      .where(ChatSession.user_id == user_id))).scalar_one()
        msgs = (await self.s.execute(select(func.count()).select_from(Message)
                                     .where(Message.user_id == user_id))).scalar_one()
        return chats, msgs
