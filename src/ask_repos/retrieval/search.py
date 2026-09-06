"""Hybrid retrieval: pgvector cosine + PostgreSQL full-text, fused, then reranked.

The fusion is reciprocal rank fusion (RRF), which needs no score calibration between
two incomparable scales:

    score(chunk) = sum over lists of  1 / (K + rank_in_that_list)

`docs/retrieval.md` reports recall@5 for each stage measured on the golden set, so the
claim that hybrid beats either half is a number, not a slogan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from ask_repos.config import get_settings
from ask_repos.retrieval.embed import Embedder, get_embedder, get_reranker

RRF_K = 60
CANDIDATES = 30


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk with everything a citation needs."""

    chunk_id: int
    repo: str
    path: str
    sha: str
    line_start: int
    line_end: int
    kind: str
    symbol: str | None
    text: str
    score: float
    vector_rank: int | None = None
    text_rank: int | None = None
    rerank_score: float | None = None

    @property
    def citation(self) -> str:
        return f"{self.repo}/{self.path}#L{self.line_start}-L{self.line_end}@{self.sha[:7]}"

    def github_url(self, html_url: str | None = None) -> str:
        base = html_url or f"https://github.com/{self.repo}"
        return f"{base}/blob/{self.sha}/{self.path}#L{self.line_start}-L{self.line_end}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "repo": self.repo,
            "path": self.path,
            "sha": self.sha,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "kind": self.kind,
            "symbol": self.symbol,
            "text": self.text,
            "score": round(self.score, 6),
            "vector_rank": self.vector_rank,
            "text_rank": self.text_rank,
            "rerank_score": self.rerank_score,
            "citation": self.citation,
            "url": self.github_url(),
        }


_ROW_SQL = """
    SELECT c.id, r.full_name AS repo, f.path, c.sha, c.line_start, c.line_end,
           c.kind, c.symbol, c.text
    FROM chunks c
    JOIN files f ON f.id = c.file_id
    JOIN repos r ON r.id = c.repo_id
"""


def _vector_candidates(
    session: Session, vector: list[float], limit: int, repo: str | None
) -> list[dict[str, Any]]:
    clause = "WHERE r.full_name = :repo" if repo else ""
    query = sql_text(
        f"{_ROW_SQL} {clause} "
        "ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :limit"
    )
    params: dict[str, Any] = {"vec": str(vector), "limit": limit}
    if repo:
        params["repo"] = repo
    return [dict(row) for row in session.execute(query, params).mappings()]


def to_or_query(query: str) -> str:
    """Turn a natural question into an OR query for `websearch_to_tsquery`.

    `websearch_to_tsquery` ANDs bare words, so "Which Kuwait branches does the Retail Ops
    Hub demo cover?" required every one of those words in a single chunk and matched almost
    nothing: the full-text arm measured recall@5 0.152 before this. Content words joined
    with OR is what a search box actually means.
    """
    from ask_repos.agent.cite_check import content_words

    words = content_words(query)
    return " OR ".join(dict.fromkeys(words)) if words else query


def _text_candidates(
    session: Session, query_text: str, limit: int, repo: str | None
) -> list[dict[str, Any]]:
    query_text = to_or_query(query_text)
    clause = "AND r.full_name = :repo" if repo else ""
    # Normalisation flag 2 divides the rank by document length. Without it an OR query
    # simply ranks the longest generated files first, because they contain more of every
    # word: measured on the golden set, recall@5 for this arm was 0.130 unnormalised and
    # 0.348 with flag 2.
    query = sql_text(
        f"{_ROW_SQL} WHERE c.tsv @@ websearch_to_tsquery('english', :q) {clause} "
        "ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', :q), 2) DESC LIMIT :limit"
    )
    params: dict[str, Any] = {"q": query_text, "limit": limit}
    if repo:
        params["repo"] = repo
    return [dict(row) for row in session.execute(query, params).mappings()]


def _fuse(
    vector_rows: list[dict[str, Any]], text_rows: list[dict[str, Any]]
) -> dict[int, tuple[float, int | None, int | None, dict[str, Any]]]:
    fused: dict[int, tuple[float, int | None, int | None, dict[str, Any]]] = {}
    for rank, row in enumerate(vector_rows, start=1):
        fused[row["id"]] = (1.0 / (RRF_K + rank), rank, None, row)
    for rank, row in enumerate(text_rows, start=1):
        contribution = 1.0 / (RRF_K + rank)
        if row["id"] in fused:
            score, vrank, _, stored = fused[row["id"]]
            fused[row["id"]] = (score + contribution, vrank, rank, stored)
        else:
            fused[row["id"]] = (contribution, None, rank, row)
    return fused


def search(
    session: Session,
    query: str,
    k: int = 8,
    mode: str = "hybrid",
    repo: str | None = None,
    rerank: bool | None = None,
    embedder: Embedder | None = None,
    candidates: int = CANDIDATES,
) -> list[Hit]:
    """Retrieve `k` chunks.

    `mode` is one of `vector`, `text`, `hybrid`. It exists so `docs/retrieval.md` can
    report each arm honestly rather than asserting the hybrid is better.
    """
    settings = get_settings()
    use_rerank = settings.rerank_enabled if rerank is None else rerank
    embedder = embedder or get_embedder()

    vector_rows: list[dict[str, Any]] = []
    text_rows: list[dict[str, Any]] = []
    if mode in ("vector", "hybrid"):
        vector_rows = _vector_candidates(session, embedder.embed_query(query), candidates, repo)
    if mode in ("text", "hybrid"):
        text_rows = _text_candidates(session, query, candidates, repo)

    fused = _fuse(vector_rows, text_rows)
    ordered = sorted(fused.items(), key=lambda item: item[1][0], reverse=True)
    shortlist = ordered[: max(candidates, k)]

    rerank_scores: dict[int, float] = {}
    if use_rerank and shortlist:
        passages = [
            f"{row['path']} {row['symbol'] or ''}\n{row['text']}" for _, (_, _, _, row) in shortlist
        ]
        scores = get_reranker().score(query, passages)
        rerank_scores = {
            chunk_id: score for (chunk_id, _), score in zip(shortlist, scores, strict=True)
        }
        shortlist = sorted(shortlist, key=lambda item: rerank_scores[item[0]], reverse=True)

    hits: list[Hit] = []
    for chunk_id, (score, vector_rank, text_rank, row) in shortlist[:k]:
        hits.append(
            Hit(
                chunk_id=chunk_id,
                repo=row["repo"],
                path=row["path"],
                sha=row["sha"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                kind=row["kind"],
                symbol=row["symbol"],
                text=row["text"],
                score=score,
                vector_rank=vector_rank,
                text_rank=text_rank,
                rerank_score=rerank_scores.get(chunk_id),
            )
        )
    return hits


def get_chunks(session: Session, chunk_ids: list[int]) -> dict[int, Hit]:
    """Load specific chunks by id (used by the cite-check node and the MCP tools)."""
    if not chunk_ids:
        return {}
    query = sql_text(f"{_ROW_SQL} WHERE c.id = ANY(:ids)")
    out: dict[int, Hit] = {}
    for row in session.execute(query, {"ids": chunk_ids}).mappings():
        out[row["id"]] = Hit(
            chunk_id=row["id"],
            repo=row["repo"],
            path=row["path"],
            sha=row["sha"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            kind=row["kind"],
            symbol=row["symbol"],
            text=row["text"],
            score=0.0,
        )
    return out
