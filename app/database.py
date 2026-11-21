"""Подключение к БД и сессии SQLAlchemy."""
import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

url = settings.sqlalchemy_url

# Для SQLite создаём каталог под файл БД и разрешаем доступ из разных потоков.
connect_args = {}
if url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    db_file = url.replace("sqlite:///", "")
    parent = os.path.dirname(db_file)
    if parent:
        os.makedirs(parent, exist_ok=True)

engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_schema():
    """Лёгкая авто-миграция: добавляет недостающие колонки в существующие
    таблицы (чтобы обновление со старой БД не падало). Для серьёзных
    изменений схемы используйте Alembic."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "users" not in tables:
        return
    dialect = engine.dialect.name
    dt = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    bool_false = ("BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql"
                  else "BOOLEAN NOT NULL DEFAULT 0")
    cols_by_table = {t: {c["name"] for c in insp.get_columns(t)} for t in tables}

    # (таблица, колонка, DDL-тип) — добавляются, если отсутствуют
    adds = [
        ("users", "email", "VARCHAR(255)"),
        ("users", "telegram_chat_id", "VARCHAR(32)"),
        ("users", "telegram_link_code", "VARCHAR(16)"),
        ("notes", "remind_at", dt),
        ("notes", "remind_channels", "VARCHAR(64)"),
        ("notes", "remind_sent", bool_false),
        ("notes", "repeat", "VARCHAR(12) NOT NULL DEFAULT 'none'"),
        ("notes", "repeat_until", "DATE"),
        ("notes", "is_quick", bool_false),
    ]
    with engine.begin() as conn:
        if "role" not in cols_by_table.get("users", set()):
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(16) "
                "NOT NULL DEFAULT 'user'"))
            # Существующего первого пользователя делаем администратором.
            conn.execute(text(
                "UPDATE users SET role='admin' WHERE id = "
                "(SELECT id FROM users ORDER BY id LIMIT 1)"))
        for table, col, ddl in adds:
            if table in tables and col not in cols_by_table.get(table, set()):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def init_db():
    from . import models  # noqa: F401  (регистрация моделей)
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
