"""Drive the real MCP server the way a client does, and print what came back.

Starts `ask-repos mcp --stdio` as a subprocess, connects with the official MCP Python
client, lists the tools, and asks one question. The output of this script is the proof in
`docs/proof/mcp-smoke.txt` — it is a transcript, not a claim.

    python scripts/mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import Client, StdioServerParameters

ANSWERABLE = "Which Kuwait branches does the Retail Ops Hub demo cover?"
UNANSWERABLE = "Which certifications does the author hold?"


def unwrap(result: Any) -> dict[str, Any]:
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ask_repos.cli", "mcp", "--stdio"],
        env={**os.environ},
    )
    async with Client(params) as client:
        tools = await client.list_tools()
        print("tools:", ", ".join(sorted(tool.name for tool in tools.tools)))

        repos = unwrap(await client.call_tool("list_repos", {}))
        print(f"corpus: {repos['repo_count']} repos, {repos['chunk_count']} chunks")
        print(f"embeddings: {repos['embed_model']}   generation: {repos['generation']}")

        for question in (ANSWERABLE, UNANSWERABLE):
            answer = unwrap(
                await client.call_tool("answer_with_citations", {"question": question})
            )
            print()
            print("Q:", question)
            print("refused:", answer["refused"])
            print("A:", (answer["answer"] or "")[:400])
            for citation in answer["citations"][:3]:
                print("  ->", citation["citation"])
                print("    ", citation["url"])

            if answer["citations"]:
                first = answer["citations"][0]
                span = unwrap(
                    await client.call_tool(
                        "get_file_span",
                        {
                            "repo": first["repo"],
                            "path": first["path"],
                            "line_start": first["line_start"],
                            "line_end": first["line_end"],
                        },
                    )
                )
                print("    get_file_span returns the stored lines behind that citation:")
                for line in span["text"].splitlines()[:4]:
                    print("       ", line[:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
