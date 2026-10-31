from app.core.config import settings
from app.providers import EmbeddingProvider, Hit, RerankerProvider, VectorStoreProvider


class Retriever:
    """embed query -> (hybrid|dense) search filtered by grade -> optional rerank + relevance threshold."""

    def __init__(self, embedder: EmbeddingProvider, vectors: VectorStoreProvider, reranker: RerankerProvider):
        self.embedder, self.vectors, self.reranker = embedder, vectors, reranker

    async def retrieve(self, query: str, grade: str, subject: str | None = None,
                       book_id: str | None = None) -> list[Hit]:
        emb = await self.embedder.embed_query(query)
        hits = await self.vectors.search(emb, grade=grade, subject=subject, book_id=book_id,
                                         limit=settings.top_k_candidates)
        if not hits:
            return []
        scores = await self.reranker.rerank(query, [h.text for h in hits])
        if scores is not None:
            for h, s in zip(hits, scores):
                h.score = s
            hits.sort(key=lambda h: h.score, reverse=True)
            hits = [h for h in hits if h.score >= settings.rerank_min_score]
        return hits[:settings.top_k_final]
