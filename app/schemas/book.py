import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.constants import LANGUAGES, is_valid_grade


class BookOut(BaseModel):
    id: uuid.UUID
    title: str
    subject: str
    grade: str
    term: str | None
    language: str
    status: str
    page_count: int
    pages_done: int
    pages_failed: int
    chunk_count: int
    error: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


def validate_book_meta(grade: str, language: str) -> None:
    if not is_valid_grade(grade):
        raise ValueError("invalid grade")
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {LANGUAGES}")
