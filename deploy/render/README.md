# The API, on Render

The hosted API is a Render **Free** web service named `ask-repos`, region Frankfurt, built by
Render from this repository's `main` with Dockerfile path `./deploy/hf-space/Dockerfile` and
the repository root as the build context. The image is the one described in that folder: the
CI-published `ghcr.io/mohamed3042/ask-repos` image plus PostgreSQL 16 and pgvector, with the
frozen corpus loaded into `PGDATA` at image-build time. Health check path `/health`; no
environment variables set on the service — everything the demo needs is in the Dockerfile,
so there is no form field to mistype into a deployment that quietly is not read-only.

Live: <https://ask-repos.onrender.com> (`/health`, `/v1/corpus`, `/docs`).

## Why Render, and what it costs

Measured 2026-09-06:

- Hugging Face refused to create a Docker Space on this account — `402 Payment Required`,
  *"hosting Gradio and Docker Spaces on free cpu-basic requires a PRO subscription"* — after a
  successful `hf auth login`. `deploy/hf-space/` is kept, correct, for a PRO account; the
  Dockerfile there is exactly what Render builds.
- Render creates nothing without payment information on file, Free plan included —
  `402 Payment information is required to complete this request` from `POST /v1/services`.
  With a card on file the Free instance costs nothing.
- Free instances sleep after ~15 minutes idle. The first request after a pause takes 30 s or
  more while the container wakes; the hourly uptime probe waits up to 90 s, so a wake is
  recorded in `docs/proof/uptime.json` as a slow success with its latency, not as downtime
  and not as a prober failure.

## Creating it (once)

The service was created through the Render API rather than the dashboard, so the settings
above are a record rather than a memory: `POST /v1/services` with
`type: web_service`, `repo: https://github.com/Mohamed3042/ask-repos`, `branch: main`,
`serviceDetails: {runtime: docker, plan: free, region: frankfurt, healthCheckPath: /health,
envSpecificDetails: {dockerfilePath: ./deploy/hf-space/Dockerfile, dockerContext: .}}`, using
an API key from *Account Settings → API Keys* held in `RENDER_API_KEY`, never in the
repository. `POST /v1/services/<id>/deploys` redeploys it after a release. The dashboard form
(**New + → Web Service → this repository → Docker → Dockerfile Path
`./deploy/hf-space/Dockerfile` → Free**) creates the same service.

The first build takes about 36 minutes: `evals load` embeds the whole corpus on Render's
builder CPU. Later builds reuse that layer from the registry cache and take minutes, because
the Dockerfile puts the bake before the entrypoint and environment layers.

## What 512 MB taught the reranker

The first deploy built, booted, answered one question and was killed by the kernel about
fifteen seconds later — health checks still green, no traceback, and Render's own memory graph
flat at ~130 MB between answers. Trimming PostgreSQL (`ASK_REPOS_PG_OPTIONS`) was measured
**not** to be enough on its own. The spike was the cross-encoder scoring the whole 30-passage
shortlist in fastembed's default batch of 64: MiniLM's attention on 64 × 512 tokens is on the
order of 800 MB of activations. `ASK_REPOS_RERANK_BATCH` (default 8) now reaches the model
call; a pair's score does not depend on its batch, so the retrieval numbers in `docs/retrieval.md`
describe the hosted demo unchanged. Both settings are in `deploy/hf-space/Dockerfile`.

Before that, the very first deploy exited with status 128 before printing a line: the
entrypoint had been committed as mode 100644. Docker Desktop on Windows copies files from a
Windows build context as 0755, which is why the local Space build had booted; Render's Linux
builder honours the git mode. The bit is now set in git and forced with `COPY --chmod=755`.
