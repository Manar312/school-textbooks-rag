from openai import AsyncOpenAI

from app.core.errors import ConfigError
from app.providers.base import Embedding, EmbeddingProvider
from app.providers.embeddings.bge_m3 import slug


class OpenAIEmbeddings(EmbeddingProvider):
    """Any OpenAI-compatible /embeddings endpoint (OpenAI, vLLM, Ollama, TEI...). Dense only => dense retrieval."""
    name = "openai"
    supports_sparse = False

    def __init__(self, model: str, dim: int, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.model_id = slug(model)
        self.dim = dim
        self.client = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url, max_retries=3, timeout=60)

    async def _embed(self, texts: list[str]) -> list[Embedding]:
        out: list[Embedding] = []
        for i in range(0, len(texts), 64):
            r = await self.client.embeddings.create(model=self.model, input=texts[i:i + 64])
            for d in r.data:
                if len(d.embedding) != self.dim:
                    raise ConfigError(f"EMBED_DIM={self.dim} but model '{self.model}' returned {len(d.embedding)} dims")
                out.append(Embedding(list(d.embedding)))
        return out

    async def embed_documents(self, texts: list[str]) -> list[Embedding]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> Embedding:
        return (await self._embed([text]))[0]

    async def aclose(self) -> None:
        await self.client.close()
