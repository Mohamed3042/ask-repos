"""A fixed-window rate limiter for the public demo, and the read-only guard.

Both exist for the same reason: the hosted Space answers questions for anyone who opens
the URL, on a corpus it must not let a stranger rewrite. The limiter is deliberately
in-process and per-instance — one container, one window — because a demo that needs Redis
to say "slow down" has bought the wrong thing. It is off by default
(`ASK_REPOS_RATE_LIMIT_PER_MINUTE=0`) so local runs and CI are unaffected.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from ask_repos.config import get_settings

# Routes worth limiting: the ones that run retrieval or a model. Health, metrics and the
# corpus summary stay open so an uptime probe never spends a caller's budget.
LIMITED_PREFIXES = ("/v1/ask", "/v1/search")

READONLY_DETAIL = (
    "this deployment is read-only: the corpus is fixed and indexing is disabled. "
    "Run it yourself to index any account — https://github.com/Mohamed3042/ask-repos"
)


class FixedWindowLimiter:
    """Counts requests per client per minute. Not distributed, and says so."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, client: str, limit: int, now: float | None = None) -> tuple[bool, int, int]:
        """Return `(allowed, remaining, retry_after_seconds)` and record the hit."""
        if limit <= 0:
            return True, -1, 0
        moment = time.monotonic() if now is None else now
        floor = moment - self.window_seconds
        with self._lock:
            hits = [stamp for stamp in self._hits[client] if stamp > floor]
            if len(hits) >= limit:
                self._hits[client] = hits
                oldest = min(hits)
                retry_after = max(1, int(oldest + self.window_seconds - moment) + 1)
                return False, 0, retry_after
            hits.append(moment)
            self._hits[client] = hits
            return True, limit - len(hits), 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = FixedWindowLimiter()


def client_key(request: Request) -> str:
    """Identify the caller behind a proxy.

    Hugging Face Spaces and Netlify both terminate TLS in front of the app, so
    `request.client.host` is the proxy. The left-most `X-Forwarded-For` entry is the
    original client; it is spoofable, which is acceptable for a demo throttle and is not
    used for anything else.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else "unknown"


def enforce_rate_limit(request: Request) -> dict[str, str]:
    """Raise 429 when the caller is over the window. Returns headers to echo back."""
    settings = get_settings()
    limit = settings.rate_limit_per_minute
    if limit <= 0 or not request.url.path.startswith(LIMITED_PREFIXES):
        return {}
    allowed, remaining, retry_after = LIMITER.check(client_key(request), limit)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limit is {limit} requests per minute on this demo",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limit)},
        )
    return {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(remaining)}


def refuse_when_readonly() -> None:
    """Guard every write route. Called before the API-key check so the reason is honest:
    a read-only deployment has no key to be missing."""
    if get_settings().readonly:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=READONLY_DETAIL)
