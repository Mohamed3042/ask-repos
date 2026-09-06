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

The first working deploy built, booted, answered one question and was killed by the kernel
about fifteen seconds later — health checks still green, no traceback, Render's memory graph
~130 MB between answers and 331 MB at the last 30-second sample before the kill. Three fixes
were deployed and measured in turn:

| deploy | change | six-question hammer |
|---|---|---|
| PostgreSQL trimmed (`ASK_REPOS_PG_OPTIONS`) | smaller shared_buffers, no autovacuum, no parallel workers | killed after answer 1 |
| reranker batch 64 → 8 (`ASK_REPOS_RERANK_BATCH`) | fewer pairs per forward pass | killed after answer 1 |
| onnxruntime arena off + batch 1 | see below; uvicorn still PID 1 | killed 19–37 s after answer 1, health checks green, cgroup peak 456 MB, no exit line |
| the server as a child of the entrypoint shell | shell is PID 1, reports the server's exit status | **6 of 6 answered, 0 restarts**, cgroup steady 424 MB, peak 469 MB |
| + server pinned to one CPU (`ASK_REPOS_CPUSET=0`) | thread pools sized to one CPU | **6 of 6, 0 restarts**; 75–131 s per answer — no faster, so the pools were not the cost |
| + glibc mmap/trim thresholds raised | freed buffers stay in the heap | two concurrent answers, then the container died with no exit line at all (whole-group kill); **reverted** |

The last row is the same image bytes as the row above it. With uvicorn as PID 1 the container was
restarted 19–37 s after every answer — no kernel memory kill (the in-container sampler saw the
cgroup counter peak at 456 MB of 512), no traceback, no exit status, health checks answering
every five seconds throughout. With a shell as PID 1 and the server as its child, the same
questions were answered six times in a row without a restart. Whatever the host does with a
container whose PID 1 is the application, it is not visible from inside, so it is recorded as
measured behaviour rather than explained. The shell also prints the server's exit status when
it does die (137 kernel kill, 139 native crash), which every earlier deploy lacked.

Answers on the Free instance are slow: 99–165 s each in that run, measured with the memory
sampler on (`ASK_REPOS_MEMORY_LOG`, off by default) and 0.1 CPU; the interface streams sentence
by sentence and says the API is a Free instance.

The instrument that settled it was local: peak working set of one process loading the same two
models and scoring 30 passages. With onnxruntime's default CPU memory arena the process holds
**755 MB** after one rerank at batch 8 (1,578 MB at batch 64) — the arena keeps every buffer it
ever grew to. With the arena off (`enable_cpu_mem_arena=False`, exposed by fastembed) the steady
state is 289 MB and the peak is 323 MB at batch 1, 348 at 2, 410 at 4, 534 at 8 — and every
batch size takes the same ~1.1 s on a CPU, so batching buys nothing here. The application now
runs both sessions with the arena off by default (`ASK_REPOS_ONNX_ARENA=1` turns it back on) and
the hosted image scores one pair per pass. Neither changes a score: the arena is a cache, not
arithmetic, and a pair's score does not depend on its batch, so `docs/retrieval.md` still
describes the hosted demo. All settings are in `deploy/hf-space/Dockerfile`.

Before that, the very first deploy exited with status 128 before printing a line: the
entrypoint had been committed as mode 100644. Docker Desktop on Windows copies files from a
Windows build context as 0755, which is why the local Space build had booted; Render's Linux
builder honours the git mode. The bit is now set in git and forced with `COPY --chmod=755`.
