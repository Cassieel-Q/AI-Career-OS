from __future__ import annotations

from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engines: dict[str, object] = {}


def _session_factory():
    from app.local_mode import resolve_database_url

    database_url = resolve_database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="Profile persistence is not configured")
    engine = _engines.get(database_url)
    if engine is None:
        engine = create_engine(database_url, pool_pre_ping=True)
        _engines[database_url] = engine
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def open_session() -> Session:
    """给后台线程/脚本使用的独立 Session（调用方负责关闭）。"""
    return _session_factory()()


def get_db() -> Generator[Session, None, None]:
    # 本地优先模式：启用 AI_CAREER_DATA_DIR 时由数据集指针决定数据库；
    # 否则行为不变，只用 DATABASE_URL。
    from app.local_mode import resolve_database_url

    database_url = resolve_database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="Profile persistence is not configured")
    engine = _engines.get(database_url)
    if engine is None:
        engine = create_engine(database_url, pool_pre_ping=True)
        _engines[database_url] = engine
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
