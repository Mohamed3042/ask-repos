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
# keep PostgreSQL small, because the container shares 512 MB with two ONNX models. (The
# memory kill measured on 2026-09-06 was the reranker's batch size, fixed in the image's
# environment; this trim is the smaller of the two levers and was not enough on its own.)
pg_ctl -D "$PGDATA" \
  -o "-c listen_addresses='' -c unix_socket_directories=$SOCKET_DIR ${ASK_REPOS_PG_OPTIONS:-}" \
  -l /tmp/postgres.log -w start

trap 'pg_ctl -D "$PGDATA" -m fast stop >/dev/null 2>&1 || true' TERM INT

echo "ask-repos: read-only=${ASK_REPOS_READONLY:-0} rate-limit=${ASK_REPOS_RATE_LIMIT_PER_MINUTE:-0}/min"
ask-repos corpus || echo "ask-repos: corpus summary unavailable at start-up"

# ASK_REPOS_MEMORY_LOG=<seconds>: print the container's memory counter (cgroup v2 or v1) and
# the server's resident set every N seconds. The sampler is forked before `exec`, so it
# outlives the shell and keeps writing to the same log the host collects. It is how the
# 512 MB kill on the hosted demo was finally measured from inside rather than guessed.
if [ -n "${ASK_REPOS_MEMORY_LOG:-}" ]; then
  (
    while :; do
      cg=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || echo 0)
      rss=$(awk '/VmRSS/ {print $2 * 1024}' /proc/1/status 2>/dev/null || echo 0)
      pg=0
      for p in /proc/[0-9]*; do
        if grep -qs '^Name:.*postgres' "$p/status" 2>/dev/null; then
          pg=$((pg + $(awk '/VmRSS/ {print $2 * 1024}' "$p/status" 2>/dev/null || echo 0)))
        fi
      done
      echo "mem cgroup=$((cg / 1048576))MB server_rss=$((rss / 1048576))MB postgres_rss=$((pg / 1048576))MB"
      sleep "${ASK_REPOS_MEMORY_LOG}"
    done
  ) &
fi

# The server runs as a child rather than replacing the shell, so that when it dies the shell
# can report HOW: 137 is the kernel's memory kill, 139 a native crash, anything else Python.
# The status is then handed to the host, which restarts the container as before.
ask-repos serve --host 0.0.0.0 --port "${PORT:-7860}" &
server=$!
trap 'kill -TERM "$server" 2>/dev/null; pg_ctl -D "$PGDATA" -m fast stop >/dev/null 2>&1 || true' TERM INT
wait "$server"
code=$?
echo "ask-repos: server exited with status $code (cgroup=$(( $(cat /sys/fs/cgroup/memory.current 2>/dev/null || cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || echo 0) / 1048576 ))MB at exit)"
exit "$code"
