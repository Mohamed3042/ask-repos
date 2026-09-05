"""The GitHub client, driven against recorded HTTP with `respx`.

Two of these are guarantees, not conveniences: private repositories are never returned,
and an empty repository is reported as such instead of exploding the run.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest
import respx

from ask_repos.githubapi.client import EmptyRepository, GitHubClient, RateLimited

BASE = "https://api.github.com"


def repo_payload(name: str, private: bool = False, fork: bool = False, **extra: Any) -> dict:
    return {
        "name": name,
        "full_name": f"octo/{name}",
        "owner": {"login": "octo"},
        "description": f"{name} description",
        "default_branch": "main",
        "html_url": f"https://github.com/octo/{name}",
        "language": "Python",
        "stargazers_count": 1,
        "pushed_at": "2026-09-01T10:00:00Z",
        "private": private,
        "visibility": "private" if private else "public",
        "fork": fork,
        "archived": False,
        **extra,
    }


@respx.mock
def test_private_and_fork_repos_are_never_returned() -> None:
    respx.get(f"{BASE}/users/octo/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                repo_payload("public-one"),
                repo_payload("secret", private=True),
                repo_payload("mirror", fork=True),
                repo_payload("stale", archived=True),
            ],
        )
    )
    with GitHubClient(token=None) as client:
        repos = client.list_public_repos("octo")
    assert [repo.name for repo in repos] == ["public-one"]


@respx.mock
def test_pagination_follows_the_link_header() -> None:
    # Registered first so it wins over the catch-all below.
    respx.get(f"{BASE}/users/octo/repos", params={"page": "2"}).mock(
        return_value=httpx.Response(200, json=[repo_payload("two")])
    )
    respx.get(f"{BASE}/users/octo/repos").mock(
        return_value=httpx.Response(
            200,
            json=[repo_payload("one")],
            headers={"link": f'<{BASE}/users/octo/repos?page=2>; rel="next"'},
        )
    )
    with GitHubClient(token=None) as client:
        repos = client.list_public_repos("octo")
    assert sorted(repo.name for repo in repos) == ["one", "two"]


@respx.mock
def test_a_self_referencing_link_header_does_not_loop_for_ever() -> None:
    """A page whose `next` points at itself once cost this suite a spinning CPU."""
    respx.get(f"{BASE}/users/octo/repos").mock(
        return_value=httpx.Response(
            200,
            json=[repo_payload("one")],
            headers={"link": f'<{BASE}/users/octo/repos>; rel="next"'},
        )
    )
    with GitHubClient(token=None) as client:
        repos = client.list_public_repos("octo")
    assert [repo.name for repo in repos] == ["one"]


@respx.mock
def test_etag_makes_the_second_read_conditional() -> None:
    route = respx.get(f"{BASE}/repos/octo/one")
    route.side_effect = [
        httpx.Response(200, json=repo_payload("one"), headers={"etag": 'W/"abc"'}),
        httpx.Response(304),
    ]
    with GitHubClient(token=None) as client:
        first = client.get_repo("octo", "one")
        second = client.get_repo("octo", "one")
        assert client.conditional_hits == 1
    assert first.full_name == second.full_name == "octo/one"


@respx.mock
def test_rate_limit_waits_for_the_reset_then_succeeds() -> None:
    slept: list[float] = []
    route = respx.get(f"{BASE}/repos/octo/one")
    route.side_effect = [
        httpx.Response(403, headers={"x-ratelimit-remaining": "0", "retry-after": "7"}),
        httpx.Response(200, json=repo_payload("one")),
    ]
    with GitHubClient(token=None, sleeper=slept.append) as client:
        repo = client.get_repo("octo", "one")
    assert slept == [7.0]
    assert repo.name == "one"


@respx.mock
def test_rate_limit_beyond_the_cap_raises() -> None:
    respx.get(f"{BASE}/repos/octo/one").mock(
        return_value=httpx.Response(429, headers={"retry-after": "3600"})
    )
    with GitHubClient(token=None, sleeper=lambda _: None) as client, pytest.raises(RateLimited):
        client.get_repo("octo", "one")


@respx.mock
def test_empty_repository_is_named_not_crashed() -> None:
    respx.get(f"{BASE}/repos/octo/fresh/git/trees/main").mock(return_value=httpx.Response(409))
    with GitHubClient(token=None) as client, pytest.raises(EmptyRepository):
        client.get_tree("octo", "fresh", "main")


@respx.mock
def test_tree_and_blob_round_trip() -> None:
    respx.get(f"{BASE}/repos/octo/one/git/trees/main").mock(
        return_value=httpx.Response(
            200,
            json={
                "sha": "treesha",
                "truncated": False,
                "tree": [
                    {"path": "README.md", "type": "blob", "sha": "blob1", "size": 12},
                    {"path": "src", "type": "tree", "sha": "t2"},
                ],
            },
        )
    )
    respx.get(f"{BASE}/repos/octo/one/git/blobs/blob1").mock(
        return_value=httpx.Response(
            200,
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"# hello\n").decode(),
            },
        )
    )
    with GitHubClient(token=None) as client:
        sha, entries, truncated = client.get_tree("octo", "one", "main")
        assert (sha, truncated) == ("treesha", False)
        assert [entry.path for entry in entries] == ["README.md"]
        assert client.get_blob_text("octo", "one", "blob1") == "# hello\n"


@respx.mock
def test_binary_blob_returns_none() -> None:
    respx.get(f"{BASE}/repos/octo/one/git/blobs/binary").mock(
        return_value=httpx.Response(
            200, json={"encoding": "base64", "content": base64.b64encode(b"\xff\xfe\x00").decode()}
        )
    )
    with GitHubClient(token=None) as client:
        assert client.get_blob_text("octo", "one", "binary") is None


@respx.mock
def test_token_is_sent_as_a_bearer_header() -> None:
    captured: dict[str, str] = {}

    def record(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json=repo_payload("one"))

    respx.get(f"{BASE}/repos/octo/one").mock(side_effect=record)
    with GitHubClient(token="ghp_example") as client:
        client.get_repo("octo", "one")
    assert captured["authorization"] == "Bearer ghp_example"
