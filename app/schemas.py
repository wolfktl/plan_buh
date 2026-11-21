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
    remind_at: Optional[datetime] = None
    remind_channels: Optional[str] = Field(default=None, max_length=64)


class NoteOut(BaseModel):
    id: int
    note_date: date
    title: str
    text: Optional[str] = None
    color: Optional[str] = None
    done: bool
    remind_at: Optional[datetime] = None
    remind_channels: Optional[str] = None

    class Config:
        from_attributes = True


# ---- оповещения: серверные настройки (admin) ----
class NotificationSettingsIn(BaseModel):
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: int = 587
    smtp_user: Optional[str] = Field(default=None, max_length=255)
    smtp_password: Optional[str] = None   # пусто = не менять
    smtp_from: Optional[str] = Field(default=None, max_length=255)
    smtp_tls: bool = True
    telegram_bot_token: Optional[str] = None  # пусто = не менять
    vapid_subject: Optional[str] = Field(default=None, max_length=255)


class NotificationSettingsOut(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_tls: bool = True
    smtp_password_set: bool = False
    telegram_bot_token_set: bool = False
    vapid_subject: Optional[str] = None


# ---- оповещения: каналы пользователя ----
class ChannelsOut(BaseModel):
    email: Optional[str] = None
    telegram_linked: bool = False
    push_count: int = 0
    telegram_available: bool = False   # задан ли токен бота на сервере
    smtp_available: bool = False       # настроен ли SMTP на сервере


class EmailIn(BaseModel):
    email: Optional[str] = Field(default=None, max_length=255)


class PushSubscriptionIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class EndpointIn(BaseModel):
    endpoint: str
