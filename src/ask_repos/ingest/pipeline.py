"""The index run: GitHub tree -> selected files -> chunks -> embeddings -> PostgreSQL.

Incremental by construction. A repository whose tree SHA has not moved is skipped
entirely; inside a changed repository, a file whose blob SHA has not moved keeps its
chunks and its vectors. Re-running an index over an unchanged account therefore costs
a handful of conditional GitHub requests and writes zero chunks.

Two things here are deliberate rather than obvious. Files are fetched and written in
batches, each batch committed and then expunged: an ORM session holding thousands of
pending `Chunk` objects makes every `flush()` walk all of them, and one 251-file
repository took twenty minutes and 2.5 GB resident before that was fixed. Chunks are
inserted through a Core `insert()` of plain dictionaries for the same reason.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ask_repos.config import get_settings
from ask_repos.db.models import Chunk, File, IndexRun, Repo
from ask_repos.githubapi.client import EmptyRepository, GitHubClient, RepoMeta
from ask_repos.ingest.chunkers import ChunkDraft, chunk_file
from ask_repos.ingest.filters import classify, looks_binary
from ask_repos.retrieval.embed import Embedder, batched, get_embedder

Progress = Callable[[str], None]

FETCH_BATCH = 32


class PrivateRepoRefused(RuntimeError):
    """Raised when something hands the pipeline a repository that is not public."""


@dataclass
class IndexStats:
    repos_seen: int = 0
    repos_indexed: int = 0
    repos_unchanged: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    files_removed: int = 0
    chunks_written: int = 0
    bytes_ingested: int = 0
    github_requests: int = 0
    conditional_hits: int = 0
    seconds: float = 0.0
    repos: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"repos {self.repos_indexed} indexed / {self.repos_unchanged} unchanged of "
            f"{self.repos_seen} · files {self.files_indexed} written / "
            f"{self.files_unchanged} unchanged / {self.files_removed} removed · "
            f"chunks {self.chunks_written} · bytes {self.bytes_ingested} · "
            f"github requests {self.github_requests} · {self.seconds:.1f}s"
        )


def _upsert_repo(session: Session, meta: RepoMeta) -> Repo:
    repo = session.scalar(select(Repo).where(Repo.full_name == meta.full_name))
    if repo is None:
        repo = Repo(owner=meta.owner, name=meta.name, full_name=meta.full_name)
        session.add(repo)
    repo.description = meta.description
    repo.default_branch = meta.default_branch
    repo.html_url = meta.html_url
    repo.language = meta.language
    repo.stars = meta.stars
    repo.pushed_at = meta.pushed_at
    session.flush()
    return repo


def _store_chunks(
    session: Session,
    repo_id: int,
    file_id: int,
    path: str,
    sha: str,
    drafts: list[ChunkDraft],
    embedder: Embedder,
) -> int:
    if not drafts:
        return 0
    texts = [
        f"{path}{f' — {draft.symbol}' if draft.symbol else ''}\n{draft.text}" for draft in drafts
    ]
    vectors: list[list[float]] = []
    for batch in batched(texts, 64):
        vectors.extend(embedder.embed(batch))
    session.execute(
        insert(Chunk),
        [
            {
                "file_id": file_id,
                "repo_id": repo_id,
                "ordinal": ordinal,
                "kind": draft.kind,
                "symbol": draft.symbol,
                "line_start": draft.line_start,
                "line_end": draft.line_end,
                "sha": sha,
                "text": draft.text,
                "embedding": vector,
            }
            for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
        ],
    )
    return len(drafts)


def index_repo(
    session: Session,
    client: GitHubClient,
    meta: RepoMeta,
    embedder: Embedder,
    stats: IndexStats,
    force: bool = False,
    progress: Progress | None = None,
) -> bool:
    """Index one repository. Returns True when anything was written."""
    if meta.private or meta.visibility != "public":
        raise PrivateRepoRefused(
            f"{meta.full_name} is {meta.visibility}; ask-repos indexes public only"
        )
    # Read the tree first: a repository that cannot be read leaves no row behind.
    tree_sha, entries, truncated = client.get_tree(meta.owner, meta.name, meta.default_branch)
    repo = _upsert_repo(session, meta)
    repo_id = repo.id
    unchanged = repo.tree_sha == tree_sha
    if truncated and progress:
        progress(f"  ! {meta.full_name}: GitHub truncated the tree; indexing the visible part")

    if unchanged and not force:
        stats.repos_unchanged += 1
        session.commit()
        if progress:
            progress(f"  = {meta.full_name} unchanged ({tree_sha[:7]})")
        return False

    settings = get_settings()
    known: dict[str, tuple[int, str]] = {
        path: (file_id, sha)
        for file_id, path, sha in session.execute(
            select(File.id, File.path, File.sha).where(File.repo_id == repo_id)
        ).all()
    }
    wanted: dict[str, tuple[str, int]] = {}
    for entry in entries:
        selection = classify(entry.path)
        if selection is None or entry.size > settings.max_file_bytes:
            continue
        wanted[entry.path] = (entry.sha, entry.size)

    gone = [known[path][0] for path in set(known) - set(wanted)]
    if gone:
        session.execute(delete(File).where(File.id.in_(gone)))
        stats.files_removed += len(gone)

    to_fetch = [
        (path, blob_sha)
        for path, (blob_sha, _) in sorted(wanted.items())
        if force or path not in known or known[path][1] != blob_sha
    ]
    stats.files_unchanged += len(wanted) - len(to_fetch)

    written_files = 0
    written_chunks = 0
    total_batches = (len(to_fetch) + FETCH_BATCH - 1) // FETCH_BATCH
    for number, start in enumerate(range(0, len(to_fetch), FETCH_BATCH), start=1):
        batch = to_fetch[start : start + FETCH_BATCH]
        blobs = client.get_blobs_text(meta.owner, meta.name, [sha for _, sha in batch])
        for path, blob_sha in batch:
            text = blobs.get(blob_sha)
            if text is None or looks_binary(text.encode("utf-8", "ignore")):
                continue
            selection = classify(path)
            if selection is None:
                continue
            drafts = chunk_file(text, selection.language, selection.kind)
            if not drafts:
                continue
            size = wanted[path][1] or len(text.encode("utf-8"))
            values = {
                "repo_id": repo_id,
                "path": path,
                "sha": blob_sha,
                "size_bytes": size,
                "language": selection.language,
                "line_count": len(text.splitlines()),
                "content": text,
                "indexed_at": datetime.now(UTC),
            }
            file_id = known.get(path, (None, None))[0]
            if file_id is None:
                file_id = session.execute(
                    insert(File).values(**values).returning(File.id)
                ).scalar_one()
            else:
                session.execute(delete(Chunk).where(Chunk.file_id == file_id))
                session.execute(File.__table__.update().where(File.id == file_id).values(**values))
            known[path] = (file_id, blob_sha)
            written_chunks += _store_chunks(
                session, repo_id, file_id, path, blob_sha, drafts, embedder
            )
            written_files += 1
            stats.files_indexed += 1
            stats.bytes_ingested += size
        blobs.clear()
        # Commit each batch so the session never carries thousands of pending rows.
        session.commit()
        session.expunge_all()
        if progress and total_batches > 1:
            progress(
                f"    {meta.full_name}: batch {number}/{total_batches} — "
                f"{written_files} files, {written_chunks} chunks so far"
            )

    stats.chunks_written += written_chunks
    session.execute(
        Repo.__table__.update()
        .where(Repo.id == repo_id)
        .values(tree_sha=tree_sha, last_indexed_at=datetime.now(UTC))
    )
    session.commit()
    if progress:
        progress(
            f"  + {meta.full_name}: {written_files} files, {written_chunks} chunks ({tree_sha[:7]})"
        )
    return True


def index_owner(
    session: Session,
    owner: str,
    client: GitHubClient | None = None,
    embedder: Embedder | None = None,
    only_repo: str | None = None,
    force: bool = False,
    trigger: str = "cli",
    progress: Progress | None = None,
) -> IndexStats:
    """Index every public repository of `owner` (or just `only_repo`)."""
    started = time.perf_counter()
    stats = IndexStats()
    owned_client = client is None
    client = client or GitHubClient()
    embedder = embedder or get_embedder()
    run = IndexRun(owner=owner, trigger=trigger, status="running")
    session.add(run)
    session.commit()
    run_id = run.id
    status = "running"
    error: str | None = None
    try:
        metas = (
            [client.get_repo(owner, only_repo)]
            if only_repo
            else client.list_public_repos(owner)
        )
        stats.repos_seen = len(metas)
        for meta in metas:
            if meta.private or meta.visibility != "public":
                continue
            try:
                written = index_repo(
                    session, client, meta, embedder, stats, force=force, progress=progress
                )
            except EmptyRepository:
                session.rollback()
                stats.skipped.append({"repo": meta.full_name, "reason": "empty repository"})
                if progress:
                    progress(f"  · {meta.full_name} skipped (no commits yet)")
                continue
            if written:
                stats.repos_indexed += 1
                stats.repos.append(meta.full_name)
            session.expunge_all()
        status = "ok"
    except Exception as exc:  # the run row is the audit trail; re-raise after recording
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        session.rollback()
        raise
    finally:
        stats.seconds = time.perf_counter() - started
        stats.github_requests = client.requests_made
        stats.conditional_hits = client.conditional_hits
        # `expunge_all` detached the original object; the run row is re-read by id.
        run = session.get(IndexRun, run_id) or run
        run.status = status
        run.error = error
        run.finished_at = datetime.now(UTC)
        run.repos_seen = stats.repos_seen
        run.repos_indexed = stats.repos_indexed
        run.files_indexed = stats.files_indexed
        run.chunks_written = stats.chunks_written
        run.bytes_ingested = stats.bytes_ingested
        run.detail = stats.as_dict()
        session.commit()
        if owned_client:
            client.close()
    return stats
