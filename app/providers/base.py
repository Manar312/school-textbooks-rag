"""Provider interfaces.

Every external capability the app depends on (LLM, VLM, embeddings, reranker, vector store, OCR) is an
interface here. Business code (services/) only imports from this module, never from a concrete SDK, so a
model or vendor is swapped by changing .env — or by registering a new class in providers/factory.py.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


# ---------------------------------------------------------------- shared value objects
@dataclass(frozen=True)
class LLMResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class StreamChunk:
    """Either a text delta (text != "") or the final usage report (tokens_* set)."""
    text: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None


@dataclass
class Embedding:
    dense: list[float]
    sparse_idx: list[int] = field(default_factory=list)
    sparse_val: list[float] = field(default_factory=list)


@dataclass
class VectorPoint:
    id: str
    embedding: Embedding
    payload: dict


@dataclass
class Hit:
    chunk_key: str
    text: str
    book_id: str
    book_title: str
    subject: str
    grade: str
    page_start: int
    page_end: int
    heading: str
    score: float


# ---------------------------------------------------------------- interfaces
class LLMProvider(ABC):
    """Text generation. `messages` = [{"role": "user"|"assistant", "content": str}] (alternating, user first)."""
    name: str
    model: str

    @abstractmethod
    async def complete(self, *, system: str, messages: list[dict], max_tokens: int = 1024) -> LLMResult: ...

    @abstractmethod
    def stream(self, *, system: str, messages: list[dict], max_tokens: int = 1800) -> AsyncIterator[StreamChunk]:
        """Async generator: yields text deltas, then one usage chunk."""

    async def aclose(self) -> None:
        return None


class VLMProvider(ABC):
    """Vision-language model: reads one image and returns text."""
    name: str
    model: str

    @abstractmethod
    async def read_image(self, *, image: bytes, mime: str, system: str, instruction: str,
                         max_tokens: int) -> LLMResult: ...

    async def aclose(self) -> None:
        return None


class EmbeddingProvider(ABC):
    name: str
    model_id: str          # short slug; part of the vector collection name so models never share a collection
    dim: int
    supports_sparse: bool  # True => hybrid (dense + sparse) retrieval is used

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[Embedding]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> Embedding: ...

    async def warmup(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


class RerankerProvider(ABC):
    name: str

    @abstractmethod
    async def rerank(self, query: str, passages: list[str]) -> list[float] | None:
        """Relevance scores in [0, 1], one per passage; None if this provider does not score (no-op)."""

    async def warmup(self) -> None:
        return None


class VectorStoreProvider(ABC):
    name: str

    @abstractmethod
    async def ensure_collection(self) -> None: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def upsert(self, points: list[VectorPoint]) -> None: ...

    @abstractmethod
    async def delete_book(self, book_id: str) -> None: ...

    @abstractmethod
    async def delete_stale(self, book_id: str, index_run: str) -> None:
        """Drop the book's points whose payload index_run != index_run (zero-downtime re-index)."""

    @abstractmethod
    async def search(self, query: Embedding, *, grade: str, subject: str | None = None,
                     book_id: str | None = None, limit: int = 30) -> list[Hit]:
        """Must ALWAYS filter by `grade`: this is what keeps a student inside their own curriculum."""

    async def aclose(self) -> None:
        return None


class OCRProvider(ABC):
    name: str

    @abstractmethod
    async def read(self, image_png: bytes) -> str: ...
