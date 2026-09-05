"""initial corpus schema: repos, files, chunks, index_runs, webhook_deliveries

Revision ID: 0001
Revises:
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("html_url", sa.String(1024), nullable=False, server_default=""),
        sa.Column("language", sa.String(128)),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pushed_at", sa.DateTime(timezone=True)),
        sa.Column("tree_sha", sa.String(64)),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_repos_owner", "repos", ["owner"])

    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("language", sa.String(64), nullable=False, server_default="text"),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("repo_id", "path", name="uq_files_repo_path"),
    )
    op.create_index("ix_files_repo_id", "files", ["repo_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "repo_id", sa.Integer(), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(32), nullable=False, server_default="text"),
        sa.Column("symbol", sa.String(512)),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBED_DIM)),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
        ),
    )
    op.create_index("ix_chunks_file_id", "chunks", ["file_id"])
    op.create_index("ix_chunks_repo_id", "chunks", ["repo_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "index_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="cli"),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("repos_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repos_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_ingested", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("detail", postgresql.JSONB()),
    )
    op.create_index("ix_index_runs_owner", "index_runs", ["owner"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.String(128), nullable=False, unique=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("repo_full_name", sa.String(512), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_webhook_deliveries_repo", "webhook_deliveries", ["repo_full_name"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("index_runs")
    op.drop_table("chunks")
    op.drop_table("files")
    op.drop_table("repos")
