"""Architecture tests with FAKE providers: proves business logic depends on interfaces, not vendors,
and that swapping a model/vendor is a registration + .env change."""
import uuid
from contextlib import asynccontextmanager

import pytest

from app.core.config import Settings
from app.core.errors import ConfigError
from app.providers import (Embedding, EmbeddingProvider, Hit, LLMProvider, LLMResult, Providers, RerankerProvider,
                           StreamChunk, VectorPoint, VectorStoreProvider, available, register)
from app.services.rag_service import RagService
from app.services.retrieval import Retriever


# ------------------------------------------------------------------ fakes
class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, model="fake-1", api_key="", base_url=None, reply="النبات بيصنع غذاءه [1]."):
        self.model, self.reply, self.calls = model, reply, []

    async def complete(self, *, system, messages, max_tokens=1024):
        self.calls.append(("complete", messages))
        return LLMResult("standalone: " + messages[-1]["content"][-20:], 10, 5)

    async def stream(self, *, system, messages, max_tokens=1800):
        self.calls.append(("stream", messages))
        for word in self.reply.split(" "):
            yield StreamChunk(text=word + " ")
        yield StreamChunk(tokens_in=100, tokens_out=20)


class FakeEmbedder(EmbeddingProvider):
    name, supports_sparse, dim, model_id = "fake", False, 3, "fake-3"

    async def embed_documents(self, texts):
        return [Embedding([1.0, 0.0, 0.0]) for _ in texts]

    async def embed_query(self, text):
        return Embedding([1.0, 0.0, 0.0])


class FakeReranker(RerankerProvider):
    name = "fake"

    def __init__(self, scores=None):
        self.scores = scores

    async def rerank(self, query, passages):
        return self.scores if self.scores is not None else [0.9 - 0.1 * i for i in range(len(passages))]


class FakeVectors(VectorStoreProvider):
    name = "fake"

    def __init__(self, hits=None):
        self.hits, self.last_filter = hits or [], None

    async def ensure_collection(self): ...
    async def ping(self): return True
    async def upsert(self, points: list[VectorPoint]): ...
    async def delete_book(self, book_id): ...
    async def delete_stale(self, book_id, index_run): ...

    async def search(self, query, *, grade, subject=None, book_id=None, limit=30):
        self.last_filter = (grade, subject, book_id)
        return [h for h in self.hits if h.grade == grade]


class FakeChatRepo:
    def __init__(self):
        self.messages, self.titles = [], []

    async def recent_history(self, sid, uid, limit):
        return [{"role": m["role"], "content": m["content"]} for m in self.messages[-limit:]]

    async def add_message(self, **kw):
        self.messages.append(kw)

    async def set_title_if_default(self, sid, uid, title):
        self.titles.append(title)


class FakeQuota:
    def __init__(self):
        self.recorded = []

    async def record(self, uid, tin, tout):
        self.recorded.append((tin, tout))


def hit(grade="prep-1", text="النبات يصنع غذاءه بالبناء الضوئي", page=12):
    return Hit("k1", text, "b1", "العلوم", "science", grade, page, page, "الفصل الأول", 0.5)


def make_rag(llm=None, hits=None, reranker=None):
    repo, quota = FakeChatRepo(), FakeQuota()

    @asynccontextmanager
    async def open_repo():
        yield repo
    llm = llm or FakeLLM()
    retriever = Retriever(FakeEmbedder(), FakeVectors(hits if hits is not None else [hit()]), reranker or FakeReranker())
    return RagService(llm=llm, condense_llm=llm, retriever=retriever, quota=quota, open_chat_repo=open_repo,
                      redis=None), repo, quota, llm


async def collect(rag, question="ايه هو البناء الضوئي؟", grade="prep-1"):
    return [ev async for ev in rag.ask(user_id=uuid.uuid4(), grade=grade, session_id=uuid.uuid4(), question=question)]


# ------------------------------------------------------------------ RAG flow on fake providers
async def test_answer_streams_with_citations_and_is_saved_and_billed():
    rag, repo, quota, _ = make_rag()
    events = await collect(rag)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "meta" and "token" in kinds and kinds[-1] == "citations"
    cites = events[-1]["data"]
    assert cites[0]["n"] == 1 and cites[0]["pages"] == [12, 12] and cites[0]["book_title"] == "العلوم"
    assert [m["role"] for m in repo.messages] == ["user", "assistant"]
    assert "[1]" in repo.messages[1]["content"]
    assert quota.recorded == [(100, 20)]


async def test_no_hits_returns_canned_answer_without_calling_the_llm():
    rag, repo, quota, llm = make_rag(hits=[])
    events = await collect(rag, "what is photosynthesis?")
    assert "couldn't find" in "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert not any(c[0] == "stream" for c in llm.calls)


async def test_student_never_sees_another_grades_books():
    rag, *_ = make_rag(hits=[hit(grade="secondary-3")])
    events = await collect(rag, grade="prep-1")
    assert "couldn't find" in "".join(e["data"]["text"] for e in events if e["event"] == "token") or \
           "مش لاقي" in "".join(e["data"]["text"] for e in events if e["event"] == "token")


async def test_rerank_threshold_drops_irrelevant_hits():
    rag, *_ = make_rag(hits=[hit()], reranker=FakeReranker([0.001]))
    events = await collect(rag)
    assert events[-1]["data"] == [] and not any(e["event"] == "error" for e in events)


async def test_llm_failure_becomes_error_event_and_lock_path_still_finalizes():
    class Boom(FakeLLM):
        async def stream(self, **kw):
            raise RuntimeError("provider down")
            yield
    rag, repo, quota, _ = make_rag(llm=Boom())
    events = await collect(rag)
    assert events[-1]["event"] == "error" and events[-1]["data"]["code"] == "llm_unavailable"
    assert [m["role"] for m in repo.messages] == ["user"]  # question kept, no empty assistant message


async def test_followup_is_condensed_using_history():
    rag, repo, quota, llm = make_rag()
    repo.messages += [{"role": "user", "content": "ايه هو البناء الضوئي؟"}, {"role": "assistant", "content": "عملية..."}]
    await collect(rag, "وإيه أهميته؟")
    assert llm.calls[0][0] == "complete"  # condense ran before retrieval


async def test_smalltalk_skips_retrieval_and_llm():
    rag, repo, quota, llm = make_rag()
    events = await collect(rag, "شكرا")
    assert llm.calls == [] and events[-1]["data"] == []


# ------------------------------------------------------------------ provider registry / factory
def test_every_role_has_builtin_providers():
    assert {"anthropic", "openai"} <= set(available("llm"))
    assert {"anthropic", "openai"} <= set(available("vlm"))
    assert {"bge_m3", "openai"} <= set(available("embedding"))
    assert {"bge", "none"} <= set(available("reranker"))
    assert "qdrant" in available("vectorstore")


def test_unknown_provider_fails_fast_with_helpful_message():
    p = Providers(Settings(llm_provider="nope", jwt_secret="x"))
    with pytest.raises(ConfigError, match="Available: .*anthropic"):
        p.llm


def test_missing_api_key_fails_at_validation_not_at_first_question():
    p = Providers(Settings(llm_provider="anthropic", anthropic_api_key="", jwt_secret="x"))
    with pytest.raises(ConfigError):
        p.validate(("llm",))


def test_custom_provider_can_be_registered_and_selected_from_env():
    register("llm", "fake", "tests.test_architecture:FakeLLM")
    p = Providers(Settings(llm_provider="fake", llm_model="my-model", jwt_secret="x"))
    assert isinstance(p.llm, FakeLLM) and p.llm.model == "my-model"
    assert p.condense_llm is p.llm                      # no CONDENSE_PROVIDER => reuse the answer LLM
    assert p.describe()["llm"] == "fake:my-model"


def test_each_role_can_use_a_different_vendor():
    register("llm", "fake", "tests.test_architecture:FakeLLM")
    s = Settings(llm_provider="fake", llm_model="big", condense_provider="fake", condense_model="small",
                 jwt_secret="x")
    p = Providers(s)
    assert p.llm.model == "big" and p.condense_llm.model == "small" and p.llm is not p.condense_llm


def test_reranker_can_be_disabled_with_none():
    p = Providers(Settings(rerank_provider="none", jwt_secret="x"))
    assert p.reranker.name == "none"


async def test_noop_reranker_keeps_vector_order():
    p = Providers(Settings(rerank_provider="none", jwt_secret="x"))
    assert await p.reranker.rerank("q", ["a", "b"]) is None
    hits = [hit(text="a"), hit(text="b")]
    r = Retriever(FakeEmbedder(), FakeVectors(hits), p.reranker)
    assert [h.text for h in await r.retrieve("q", "prep-1")] == ["a", "b"]
