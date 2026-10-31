import uuid

from app.core.config import settings
from app.core.errors import AppError, Conflict, NotFound
from app.models import Book, ChatSession, Message, User
from app.repositories import BookRepository, ChatRepository
from app.services.quota_service import QuotaService
from app.services.rag_service import RagService


class ChatService:
    """Student-facing operations. Every call is scoped to the authenticated student."""

    def __init__(self, chats: ChatRepository, books: BookRepository, quota: QuotaService, rag: RagService):
        self.chats, self.books, self.quota, self.rag = chats, books, quota, rag

    async def library(self, user: User) -> dict:
        out: dict[str, list] = {}
        for b in await self.books.list_available_for_grade(user.grade):
            out.setdefault(b.subject, []).append({"id": str(b.id), "title": b.title, "term": b.term, "language": b.language})
        return {"grade": user.grade, "subjects": out}

    async def usage(self, user: User) -> dict:
        u = await self.quota.usage_today(user.id)
        return {**u, "request_limit": user.daily_request_limit, "token_limit": user.daily_token_limit}

    async def create_session(self, user: User, title: str | None, subject: str | None) -> ChatSession:
        return await self.chats.create_session(user.id, title or "New chat", subject)

    async def list_sessions(self, user: User) -> list[ChatSession]:
        return await self.chats.list_sessions(user.id)

    async def _own(self, user: User, sid: uuid.UUID) -> ChatSession:
        chat = await self.chats.get_session(sid, user.id)
        if chat is None:
            raise NotFound("Chat not found")
        return chat

    async def messages(self, user: User, sid: uuid.UUID, limit: int) -> list[Message]:
        await self._own(user, sid)
        return await self.chats.list_messages(sid, user.id, limit)

    async def delete_session(self, user: User, sid: uuid.UUID) -> None:
        await self._own(user, sid)
        await self.chats.delete_session(sid, user.id)

    async def start_ask(self, user: User, sid: uuid.UUID, question: str, subject: str | None,
                        book_id: uuid.UUID | None):
        """Runs every pre-check eagerly (so errors become proper HTTP responses), then returns the event stream."""
        question = question.strip()
        if not question:
            raise AppError("Question is empty", code="empty_question", status_code=422)
        if len(question) > settings.max_question_chars:
            raise AppError(f"Question is too long (max {settings.max_question_chars} characters)",
                           code="question_too_long", status_code=422)
        chat = await self._own(user, sid)
        target: str | None = None
        if book_id:  # a student may only target ready books of their own grade
            book: Book | None = await self.books.get(book_id)
            if book is None or book.grade != user.grade or book.status not in ("ready", "partial"):
                raise NotFound("Book not found")
            target = str(book.id)
        await self.quota.enforce(user.id, user.daily_request_limit, user.daily_token_limit)
        if not await self.rag.acquire_lock(sid):
            raise Conflict("The previous question in this chat is still being answered.", code="chat_busy")
        return self.rag.ask(user_id=user.id, grade=user.grade, session_id=sid, question=question,
                            subject=subject or chat.subject, book_id=target)
