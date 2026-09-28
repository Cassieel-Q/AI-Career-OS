from __future__ import annotations

import os
from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engines: dict[str, object] = {}


def get_db() -> Generator[Session, None, None]:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise HTTPException(status_code=503, detail="Profile persistence is not configured")
    engine = _engines.get(database_url)
    if engine is None:
        engine = create_engine(database_url, pool_pre_ping=True)
        _engines[database_url] = engine
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
