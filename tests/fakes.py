"""An in-memory GitHub the tests can rewrite between calls.

It implements exactly the surface `ingest.pipeline` uses, so pipeline behaviour
(incremental re-index, deletions, private refusal) is tested against real code paths
without touching the network.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ask_repos.githubapi.client import EmptyRepository, RepoMeta, TreeEntry


def blob_sha(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass
class FakeRepo:
    name: str
    files: dict[str, str]
    private: bool = False
    fork: bool = False
    archived: bool = False
    description: str = "a fake repository"
    language: str = "Python"
    empty: bool = False

    def tree_sha(self) -> str:
        joined = "|".join(f"{path}:{blob_sha(text)}" for path, text in sorted(self.files.items()))
        return hashlib.sha1(joined.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass
class FakeGitHub:
    owner: str = "octo"
    repos: list[FakeRepo] = field(default_factory=list)
    requests_made: int = 0
    conditional_hits: int = 0
    blob_reads: list[str] = field(default_factory=list)

    def _meta(self, repo: FakeRepo) -> RepoMeta:
        return RepoMeta(
            owner=self.owner,
            name=repo.name,
            full_name=f"{self.owner}/{repo.name}",
            description=repo.description,
            default_branch="main",
            html_url=f"https://github.com/{self.owner}/{repo.name}",
            language=repo.language,
            stars=0,
            pushed_at=datetime.now(UTC),
            private=repo.private,
            visibility="private" if repo.private else "public",
            fork=repo.fork,
            archived=repo.archived,
        )

    def _find(self, name: str) -> FakeRepo:
        for repo in self.repos:
            if repo.name == name:
                return repo
        raise KeyError(name)

    # -- GitHubClient surface -------------------------------------------------

    def list_public_repos(self, owner: str) -> list[RepoMeta]:
        self.requests_made += 1
        return [
            self._meta(repo)
            for repo in self.repos
            if not repo.private and not repo.fork and not repo.archived
        ]

    def get_repo(self, owner: str, name: str) -> RepoMeta:
        self.requests_made += 1
        return self._meta(self._find(name))

    def get_tree(self, owner: str, name: str, ref: str) -> tuple[str, list[TreeEntry], bool]:
        self.requests_made += 1
        repo = self._find(name)
        if repo.empty:
            raise EmptyRepository(f"{name} has no commits")
        entries = [
            TreeEntry(path=path, sha=blob_sha(text), size=len(text.encode("utf-8")))
            for path, text in sorted(repo.files.items())
        ]
        return repo.tree_sha(), entries, False

    def get_blob_text(self, owner: str, name: str, sha: str) -> str | None:
        self.requests_made += 1
        self.blob_reads.append(sha)
        for text in self._find(name).files.values():
            if blob_sha(text) == sha:
                return text
        return None

    def get_blobs_text(
        self, owner: str, name: str, shas: list[str], workers: int = 8
    ) -> dict[str, str | None]:
        return {sha: self.get_blob_text(owner, name, sha) for sha in dict.fromkeys(shas)}

    def close(self) -> None:
        return None


README = """\
# demo-api

A small FastAPI service used by the tests.

## Install

    pip install demo-api

## Endpoints

`GET /health` returns the version.
"""

APP_PY = '''\
"""The demo FastAPI application."""

from fastapi import FastAPI

app = FastAPI(title="demo-api")


@app.get("/health")
def health() -> dict[str, str]:
    """Return the service version."""
    return {"status": "ok", "version": "1.2.3"}


@app.get("/items/{item_id}")
def read_item(item_id: int) -> dict[str, int]:
    return {"item_id": item_id}
'''

DOCS = """\
# Architecture

The service stores nothing. It answers from memory and is deployed as a container.

## Deployment

The image is published to GHCR and runs on port 8080.
"""


def demo_corpus() -> FakeGitHub:
    """One public repo, one private repo, one empty repo."""
    return FakeGitHub(
        owner="octo",
        repos=[
            FakeRepo(
                name="demo-api",
                files={
                    "README.md": README,
                    "src/app.py": APP_PY,
                    "docs/architecture.md": DOCS,
                    "package-lock.json": '{"lockfileVersion": 3}',
                    "node_modules/left-pad/index.js": "module.exports = 1;",
                },
            ),
            FakeRepo(name="secret-thing", files={"README.md": "# private"}, private=True),
            FakeRepo(name="fresh", files={}, empty=True),
        ],
    )
