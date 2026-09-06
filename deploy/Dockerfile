# syntax=docker/dockerfile:1

# ---- build -------------------------------------------------------------------
FROM python:3.12.10-slim-bookworm AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# Bake the ONNX models into the image so `docker compose up` needs no model download
# and the container can answer with no outbound network at all.
ENV ASK_REPOS_MODEL_CACHE=/models
RUN mkdir -p /models && python - <<'PY'
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir="/models").embed(["warm"])
TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2", cache_dir="/models").rerank(
    "warm", ["warm"]
)
PY

# ---- runtime -----------------------------------------------------------------
FROM python:3.12.10-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="ask-repos" \
      org.opencontainers.image.description="Ask any GitHub account about its repositories — every answer cites file and line, or refuses" \
      org.opencontainers.image.source="https://github.com/Mohamed3042/ask-repos" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ASK_REPOS_MODEL_CACHE=/models \
    HF_HUB_OFFLINE=1

RUN useradd --create-home --uid 10001 askrepos
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=askrepos:askrepos /models /models

WORKDIR /app
COPY --chown=askrepos:askrepos alembic.ini ./
COPY --chown=askrepos:askrepos migrations ./migrations
COPY --chown=askrepos:askrepos evals ./evals
COPY --chown=askrepos:askrepos deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER askrepos
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health').read()"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
