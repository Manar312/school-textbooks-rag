from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm

from app.providers.base import Embedding, EmbeddingProvider, Hit, VectorPoint, VectorStoreProvider


class QdrantStore(VectorStoreProvider):
    """Qdrant. Hybrid (dense + sparse, RRF fusion) when the embedder supports sparse, plain dense search otherwise.
    The collection name embeds the embedding model + dim, so changing EMBED_* never mixes incompatible vectors:
    it creates a fresh collection, which you fill with POST /admin/books/{id}/reindex (no VLM calls)."""
    name = "qdrant"

    def __init__(self, url: str, prefix: str, embedder: EmbeddingProvider):
        self.client = AsyncQdrantClient(url=url, timeout=30)
        self.hybrid = embedder.supports_sparse
        self.dim = embedder.dim
        self.collection = f"{prefix}_{embedder.model_id}_{embedder.dim}"

    async def aclose(self) -> None:
        await self.client.close()

    async def ensure_collection(self) -> None:
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                self.collection,
                vectors_config={"dense": qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE)},
                sparse_vectors_config={"sparse": qm.SparseVectorParams()} if self.hybrid else None)
        for field in ("grade", "subject", "book_id", "language", "index_run"):
            try:
                await self.client.create_payload_index(self.collection, field, qm.PayloadSchemaType.KEYWORD)
            except Exception:  # already exists
                pass

    async def ping(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False

    async def upsert(self, points: list[VectorPoint]) -> None:
        for i in range(0, len(points), 64):
            batch = points[i:i + 64]
            structs = []
            for p in batch:
                vec: dict = {"dense": p.embedding.dense}
                if self.hybrid:
                    vec["sparse"] = qm.SparseVector(indices=p.embedding.sparse_idx, values=p.embedding.sparse_val)
                structs.append(qm.PointStruct(id=p.id, vector=vec, payload=p.payload))
            await self.client.upsert(self.collection, points=structs, wait=True)

    async def delete_book(self, book_id: str) -> None:
        flt = qm.Filter(must=[qm.FieldCondition(key="book_id", match=qm.MatchValue(value=book_id))])
        await self.client.delete(self.collection, points_selector=qm.FilterSelector(filter=flt), wait=True)

    async def delete_stale(self, book_id: str, index_run: str) -> None:
        flt = qm.Filter(must=[qm.FieldCondition(key="book_id", match=qm.MatchValue(value=book_id))],
                        must_not=[qm.FieldCondition(key="index_run", match=qm.MatchValue(value=index_run))])
        await self.client.delete(self.collection, points_selector=qm.FilterSelector(filter=flt), wait=True)

    async def search(self, query: Embedding, *, grade: str, subject: str | None = None,
                     book_id: str | None = None, limit: int = 30) -> list[Hit]:
        must = [qm.FieldCondition(key="grade", match=qm.MatchValue(value=grade))]
        if subject:
            must.append(qm.FieldCondition(key="subject", match=qm.MatchValue(value=subject)))
        if book_id:
            must.append(qm.FieldCondition(key="book_id", match=qm.MatchValue(value=book_id)))
        flt = qm.Filter(must=must)
        if self.hybrid and query.sparse_idx:
            res = await self.client.query_points(
                self.collection,
                prefetch=[
                    qm.Prefetch(query=query.dense, using="dense", limit=limit, filter=flt),
                    qm.Prefetch(query=qm.SparseVector(indices=query.sparse_idx, values=query.sparse_val),
                                using="sparse", limit=limit, filter=flt)],
                query=qm.FusionQuery(fusion=qm.Fusion.RRF), limit=limit, with_payload=True)
        else:
            res = await self.client.query_points(self.collection, query=query.dense, using="dense",
                                                 query_filter=flt, limit=limit, with_payload=True)
        hits = []
        for p in res.points:
            pl = p.payload or {}
            hits.append(Hit(pl.get("chunk_key", ""), pl.get("text", ""), pl.get("book_id", ""),
                            pl.get("book_title", ""), pl.get("subject", ""), pl.get("grade", ""),
                            int(pl.get("page_start", 0)), int(pl.get("page_end", 0)),
                            pl.get("heading", ""), float(p.score)))
        return hits
