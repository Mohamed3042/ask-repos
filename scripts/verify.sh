#!/usr/bin/env bash
# Verify in two minutes: bring up the database, index one repository from the frozen
# corpus (no network, no key), ask a question, and print the citation behind the answer.
#
#   ./scripts/verify.sh
#
# Requires Docker and Python 3.12. Everything else is downloaded once (~67 MB of ONNX
# weights) and cached in .fastembed_cache.
set -euo pipefail

REPO="${ASK_REPOS_VERIFY_REPO:-petpoint-ops-hub}"
QUESTION="${ASK_REPOS_VERIFY_QUESTION:-Which Kuwait branches does the Retail Ops Hub demo cover?}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://askrepos:askrepos@localhost:5433/askrepos}"
export ASK_REPOS_MODEL_CACHE="${ASK_REPOS_MODEL_CACHE:-$PWD/.fastembed_cache}"
export PYTHONIOENCODING=utf-8

echo "==> starting PostgreSQL 16 with pgvector"
docker compose up -d db >/dev/null
until docker compose exec -T db pg_isready -U askrepos -d askrepos >/dev/null 2>&1; do sleep 1; done

echo "==> installing ask-repos"
python -m pip install --quiet -e .

echo "==> creating the schema"
ask-repos migrate

echo "==> indexing $REPO from the frozen corpus (offline)"
ask-repos evals load --source evals/corpus --only "$REPO"

echo
echo "==> asking: $QUESTION"
echo
ask-repos ask "$QUESTION"
