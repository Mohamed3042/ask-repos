"""The guardrail's tests. These are the ones that matter most.

Each check is shown failing on a planted defect before it is shown passing on the real
thing, because a guardrail that cannot be made to fire is decoration.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ask_repos.agent.cite_check import REFUSAL, cite_check, resolve_citations, support_score
from ask_repos.db.models import Chunk, File

pytestmark = pytest.mark.db


def a_chunk(session: Session, contains: str = "FastAPI") -> Chunk:
    for chunk in session.scalars(select(Chunk).order_by(Chunk.id)).all():
        if contains in chunk.text:
            return chunk
    raise AssertionError(f"no seeded chunk contains {contains!r}")


def test_a_verbatim_sentence_with_a_real_citation_is_kept(seeded: Session) -> None:
    chunk = a_chunk(seeded)
    result = cite_check(seeded, [{"text": chunk.text, "citations": [chunk.id]}])
    assert not result.refused
    assert len(result.kept) == 1
    citation = result.kept[0].citations[0]
    assert citation.label.startswith("octo/demo-api/")
    assert f"#L{chunk.line_start}-L{chunk.line_end}" in citation.label
    assert citation.url.startswith("https://github.com/octo/demo-api/blob/")


def test_a_planted_hallucination_carrying_a_real_citation_is_dropped(seeded: Session) -> None:
    """The fail-first arm: with the support clause switched off the lie survives."""
    chunk = a_chunk(seeded)
    lie = "The author has ten years of production experience at a Fortune 500 bank."

    without_guard = cite_check(seeded, [{"text": lie, "citations": [chunk.id]}], min_support=0.0)
    assert without_guard.kept, "sabotage check: existence-only verification lets the lie through"

    with_guard = cite_check(seeded, [{"text": lie, "citations": [chunk.id]}])
    assert with_guard.refused
    assert with_guard.dropped_reasons == {"unsupported": 1}
    assert with_guard.answer == REFUSAL


def test_a_citation_to_a_chunk_that_does_not_exist_is_dropped(seeded: Session) -> None:
    result = cite_check(seeded, [{"text": "Anything at all.", "citations": [999_999]}])
    assert result.refused
    assert result.dropped_reasons == {"unknown_chunk": 1}


def test_a_sentence_with_no_citation_is_dropped(seeded: Session) -> None:
    result = cite_check(seeded, [{"text": "A confident claim with no anchor.", "citations": []}])
    assert result.refused
    assert result.dropped_reasons == {"no_citation": 1}


def test_a_span_that_no_longer_matches_the_file_is_dropped(seeded: Session) -> None:
    """A citation whose line span drifted from the stored text must not be citable."""
    chunk = a_chunk(seeded)
    good = cite_check(seeded, [{"text": chunk.text, "citations": [chunk.id]}])
    assert good.kept, "control: the citation is valid before the file is disturbed"

    file = seeded.get(File, chunk.file_id)
    lines = file.content.splitlines()
    lines.insert(0, "# an extra line that shifts every span below it")
    file.content = "\n".join(lines)
    seeded.flush()

    after = cite_check(seeded, [{"text": chunk.text, "citations": [chunk.id]}])
    assert after.refused
    assert after.dropped_reasons == {"span_mismatch": 1}


def test_a_citation_at_a_sha_the_file_no_longer_has_is_dropped(seeded: Session) -> None:
    chunk = a_chunk(seeded)
    file = seeded.get(File, chunk.file_id)
    file.sha = "0" * 40
    seeded.flush()

    result = cite_check(seeded, [{"text": chunk.text, "citations": [chunk.id]}])
    assert result.refused
    assert result.dropped_reasons == {"stale_sha": 1}


def test_a_span_running_past_the_end_of_the_file_is_dropped(seeded: Session) -> None:
    chunk = a_chunk(seeded)
    chunk.line_end = 10_000
    seeded.flush()
    result = cite_check(seeded, [{"text": chunk.text, "citations": [chunk.id]}])
    assert result.refused
    assert result.dropped_reasons == {"span_out_of_range": 1}


def test_mixed_answers_keep_only_the_anchored_sentences(seeded: Session) -> None:
    chunk = a_chunk(seeded)
    result = cite_check(
        seeded,
        [
            {"text": chunk.text, "citations": [chunk.id]},
            {"text": "And it also handles payroll for 4,000 employees.", "citations": [chunk.id]},
            {"text": "No anchor here.", "citations": []},
        ],
    )
    assert not result.refused
    assert len(result.kept) == 1
    assert result.dropped_reasons == {"unsupported": 1, "no_citation": 1}
    assert "payroll" not in result.answer


def test_resolve_reports_valid_and_invalid_separately(seeded: Session) -> None:
    chunk = a_chunk(seeded)
    valid, invalid = resolve_citations(seeded, [chunk.id, 888_888])
    assert list(valid) == [chunk.id]
    assert invalid == {888_888: "unknown_chunk"}


def test_support_score_is_a_fraction_of_content_words() -> None:
    assert support_score("FastAPI serves the health endpoint", "the FastAPI health endpoint") > 0.5
    assert support_score("Kubernetes autoscaling saved 40 percent", "a FastAPI health route") < 0.3
    assert support_score("", "anything") == 0.0
