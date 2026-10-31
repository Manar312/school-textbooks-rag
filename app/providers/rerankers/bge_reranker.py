import asyncio
import threading

from app.providers.base import RerankerProvider

_models: dict[str, object] = {}
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


def _fp16() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def _get_model(name: str):
    with _load_lock:
        if name not in _models:
            from FlagEmbedding import FlagReranker
            _models[name] = FlagReranker(name, use_fp16=_fp16())
        return _models[name]


class BGEReranker(RerankerProvider):
    """Local cross-encoder (bge-reranker-v2-m3): multilingual, scores in [0, 1]."""
    name = "bge"

    def __init__(self, model: str):
        self.model = model

    def _score(self, query: str, passages: list[str]) -> list[float]:
        model = _get_model(self.model)
        with _infer_lock:
            scores = model.compute_score([[query, p] for p in passages], normalize=True)
        if isinstance(scores, (int, float)):
            scores = [scores]
        return [float(s) for s in scores]

    async def rerank(self, query: str, passages: list[str]) -> list[float] | None:
        if not passages:
            return []
        return await asyncio.to_thread(self._score, query, passages)

    async def warmup(self) -> None:
        await asyncio.to_thread(_get_model, self.model)
