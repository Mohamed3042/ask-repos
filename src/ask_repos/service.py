"""Read models shared by the CLI, the HTTP API and the MCP server."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ask_repos import __version__
from ask_repos.config import get_settings
from ask_repos.db.models import Chunk, File, IndexRun, Repo


def corpus_summary(session: Session) -> dict[str, Any]:
    """Everything a reader needs to judge what the answers are drawn from."""
    settings = get_settings()
    file_counts = dict(
        session.execute(select(File.repo_id, func.count(File.id)).group_by(File.repo_id)).all()
    )
    chunk_counts = dict(
        session.execute(select(Chunk.repo_id, func.count(Chunk.id)).group_by(Chunk.repo_id)).all()
    )
    byte_counts = dict(
        session.execute(
            select(File.repo_id, func.coalesce(func.sum(File.size_bytes), 0)).group_by(File.repo_id)
        ).all()
    )
    repos = session.scalars(select(Repo).order_by(Repo.full_name)).all()
    rows = [
        {
            "full_name": repo.full_name,
            "description": repo.description,
            "language": repo.language,
            "stars": repo.stars,
            "html_url": repo.html_url,
            "default_branch": repo.default_branch,
            "tree_sha": repo.tree_sha,
            "files": int(file_counts.get(repo.id, 0)),
            "chunks": int(chunk_counts.get(repo.id, 0)),
            "bytes": int(byte_counts.get(repo.id, 0)),
            "last_indexed_at": repo.last_indexed_at.isoformat() if repo.last_indexed_at else None,
        }
        for repo in repos
    ]
    last_run = session.scalars(select(IndexRun).order_by(IndexRun.id.desc()).limit(1)).first()
    return {
        "version": __version__,
        "repo_count": len(rows),
        "file_count": sum(row["files"] for row in rows),
        "chunk_count": sum(row["chunks"] for row in rows),
        "bytes_indexed": sum(row["bytes"] for row in rows),
        "embed_model": settings.embed_model,
        "embed_dim": settings.embed_dim,
        "rerank_model": settings.rerank_model if settings.rerank_enabled else None,
        "generation": settings.gemini_model if settings.has_gemini else "extractive (keyless)",
        "last_index_run": (
            {
                "id": last_run.id,
                "owner": last_run.owner,
                "trigger": last_run.trigger,
                "status": last_run.status,
                "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
                "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
                "chunks_written": last_run.chunks_written,
                "error": last_run.error,
            }
            if last_run
            else None
        ),
        "repos": rows,
    }


def file_span(
    session: Session, repo: str, path: str, start: int, end: int
) -> dict[str, Any] | None:
    """Return the exact stored lines for a span — how a client verifies a citation."""
    row = session.execute(
        select(File, Repo)
        .join(Repo, Repo.id == File.repo_id)
        .where(Repo.full_name == repo, File.path == path)
    ).first()
    if row is None:
        return None
    file, repo_row = row
    lines = file.content.splitlines()
    start = max(1, start)
    end = min(len(lines), end if end > 0 else len(lines))
    if start > len(lines):
        return None
    return {
        "repo": repo_row.full_name,
        "path": file.path,
        "sha": file.sha,
        "language": file.language,
        "line_start": start,
        "line_end": end,
        "line_count": len(lines),
        "text": "\n".join(lines[start - 1 : end]),
        "url": f"{repo_row.html_url or f'https://github.com/{repo_row.full_name}'}"
        f"/blob/{file.sha}/{file.path}#L{start}-L{end}",
    }


def reindex(target: str | None = None) -> dict[str, Any]:
    """Run an index for one `owner/repo` or for the default owner. Used by the agent tool."""
    from ask_repos.db.session import session_scope
    from ask_repos.ingest.pipeline import index_owner

    settings = get_settings()
    owner = settings.default_owner
    repo_name = None
    if target and "/" in target:
        owner, repo_name = target.split("/", 1)
    elif target:
        repo_name = target
    with session_scope() as session:
        stats = index_owner(session, owner, only_repo=repo_name, trigger="agent")
    return {"summary": stats.summary(), **stats.as_dict()}
