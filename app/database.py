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
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "role" not in cols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(16) "
                "NOT NULL DEFAULT 'user'"))
            # Существующего первого пользователя делаем администратором,
            # иначе после миграции не останется ни одного админа.
            conn.execute(text(
                "UPDATE users SET role='admin' WHERE id = "
                "(SELECT id FROM users ORDER BY id LIMIT 1)"))


def init_db():
    from . import models  # noqa: F401  (регистрация моделей)
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
