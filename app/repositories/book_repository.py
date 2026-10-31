import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookPage


class BookRepository:
    def __init__(self, s: AsyncSession):
        self.s = s

    # ---- books
    async def get(self, book_id: uuid.UUID) -> Book | None:
        return await self.s.get(Book, book_id)

    async def sha_exists(self, digest: str) -> bool:
        return (await self.s.execute(select(Book.id).where(Book.file_sha256 == digest))).first() is not None

    async def add(self, book: Book) -> Book:
        self.s.add(book)
        await self.s.commit()
        return book

    async def list_books(self, grade: str | None = None, subject: str | None = None) -> list[Book]:
        q = select(Book).order_by(Book.grade, Book.subject, Book.title)
        if grade:
            q = q.where(Book.grade == grade)
        if subject:
            q = q.where(Book.subject == subject)
        return list((await self.s.execute(q)).scalars().all())

    async def list_available_for_grade(self, grade: str) -> list[Book]:
        q = (select(Book).where(Book.grade == grade, Book.status.in_(["ready", "partial"]))
             .order_by(Book.subject, Book.term, Book.title))
        return list((await self.s.execute(q)).scalars().all())

    async def update(self, book_id: uuid.UUID, **values) -> None:
        await self.s.execute(update(Book).where(Book.id == book_id).values(**values))
        await self.s.commit()

    async def delete(self, book: Book) -> None:
        await self.s.delete(book)
        await self.s.commit()

    # ---- pages
    async def ensure_pages(self, book_id: uuid.UUID, count: int) -> None:
        if count <= 0:
            return
        await self.s.execute(pg_insert(BookPage).values(
            [{"book_id": book_id, "page_number": i + 1, "status": "pending"} for i in range(count)]
        ).on_conflict_do_nothing())
        await self.s.commit()

    async def pages_to_extract(self, book_id: uuid.UUID) -> list[int]:
        """pending + failed + pages left mid-flight by a crashed worker."""
        rows = await self.s.execute(select(BookPage.page_number).where(
            BookPage.book_id == book_id, BookPage.status != "done").order_by(BookPage.page_number))
        return [r for (r,) in rows.all()]

    async def save_page(self, book_id: uuid.UUID, page: int, *, ok: bool, method: str | None,
                        text: str | None, error: str | None) -> None:
        await self.s.execute(update(BookPage).where(BookPage.book_id == book_id, BookPage.page_number == page).values(
            status="done" if ok else "failed", method=method if ok else None, text=text if ok else None, error=error))
        await self.s.commit()

    async def done_pages(self, book_id: uuid.UUID) -> list[tuple[int, str]]:
        rows = await self.s.execute(select(BookPage.page_number, BookPage.text).where(
            BookPage.book_id == book_id, BookPage.status == "done").order_by(BookPage.page_number))
        return [(n, t or "") for n, t in rows.all()]

    async def count_pages(self, book_id: uuid.UUID, status: str) -> int:
        return (await self.s.execute(select(func.count()).select_from(BookPage).where(
            BookPage.book_id == book_id, BookPage.status == status))).scalar_one()

    async def failed_pages(self, book_id: uuid.UUID) -> list[tuple[int, str | None]]:
        rows = await self.s.execute(select(BookPage.page_number, BookPage.error).where(
            BookPage.book_id == book_id, BookPage.status == "failed").order_by(BookPage.page_number))
        return [(n, e) for n, e in rows.all()]

    async def method_breakdown(self, book_id: uuid.UUID) -> dict[str, int]:
        rows = await self.s.execute(select(BookPage.method, func.count()).where(
            BookPage.book_id == book_id, BookPage.status == "done").group_by(BookPage.method))
        return {m: c for m, c in rows.all()}
