"""Retrieval against a real PostgreSQL: each arm, the fusion, and the query translation."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ask_repos.retrieval.embed import HashEmbedder
from ask_repos.retrieval.search import get_chunks, search, to_or_query

pytestmark = pytest.mark.db


def test_or_query_keeps_content_words_and_drops_the_rest() -> None:
    query = to_or_query("Which Kuwait branches does the Retail Ops Hub demo cover?")
    for word in ("kuwait", "branches", "retail", "cover"):
        assert word in query
    assert " OR " in query
    assert "does" not in query.split(" OR "), "stopwords carry no signal"


def test_or_query_survives_a_question_with_no_content_words() -> None:
    assert to_or_query("is it?") == "is it?"


def test_full_text_arm_finds_a_chunk_by_one_distinctive_word(seeded: Session) -> None:
    """`websearch_to_tsquery` ANDs bare words; a whole question then matched nothing."""
    hits = search(seeded, "Which endpoint returns the service version?", mode="text", k=5)
    assert hits, "the OR translation is what makes the full-text arm usable"
    assert any("health" in hit.text for hit in hits)


def test_vector_arm_returns_something_for_a_paraphrase(seeded: Session) -> None:
    hits = search(
        seeded, "how is the project installed", mode="vector", k=5, embedder=HashEmbedder()
    )
    assert hits


def test_hybrid_reports_which_arm_found_each_hit(seeded: Session) -> None:
    hits = search(seeded, "health endpoint version", mode="hybrid", k=8, embedder=HashEmbedder())
    assert hits
    assert any(hit.vector_rank for hit in hits)
    assert any(hit.text_rank for hit in hits)
    fused = [hit for hit in hits if hit.vector_rank and hit.text_rank]
    assert fused, "at least one chunk should be found by both arms and fused"


def test_repo_filter_restricts_results(seeded: Session) -> None:
    assert search(seeded, "health", repo="octo/demo-api", embedder=HashEmbedder())
    assert search(seeded, "health", repo="octo/nothing-here", embedder=HashEmbedder()) == []


def test_hits_render_a_citation_and_a_github_url(seeded: Session) -> None:
    hit = search(seeded, "health endpoint", k=1, embedder=HashEmbedder())[0]
    assert hit.citation.startswith("octo/demo-api/")
    assert f"#L{hit.line_start}-L{hit.line_end}" in hit.citation
    assert hit.github_url().startswith("https://github.com/octo/demo-api/blob/")


def test_get_chunks_loads_specific_ids(seeded: Session) -> None:
    hits = search(seeded, "health endpoint", k=3, embedder=HashEmbedder())
    wanted = [hit.chunk_id for hit in hits]
    loaded = get_chunks(seeded, wanted)
    assert sorted(loaded) == sorted(wanted)
    assert get_chunks(seeded, []) == {}
