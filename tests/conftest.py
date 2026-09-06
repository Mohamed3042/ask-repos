"""Test fixtures.

The database tests run against a real PostgreSQL with pgvector, because the retrieval
half of this project *is* PostgreSQL: an in-memory substitute would test nothing.
CI provides the service; locally `docker compose up -d db` does. When `REQUIRE_DB=1`
(CI sets it) an unreachable database is a failure, never a skip.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from ask_repos.config import Settings, reset_settings_cache
from ask_repos.db.models import Base

DEFAULT_URL = "postgresql+psycopg://askrepos:askrepos@localhost:5433/askrepos"


def _test_url() -> str:
    if explicit := os.environ.get("TEST_DATABASE_URL"):
        return explicit
    base = make_url(os.environ.get("DATABASE_URL", DEFAULT_URL))
    # `str(URL)` masks the password as ***; that silently broke every database test once.
    return base.set(database=f"{base.database}_test").render_as_string(hide_password=False)


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(
        target.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_url()
    required = os.environ.get("REQUIRE_DB") == "1"
    try:
        _ensure_database(url)
        eng = create_engine(url, future=True)
        with eng.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception as exc:
        if required:
            raise
        pytest.skip(f"no PostgreSQL+pgvector at {make_url(url).render_as_string()}: {exc}")
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE repos, files, chunks, index_runs, webhook_deliveries"
                " RESTART IDENTITY CASCADE"
            )
        )
        conn.commit()
    db = factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never inherit the developer's keys, and never see a stale settings cache."""
    # A developer's local `.env` is real configuration for the app and noise for the tests.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in ("GEMINI_API_KEY", "ASK_REPOS_API_KEY", "ASK_REPOS_WEBHOOK_SECRET", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ASK_REPOS_RERANK", "0")
    monkeypatch.setenv("ASK_REPOS_OTEL_EXPORTER", "none")
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture()
def seeded(session: Session) -> Session:
    """A session holding the fake demo corpus, indexed with the deterministic embedder."""
    from ask_repos.ingest.pipeline import index_owner
    from ask_repos.retrieval.embed import HashEmbedder
    from tests.fakes import demo_corpus

    index_owner(session, "octo", client=demo_corpus(), embedder=HashEmbedder())
    session.commit()
    return session


@pytest.fixture()
def api_client(seeded: Session, monkeypatch: pytest.MonkeyPatch):
    """A TestClient whose `session_scope()` reaches the same test database as `seeded`."""
    from fastapi.testclient import TestClient

    from ask_repos.api.app import create_app
    from ask_repos.db.session import reset_engine_cache

    monkeypatch.setenv("DATABASE_URL", _test_url())
    reset_settings_cache()
    reset_engine_cache()
    with TestClient(create_app()) as client:
        yield client
    reset_engine_cache()
