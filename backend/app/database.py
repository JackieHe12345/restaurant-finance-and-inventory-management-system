from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL
from .money import storage_json_dumps, storage_json_loads


engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       json_serializer=storage_json_dumps, json_deserializer=storage_json_loads)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
