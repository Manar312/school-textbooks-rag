import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    subject: str | None = Field(default=None, max_length=100)


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    subject: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    citations: list | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=100)
    book_id: uuid.UUID | None = None
    stream: bool = True
