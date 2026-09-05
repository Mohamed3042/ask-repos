"""Engine and session factory. One engine per process, created lazily."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ask_repos.config import get_settings


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    dsn = url or get_settings().database_url
    return create_engine(dsn, pool_pre_ping=True, future=True)


@lru_cache(maxsize=4)
def _session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    session = _session_factory(url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(url: str | None = None) -> bool:
    """True when the database answers. Used by /ready and by the test harness."""
    try:
        with get_engine(url).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_engine_cache() -> None:
    get_engine.cache_clear()
    _session_factory.cache_clear()
