#!/usr/bin/env bash
# Verify in two minutes: bring up the database, index one repository from the frozen
# corpus (no network, no key), ask a question, and print the citation behind the answer.
#
#   ./scripts/verify.sh
#
# Needs Docker and Python 3.12 (set PYTHON=/path/to/python3.12 if it is not on PATH).
# Everything else is downloaded once — about 67 MB of ONNX weights, cached in
# .fastembed_cache — and the corpus itself is already in the repository.
set -euo pipefail

REPO="${ASK_REPOS_VERIFY_REPO:-petpoint-ops-hub}"
QUESTION="${ASK_REPOS_VERIFY_QUESTION:-Which Kuwait branches does the Retail Ops Hub demo cover?}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://askrepos:askrepos@localhost:5433/askrepos}"
export ASK_REPOS_MODEL_CACHE="${ASK_REPOS_MODEL_CACHE:-$PWD/.fastembed_cache}"
export PYTHONIOENCODING=utf-8

pick_python() {
  for candidate in "${PYTHON:-}" python3.12 python3 python; do
    [ -n "$candidate" ] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PY=$(pick_python); then
  echo "ask-repos needs Python 3.12 (the dependency pins are resolved for it)." >&2
  echo "Install it, or run:  PYTHON=/path/to/python3.12 ./scripts/verify.sh" >&2
  exit 1
fi
echo "==> using $("$PY" -V)"

echo "==> starting PostgreSQL 16 with pgvector on localhost:5433"
docker compose up -d db >/dev/null
until docker compose exec -T db pg_isready -U askrepos -d askrepos >/dev/null 2>&1; do sleep 1; done

echo "==> installing ask-repos into .venv-verify"
"$PY" -m venv .venv-verify >/dev/null
VENV_BIN=".venv-verify/bin"
[ -d "$VENV_BIN" ] || VENV_BIN=".venv-verify/Scripts"
"$VENV_BIN/python" -m pip install --quiet --upgrade pip
"$VENV_BIN/python" -m pip install --quiet -e .

echo "==> creating the schema"
"$VENV_BIN/python" -m ask_repos.cli migrate

echo "==> indexing $REPO from the frozen corpus (offline)"
"$VENV_BIN/python" -m ask_repos.cli evals load --source evals/corpus --only "$REPO"

echo
echo "==> asking: $QUESTION"
echo
"$VENV_BIN/python" -m ask_repos.cli ask "$QUESTION"
