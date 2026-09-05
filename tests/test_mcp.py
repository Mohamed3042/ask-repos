"""The MCP surface, exercised through a real MCP client over an in-memory transport."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp import Client
from sqlalchemy.orm import Session

from ask_repos.config import reset_settings_cache
from ask_repos.db.session import reset_engine_cache
from ask_repos.mcpsrv.server import build_server
from tests.conftest import _test_url

pytestmark = pytest.mark.db


@pytest.fixture()
def mcp_env(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _test_url())
    reset_settings_cache()
    reset_engine_cache()
    yield
    reset_engine_cache()


def payload(result: Any) -> dict[str, Any]:
    """Tool results arrive as structured content, or as JSON in a text block."""
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def test_the_server_advertises_its_four_read_only_tools(mcp_env: None) -> None:
    async with Client(build_server()) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools.tools}
    assert names == {"list_repos", "search_corpus", "answer_with_citations", "get_file_span"}
    for tool in tools.tools:
        assert tool.description, f"{tool.name} has no description for the model to read"
        assert tool.input_schema["type"] == "object"


async def test_list_repos_reports_the_corpus(mcp_env: None) -> None:
    async with Client(build_server()) as client:
        body = payload(await client.call_tool("list_repos", {}))
    assert body["repo_count"] == 1
    assert body["repos"][0]["full_name"] == "octo/demo-api"
    assert body["chunk_count"] > 0


async def test_search_corpus_returns_citations(mcp_env: None) -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("search_corpus", {"query": "health endpoint", "k": 3})
    body = payload(result)
    assert body["count"] >= 1
    assert body["hits"][0]["citation"].startswith("octo/demo-api/")
    assert body["hits"][0]["url"].startswith("https://github.com/octo/demo-api/blob/")


async def test_answer_with_citations_refuses_when_unanchored(mcp_env: None) -> None:
    async with Client(build_server()) as client:
        good = payload(
            await client.call_tool(
                "answer_with_citations", {"question": "What does the health endpoint return?"}
            )
        )
        bad = payload(
            await client.call_tool(
                "answer_with_citations", {"question": "What is the maintainer's day rate?"}
            )
        )
    assert good["refused"] is False
    assert good["citations"]
    assert bad["refused"] is True
    assert bad["citations"] == []


async def test_get_file_span_returns_the_exact_stored_lines(mcp_env: None) -> None:
    async with Client(build_server()) as client:
        found = await client.call_tool("search_corpus", {"query": "health endpoint", "k": 1})
        hit = payload(found)["hits"][0]
        repo, rest = hit["citation"].split("/", 1)
        owner_repo = f"{repo}/{rest.split('/', 1)[0]}"
        path = rest.split("/", 1)[1].split("#")[0]
        body = payload(
            await client.call_tool(
                "get_file_span",
                {"repo": owner_repo, "path": path, "line_start": 1, "line_end": 2},
            )
        )
        missing = payload(
            await client.call_tool(
                "get_file_span", {"repo": "octo/demo-api", "path": "does/not/exist.py"}
            )
        )
    assert body["found"] is True
    assert (body["line_start"], body["line_end"]) == (1, 2)
    # Line 2 of the fixture is blank, so `splitlines()` would report one line here.
    assert body["text"].count(chr(10)) == 1
    assert missing["found"] is False
