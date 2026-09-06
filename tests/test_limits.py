"""The two guards a public deployment needs: read-only, and a throttle.

The hosted Space answers for anyone with the URL, so both of these are load-bearing. Each
is proved to close, not merely to exist: `scripts/prove_gate_fails_first.py` disables them
on a copy of the source and shows the same assertions going red.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ask_repos.api.limits import LIMITER, FixedWindowLimiter, client_key
from ask_repos.config import reset_settings_cache

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _clear_limiter():
    LIMITER.reset()
    yield
    LIMITER.reset()


# -- the window itself --------------------------------------------------------


def test_window_allows_up_to_the_limit_then_refuses() -> None:
    limiter = FixedWindowLimiter(window_seconds=60.0)
    for expected_remaining in (2, 1, 0):
        allowed, remaining, retry_after = limiter.check("1.2.3.4", limit=3, now=100.0)
        assert allowed is True
        assert remaining == expected_remaining
        assert retry_after == 0
    allowed, remaining, retry_after = limiter.check("1.2.3.4", limit=3, now=100.0)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_window_slides_and_clients_are_independent() -> None:
    limiter = FixedWindowLimiter(window_seconds=60.0)
    limiter.check("a", limit=1, now=100.0)
    assert limiter.check("a", limit=1, now=130.0)[0] is False
    assert limiter.check("a", limit=1, now=161.0)[0] is True
    assert limiter.check("b", limit=1, now=161.0)[0] is True


def test_limit_of_zero_is_off() -> None:
    limiter = FixedWindowLimiter()
    for _ in range(50):
        assert limiter.check("anyone", limit=0)[0] is True


def test_client_key_prefers_the_first_forwarded_hop() -> None:
    class _Request:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers
            self.client = type("C", (), {"host": "10.0.0.1"})()

    assert client_key(_Request({"x-forwarded-for": "203.0.113.9, 10.0.0.1"})) == "203.0.113.9"
    assert client_key(_Request({})) == "10.0.0.1"


# -- through the API ----------------------------------------------------------


def test_answer_route_is_throttled(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASK_REPOS_RATE_LIMIT_PER_MINUTE", "2")
    reset_settings_cache()
    body = {"question": "what is in the corpus?"}

    first = api_client.post("/v1/ask", json=body)
    second = api_client.post("/v1/ask", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["X-RateLimit-Remaining"] == "0"

    third = api_client.post("/v1/ask", json=body)
    assert third.status_code == 429
    assert "per minute" in third.json()["detail"]
    assert int(third.headers["Retry-After"]) >= 1


def test_corpus_and_health_are_never_throttled(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An uptime probe must not spend a visitor's budget."""
    monkeypatch.setenv("ASK_REPOS_RATE_LIMIT_PER_MINUTE", "1")
    reset_settings_cache()
    for _ in range(5):
        assert api_client.get("/health").status_code == 200
        assert api_client.get("/v1/corpus").status_code == 200


# -- read-only ----------------------------------------------------------------


def test_readonly_refuses_indexing_before_it_asks_for_a_key(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """403 with a reason, not 503 "no key configured" - the deployment has no key by design."""
    monkeypatch.setenv("ASK_REPOS_READONLY", "1")
    monkeypatch.delenv("ASK_REPOS_API_KEY", raising=False)
    reset_settings_cache()
    response = api_client.post("/v1/index", json={"owner": "octocat"})
    assert response.status_code == 403
    assert "read-only" in response.json()["detail"]


def test_readonly_refuses_the_push_webhook(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASK_REPOS_READONLY", "1")
    monkeypatch.setenv("ASK_REPOS_WEBHOOK_SECRET", "irrelevant-when-read-only")
    reset_settings_cache()
    body = json.dumps({"repository": {"full_name": "octo/demo", "private": False}}).encode()
    response = api_client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "d-1"},
    )
    assert response.status_code == 403


def test_readonly_refuses_approval_but_still_allows_declining(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interrupt is the feature being demonstrated, so it must still fire and still be
    declinable; only *approving* a re-index is a write."""
    monkeypatch.setenv("ASK_REPOS_READONLY", "1")
    reset_settings_cache()

    started = api_client.post("/v1/ask", json={"question": "reindex Mohamed3042"})
    assert started.status_code == 200
    payload = started.json()
    assert payload["status"] == "interrupted"
    thread = payload["thread_id"]
    assert payload["request"]["action"] == "reindex"

    approve = api_client.post(f"/v1/ask/{thread}/resume", json={"approved": True})
    assert approve.status_code == 403
    assert "read-only" in approve.json()["detail"]

    decline = api_client.post(
        f"/v1/ask/{thread}/resume", json={"approved": False, "reason": "demo"}
    )
    assert decline.status_code == 200
    assert decline.json()["status"] == "ok"


def test_writes_still_work_when_not_read_only(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must be the flag, not a permanently disabled route."""
    monkeypatch.setenv("ASK_REPOS_READONLY", "0")
    monkeypatch.setenv("ASK_REPOS_API_KEY", "k")
    reset_settings_cache()
    monkeypatch.setattr("ask_repos.api.app.background_reindex", lambda target: None)
    response = api_client.post(
        "/v1/index", json={"owner": "octocat"}, headers={"X-API-Key": "k"}
    )
    assert response.status_code == 200
    assert response.json()["started"] is True


# -- what the UI reads --------------------------------------------------------


def test_corpus_summary_reports_the_demo_state_and_webhook_health(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASK_REPOS_READONLY", "1")
    monkeypatch.setenv("ASK_REPOS_RATE_LIMIT_PER_MINUTE", "20")
    monkeypatch.setenv("ASK_REPOS_DEMO_NOTE", "corpus: Mohamed3042")
    monkeypatch.delenv("ASK_REPOS_WEBHOOK_SECRET", raising=False)
    reset_settings_cache()

    body = api_client.get("/v1/corpus").json()
    assert body["readonly"] is True
    assert body["rate_limit_per_minute"] == 20
    assert body["demo_note"] == "corpus: Mohamed3042"
    assert body["owner"]
    # Unconfigured is its own state; it is not "zero deliveries, healthy".
    assert body["webhook"]["configured"] is False
    assert body["webhook"]["enabled"] is False
    assert body["webhook"]["deliveries"] == 0
    assert body["webhook"]["last_delivery_at"] is None


def test_webhook_health_counts_a_real_delivery(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import hmac

    secret = "a-test-webhook-secret"
    monkeypatch.setenv("ASK_REPOS_READONLY", "0")
    monkeypatch.setenv("ASK_REPOS_WEBHOOK_SECRET", secret)
    reset_settings_cache()
    monkeypatch.setattr("ask_repos.api.app.background_reindex", lambda target: None)

    body = json.dumps({"repository": {"full_name": "octo/health-demo", "private": False}}).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    accepted = api_client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-health-1",
            "X-Hub-Signature-256": signature,
        },
    )
    assert accepted.status_code == 200

    health = api_client.get("/v1/corpus").json()["webhook"]
    assert health["configured"] is True
    assert health["enabled"] is True
    assert health["deliveries"] >= 1
    assert health["last_repo"] == "octo/health-demo"
    assert health["last_delivery_at"] is not None
