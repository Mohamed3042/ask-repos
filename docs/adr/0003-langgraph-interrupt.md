# 0003 — Re-indexing behind a LangGraph interrupt

Status: accepted · 2026-09-05

## Context

Everything the agent does is read-only except one action: re-indexing. That one call spends
GitHub API quota, rewrites corpus rows, and changes what every later answer says. It is
also the action a user is most likely to ask for in passing ("reindex and then tell me…"),
and the one an injected instruction inside a repository would most like to trigger.

## Decision

`reindex` is a graph node that raises a LangGraph `interrupt`. The run stops there and
returns `{"status": "interrupted", "thread_id": …, "request": {…}}`. It continues only when
a human resumes the thread:

    POST /v1/ask/{thread_id}/resume  {"approved": true}

A declined resume returns a run that did nothing and says so. The MCP surface does not
expose the tool at all: MCP clients get four read-only tools, so an MCP client cannot reach
the side effect even with approval.

## Consequences

* The API is stateful for exactly one thing, so the graph needs a checkpointer. It uses the
  in-process `InMemorySaver`: threads do not survive a restart, which is acceptable for an
  approval that is seconds old, and is stated rather than hidden.
* `tests/test_graph.py` asserts the reindexer is not called before approval and is called
  exactly once after — the approval is a gate, not a notification.
* Direct re-indexing still exists for operators (`POST /v1/index` behind an API key, the
  HMAC-verified push webhook, `ask-repos index`). The interrupt guards the *agent's* route
  to the side effect, which is the route a model or an injected instruction could take.
