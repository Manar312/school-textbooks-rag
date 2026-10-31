import uuid

from app.schemas import BookOut
from app.services.book_service import BookService


class BookController:
    def __init__(self, books: BookService):
        self.books = books

    async def upload(self, file, title: str, subject: str, grade: str, language: str, term: str | None) -> BookOut:
        book = await self.books.upload(file, title=title, subject=subject, grade=grade, language=language, term=term)
        return BookOut.model_validate(book)

    async def list_books(self, grade: str | None, subject: str | None) -> list[BookOut]:
        return [BookOut.model_validate(b) for b in await self.books.books.list_books(grade, subject)]

    async def details(self, book_id: uuid.UUID) -> dict:
        book, failed, methods = await self.books.details(book_id)
        return {**BookOut.model_validate(book).model_dump(mode="json"), "extraction_methods": methods,
                "failed_pages": [{"page": p, "error": e} for p, e in failed]}

    async def retry(self, book_id: uuid.UUID) -> dict:
        await self.books.retry(book_id)
        return {"status": "queued"}

    async def reindex(self, book_id: uuid.UUID) -> dict:
        await self.books.reindex(book_id)
        return {"status": "queued"}

    async def delete(self, book_id: uuid.UUID) -> None:
        await self.books.delete(book_id)
