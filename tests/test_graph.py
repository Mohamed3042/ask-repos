"""The agent end to end: answers that cite, refusals that refuse, and the approval gate."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.orm import Session

from ask_repos.agent.cite_check import REFUSAL
from ask_repos.agent.graph import ask, resume
from ask_repos.agent.providers import Draft, ExtractiveProvider
from ask_repos.retrieval.embed import HashEmbedder

pytestmark = pytest.mark.db


def run(seeded: Session, question: str, **kwargs):
    return ask(
        seeded,
        question,
        embedder=HashEmbedder(),
        provider=kwargs.pop("provider", ExtractiveProvider()),
        checkpointer=InMemorySaver(),
        **kwargs,
    )


def test_a_supported_question_is_answered_with_citations(seeded: Session) -> None:
    result = run(seeded, "What does the FastAPI health endpoint return?")
    assert result["status"] == "ok"
    assert result["refused"] is False
    kept = [sentence for sentence in result["sentences"] if sentence["kept"]]
    assert kept, "the corpus contains the answer"
    for sentence in kept:
        assert sentence["citations"], "every kept sentence carries at least one citation"
        for citation in sentence["citations"]:
            assert citation["line_start"] >= 1
            assert citation["citation"].count("#L") == 1
            assert "@" in citation["citation"]
    assert result["steps"] == ["plan", "retrieve", "expand", "draft", "cite_check", "answer"]


def test_a_question_the_corpus_cannot_answer_is_refused(seeded: Session) -> None:
    result = run(seeded, "What salary does the maintainer earn and who are his clients?")
    assert result["refused"] is True
    assert result["answer"] == REFUSAL


def test_a_hallucinating_provider_cannot_get_a_sentence_through(seeded: Session) -> None:
    class Liar:
        name = "liar"

        def draft(self, question, hits):
            return Draft(
                sentences=[
                    {
                        "text": "The service processes 2.4 million payments a day for Visa.",
                        "citations": [hits[0].chunk_id] if hits else [],
                    }
                ],
                provider=self.name,
            )

    result = run(seeded, "What does the service do?", provider=Liar())
    assert result["refused"] is True
    assert result["dropped"] == {"unsupported": 1}


def test_expand_adds_neighbouring_chunks_that_are_themselves_citable(seeded: Session) -> None:
    # k=2 so the neighbours are genuinely outside what retrieval returned.
    result = run(seeded, "What does the FastAPI health endpoint return?", k=2)
    expanded = [hit for hit in result["hits"] if hit.get("expanded_from")]
    assert expanded, "neighbours of the best hits are pulled in"
    for hit in expanded:
        assert hit["chunk_id"] and hit["line_start"] >= 1


def test_reindex_stops_for_a_human_and_only_runs_once_approved(seeded: Session) -> None:
    calls: list[str | None] = []

    def reindexer(target):
        calls.append(target)
        return {"summary": "1 repo re-indexed"}

    checkpointer = InMemorySaver()
    first = ask(
        seeded,
        "reindex octo/demo-api",
        embedder=HashEmbedder(),
        provider=ExtractiveProvider(),
        thread_id="t1",
        reindexer=reindexer,
        checkpointer=checkpointer,
    )
    assert first["status"] == "interrupted"
    assert first["request"]["action"] == "reindex"
    assert first["request"]["target"] == "octo/demo-api"
    assert calls == [], "nothing ran before a human said yes"

    approved = resume(
        seeded,
        "t1",
        approved=True,
        reindexer=reindexer,
        embedder=HashEmbedder(),
        provider=ExtractiveProvider(),
        checkpointer=checkpointer,
    )
    assert approved["status"] == "ok"
    assert calls == ["octo/demo-api"]
    assert "re-indexed" in approved["answer"]


def test_a_declined_reindex_does_nothing(seeded: Session) -> None:
    calls: list[str | None] = []
    checkpointer = InMemorySaver()
    ask(
        seeded,
        "reindex octo/demo-api",
        embedder=HashEmbedder(),
        provider=ExtractiveProvider(),
        thread_id="t2",
        reindexer=calls.append,
        checkpointer=checkpointer,
    )
    declined = resume(
        seeded,
        "t2",
        approved=False,
        reason="not now",
        reindexer=calls.append,
        embedder=HashEmbedder(),
        provider=ExtractiveProvider(),
        checkpointer=checkpointer,
    )
    assert calls == []
    assert "not now" in declined["answer"]
