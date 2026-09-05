"""SQLAlchemy models. The store is PostgreSQL 16 + pgvector.

`files.content` keeps the full text of every indexed file at the SHA it was read at.
That is not a convenience: the cite-check guardrail resolves each citation back to
`(repo, path, sha, L<start>-L<end>)` and re-reads those lines, so an answer can only
cite text that is provably still in the corpus.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBED_DIM = 384


class Base(DeclarativeBase):
    pass


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(512), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    html_url: Mapped[str] = mapped_column(String(1024), default="")
    language: Mapped[str | None] = mapped_column(String(128))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tree_sha: Mapped[str | None] = mapped_column(String(64))
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    files: Mapped[list[File]] = relationship(back_populates="repo", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("repo_id", "path", name="uq_files_repo_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(1024))
    sha: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(64), default="text")
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repo: Mapped[Repo] = relationship(back_populates="files")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="file", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(32), default="text")
    symbol: Mapped[str | None] = mapped_column(String(512))
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    sha: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )

    file: Mapped[File] = relationship(back_populates="chunks")


class IndexRun(Base):
    __tablename__ = "index_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="cli")
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repos_seen: Mapped[int] = mapped_column(Integer, default=0)
    repos_indexed: Mapped[int] = mapped_column(Integer, default=0)
    files_indexed: Mapped[int] = mapped_column(Integer, default=0)
    chunks_written: Mapped[int] = mapped_column(Integer, default=0)
    bytes_ingested: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSONB)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(128), unique=True)
    event: Mapped[str] = mapped_column(String(64))
    repo_full_name: Mapped[str] = mapped_column(String(512), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
