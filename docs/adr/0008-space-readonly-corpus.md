# 0008 — PostgreSQL inside the Space, and the corpus baked into the image

Status: accepted · 2026-09-06

## Context

The API had to be reachable from a URL a stranger can open. A Hugging Face Docker Space is
one container: no attached database, no durable disk, and a cold boot every time it wakes.
`ask-repos` is PostgreSQL 16 + pgvector, and its central claim is that a citation can be
re-verified against stored bytes — so whatever hosts it has to bring the corpus with it.

Indexing on first boot was never an option: a cold index of the account measured
**3,244.6 s** in the core lane. A Space that spends an hour before it can answer is a Space
nobody sees working.

## Decision

Install **PostgreSQL 16 with pgvector inside the Space image**, and build its data
directory at *image-build* time by replaying the committed corpus snapshot
(`evals/corpus/`) through the real ingestion code. The Space starts `postgres`, then
`uvicorn`, and answers as soon as the socket is up.

The image starts `FROM ghcr.io/mohamed3042/ask-repos` — the image CI already publishes — so
the Space and `docker compose up` run the same build of the same code.

The corpus is the **14-repository subset CI measures** (250 files, 1,625 chunks), not the
full 16, so the numbers published in the README and rendered on `/evals` describe exactly
what the Space is answering from.

## Consequences

* **The demo runs the measured code.** Retrieval, chunking, `cite_check`, the SQL — all of
  it is the shipped implementation, not a demo-only path.
* **Boot is seconds, not an hour.** Verified locally: the image reports
  `14 repos · 250 files · 1625 chunks · 1642788 bytes` at start-up and answers
  `GET /health` 200.
* **The image is 1.96 GB** (1.04 GB base + PostgreSQL + the baked PGDATA). Well inside a
  Space's limits, slow to rebuild — about ten minutes, dominated by embedding 1,625 chunks.
* **The corpus cannot move.** A Space cannot follow the repositories, so the push webhook
  is disabled there. That is stated on the Space card and on `/corpus`, which shows the
  webhook as *not configured* rather than as *zero deliveries, healthy*.
* **Everything that writes is refused with a reason.** `ASK_REPOS_READONLY=1` makes
  `POST /v1/index`, `POST /webhooks/github` and *approving* a re-index answer 403; the
  interrupt still fires and can still be declined, because the approval gate is the
  feature being demonstrated. `tests/test_limits.py` covers all four cases and
  `scripts/prove_gate_fails_first.py` shows them red on a sabotaged copy.
* **A fixed-window limiter (12/min per client) protects it.** In-process, per container,
  not distributed — which is honest for one instance and would be wrong for several.
  `/health` and `/v1/corpus` are exempt so an uptime probe never spends a visitor's budget.

## Alternatives

* **SQLite + `sqlite-vec` read replica.** Smaller and simpler to ship, and rejected: it is
  a second storage implementation. The recall numbers on `/evals` would then describe
  software that only the demo runs, and the fusion, the `ts_rank_cd` normalisation and the
  span verification would all need a parallel implementation to keep honest.
* **A managed Postgres (Neon, Supabase) behind the Space.** Adds an account, a secret and
  a network dependency to a demo whose whole point is that it works offline from a frozen
  corpus. Worth doing the day the corpus needs to change without a rebuild.
* **Fly.io / Render with a volume.** Would allow a live, webhook-driven corpus. Rejected
  for now because it needs a paid plan for a persistent volume, and the Space costs
  nothing.
