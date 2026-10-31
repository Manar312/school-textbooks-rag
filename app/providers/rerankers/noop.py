from app.providers.base import RerankerProvider


class NoopReranker(RerankerProvider):
    """No reranking: keep the vector-store order. Retrieval then skips the relevance threshold."""
    name = "none"

    def __init__(self, model: str | None = None):
        pass

    async def rerank(self, query: str, passages: list[str]) -> list[float] | None:
        return None
