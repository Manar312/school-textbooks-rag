import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_uuid


class Book(Base):
    __tablename__ = "books"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(100), index=True)
    grade: Mapped[str] = mapped_column(String(20), index=True)
    term: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="ar")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|processing|ready|partial|failed
    file_path: Mapped[str] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BookPage(Base):
    """Per-page extraction result. Persisted so re-chunking / re-embedding (or switching embedding model)
    never repeats VLM calls."""
    __tablename__ = "book_pages"
    __table_args__ = (UniqueConstraint("book_id", "page_number"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|done|failed
    method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # native|vlm|ocr
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
