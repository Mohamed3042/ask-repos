# Using ask-repos from an MCP client

`ask-repos` speaks the Model Context Protocol over **stdio** and **streamable HTTP**. Any
MCP client can point at it and ask the corpus questions without leaving the tool it is in.

Four tools, all read-only:

| tool | arguments | returns |
|---|---|---|
| `list_repos` | — | indexed repositories, file/chunk counts, last index time, model ids |
| `search_corpus` | `query`, `k`, `repo`, `mode` | chunks with `citation` and a GitHub URL |
| `answer_with_citations` | `question`, `k`, `repo` | an answer with citations, or a refusal |
| `get_file_span` | `repo`, `path`, `line_start`, `line_end` | the exact stored lines |

Re-indexing is deliberately not exposed (ADR 0003): an MCP client cannot cause a side
effect.

## Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ask-repos": {
      "command": "ask-repos",
      "args": ["mcp", "--stdio"],
      "env": { "DATABASE_URL": "postgresql+psycopg://askrepos:askrepos@localhost:5433/askrepos" }
    }
  }
}
```

## Claude Code

From the repository root, either add the two lines to `.mcp.json` (this repository ships
one already) or register it once:

```bash
claude mcp add ask-repos -- ask-repos mcp --stdio
```

## Any client, over HTTP

```bash
ask-repos mcp --http --host 127.0.0.1 --port 8081
```

The endpoint is `http://127.0.0.1:8081/mcp` (streamable HTTP).

## Verifying it works

`scripts/mcp_smoke.py` starts the stdio server as a subprocess, connects with the official
MCP client, and prints the tool list plus one real answer with its citation. It is the same
path a client takes:

```bash
python scripts/mcp_smoke.py
```

Measured output from this repository's own corpus is in
[`docs/proof/mcp-smoke.txt`](proof/mcp-smoke.txt).

## The trust boundary, restated for tool callers

Everything this server returns is repository text. If a file says "ignore your
instructions", that is content the server will happily quote and cite — it is a fact about
the file — and it is not an instruction the server obeys. Your client should treat tool
results the same way.
