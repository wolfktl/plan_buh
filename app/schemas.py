"""Pydantic-схемы запросов/ответов."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---- auth ----
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class TotpCode(BaseModel):
    code: str = Field(min_length=6, max_length=10)


# ---- админ: пользователи ----
class AdminUserOut(BaseModel):
    id: int
    username: str
    role: str
    totp_enabled: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: Literal["admin", "user"] = "user"


class AdminUserUpdate(BaseModel):
    role: Optional[Literal["admin", "user"]] = None
    is_active: Optional[bool] = None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=6, max_length=128)


# ---- counterparties ----
class CounterpartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    inn: Optional[str] = Field(default=None, max_length=12)
    kpp: Optional[str] = Field(default=None, max_length=9)
    form: str = Field(default="ooo")          # ooo | ip
    tax_system: str = Field(default="osno")   # osno | usn
    has_employees: bool = True
    note: Optional[str] = None


class CounterpartyOut(CounterpartyIn):
    id: int
    is_active: bool = True

    class Config:
        from_attributes = True


# ---- custom tasks ----
class CustomTaskIn(BaseModel):
    counterparty_id: int
    title: str = Field(min_length=1, max_length=255)
    due_date: date
    note: Optional[str] = None


class CustomTaskOut(BaseModel):
    id: int
    counterparty_id: int
    title: str
    due_date: date
    note: Optional[str] = None
    done: bool

    class Config:
        from_attributes = True


# ---- completions ----
class CompletionIn(BaseModel):
    counterparty_id: int
    event_key: str
    done: bool


# ---- заметки ----
class NoteIn(BaseModel):
    note_date: date
    title: str = Field(min_length=1, max_length=255)
    text: Optional[str] = None
    color: Optional[str] = Field(default=None, max_length=16)
    done: bool = False


class NoteOut(BaseModel):
    id: int
    note_date: date
    title: str
    text: Optional[str] = None
    color: Optional[str] = None
    done: bool

    class Config:
        from_attributes = True
