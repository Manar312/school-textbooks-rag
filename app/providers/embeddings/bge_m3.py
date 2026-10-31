import asyncio
import re
import threading

from app.core.config import settings
from app.providers.base import Embedding, EmbeddingProvider

# One model object per process (loading BGE-M3 is slow and ~2GB). Provider instances stay cheap, so they can be
# created per Celery task / event loop while sharing the weights.
_models: dict[str, object] = {}
_load_lock = threading.Lock()
_infer_lock = threading.Lock()  # one forward pass at a time; the model is shared across request threads


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _fp16() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def _get_model(name: str):
    with _load_lock:
        if name not in _models:
            from FlagEmbedding import BGEM3FlagModel
            _models[name] = BGEM3FlagModel(name, use_fp16=_fp16())
        return _models[name]


class BGEM3Embeddings(EmbeddingProvider):
    """Local BGE-M3: multilingual (ar/en/fr and 100+), dense + sparse in one pass => hybrid retrieval."""
    name = "bge_m3"
    supports_sparse = True

    def __init__(self, model: str, dim: int = 1024, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.model_id = slug(model)
        self.dim = dim

    def _encode(self, texts: list[str], batch_size: int = 16) -> list[Embedding]:
        model = _get_model(self.model)
        with _infer_lock:
            out = model.encode(texts, batch_size=batch_size, max_length=1024,
                               return_dense=True, return_sparse=True, return_colbert_vecs=False)
        res = []
        for dense, lex in zip(out["dense_vecs"], out["lexical_weights"]):
            res.append(Embedding([float(x) for x in dense], [int(k) for k in lex.keys()],
                                 [float(v) for v in lex.values()]))
        return res

    async def embed_documents(self, texts: list[str]) -> list[Embedding]:
        return await asyncio.to_thread(self._encode, texts)

    async def embed_query(self, text: str) -> Embedding:
        return (await asyncio.to_thread(self._encode, [text]))[0]

    async def warmup(self) -> None:
        await asyncio.to_thread(_get_model, self.model)
