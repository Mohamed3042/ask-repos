#!/bin/sh
# Start the bundled PostgreSQL, then serve. One container, two processes, no orchestrator.
#
# The database is already populated: its data directory was built into the image from the
# frozen corpus (see the Dockerfile). Nothing is indexed at start-up, so the Space answers
# as soon as PostgreSQL accepts a connection — a few seconds, not the better part of an hour.
set -e

PGDATA="${PGDATA:-/var/lib/ask-repos/pgdata}"
SOCKET_DIR=/var/run/postgresql

mkdir -p "$SOCKET_DIR"

# A Space container can be stopped hard; `pg_ctl start` on an unclean directory recovers
# from the WAL, which is what we want, and is why the log is left where it can be read.
#
# ASK_REPOS_PG_OPTIONS carries extra `-c name=value` settings. The hosted demo uses it to
# keep PostgreSQL small: the container shares 512 MB with two ONNX models, and the stock
# 128 MB shared_buffers plus a dozen worker processes was the difference between answering
# and being killed by the kernel after the second question (measured 2026-09-06 on Render).
pg_ctl -D "$PGDATA" \
  -o "-c listen_addresses='' -c unix_socket_directories=$SOCKET_DIR ${ASK_REPOS_PG_OPTIONS:-}" \
  -l /tmp/postgres.log -w start

trap 'pg_ctl -D "$PGDATA" -m fast stop >/dev/null 2>&1 || true' TERM INT

echo "ask-repos: read-only=${ASK_REPOS_READONLY:-0} rate-limit=${ASK_REPOS_RATE_LIMIT_PER_MINUTE:-0}/min"
ask-repos corpus || echo "ask-repos: corpus summary unavailable at start-up"

exec ask-repos serve --host 0.0.0.0 --port "${PORT:-7860}"
