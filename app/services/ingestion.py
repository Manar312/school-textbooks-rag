"""Resumable book ingestion: per-page extraction (persisted) -> chunking -> embeddings -> vector store.

Safe to re-run: finished pages are skipped, chunk keys are stable, and a re-index writes the new points
before deleting the previous run's points. Depends on provider interfaces + repositories only.
"""
import asyncio
import logging
import uuid

from app.core.config import settings
from app.providers import Providers, VectorPoint
from app.repositories import BookRepository
from app.services.chunking import build_chunks, embedding_text
from app.services.extraction import PageExtractor, PageResult, page_count

log = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, repo: BookRepository, repo_factory, providers: Providers):
        """repo: used for sequential steps. repo_factory: opens a fresh repo/session per concurrent page task."""
        self.repo = repo
        self.repo_factory = repo_factory
        self.p = providers

    async def run(self, book_id: uuid.UUID, *, reindex_only: bool = False) -> None:
        book = await self.repo.get(book_id)
        if book is None:
            log.error("book %s not found", book_id)
            return
        path, title, subject, grade, language = book.file_path, book.title, book.subject, book.grade, book.language
        try:
            await self.repo.update(book_id, status="processing", error=None)
            if not reindex_only:
                await self._extract_pages(book_id, path)

            pages = await self.repo.done_pages(book_id)
            failed = await self.repo.count_pages(book_id, "failed")
            if not any(t.strip() for _, t in pages):
                await self.repo.update(book_id, status="failed", pages_done=len(pages), pages_failed=failed,
                                       error="No text could be extracted from any page")
                return

            chunks = build_chunks(pages, str(book_id), settings.chunk_target_chars, settings.chunk_max_chars)
            await self.p.vectors.ensure_collection()
            run = uuid.uuid4().hex
            for i in range(0, len(chunks), 32):
                batch = chunks[i:i + 32]
                embs = await self.p.embedder.embed_documents([embedding_text(c, title, subject) for c in batch])
                await self.p.vectors.upsert([VectorPoint(c.point_id, e, {
                    "chunk_key": c.key, "text": c.text, "book_id": str(book_id), "book_title": title,
                    "subject": subject, "grade": grade, "language": language, "heading": " > ".join(c.heading_path),
                    "page_start": c.page_start, "page_end": c.page_end, "chunk_index": c.index, "index_run": run,
                }) for c, e in zip(batch, embs)])
            await self.p.vectors.delete_stale(str(book_id), run)

            await self.repo.update(book_id, status="partial" if failed else "ready", pages_done=len(pages),
                                   pages_failed=failed, chunk_count=len(chunks),
                                   error=f"{failed} page(s) failed extraction; use /retry" if failed else None)
            log.info("book %s indexed: %s pages, %s chunks, %s failed", book_id, len(pages), len(chunks), failed)
        except Exception as e:
            log.exception("ingestion failed for %s", book_id)
            await self.repo.update(book_id, status="failed", error=f"{type(e).__name__}: {e}"[:2000])
            raise

    async def _extract_pages(self, book_id: uuid.UUID, path: str) -> None:
        n = await asyncio.to_thread(page_count, path)
        await self.repo.ensure_pages(book_id, n)
        await self.repo.update(book_id, page_count=n)
        todo = await self.repo.pages_to_extract(book_id)  # pending + failed + crash leftovers

        extractor = PageExtractor(self.p.vlm, self.p.ocr)
        sem = asyncio.Semaphore(settings.vlm_concurrency)
        finished = 0

        async def work(pn: int):
            nonlocal finished
            async with sem:
                try:
                    res = await extractor.extract(path, pn - 1)
                except Exception as e:  # corrupt page, render failure...
                    res = PageResult(pn, "", "failed", f"{type(e).__name__}: {e}")
            ok = res.method != "failed"
            async with self.repo_factory() as r:
                await r.save_page(book_id, pn, ok=ok, method=res.method, text=res.text, error=res.error)
                finished += 1
                if finished % 10 == 0:
                    await r.update(book_id, pages_done=await r.count_pages(book_id, "done"))

        await asyncio.gather(*(work(pn) for pn in todo))
