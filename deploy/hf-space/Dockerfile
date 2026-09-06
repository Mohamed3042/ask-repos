# syntax=docker/dockerfile:1
#
# ask-repos as a Hugging Face Docker Space.
#
# The hard constraint of a Space is that it is ONE container with no attached database and
# no durable disk. ask-repos is a PostgreSQL + pgvector service, and the whole claim of the
# project is that a citation can be re-verified against stored bytes — so the corpus has to
# come with it.
#
# Two ways to do that:
#   (a) reimplement the store on bundled SQLite + a brute-force vector scan, or
#   (b) put PostgreSQL 16 with pgvector *inside* the image, with its data directory built
#       at image-build time from the frozen corpus.
#
# (b) wins because it runs the same code the eval numbers were measured on. (a) would mean
# the demo is a second implementation, and any number it produced would describe software
# nobody else runs. See docs/adr/0008-space-readonly-corpus.md.
#
# Everything that writes is refused at runtime: ASK_REPOS_READONLY=1 turns POST /v1/index,
# the push webhook and *approving* an agent-requested re-index into 403s. The interrupt
# itself still fires, because the approval gate is the thing worth showing.

# Pinned to the commit-sha tag CI publishes, not `:latest`. Two measured reasons: a build host
# caches the 36-minute corpus bake below only while the base digest is unchanged, and `:latest`
# moves on every merge to main whether or not the runtime changed; and the hosted demo's numbers
# describe one set of bytes. Bump deliberately when a release should reach the demo.
ARG BASE=ghcr.io/mohamed3042/ask-repos:aaa0aa4805ed02a3d19b3554ae4392779096cede
FROM ${BASE} AS space

USER root

# PostgreSQL 16 + pgvector from PGDG. The base is python:3.12-slim-bookworm, so this is
# the bookworm-pgdg archive; versions are pinned by the archive, and the packages are
# removed from the apt cache in the same layer.
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-16 postgresql-16-pgvector; \
    apt-get purge -y --auto-remove gnupg lsb-release; \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/lib/postgresql/16/bin:${PATH}" \
    PGDATA=/var/lib/ask-repos/pgdata \
    ASK_REPOS_MODEL_CACHE=/models \
    HF_HUB_OFFLINE=1

# Hugging Face Spaces run the container as uid 1000. PostgreSQL also refuses to run as
# root, so the same account owns the data directory, initialises it, and serves.
RUN set -eux; \
    if ! getent passwd 1000 >/dev/null; then \
      useradd --create-home --uid 1000 --shell /bin/sh spaceuser; \
    fi; \
    mkdir -p "${PGDATA}" /var/run/postgresql; \
    chown -R 1000:1000 "${PGDATA}" /var/run/postgresql /app /models

USER 1000

# ---- bake the corpus into PGDATA --------------------------------------------------
# `evals load` replays the committed snapshot in evals/corpus/ through the real ingestion
# code with no network at all, so the image build needs neither GitHub nor an API key. The
# two portfolio repositories are excluded: they are 73% of the corpus by chunk count, and
# leaving them out gives exactly the 14-repository / 1,625-chunk corpus whose retrieval
# numbers CI publishes — the Space is therefore the corpus the numbers describe.
ARG CORPUS_EXCLUDE=flagship-portfolio,Flagship-One-Page
ENV DATABASE_URL=postgresql+psycopg://postgres@/askrepos?host=/var/run/postgresql

WORKDIR /app
RUN set -eux; \
    initdb --username=postgres --auth=trust --encoding=UTF8 --locale=C; \
    pg_ctl -D "${PGDATA}" -o "-c listen_addresses='' -c unix_socket_directories=/var/run/postgresql" -w start; \
    createdb --username=postgres askrepos; \
    psql --username=postgres -d askrepos -c 'CREATE EXTENSION IF NOT EXISTS vector'; \
    python -m alembic upgrade head; \
    ask-repos evals load --source evals/corpus --exclude "${CORPUS_EXCLUDE}"; \
    ask-repos corpus; \
    pg_ctl -D "${PGDATA}" -m fast -w stop

COPY --chown=1000:1000 --chmod=755 deploy/hf-space/entrypoint.sh /usr/local/bin/space-entrypoint.sh

# The demo's guard rails. Every one of them is a runtime refusal with a reason, not a
# route that quietly disappeared.
ENV ASK_REPOS_READONLY=1 \
    ASK_REPOS_BOOTSTRAP_INDEX=0 \
    ASK_REPOS_RATE_LIMIT_PER_MINUTE=12 \
    ASK_REPOS_OWNER=Mohamed3042 \
    ASK_REPOS_DEMO_NOTE="Public demo." \
    ASK_REPOS_CORS_ORIGINS="https://mohamed-mahmoud-kuwait.netlify.app,https://mohamed3042.github.io" \
    PORT=7860

# Memory. The hosted instance has 512 MB for PostgreSQL, the embedding model, the reranker
# and the Python process together. Measured 2026-09-06 on Render Free: the container boots,
# answers a question, and is killed by the kernel about fifteen seconds later with health
# checks still green and no traceback; the host's memory graph reads ~130 MB between
# answers and 331 MB at the last 30-second sample before the kill. Measured locally on the
# same two models (peak working set of the process, 30 passages): onnxruntime's default
# memory arena holds 755 MB after one rerank at batch 8 and 1,578 MB at batch 64; with the
# arena off the steady state is 289 MB and the peak is 323 MB at batch 1, 348 at 2, 410 at 4,
# 534 at 8 - and every batch size takes the same ~1.1 s on a CPU. Trimming PostgreSQL alone
# was deployed and measured NOT to be enough; batch 8 with the arena on, likewise. Settings,
# none of which changes what the demo serves (a pair's score does not depend on its batch,
# and the arena is a cache, not arithmetic):
#   - the arena is off by default in the application (ASK_REPOS_ONNX_ARENA=0);
#   - ASK_REPOS_RERANK_BATCH=1 scores one pair per forward pass (peak 323 MB measured);
#   - PostgreSQL is a read-only 1.6 MB corpus here, so shared_buffers, worker processes,
#     autovacuum and parallel query are set to the minimum;
#   - MALLOC_ARENA_MAX stops glibc from keeping one arena per thread alive for the
#     onnxruntime and uvicorn thread pools.
ENV ASK_REPOS_RERANK_BATCH=1 \
    ASK_REPOS_ONNX_ARENA=0 \
    ASK_REPOS_PG_OPTIONS="-c shared_buffers=16MB -c max_connections=20 -c work_mem=1MB -c maintenance_work_mem=8MB -c autovacuum=off -c max_parallel_workers=0 -c max_worker_processes=2 -c wal_buffers=1MB -c effective_cache_size=64MB -c synchronous_commit=off -c huge_pages=off" \
    MALLOC_ARENA_MAX=2

EXPOSE 7860

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:7860/health').read()"

ENTRYPOINT ["/usr/local/bin/space-entrypoint.sh"]
