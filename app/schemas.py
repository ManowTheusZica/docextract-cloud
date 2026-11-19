from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class FieldOut(BaseModel):
    key: str
    value: str
    confidence: float

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: int
    filename: str
    status: str
    pages: int
    text_chars: int
    error: str | None = None
    created_at: datetime
    fields: list[FieldOut] = []

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    document_id: int
    status: str
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
