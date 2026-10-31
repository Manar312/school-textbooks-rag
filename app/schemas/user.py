import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import is_valid_grade


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    grade: str | None
    is_active: bool
    daily_request_limit: int
    daily_token_limit: int
    model_config = {"from_attributes": True}


class StudentCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    grade: str
    daily_request_limit: int | None = Field(default=None, ge=0)
    daily_token_limit: int | None = Field(default=None, ge=0)

    @field_validator("grade")
    @classmethod
    def _grade(cls, v: str) -> str:
        if not is_valid_grade(v):
            raise ValueError("grade must look like primary-4, prep-2 or secondary-3")
        return v


class StudentPatch(BaseModel):
    grade: str | None = None
    is_active: bool | None = None
    daily_request_limit: int | None = Field(default=None, ge=0)
    daily_token_limit: int | None = Field(default=None, ge=0)

    @field_validator("grade")
    @classmethod
    def _grade(cls, v):
        if v is not None and not is_valid_grade(v):
            raise ValueError("invalid grade")
        return v
