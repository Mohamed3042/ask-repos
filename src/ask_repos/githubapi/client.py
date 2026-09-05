"""A small, well-behaved GitHub REST client.

Well-behaved means: conditional requests (ETag) so a re-index costs almost no quota,
Link-header pagination, and rate-limit handling that waits for the documented reset
instead of hammering. Anonymous access works (60 requests/hour); a token raises that
to 5,000 and is the only difference.

Private repositories are filtered out here even when the token can see them - the
second half of that guarantee lives in `ingest.pipeline`, which refuses to write a
repo whose payload is not public.
"""

from __future__ import annotations

import base64
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from ask_repos.config import get_settings

API_ROOT = "https://api.github.com"
USER_AGENT = "ask-repos/0.1 (+https://github.com/Mohamed3042/ask-repos)"
MAX_RATE_LIMIT_WAIT_S = 90.0
_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubError(RuntimeError):
    pass


class EmptyRepository(GitHubError):
    """GitHub answers 409 for a repository that has no commits yet."""


class RateLimited(GitHubError):
    def __init__(self, reset_in: float) -> None:
        super().__init__(f"GitHub rate limit exhausted; resets in {reset_in:.0f}s")
        self.reset_in = reset_in


@dataclass(frozen=True)
class RepoMeta:
    owner: str
    name: str
    full_name: str
    description: str | None
    default_branch: str
    html_url: str
    language: str | None
    stars: int
    pushed_at: datetime | None
    private: bool
    visibility: str
    fork: bool
    archived: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RepoMeta:
        pushed = payload.get("pushed_at")
        private = bool(payload.get("private", False))
        return cls(
            owner=payload["owner"]["login"],
            name=payload["name"],
            full_name=payload["full_name"],
            description=payload.get("description"),
            default_branch=payload.get("default_branch") or "main",
            html_url=payload.get("html_url") or "",
            language=payload.get("language"),
            stars=int(payload.get("stargazers_count") or 0),
            pushed_at=datetime.fromisoformat(pushed.replace("Z", "+00:00")) if pushed else None,
            private=private,
            visibility=payload.get("visibility") or ("private" if private else "public"),
            fork=bool(payload.get("fork", False)),
            archived=bool(payload.get("archived", False)),
        )


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int


class GitHubClient:
    """Synchronous client; one instance per index run."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = API_ROOT,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token if token is not None else get_settings().github_token
        self._etags: dict[str, str] = {}
        self._cache: dict[str, Any] = {}
        self._sleep = sleeper
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = client or httpx.Client(headers=headers, timeout=30.0, follow_redirects=True)
        if client is not None:
            self._client.headers.update(headers)
        self.requests_made = 0
        self.conditional_hits = 0
        self._counter_lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- plumbing -------------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None = None) -> tuple[Any, httpx.Response]:
        full = url if url.startswith("http") else f"{self.base_url}{url}"
        cache_key = full + repr(sorted((params or {}).items()))
        headers: dict[str, str] = {}
        if etag := self._etags.get(cache_key):
            headers["If-None-Match"] = etag
        for attempt in range(4):
            response = self._client.get(full, params=params, headers=headers)
            with self._counter_lock:
                self.requests_made += 1
            if response.status_code == 304:
                with self._counter_lock:
                    self.conditional_hits += 1
                return self._cache[cache_key], response
            if response.status_code in (403, 429) and self._is_rate_limited(response):
                wait = self._reset_delay(response)
                if wait > MAX_RATE_LIMIT_WAIT_S or attempt == 3:
                    raise RateLimited(wait)
                self._sleep(wait)
                continue
            if response.status_code == 404:
                raise GitHubError(f"404 from GitHub for {full}")
            if response.status_code == 409:
                raise EmptyRepository(f"409 from GitHub for {full} (repository has no commits)")
            if response.status_code >= 500 and attempt < 3:
                self._sleep(float(2**attempt))
                continue
            response.raise_for_status()
            payload = response.json()
            # Blob bodies are cached nowhere: keeping every base64 file body keyed by ETag
            # took an index run of 17 repositories to 2.7 GB resident before this line.
            if (tag := response.headers.get("etag")) and "/git/blobs/" not in full:
                self._etags[cache_key] = tag
                self._cache[cache_key] = payload
            return payload, response
        raise GitHubError(f"giving up on {full}")

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        if response.headers.get("x-ratelimit-remaining") == "0":
            return True
        return "retry-after" in response.headers

    @staticmethod
    def _reset_delay(response: httpx.Response) -> float:
        if retry_after := response.headers.get("retry-after"):
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        if reset := response.headers.get("x-ratelimit-reset"):
            try:
                return max(0.0, float(reset) - datetime.now(UTC).timestamp())
            except ValueError:
                pass
        return 60.0

    def _paginate(self, url: str, params: dict[str, Any], max_pages: int = 100) -> list[Any]:
        """Follow `rel="next"` links. A link that points back at a page already read ends
        the walk: a self-referencing Link header would otherwise loop for ever."""
        items: list[Any] = []
        seen: set[str] = set()
        next_url: str | None = url
        next_params: dict[str, Any] | None = params
        for _ in range(max_pages):
            if next_url is None:
                break
            key = next_url + repr(sorted((next_params or {}).items()))
            if key in seen:
                break
            seen.add(key)
            payload, response = self._get(next_url, next_params)
            items.extend(payload)
            match = _NEXT_LINK.search(response.headers.get("link", ""))
            next_url = match.group(1) if match else None
            next_params = None
        return items

    # -- API surface ----------------------------------------------------------

    def list_public_repos(
        self, owner: str, include_forks: bool = False, include_archived: bool = False
    ) -> list[RepoMeta]:
        """Public, non-fork, non-archived repositories of `owner`, newest push first."""
        payload = self._paginate(
            f"/users/{owner}/repos", {"per_page": 100, "type": "owner", "sort": "pushed"}
        )
        seen: set[str] = set()
        repos: list[RepoMeta] = []
        for item in payload:
            repo = RepoMeta.from_payload(item)
            if repo.full_name in seen:
                continue
            seen.add(repo.full_name)
            if (
                repo.visibility == "public"
                and not repo.private
                and (include_forks or not repo.fork)
                and (include_archived or not repo.archived)
            ):
                repos.append(repo)
        return repos

    def get_repo(self, owner: str, name: str) -> RepoMeta:
        payload, _ = self._get(f"/repos/{owner}/{name}")
        return RepoMeta.from_payload(payload)

    def get_tree(self, owner: str, name: str, ref: str) -> tuple[str, list[TreeEntry], bool]:
        payload, _ = self._get(f"/repos/{owner}/{name}/git/trees/{ref}", {"recursive": "1"})
        entries = [
            TreeEntry(path=item["path"], sha=item["sha"], size=int(item.get("size") or 0))
            for item in payload.get("tree", [])
            if item.get("type") == "blob"
        ]
        return payload["sha"], entries, bool(payload.get("truncated"))

    def get_blobs_text(
        self, owner: str, name: str, shas: list[str], workers: int = 8
    ) -> dict[str, str | None]:
        """Fetch many blobs concurrently.

        One HTTP round trip per file dominates an index run, so this is the difference
        between minutes and tens of minutes. Eight workers stays well inside GitHub's
        secondary rate limits; `httpx.Client` is safe to share across threads.
        """
        unique = list(dict.fromkeys(shas))
        if not unique:
            return {}
        if workers <= 1 or len(unique) == 1:
            return {sha: self.get_blob_text(owner, name, sha) for sha in unique}
        out: dict[str, str | None] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self.get_blob_text, owner, name, sha): sha for sha in unique
            }
            for future in as_completed(futures):
                out[futures[future]] = future.result()
        return out

    def get_blob_text(self, owner: str, name: str, sha: str) -> str | None:
        """Decoded UTF-8 text, or None when the blob is binary or undecodable."""
        payload, _ = self._get(f"/repos/{owner}/{name}/git/blobs/{sha}")
        if payload.get("encoding") != "base64":
            return None
        raw = base64.b64decode(payload["content"])
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def rate_limit(self) -> dict[str, Any]:
        payload, _ = self._get("/rate_limit")
        return payload
