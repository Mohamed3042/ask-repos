---
title: ask-repos
emoji: 📎
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Ask a GitHub account about its repos — every answer cites file and line
---

# ask-repos — the API

Answers questions about a GitHub account's **public** repositories, and anchors every
sentence to `owner/repo/path#Lstart-Lend@sha`. Before a sentence is returned the service
re-opens the stored file at that commit and checks those exact lines are still there. A
sentence it cannot anchor is dropped; when nothing survives, it refuses.

This Space runs the API. The user interface is at the URL in the repository README.

* Source, and how to run it over your own account: <https://github.com/Mohamed3042/ask-repos>
* OpenAPI: `/docs` · corpus summary: `/v1/corpus` · health: `/health`

## What this deployment will and will not do

| | |
|---|---|
| Corpus | 14 public repositories of `Mohamed3042`, frozen at the commits in `evals/corpus/`, baked into the image at build time. This is the same subset CI measures, so the numbers in the repository describe **this** corpus. |
| Answers | Extractive and keyless by default: retrieved lines, stitched verbatim, with citations. Set the Space secret `GEMINI_API_KEY` to get prose from the same retrieved chunks. |
| Read-only | `POST /v1/index`, the GitHub push webhook, and *approving* an agent-requested re-index all answer **403**. The approval interrupt itself still fires — that gate is the point. |
| Rate limit | 12 requests per minute per client on `/v1/ask*` and `/v1/search`, fixed window, per container. `/health` and `/v1/corpus` are never throttled, so an uptime probe costs a visitor nothing. |
| Data | Only public repository text was ever indexed. No visitor input is stored. |

## Why PostgreSQL is inside the container

A Space is one container with no attached database, and the project's claim is that a
citation can be re-verified against stored bytes. So PostgreSQL 16 with pgvector is
installed in the image and its data directory is built at image-build time from the
committed corpus snapshot — no network, no key, no first-boot indexing. The alternative,
a second storage implementation for the demo, would mean the published retrieval numbers
described software nobody else runs.

Details: [`docs/adr/0008-space-readonly-corpus.md`](https://github.com/Mohamed3042/ask-repos/blob/main/docs/adr/0008-space-readonly-corpus.md).

MIT © Mohamed Mahmoud
