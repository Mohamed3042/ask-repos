"""A frozen copy of a live corpus, so evaluation is reproducible.

Metrics measured against GitHub's HEAD are not comparable from one week to the next:
the repositories move. `ask-repos evals snapshot` records exactly the files an index run
selected, and `SnapshotClient` replays them through the same ingestion code with no
network at all. CI therefore measures the same corpus every time, and the golden set's
expected citations stay meaningful.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ask_repos.config import get_settings
from ask_repos.githubapi.client import EmptyRepository, GitHubClient, RepoMeta, TreeEntry
from ask_repos.ingest.filters import classify, looks_binary

MANIFEST = "manifest.json"


def _repo_record(meta: RepoMeta, tree_sha: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "owner": meta.owner,
        "name": meta.name,
        "full_name": meta.full_name,
        "description": meta.description,
        "default_branch": meta.default_branch,
        "html_url": meta.html_url,
        "language": meta.language,
        "stars": meta.stars,
        "pushed_at": meta.pushed_at.isoformat() if meta.pushed_at else None,
        "tree_sha": tree_sha,
        "files": files,
    }


def write_snapshot(owner: str, out_dir: str, client: GitHubClient | None = None) -> Path:
    """Freeze `owner`'s public repositories into `<out_dir>/<repo>.json.gz`."""
    settings = get_settings()
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    owned = client is None
    client = client or GitHubClient()
    manifest: dict[str, Any] = {
        "owner": owner,
        "captured_at": datetime.now(UTC).isoformat(),
        "max_file_bytes": settings.max_file_bytes,
        "repos": [],
    }
    try:
        for meta in client.list_public_repos(owner):
            try:
                tree_sha, entries, _ = client.get_tree(meta.owner, meta.name, meta.default_branch)
            except EmptyRepository:
                continue
            wanted: list[TreeEntry] = [
                entry
                for entry in entries
                if classify(entry.path) is not None and entry.size <= settings.max_file_bytes
            ]
            blobs = client.get_blobs_text(meta.owner, meta.name, [entry.sha for entry in wanted])
            files: list[dict[str, Any]] = []
            for entry in sorted(wanted, key=lambda item: item.path):
                text = blobs.get(entry.sha)
                if text is None or looks_binary(text.encode("utf-8", "ignore")):
                    continue
                files.append(
                    {"path": entry.path, "sha": entry.sha, "size": entry.size, "content": text}
                )
            record = _repo_record(meta, tree_sha, files)
            path = target / f"{meta.name}.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False)
            manifest["repos"].append(
                {
                    "full_name": meta.full_name,
                    "file": path.name,
                    "files": len(files),
                    "bytes": sum(file["size"] for file in files),
                    "tree_sha": tree_sha,
                }
            )
    finally:
        if owned:
            client.close()
    manifest_path = target / MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


class SnapshotClient:
    """Replays a snapshot through the `GitHubClient` surface. No network."""

    def __init__(
        self,
        source: str | Path,
        only: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> None:
        self.source = Path(source)
        self.only = {name.strip() for name in only} if only else None
        self.exclude = {name.strip() for name in exclude} if exclude else set()
        manifest_path = self.source / MANIFEST
        if not manifest_path.exists():
            raise FileNotFoundError(f"no snapshot manifest at {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.owner: str = self.manifest["owner"]
        self._records: dict[str, dict[str, Any]] = {}
        for row in self.manifest["repos"]:
            with gzip.open(self.source / row["file"], "rt", encoding="utf-8") as handle:
                record = json.load(handle)
            if self.only and record["name"] not in self.only:
                continue
            if record["name"] in self.exclude:
                continue
            self._records[record["name"]] = record
        if self.only:
            missing = self.only - set(self._records)
            if missing:
                raise KeyError(f"snapshot has no repositories named {sorted(missing)}")
        self.requests_made = 0
        self.conditional_hits = 0

    # -- GitHubClient surface -------------------------------------------------

    def _meta(self, record: dict[str, Any]) -> RepoMeta:
        pushed = record.get("pushed_at")
        return RepoMeta(
            owner=record["owner"],
            name=record["name"],
            full_name=record["full_name"],
            description=record.get("description"),
            default_branch=record.get("default_branch") or "main",
            html_url=record.get("html_url") or "",
            language=record.get("language"),
            stars=int(record.get("stars") or 0),
            pushed_at=datetime.fromisoformat(pushed) if pushed else None,
            private=False,
            visibility="public",
            fork=False,
            archived=False,
        )

    def list_public_repos(self, owner: str) -> list[RepoMeta]:
        return [self._meta(record) for record in self._records.values()]

    def get_repo(self, owner: str, name: str) -> RepoMeta:
        return self._meta(self._records[name])

    def get_tree(self, owner: str, name: str, ref: str) -> tuple[str, list[TreeEntry], bool]:
        record = self._records[name]
        entries = [
            TreeEntry(path=file["path"], sha=file["sha"], size=int(file["size"]))
            for file in record["files"]
        ]
        return record["tree_sha"], entries, False

    def get_blob_text(self, owner: str, name: str, sha: str) -> str | None:
        for file in self._records[name]["files"]:
            if file["sha"] == sha:
                return file["content"]
        return None

    def get_blobs_text(
        self, owner: str, name: str, shas: list[str], workers: int = 8
    ) -> dict[str, str | None]:
        wanted = set(shas)
        return {
            file["sha"]: file["content"]
            for file in self._records[name]["files"]
            if file["sha"] in wanted
        }

    def close(self) -> None:
        return None


def load_snapshot(
    source: str | Path,
    force: bool = True,
    progress: Any = None,
    only: list[str] | None = None,
    exclude: list[str] | None = None,
):
    """Index a snapshot (or a named subset of it) into the configured database."""
    from ask_repos.db.session import session_scope
    from ask_repos.ingest.pipeline import index_owner

    client = SnapshotClient(source, only=only, exclude=exclude)
    with session_scope() as session:
        return index_owner(
            session,
            client.owner,
            client=client,  # type: ignore[arg-type]
            force=force,
            trigger="snapshot",
            progress=progress,
        )
