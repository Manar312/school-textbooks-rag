"""Answer orchestration: smalltalk shortcut -> condense follow-up -> retrieve -> stream answer with citations.
Depends only on provider interfaces (via Retriever / LLMProvider) and repositories."""
import asyncio
import logging
import uuid
from typing import AsyncIterator

from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import AppError
from app.core.textutil import NOT_FOUND_MESSAGES, detect_language, smalltalk_reply
from app.providers import LLMProvider
from app.services.prompts import (CONDENSE_SYSTEM, SYSTEM_TEMPLATE, format_context, grade_label, normalize_history,
                                  used_citation_numbers)
from app.services.quota_service import QuotaService
from app.services.retrieval import Retriever

log = logging.getLogger(__name__)
LOCK_TTL = 120


class RagService:
    def __init__(self, *, llm: LLMProvider, condense_llm: LLMProvider, retriever: Retriever, quota: QuotaService,
                 open_chat_repo, redis: Redis | None):
        self.llm, self.condense_llm, self.retriever = llm, condense_llm, retriever
        self.quota, self.open_chat_repo, self.redis = quota, open_chat_repo, redis

    # one in-flight answer per chat: prevents interleaved history when a student double-submits
    async def acquire_lock(self, session_id: uuid.UUID) -> bool:
        if self.redis is None:
            return True
        try:
            return bool(await self.redis.set(f"chatlock:{session_id}", "1", nx=True, ex=LOCK_TTL))
        except Exception:
            log.warning("redis unavailable: chat lock skipped")
            return True

    async def release_lock(self, session_id: uuid.UUID) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.delete(f"chatlock:{session_id}")
        except Exception:
            log.warning("could not release chat lock %s (expires by TTL)", session_id)

    async def _prepare(self, user_id, session_id, question) -> list[dict]:
        async with self.open_chat_repo() as repo:
            history = await repo.recent_history(session_id, user_id, settings.history_messages)
            await repo.add_message(session_id=session_id, user_id=user_id, role="user", content=question)
            await repo.set_title_if_default(session_id, user_id, question.strip().replace("\n", " ")[:60])
        return [{"role": m["role"], "content": m["content"][:2000]} for m in history]

    async def _finalize(self, user_id, session_id, answer, citations, tin, tout) -> None:
        try:
            if answer.strip():
                async with self.open_chat_repo() as repo:
                    await repo.add_message(session_id=session_id, user_id=user_id, role="assistant", content=answer,
                                           citations=citations, tokens_in=tin, tokens_out=tout)
            if answer.strip() or tin or tout:
                await self.quota.record(user_id, tin, tout)
        except Exception:
            log.exception("finalize failed for session %s", session_id)
        finally:
            await self.release_lock(session_id)

    async def _condense(self, history: list[dict], question: str) -> tuple[str, int, int]:
        convo = "\n".join(f"{m['role']}: {m['content'][:600]}" for m in history[-6:])
        r = await self.condense_llm.complete(
            system=CONDENSE_SYSTEM, max_tokens=200,
            messages=[{"role": "user", "content": f"Conversation:\n{convo}\n\nLast question: {question}"}])
        return (r.text or question), r.tokens_in, r.tokens_out

    async def ask(self, *, user_id: uuid.UUID, grade: str, session_id: uuid.UUID, question: str,
                  subject: str | None = None, book_id: str | None = None) -> AsyncIterator[dict]:
        answer_parts: list[str] = []
        citations: list[dict] | None = None
        tin = tout = prompt_chars = 0
        usage_seen = False
        try:
            yield {"event": "meta", "data": {"session_id": str(session_id)}}
            history = await self._prepare(user_id, session_id, question)

            canned = smalltalk_reply(question)
            if canned:
                answer_parts.append(canned)
                yield {"event": "token", "data": {"text": canned}}
                yield {"event": "citations", "data": []}
                return

            query = question
            if history:
                try:
                    query, ci, co = await self._condense(history, question)
                    tin, tout = tin + ci, tout + co
                except Exception:
                    log.warning("condense failed, using raw question", exc_info=True)

            try:
                hits = await self.retriever.retrieve(query, grade, subject, book_id)
            except Exception as e:
                log.exception("retrieval failed")
                raise AppError("Search is temporarily unavailable, please try again.", code="search_unavailable",
                               status_code=503) from e

            if not hits:
                msg = NOT_FOUND_MESSAGES[detect_language(question)]
                answer_parts.append(msg)
                yield {"event": "token", "data": {"text": msg}}
                yield {"event": "citations", "data": []}
                return

            context, used = format_context(hits, settings.max_context_chars)
            system = SYSTEM_TEMPLATE.format(grade_label=grade_label(grade))
            messages = normalize_history(history + [{"role": "user", "content": f"{context}\n\nStudent question: {question}"}])
            prompt_chars = len(system) + sum(len(m["content"]) for m in messages)

            try:
                async for chunk in self.llm.stream(system=system, messages=messages,
                                                   max_tokens=settings.answer_max_tokens):
                    if chunk.text:
                        answer_parts.append(chunk.text)
                        yield {"event": "token", "data": {"text": chunk.text}}
                    if chunk.tokens_in is not None:
                        tin += chunk.tokens_in
                        tout += chunk.tokens_out or 0
                        usage_seen = True
            except Exception as e:
                log.exception("llm stream failed")
                raise AppError("The tutor is temporarily unavailable, please try again.", code="llm_unavailable",
                               status_code=502) from e

            answer = "".join(answer_parts)
            nums = used_citation_numbers(answer, len(used)) or list(range(1, len(used) + 1))
            citations = [{
                "n": n, "book_id": used[n - 1].book_id, "book_title": used[n - 1].book_title,
                "subject": used[n - 1].subject, "section": used[n - 1].heading,
                "pages": [used[n - 1].page_start, used[n - 1].page_end], "snippet": used[n - 1].text[:240],
            } for n in nums]
            yield {"event": "citations", "data": citations}
        except AppError as e:
            yield {"event": "error", "data": {"code": e.code, "message": e.message}}
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("ask failed")
            yield {"event": "error", "data": {"code": "internal", "message": "Something went wrong."}}
        finally:
            if not usage_seen and answer_parts and prompt_chars:  # client disconnected mid-stream: estimate
                tin += prompt_chars // 3
                tout += len("".join(answer_parts)) // 3
            # shielded: must still persist the (partial) answer and release the lock on client disconnect
            await asyncio.shield(self._finalize(user_id, session_id, "".join(answer_parts), citations, tin, tout))
