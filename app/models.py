"""Модели данных."""
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    role = Column(String(16), default="user", nullable=False)  # admin | user
    is_active = Column(Boolean, default=True, nullable=False)
    # каналы оповещений пользователя
    email = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(32), nullable=True)
    telegram_link_code = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    counterparties = relationship("Counterparty", back_populates="owner",
                                  cascade="all, delete-orphan")


class Counterparty(Base):
    """Контрагент/клиент, по которому бухгалтер ведёт учёт сроков."""
    __tablename__ = "counterparties"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    name = Column(String(255), nullable=False)
    inn = Column(String(12), nullable=True)
    kpp = Column(String(9), nullable=True)
    form = Column(String(16), default="ooo", nullable=False)          # ooo | ip
    tax_system = Column(String(16), default="osno", nullable=False)   # osno | usn
    has_employees = Column(Boolean, default=True, nullable=False)
    note = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    owner = relationship("User", back_populates="counterparties")
    completions = relationship("Completion", back_populates="counterparty",
                               cascade="all, delete-orphan")
    custom_tasks = relationship("CustomTask", back_populates="counterparty",
                                cascade="all, delete-orphan")


class Completion(Base):
    """Отметка 'выполнено' по конкретному событию календаря для контрагента."""
    __tablename__ = "completions"
    __table_args__ = (UniqueConstraint("counterparty_id", "event_key",
                                       name="uq_completion"),)

    id = Column(Integer, primary_key=True)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    event_key = Column(String(64), nullable=False)
    done_at = Column(DateTime, default=utcnow, nullable=False)

    counterparty = relationship("Counterparty", back_populates="completions")


class CustomTask(Base):
    """Произвольная задача бухгалтера (не из налогового календаря)."""
    __tablename__ = "custom_tasks"

    id = Column(Integer, primary_key=True)
    counterparty_id = Column(Integer, ForeignKey("counterparties.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    due_date = Column(Date, nullable=False)
    note = Column(Text, nullable=True)
    done = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    counterparty = relationship("Counterparty", back_populates="custom_tasks")


class Note(Base):
    """Личная заметка пользователя в календаре (как в tweek): дата, заголовок,
    текст, цвет, отметка выполнения."""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    note_date = Column(Date, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    text = Column(Text, nullable=True)
    color = Column(String(16), nullable=True)   # ключ цвета из палитры
    done = Column(Boolean, default=False, nullable=False)
    is_quick = Column(Boolean, default=False, nullable=False)  # быстрая заметка (вне календаря)
    # напоминание
    remind_at = Column(DateTime, nullable=True)
    remind_channels = Column(String(64), nullable=True)  # "tg,email,push"
    remind_sent = Column(Boolean, default=False, nullable=False)
    # повтор: none | daily | weekly | monthly | yearly
    repeat = Column(String(12), default="none", nullable=False)
    repeat_until = Column(Date, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class NoteDone(Base):
    """Отметка выполнения конкретного вхождения повторяющейся заметки."""
    __tablename__ = "note_done"
    __table_args__ = (UniqueConstraint("note_id", "occ_date", name="uq_note_done"),)

    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    occ_date = Column(Date, nullable=False)


class NotificationSettings(Base):
    """Серверные настройки оповещений (один ряд, id=1). Правит администратор."""
    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, default=587, nullable=False)
    smtp_user = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    smtp_from = Column(String(255), nullable=True)
    smtp_tls = Column(Boolean, default=True, nullable=False)
    telegram_bot_token = Column(String(128), nullable=True)
    # VAPID-ключи для Web Push (генерируются автоматически при первом старте)
    vapid_public = Column(Text, nullable=True)
    vapid_private = Column(Text, nullable=True)
    vapid_subject = Column(String(255), default="mailto:admin@example.com", nullable=False)


class PushSubscription(Base):
    """Подписка браузера на Web Push (на пользователя может быть несколько)."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
