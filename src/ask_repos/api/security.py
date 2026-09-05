"""API key checks and GitHub webhook signature verification.

Both refuse rather than degrade: with no key configured the protected routes answer 503,
because a route that silently stops checking is worse than a route that is switched off.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, status

from ask_repos.config import get_settings

SIGNATURE_HEADER = "X-Hub-Signature-256"


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ASK_REPOS_API_KEY is not configured; write routes are disabled",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


def expected_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_github_signature(body: bytes, signature: str | None) -> None:
    settings = get_settings()
    if not settings.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ASK_REPOS_WEBHOOK_SECRET is not configured; the webhook is disabled",
        )
    if not signature or not hmac.compare_digest(
        signature, expected_signature(settings.webhook_secret, body)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad signature")
