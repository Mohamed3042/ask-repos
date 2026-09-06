"""Frozen corpora: capture, replay, and the subset selection CI depends on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ask_repos.db.models import Repo
from ask_repos.evals.snapshot import SnapshotClient, write_snapshot
from ask_repos.ingest.pipeline import index_owner
from ask_repos.retrieval.embed import HashEmbedder
from tests.fakes import demo_corpus

pytestmark = pytest.mark.db


@pytest.fixture()
def snapshot(tmp_path: Path) -> Path:
    write_snapshot("octo", str(tmp_path), client=demo_corpus())  # type: ignore[arg-type]
    return tmp_path


def test_a_snapshot_records_only_what_ingestion_would_select(snapshot: Path) -> None:
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["owner"] == "octo"
    assert [row["full_name"] for row in manifest["repos"]] == ["octo/demo-api"]
    assert (snapshot / "demo-api.json.gz").exists()

    client = SnapshotClient(snapshot)
    _sha, entries, truncated = client.get_tree("octo", "demo-api", "main")
    assert truncated is False
    paths = {entry.path for entry in entries}
    assert paths == {"README.md", "src/app.py", "docs/architecture.md"}
    assert "package-lock.json" not in paths, "the filters run before the snapshot is written"


def test_replaying_a_snapshot_produces_the_same_corpus(snapshot: Path, session: Session) -> None:
    live = index_owner(session, "octo", client=demo_corpus(), embedder=HashEmbedder())
    session.execute(Repo.__table__.delete())
    session.commit()

    frozen = index_owner(
        session,
        "octo",
        client=SnapshotClient(snapshot),  # type: ignore[arg-type]
        embedder=HashEmbedder(),
    )
    assert frozen.files_indexed == live.files_indexed
    assert frozen.chunks_written == live.chunks_written
    assert frozen.github_requests == 0, "a replay never touches the network"


def test_only_and_exclude_select_repositories(snapshot: Path) -> None:
    assert set(SnapshotClient(snapshot, only=["demo-api"])._records) == {"demo-api"}
    assert SnapshotClient(snapshot, exclude=["demo-api"])._records == {}
    with pytest.raises(KeyError):
        SnapshotClient(snapshot, only=["not-in-the-snapshot"])


def test_a_missing_snapshot_is_named(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SnapshotClient(tmp_path / "nowhere")


def test_the_shipped_corpus_manifest_matches_its_files() -> None:
    """The corpus committed to this repository is the one CI measures."""
    corpus = Path("evals/corpus")
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    client = SnapshotClient(corpus)
    assert manifest["owner"] == "Mohamed3042"
    assert len(manifest["repos"]) == len(client._records) == 16
    for row in manifest["repos"]:
        assert (corpus / row["file"]).exists()
        record = client._records[row["full_name"].split("/", 1)[1]]
        assert len(record["files"]) == row["files"]


def test_the_injection_fixtures_are_loadable_and_probed() -> None:
    corpus = Path("evals/injection")
    client = SnapshotClient(corpus)
    probes = json.loads((corpus / "probes.json").read_text(encoding="utf-8"))
    assert client.owner == "ask-repos-redteam"
    assert len(probes) >= 6
    assert all(probe["must_not_contain"] for probe in probes)
    _sha, entries, _ = client.get_tree("ask-repos-redteam", "tidyflow", "main")
    assert {entry.path for entry in entries} == {
        "README.md",
        "docs/policy.md",
        "src/tidyflow/config.py",
    }


def test_selecting_the_ci_subset_of_the_shipped_corpus() -> None:
    """CI excludes the two portfolio repositories; the rest must still be there."""
    client = SnapshotClient(
        Path("evals/corpus"), exclude=["flagship-portfolio", "Flagship-One-Page"]
    )
    assert len(client._records) == 14
    assert "flagship-portfolio" not in client._records
    assert "petpoint-ops-hub" in client._records


def test_snapshot_is_stable_across_captures(snapshot: Path, tmp_path: Path) -> None:
    second = tmp_path / "again"
    write_snapshot("octo", str(second), client=demo_corpus())  # type: ignore[arg-type]
    first_records = SnapshotClient(snapshot)._records["demo-api"]
    second_records = SnapshotClient(second)._records["demo-api"]
    assert first_records["tree_sha"] == second_records["tree_sha"]
    assert first_records["files"] == second_records["files"]


def test_a_snapshot_client_reports_no_requests(snapshot: Path) -> None:
    client = SnapshotClient(snapshot)
    client.get_blob_text("octo", "demo-api", "nope")
    assert client.requests_made == 0
    assert client.conditional_hits == 0
