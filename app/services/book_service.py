import asyncio
import hashlib
import logging
import os
import uuid

import fitz

from app.core.config import settings
from app.core.errors import AppError, Conflict, InvalidUpload, NotFound
from app.models import Book
from app.providers import VectorStoreProvider
from app.repositories import BookRepository
from app.schemas import validate_book_meta
from app.workers.queue import JobQueue

log = logging.getLogger(__name__)


def inspect_pdf(path: str) -> int:
    """Blocking. Returns the page count or raises InvalidUpload."""
    try:
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise InvalidUpload("The PDF is password-protected.")
            if doc.page_count == 0:
                raise InvalidUpload("The PDF has no pages.")
            doc[0].get_text()  # forces a parse of the first page: catches many corrupt files
            return doc.page_count
    except InvalidUpload:
        raise
    except Exception as e:
        raise InvalidUpload(f"Not a readable PDF: {type(e).__name__}") from e


class BookService:
    def __init__(self, books: BookRepository, vectors: VectorStoreProvider, jobs: JobQueue):
        self.books, self.vectors, self.jobs = books, vectors, jobs

    async def upload(self, file, *, title: str, subject: str, grade: str, language: str, term: str | None) -> Book:
        """`file` is anything with `async read(n) -> bytes` (FastAPI UploadFile)."""
        try:
            validate_book_meta(grade, language)
        except ValueError as e:
            raise InvalidUpload(str(e))
        folder = os.path.join(settings.storage_dir, "books")
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, f".upload-{uuid.uuid4().hex}")
        sha, size, limit = hashlib.sha256(), 0, settings.max_upload_mb * 1024 * 1024
        try:
            with open(tmp, "wb") as out:
                first = True
                while chunk := await file.read(1024 * 1024):
                    if first:
                        if not chunk.startswith(b"%PDF-"):
                            raise InvalidUpload("Only PDF files are accepted.")
                        first = False
                    size += len(chunk)
                    if size > limit:
                        raise InvalidUpload(f"File too large (max {settings.max_upload_mb} MB).")
                    sha.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise InvalidUpload("Empty file.")
            digest = sha.hexdigest()
            if await self.books.sha_exists(digest):
                raise Conflict("This exact file was already uploaded.", code="duplicate_file")
            pages = await asyncio.to_thread(inspect_pdf, tmp)
            book_id = uuid.uuid4()
            final = os.path.join(folder, f"{book_id}.pdf")
            os.replace(tmp, final)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        book = await self.books.add(Book(id=book_id, title=title, subject=subject.strip(), grade=grade, term=term,
                                         language=language, file_path=final, file_sha256=digest,
                                         page_count=pages, status="pending"))
        try:
            self.jobs.enqueue_ingest(str(book.id))
        except AppError:
            await self.books.update(book.id, status="failed", error="could not enqueue the job; call POST /admin/books/{id}/retry")
            raise
        return book

    async def get(self, book_id: uuid.UUID) -> Book:
        book = await self.books.get(book_id)
        if not book:
            raise NotFound("Book not found")
        return book

    async def details(self, book_id: uuid.UUID) -> tuple[Book, list, dict]:
        book = await self.get(book_id)
        return book, await self.books.failed_pages(book_id), await self.books.method_breakdown(book_id)

    async def _requeue(self, book_id: uuid.UUID, *, reindex_only: bool) -> None:
        book = await self.get(book_id)
        if book.status in ("processing", "pending"):
            raise Conflict("Book is already being processed.")
        await self.books.update(book_id, status="pending")
        self.jobs.enqueue_ingest(str(book_id), reindex_only=reindex_only)

    async def retry(self, book_id: uuid.UUID) -> None:
        """Re-extract pending/failed pages only, then re-index."""
        await self._requeue(book_id, reindex_only=False)

    async def reindex(self, book_id: uuid.UUID) -> None:
        """Re-chunk + re-embed from stored page text (no VLM calls): after changing chunking or embedding model."""
        await self._requeue(book_id, reindex_only=True)

    async def delete(self, book_id: uuid.UUID) -> None:
        book = await self.get(book_id)
        if book.status == "processing":
            raise Conflict("Book is being processed; try again when it finishes.")
        try:
            await self.vectors.delete_book(str(book_id))  # vectors first: if this fails nothing else is lost
        except Exception as e:
            raise AppError("Vector store unavailable; book not deleted.", code="search_unavailable",
                           status_code=503) from e
        path = book.file_path
        await self.books.delete(book)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
