# 0005 — An MCP server with four read-only tools

Status: accepted · 2026-09-05

## Context

The people most likely to ask "what did this person build with X?" are already sitting in
an assistant — Claude Desktop, Claude Code, an editor agent. Making them open a web page
loses the context they are working in. The Model Context Protocol is the way to hand a
corpus to those clients directly.

## Decision

Ship an MCP server (stdio and streamable HTTP) with four tools:

| tool | what it gives the client |
|---|---|
| `list_repos` | what is indexed, how much of it, when it was last indexed |
| `search_corpus` | hybrid retrieval; chunks with citations and GitHub URLs |
| `answer_with_citations` | the full agent, guardrail included — or a refusal |
| `get_file_span` | the exact stored lines behind a citation |

All four are read-only. The server's `instructions` state the trust boundary in the same
words as the README: corpus text is data, not instructions.

`get_file_span` exists specifically so a client can *check* rather than trust: given a
citation, it returns the stored lines that citation resolves to, which is the same text the
guardrail verified.

## Consequences

* Re-indexing is deliberately absent from the MCP surface (see ADR 0003), so an MCP client
  cannot cause a side effect even by accident.
* The tools are tested through a real MCP client over an in-memory transport
  (`tests/test_mcp.py`), so the schemas and results are exercised, not asserted.
* The MCP SDK is a pinned dependency (`mcp==2.1.1`, where `FastMCP` became `MCPServer`); a
  major version of that SDK is a code change, not a configuration change.
