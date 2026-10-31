import json
import uuid
from typing import AsyncIterator

from app.core.errors import AppError
from app.models import User
from app.schemas import AskIn, MessageOut, SessionCreate, SessionOut
from app.services.chat_service import ChatService

_STATUS = {"search_unavailable": 503, "llm_unavailable": 502}


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatController:
    def __init__(self, chat: ChatService):
        self.chat = chat

    async def library(self, user: User) -> dict:
        return await self.chat.library(user)

    async def usage(self, user: User) -> dict:
        return await self.chat.usage(user)

    async def create_session(self, user: User, body: SessionCreate) -> SessionOut:
        return SessionOut.model_validate(await self.chat.create_session(user, body.title, body.subject))

    async def list_sessions(self, user: User) -> list[SessionOut]:
        return [SessionOut.model_validate(c) for c in await self.chat.list_sessions(user)]

    async def messages(self, user: User, sid: uuid.UUID, limit: int) -> list[MessageOut]:
        return [MessageOut.model_validate(m) for m in await self.chat.messages(user, sid, limit)]

    async def delete_session(self, user: User, sid: uuid.UUID) -> None:
        await self.chat.delete_session(user, sid)

    async def start(self, user: User, sid: uuid.UUID, body: AskIn) -> AsyncIterator[dict]:
        return await self.chat.start_ask(user, sid, body.question, body.subject, body.book_id)

    @staticmethod
    async def as_sse(events: AsyncIterator[dict]) -> AsyncIterator[str]:
        async for ev in events:
            yield sse(ev["event"], ev["data"])
        yield sse("done", {})

    @staticmethod
    async def as_json(events: AsyncIterator[dict]) -> dict:
        parts, citations = [], []
        async for ev in events:
            if ev["event"] == "token":
                parts.append(ev["data"]["text"])
            elif ev["event"] == "citations":
                citations = ev["data"]
            elif ev["event"] == "error":
                raise AppError(ev["data"]["message"], code=ev["data"]["code"],
                               status_code=_STATUS.get(ev["data"]["code"], 500))
        return {"answer": "".join(parts), "citations": citations}
