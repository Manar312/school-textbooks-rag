"""Provider registry + factory: .env decides which implementation serves each role.

Add a new vendor/model in 2 steps:
  1. implement the matching interface from app/providers/base.py (e.g. class MyLLM(LLMProvider))
  2. register it:  register("llm", "mine", "my_package.my_module:MyLLM")   and set LLM_PROVIDER=mine

Providers are built lazily (cached_property), so each process only creates what it actually uses
(the worker never builds the answer LLM; the API never builds the VLM).
"""
import importlib
from functools import cached_property

from app.core.config import Settings
from app.core.errors import ConfigError
from app.providers.base import (EmbeddingProvider, LLMProvider, OCRProvider, RerankerProvider, VectorStoreProvider,
                                VLMProvider)

_P = "app.providers."
_REGISTRY: dict[str, dict[str, str]] = {
    "llm": {"anthropic": _P + "llm.anthropic_llm:AnthropicLLM", "openai": _P + "llm.openai_llm:OpenAILLM"},
    "vlm": {"anthropic": _P + "vlm.anthropic_vlm:AnthropicVLM", "openai": _P + "vlm.openai_vlm:OpenAIVLM"},
    "embedding": {"bge_m3": _P + "embeddings.bge_m3:BGEM3Embeddings",
                  "openai": _P + "embeddings.openai_embeddings:OpenAIEmbeddings"},
    "reranker": {"bge": _P + "rerankers.bge_reranker:BGEReranker", "none": _P + "rerankers.noop:NoopReranker"},
    "vectorstore": {"qdrant": _P + "vectorstores.qdrant_store:QdrantStore"},
    "ocr": {"tesseract": _P + "ocr.tesseract:TesseractOCR", "none": _P + "ocr.noop:NoopOCR"},
}


def register(kind: str, name: str, path: str) -> None:
    """Plug in a custom provider class ("module.path:ClassName")."""
    if kind not in _REGISTRY:
        raise ConfigError(f"unknown provider kind '{kind}', expected one of {sorted(_REGISTRY)}")
    _REGISTRY[kind][name] = path


def available(kind: str) -> list[str]:
    return sorted(_REGISTRY[kind])


def _resolve(kind: str, name: str):
    try:
        path = _REGISTRY[kind][name]
    except KeyError:
        raise ConfigError(f"Unknown {kind} provider '{name}'. Available: {', '.join(available(kind))}") from None
    module, cls = path.split(":")
    return getattr(importlib.import_module(module), cls)


class Providers:
    """Container of the configured providers for one process."""

    def __init__(self, s: Settings):
        self.s = s

    def _key(self, provider: str, explicit: str | None) -> str:
        if explicit:
            return explicit
        return {"anthropic": self.s.anthropic_api_key, "openai": self.s.openai_api_key}.get(provider, "")

    @cached_property
    def llm(self) -> LLMProvider:
        s = self.s
        return _resolve("llm", s.llm_provider)(s.llm_model, self._key(s.llm_provider, s.llm_api_key), s.llm_base_url)

    @cached_property
    def condense_llm(self) -> LLMProvider:
        s = self.s
        if not s.condense_provider:
            return self.llm
        return _resolve("llm", s.condense_provider)(
            s.condense_model, self._key(s.condense_provider, s.condense_api_key), s.condense_base_url)

    @cached_property
    def vlm(self) -> VLMProvider:
        s = self.s
        return _resolve("vlm", s.vlm_provider)(s.vlm_model, self._key(s.vlm_provider, s.vlm_api_key), s.vlm_base_url)

    @cached_property
    def embedder(self) -> EmbeddingProvider:
        s = self.s
        return _resolve("embedding", s.embed_provider)(
            s.embed_model, s.embed_dim, self._key(s.embed_provider, s.embed_api_key), s.embed_base_url)

    @cached_property
    def reranker(self) -> RerankerProvider:
        return _resolve("reranker", self.s.rerank_provider)(self.s.rerank_model)

    @cached_property
    def vectors(self) -> VectorStoreProvider:
        s = self.s
        return _resolve("vectorstore", s.vectorstore_provider)(s.qdrant_url, s.collection_prefix, self.embedder)

    @cached_property
    def ocr(self) -> OCRProvider:
        return _resolve("ocr", self.s.ocr_provider)(self.s.ocr_languages)

    def validate(self, roles: tuple[str, ...]) -> None:
        """Instantiate the given roles now so a bad .env fails at startup, not on the first student's question."""
        for r in roles:
            getattr(self, r)

    def describe(self) -> dict:
        s = self.s
        return {"llm": f"{s.llm_provider}:{s.llm_model}",
                "condense": f"{s.condense_provider}:{s.condense_model}" if s.condense_provider else "same as llm",
                "vlm": f"{s.vlm_provider}:{s.vlm_model}", "embeddings": f"{s.embed_provider}:{s.embed_model}",
                "reranker": f"{s.rerank_provider}:{s.rerank_model}", "vectorstore": s.vectorstore_provider,
                "ocr": s.ocr_provider}

    async def aclose(self) -> None:
        for attr in ("llm", "condense_llm", "vlm", "embedder", "vectors"):
            obj = self.__dict__.get(attr)
            if obj is not None:
                try:
                    await obj.aclose()
                except Exception:
                    pass
