# 0001 — Hybrid retrieval with reciprocal rank fusion and a local reranker

Status: accepted · 2026-09-05

## Context

The corpus is source files and documentation from public GitHub repositories. Questions
about it come in two shapes that fail differently:

* **Lexical.** "Where is `websearch_to_tsquery` used?" — the answer contains the literal
  token. Embeddings blur identifiers; full-text search finds them exactly.
* **Semantic.** "What did he build with FastAPI?" — the answer may never contain the word
  "build". Full-text search misses it; embeddings do not.

The corpus is small (thousands of chunks, not millions), so retrieval quality matters far
more than retrieval throughput.

## Decision

Run both arms and fuse them with **reciprocal rank fusion**:

    score(chunk) = sum over lists of 1 / (60 + rank_in_that_list)

then rerank the fused shortlist with a local cross-encoder.

RRF was chosen over score normalisation because cosine distance and `ts_rank_cd` are not
comparable quantities, and any weighting between them would be a tuned constant that rots
as the corpus changes. RRF needs only the ranks.

Both arms remain individually selectable (`mode=vector|text|hybrid`,
`--rerank/--no-rerank`) so that the four-row table in `docs/retrieval.md` is a measurement
of this decision rather than an assertion about it — including the case where reranking
does not help.

## Consequences

* Two indexes per chunk: an HNSW index over `vector(384)` and a GIN index over a generated
  `tsvector`. Both are built by the initial migration.
* Every query costs two SQL statements plus one cross-encoder pass over ~30 candidates.
  The reranker is the dominant term.
* The reranker is optional at runtime (`ASK_REPOS_RERANK=0`) because it is the one part of
  retrieval that scales with candidate count rather than corpus size.
* If the corpus grows by orders of magnitude the fusion stays valid, but the candidate
  count (30) and `ef_search` become tuning knobs. They are not tuned today, and nothing in
  this repository claims they are.
