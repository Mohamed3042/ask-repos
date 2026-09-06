#!/bin/sh
# Container entrypoint: migrate, optionally start a first index in the background, serve.
#
# The index runs in the background on purpose. A cold index of a real account takes
# minutes; the API answers /health immediately and /ready flips to 200 once the corpus
# has chunks, so an orchestrator sees an honest readiness signal instead of a long hang.
set -e

python -m alembic upgrade head

if [ "${ASK_REPOS_BOOTSTRAP_INDEX:-0}" = "1" ]; then
  echo "ask-repos: bootstrap index of ${ASK_REPOS_OWNER:-Mohamed3042} started in the background"
  ( ask-repos index --owner "${ASK_REPOS_OWNER:-Mohamed3042}" || echo "ask-repos: bootstrap index failed; serving anyway" ) &
fi

exec ask-repos serve --host 0.0.0.0 --port "${PORT:-8080}"
