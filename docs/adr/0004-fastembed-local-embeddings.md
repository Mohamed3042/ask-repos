# 0004 — Local ONNX embeddings and reranking (fastembed), no paid API

Status: accepted · 2026-09-05

## Context

A retrieval service needs an embedding model at index time and at query time, and this one
also wants a reranker. The obvious choice is a hosted embedding API. That would make the
project unrunnable for anyone without a key, make CI depend on a third party's uptime and
billing, and put the cost of a re-index on a card.

## Decision

Use `fastembed`, which runs quantised ONNX models on the CPU:

* embeddings — `BAAI/bge-small-en-v1.5`, 384 dimensions, ~67 MB
* reranking — `Xenova/ms-marco-MiniLM-L-6-v2` cross-encoder, ~80 MB

Both model ids are pinned in settings, printed by `ask-repos version` and `GET /v1/corpus`,
and baked into the container image at build time, so the running service needs no outbound
network to answer.

Generation stays optional and hosted: Gemini improves the wording when `GEMINI_API_KEY` is
set; without it the extractive provider stitches retrieved lines verbatim. Indexing,
search, answering, the MCP server and the whole eval suite run with no key at all.

## Consequences

* Cold indexing is CPU-bound. Measured on a 16-core desktop that was simultaneously running
  three other builds: ~3.8 chunks/second. The honest number to plan with is "minutes for a
  small account, not seconds".
* The 384-dimension vector width is baked into the schema (`vector(384)` and the HNSW
  index). Changing the embedding model means a migration and a full re-index; the
  `ASK_REPOS_EMBED_MODEL` setting exists but is not a drop-in swap.
* The container image carries ~145 MB of model weights and measures **1.04 GB** in total
  (onnxruntime, numpy and the LangGraph stack are the rest). That is the price of a service
  that boots and answers without reaching out to anything.
* Nothing in the retrieval path can be rate-limited or deprecated by a vendor.
