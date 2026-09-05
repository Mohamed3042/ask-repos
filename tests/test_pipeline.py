"""Ingestion against a real PostgreSQL: incremental behaviour and the public-only rule."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ask_repos.db.models import Chunk, File, IndexRun, Repo
from ask_repos.ingest.pipeline import PrivateRepoRefused, index_owner, index_repo
from ask_repos.retrieval.embed import HashEmbedder
from tests.fakes import FakeGitHub, FakeRepo, demo_corpus

pytestmark = pytest.mark.db


def counts(session: Session) -> tuple[int, int, int]:
    return (
        int(session.scalar(select(func.count(Repo.id))) or 0),
        int(session.scalar(select(func.count(File.id))) or 0),
        int(session.scalar(select(func.count(Chunk.id))) or 0),
    )


def test_index_writes_repos_files_and_chunks(session: Session) -> None:
    github = demo_corpus()
    stats = index_owner(session, "octo", client=github, embedder=HashEmbedder())
    repos, files, chunks = counts(session)

    assert repos == 1, "the private repo is not stored and the empty one has nothing to store"
    assert stats.skipped == [{"repo": "octo/fresh", "reason": "empty repository"}]
    assert files == 3, "lockfile and node_modules are filtered out"
    assert chunks > files
    assert stats.chunks_written == chunks
    assert {file.path for file in session.scalars(select(File)).all()} == {
        "README.md",
        "src/app.py",
        "docs/architecture.md",
    }


def test_private_repositories_are_never_indexed(session: Session) -> None:
    github = demo_corpus()
    index_owner(session, "octo", client=github, embedder=HashEmbedder())
    stored = {repo.full_name for repo in session.scalars(select(Repo)).all()}
    assert "octo/secret-thing" not in stored


def test_the_pipeline_refuses_a_private_repo_handed_to_it_directly(session: Session) -> None:
    """The list filter is one guard; this is the second, for a repo fetched by name."""
    secret = FakeRepo("secret", {"README.md": "# x"}, private=True)
    github = FakeGitHub(owner="octo", repos=[secret])
    with pytest.raises(PrivateRepoRefused):
        index_repo(
            session,
            github,  # type: ignore[arg-type]
            github.get_repo("octo", "secret"),
            HashEmbedder(),
            __import__("ask_repos.ingest.pipeline", fromlist=["IndexStats"]).IndexStats(),
        )


def test_reindex_of_an_unchanged_account_writes_nothing(session: Session) -> None:
    github = demo_corpus()
    first = index_owner(session, "octo", client=github, embedder=HashEmbedder())
    before = counts(session)
    reads_before = len(github.blob_reads)

    second = index_owner(session, "octo", client=github, embedder=HashEmbedder())

    assert second.chunks_written == 0, "an unchanged tree must write zero chunks"
    assert second.files_indexed == 0
    assert second.repos_unchanged == 1
    assert counts(session) == before
    assert len(github.blob_reads) == reads_before, "no blob is fetched again"
    assert first.chunks_written > 0


def test_changed_file_is_rechunked_and_unchanged_files_are_left_alone(session: Session) -> None:
    github = demo_corpus()
    index_owner(session, "octo", client=github, embedder=HashEmbedder())
    reads_before = len(github.blob_reads)

    repo = github.repos[0]
    repo.files["README.md"] = repo.files["README.md"] + "\n## New section\n\nAdded later.\n"

    stats = index_owner(session, "octo", client=github, embedder=HashEmbedder())

    assert stats.files_indexed == 1, "only the changed file is re-read"
    assert stats.files_unchanged == 2
    assert len(github.blob_reads) == reads_before + 1
    readme = session.scalar(select(File).where(File.path == "README.md"))
    assert "New section" in readme.content
    assert all(chunk.sha == readme.sha for chunk in readme.chunks), "chunk SHAs follow the file"


def test_deleted_file_and_its_chunks_are_removed(session: Session) -> None:
    github = demo_corpus()
    index_owner(session, "octo", client=github, embedder=HashEmbedder())
    github.repos[0].files.pop("docs/architecture.md")

    stats = index_owner(session, "octo", client=github, embedder=HashEmbedder())

    assert stats.files_removed == 1
    assert session.scalar(select(File).where(File.path == "docs/architecture.md")) is None
    orphans = session.scalars(
        select(Chunk).join(File, File.id == Chunk.file_id, isouter=True).where(File.id.is_(None))
    ).all()
    assert orphans == []


def test_chunk_spans_match_the_stored_file_text(session: Session) -> None:
    """The database-level version of the chunker invariant, over every stored chunk."""
    github = demo_corpus()
    index_owner(session, "octo", client=github, embedder=HashEmbedder())
    for file in session.scalars(select(File)).all():
        lines = file.content.splitlines()
        for chunk in file.chunks:
            assert chunk.text == "\n".join(lines[chunk.line_start - 1 : chunk.line_end])
            assert chunk.sha == file.sha


def test_index_run_is_recorded(session: Session) -> None:
    github = demo_corpus()
    index_owner(session, "octo", client=github, embedder=HashEmbedder(), trigger="webhook")
    run = session.scalars(select(IndexRun).order_by(IndexRun.id.desc())).first()
    assert run is not None
    assert run.status == "ok"
    assert run.trigger == "webhook"
    assert run.chunks_written > 0
    assert run.finished_at is not None


def test_a_failing_run_is_recorded_as_failed(session: Session) -> None:
    class Broken(FakeGitHub):
        def get_tree(self, owner: str, name: str, ref: str):  # type: ignore[override]
            raise RuntimeError("GitHub is down")

    github = Broken(owner="octo", repos=[FakeRepo("demo", {"README.md": "# demo"})])
    with pytest.raises(RuntimeError):
        index_owner(session, "octo", client=github, embedder=HashEmbedder())
    session.commit()
    run = session.scalars(select(IndexRun).order_by(IndexRun.id.desc())).first()
    assert run is not None
    assert run.status == "failed"
    assert "GitHub is down" in run.error
