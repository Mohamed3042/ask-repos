"""Alembic environment. The URL always comes from ask-repos settings, never from alembic.ini."""

from __future__ import annotations

from alembic import context
from sqlalchemy import pool

from ask_repos.config import get_settings
from ask_repos.db.models import Base
from ask_repos.db.session import get_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = get_engine().execution_options(poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
