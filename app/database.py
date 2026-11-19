"""Подключение к БД и сессии SQLAlchemy."""
import os
from sqlalchemy import create_engine
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


def init_db():
    from . import models  # noqa: F401  (регистрация моделей)
    Base.metadata.create_all(bind=engine)
