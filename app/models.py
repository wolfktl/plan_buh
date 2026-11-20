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
