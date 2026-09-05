"""The guardrail. Citations are the product, so this module is the product.

A sentence reaches the user only if both of these hold:

1. **The anchor exists.** Every citation is resolved against the database - not against
   what the model said - and the stored file at that SHA still contains exactly the lines
   the chunk claims. A citation to a chunk id that does not exist, or whose line span no
   longer matches the file text at that SHA, is invalid.
2. **The sentence is supported by what it cites.** At least `MIN_SUPPORT` of the
   sentence's content words appear in the cited text. This is the clause that catches a
   fluent invention wearing a real citation, which existence checking alone cannot see.

Everything that fails is dropped and counted. If nothing survives, the answer is a
refusal - "not in the corpus" - never a softened guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

MIN_SUPPORT = 0.34
REFUSAL = (
    "Not in the corpus. I could not anchor an answer to indexed file lines, "
    "so I am not answering."
)

_WORD = re.compile(r"[A-Za-z0-9_./-]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`\"'(\[])")

STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then than that this these those is are was were be been being
    it its of to in on at for with from by as into over under about after before while
    do does did doing have has had having i you he she they we them his her their our your
    not no nor so such can could should would may might must will shall there here what
    which who whom whose when where why how all any both each few more most other some
    only own same too very just also using use used uses
    """.split()
)


@dataclass(frozen=True)
class ResolvedCitation:
    chunk_id: int
    repo: str
    path: str
    sha: str
    line_start: int
    line_end: int
    text: str
    html_url: str

    @property
    def label(self) -> str:
        return f"{self.repo}/{self.path}#L{self.line_start}-L{self.line_end}@{self.sha[:7]}"

    @property
    def url(self) -> str:
        base = self.html_url or f"https://github.com/{self.repo}"
        return f"{base}/blob/{self.sha}/{self.path}#L{self.line_start}-L{self.line_end}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "repo": self.repo,
            "path": self.path,
            "sha": self.sha,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "citation": self.label,
            "url": self.url,
        }


@dataclass
class SentenceVerdict:
    text: str
    kept: bool
    citations: list[ResolvedCitation] = field(default_factory=list)
    reason: str | None = None
    support: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "kept": self.kept,
            "reason": self.reason,
            "support": round(self.support, 3),
            "citations": [citation.as_dict() for citation in self.citations],
        }


@dataclass
class CiteCheckResult:
    verdicts: list[SentenceVerdict]
    refused: bool
    dropped_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def kept(self) -> list[SentenceVerdict]:
        return [verdict for verdict in self.verdicts if verdict.kept]

    @property
    def answer(self) -> str:
        if self.refused:
            return REFUSAL
        return " ".join(verdict.text.strip() for verdict in self.kept)

    def as_dict(self) -> dict[str, Any]:
        return {
            "refused": self.refused,
            "answer": self.answer,
            "sentences": [verdict.as_dict() for verdict in self.verdicts],
            "dropped": self.dropped_reasons,
        }


_RESOLVE_SQL = sql_text(
    """
    SELECT c.id, c.line_start, c.line_end, c.sha AS chunk_sha, c.text AS chunk_text,
           f.path, f.sha AS file_sha, f.content, r.full_name AS repo, r.html_url
    FROM chunks c
    JOIN files f ON f.id = c.file_id
    JOIN repos r ON r.id = c.repo_id
    WHERE c.id = ANY(:ids)
    """
)


def resolve_citations(
    session: Session, chunk_ids: list[int]
) -> tuple[dict[int, ResolvedCitation], dict[int, str]]:
    """Resolve chunk ids to citations, verifying each span against the stored file.

    Returns `(valid, invalid)`; `invalid` maps a chunk id to the reason it failed.
    """
    valid: dict[int, ResolvedCitation] = {}
    invalid: dict[int, str] = {}
    if not chunk_ids:
        return valid, invalid
    wanted = sorted({int(chunk_id) for chunk_id in chunk_ids})
    seen: set[int] = set()
    for row in session.execute(_RESOLVE_SQL, {"ids": wanted}).mappings():
        seen.add(row["id"])
        if row["file_sha"] != row["chunk_sha"]:
            invalid[row["id"]] = "stale_sha"
            continue
        lines = row["content"].splitlines()
        if row["line_start"] < 1 or row["line_end"] > len(lines):
            invalid[row["id"]] = "span_out_of_range"
            continue
        actual = "\n".join(lines[row["line_start"] - 1 : row["line_end"]])
        if actual != row["chunk_text"]:
            invalid[row["id"]] = "span_mismatch"
            continue
        valid[row["id"]] = ResolvedCitation(
            chunk_id=row["id"],
            repo=row["repo"],
            path=row["path"],
            sha=row["chunk_sha"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            text=row["chunk_text"],
            html_url=row["html_url"] or "",
        )
    for chunk_id in wanted:
        if chunk_id not in seen:
            invalid[chunk_id] = "unknown_chunk"
    return valid, invalid


def content_words(sentence: str) -> list[str]:
    return [
        word.lower()
        for word in _WORD.findall(sentence)
        if len(word) > 2 and word.lower() not in STOPWORDS
    ]


def support_score(sentence: str, evidence: str) -> float:
    """Fraction of the sentence's content words that appear in the cited text."""
    words = content_words(sentence)
    if not words:
        return 0.0
    haystack = set(content_words(evidence))
    # Sub-token match so `fastembed` matches `fastembed.embed` and `L12-L40` matches `L12`.
    hits = sum(
        1 for word in words if word in haystack or any(word in token for token in haystack)
    )
    return hits / len(words)


def split_sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def cite_check(
    session: Session,
    sentences: list[dict[str, Any]],
    min_support: float = MIN_SUPPORT,
) -> CiteCheckResult:
    """Verify a drafted answer. `sentences` is `[{"text": str, "citations": [chunk_id]}]`."""
    all_ids = [
        int(chunk_id)
        for sentence in sentences
        for chunk_id in sentence.get("citations", [])
        if str(chunk_id).lstrip("-").isdigit()
    ]
    valid, invalid = resolve_citations(session, all_ids)

    verdicts: list[SentenceVerdict] = []
    dropped: dict[str, int] = {}

    def drop(sentence_text: str, reason: str, support: float = 0.0) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1
        verdicts.append(SentenceVerdict(sentence_text, False, [], reason, support))

    for sentence in sentences:
        sentence_text = (sentence.get("text") or "").strip()
        if not sentence_text:
            continue
        raw_ids = [
            int(chunk_id)
            for chunk_id in sentence.get("citations", [])
            if str(chunk_id).lstrip("-").isdigit()
        ]
        if not raw_ids:
            drop(sentence_text, "no_citation")
            continue
        anchors = [valid[chunk_id] for chunk_id in raw_ids if chunk_id in valid]
        if not anchors:
            reason = invalid.get(raw_ids[0], "unknown_chunk")
            drop(sentence_text, reason)
            continue
        evidence = "\n".join(anchor.text for anchor in anchors)
        support = support_score(sentence_text, evidence)
        if support < min_support:
            drop(sentence_text, "unsupported", support)
            continue
        verdicts.append(SentenceVerdict(sentence_text, True, anchors, None, support))

    return CiteCheckResult(
        verdicts, refused=not any(verdict.kept for verdict in verdicts), dropped_reasons=dropped
    )
