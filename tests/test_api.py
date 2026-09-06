"""The HTTP surface, including the two security gates that must fail closed."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ask_repos.config import reset_settings_cache
from ask_repos.db.models import WebhookDelivery

pytestmark = pytest.mark.db

SECRET = "a-test-webhook-secret"


@pytest.fixture()
def captured_reindex(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """The webhook queues a real index run; in tests we record the call instead."""
    calls: list[str | None] = []
    monkeypatch.setattr("ask_repos.api.app.background_reindex", calls.append)
    return calls


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def push_body(full_name: str = "octo/demo-api", private: bool = False) -> bytes:
    return json.dumps(
        {"repository": {"full_name": full_name, "private": private}, "ref": "refs/heads/main"}
    ).encode()


def test_health_and_ready(api_client: TestClient) -> None:
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = api_client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] is True
    assert ready.json()["chunks"] > 0


def test_openapi_document_is_served(api_client: TestClient) -> None:
    document = api_client.get("/openapi.json").json()
    assert document["info"]["title"] == "ask-repos"
    for route in ("/v1/ask", "/v1/search", "/v1/corpus", "/v1/index", "/webhooks/github"):
        assert route in document["paths"], route


def test_metrics_are_exposed(api_client: TestClient) -> None:
    body = api_client.get("/metrics").text
    assert "ask_repos_ask_total" in body


def test_search_returns_citable_hits(api_client: TestClient) -> None:
    payload = api_client.get("/v1/search", params={"q": "health endpoint", "k": 3}).json()
    assert payload["count"] >= 1
    hit = payload["hits"][0]
    assert hit["citation"].startswith("octo/demo-api/")
    assert hit["url"].startswith("https://github.com/octo/demo-api/blob/")


def test_ask_answers_with_citations(api_client: TestClient) -> None:
    payload = api_client.post(
        "/v1/ask",
        json={"question": "What does the health endpoint return?", "provider": "extractive"},
    ).json()
    assert payload["status"] == "ok"
    assert payload["refused"] is False
    kept = [sentence for sentence in payload["sentences"] if sentence["kept"]]
    assert kept and all(sentence["citations"] for sentence in kept)


def test_ask_refuses_what_the_corpus_does_not_contain(api_client: TestClient) -> None:
    payload = api_client.post(
        "/v1/ask", json={"question": "How much does the maintainer charge per hour?"}
    ).json()
    assert payload["refused"] is True
    assert payload["answer"].startswith("Not in the corpus")


def test_ask_stream_emits_sentence_then_done(api_client: TestClient) -> None:
    with api_client.stream(
        "POST",
        "/v1/ask/stream",
        json={"question": "What does the health endpoint return?", "provider": "extractive"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert "event: sentence" in body
    assert "event: done" in body


def test_corpus_and_file_span(api_client: TestClient) -> None:
    corpus = api_client.get("/v1/corpus").json()
    assert corpus["repo_count"] == 1
    assert corpus["chunk_count"] > 0
    assert corpus["embed_model"]

    hit = api_client.get("/v1/search", params={"q": "health endpoint", "k": 1}).json()["hits"][0]
    listing = api_client.get("/v1/search", params={"q": hit["path"], "k": 1}).json()
    assert listing["count"] >= 1

    span = api_client.get("/v1/files/1", params={"start": 1, "end": 3}).json()
    assert span["line_start"] == 1
    assert span["line_end"] == 3
    assert len(span["text"].splitlines()) == 3


def test_unknown_file_is_404(api_client: TestClient) -> None:
    assert api_client.get("/v1/files/424242").status_code == 404


def test_index_route_is_off_without_a_key_and_closed_with_a_wrong_one(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, captured_reindex: list
) -> None:
    assert api_client.post("/v1/index", json={}).status_code == 503, "no key configured = disabled"

    monkeypatch.setenv("ASK_REPOS_API_KEY", "s3cret")
    reset_settings_cache()
    assert api_client.post("/v1/index", json={}, headers={"x-api-key": "wrong"}).status_code == 401

    accepted = api_client.post(
        "/v1/index", json={"repo": "demo-api"}, headers={"x-api-key": "s3cret"}
    )
    assert accepted.status_code == 200
    assert captured_reindex == ["Mohamed3042/demo-api"]


def test_webhook_rejects_a_tampered_signature(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, captured_reindex: list
) -> None:
    monkeypatch.setenv("ASK_REPOS_WEBHOOK_SECRET", SECRET)
    reset_settings_cache()
    body = push_body()

    good = api_client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sign(body),
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-good",
        },
    )
    assert good.status_code == 200, "control: a correctly signed delivery is accepted"

    tampered = api_client.post(
        "/webhooks/github",
        content=body + b" ",
        headers={
            "X-Hub-Signature-256": sign(body),
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-tampered",
        },
    )
    assert tampered.status_code == 401


def test_webhook_is_disabled_when_no_secret_is_configured(api_client: TestClient) -> None:
    body = push_body()
    response = api_client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "push"},
    )
    assert response.status_code == 503


def test_replayed_delivery_does_no_work(
    api_client: TestClient,
    seeded: Session,
    monkeypatch: pytest.MonkeyPatch,
    captured_reindex: list,
) -> None:
    monkeypatch.setenv("ASK_REPOS_WEBHOOK_SECRET", SECRET)
    reset_settings_cache()
    body = push_body()
    headers = {
        "X-Hub-Signature-256": sign(body),
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": "delivery-1",
    }
    first = api_client.post("/webhooks/github", content=body, headers=headers).json()
    second = api_client.post("/webhooks/github", content=body, headers=headers).json()

    assert first["queued"] == "octo/demo-api"
    assert second["duplicate"] is True
    assert captured_reindex == ["octo/demo-api"], "the replay queued no second run"
    seeded.expire_all()
    assert int(seeded.scalar(select(func.count(WebhookDelivery.id))) or 0) == 1


def test_webhook_ignores_private_pushes_and_pings(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, captured_reindex: list
) -> None:
    monkeypatch.setenv("ASK_REPOS_WEBHOOK_SECRET", SECRET)
    reset_settings_cache()

    ping_body = b'{"zen": "hello"}'
    ping = api_client.post(
        "/webhooks/github",
        content=ping_body,
        headers={"X-Hub-Signature-256": sign(ping_body), "X-GitHub-Event": "ping"},
    )
    assert ping.json()["pong"] is True

    private = push_body("octo/secret-thing", private=True)
    response = api_client.post(
        "/webhooks/github",
        content=private,
        headers={
            "X-Hub-Signature-256": sign(private),
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-private",
        },
    )
    assert response.json()["ignored"] == "private repository"
    assert captured_reindex == [], "a private push never queues an index run"


def test_interrupted_run_returns_200_through_the_json_route(api_client: TestClient) -> None:
    """v0.1.0 regression: the interrupt path answered 500 because `AskResponse` required
    `answer` and `refused`, which an interrupted run does not have. Measured on the
    untouched v0.1.0 container before the fix: `HTTP 500`, `Field required ... answer`.
    """
    reset_settings_cache()
    response = api_client.post("/v1/ask", json={"question": "reindex Mohamed3042"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "interrupted"
    assert payload["answer"] == ""
    assert payload["refused"] is False
    assert payload["request"]["action"] == "reindex"
    assert payload["thread_id"]


def test_server_span_is_installed_when_tracing_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """v0.1.0 regression: instrumentation ran in `lifespan`, after Starlette had built its
    middleware stack, and the failure was swallowed. Measured RED against v0.1.0 in Jaeger:
    every `ask-repos` trace held a single root span (`retrieve` / `draft` / `cite_check`)
    with no parent, so the UI's `traceparent` was never joined.
    """
    from ask_repos.api.app import create_app, instrument

    def stack(app) -> list[str]:
        # The instrumentation wraps `build_middleware_stack`, so it is not in
        # `user_middleware`; the only honest place to look is the stack that gets built.
        names: list[str] = []
        node = app.build_middleware_stack()
        while node is not None:
            names.append(type(node).__name__)
            node = getattr(node, "app", None)
        return names

    monkeypatch.setenv("ASK_REPOS_OTEL_EXPORTER", "console")
    reset_settings_cache()
    app = create_app()
    assert app._is_instrumented_by_opentelemetry is True
    assert "OpenTelemetryMiddleware" in stack(app), stack(app)
    # Idempotent: create_app already instrumented it, and a second call must not raise.
    assert instrument(app) is True

    monkeypatch.setenv("ASK_REPOS_OTEL_EXPORTER", "none")
    reset_settings_cache()
    off = create_app()
    assert "OpenTelemetryMiddleware" not in stack(off), stack(off)
