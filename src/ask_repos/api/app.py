"""The HTTP API.

`POST /v1/ask` is the product surface: it streams sentences with their citations, and a
sentence only reaches the wire after `cite_check` has resolved every citation against the
stored file at the stored SHA.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select

from ask_repos import __version__
from ask_repos.agent.graph import ask as run_ask
from ask_repos.agent.graph import resume as resume_ask
from ask_repos.api.limits import enforce_rate_limit, refuse_when_readonly
from ask_repos.api.schemas import (
    AskRequest,
    AskResponse,
    FileSpanResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    ReadyResponse,
    ResumeRequest,
    SearchResponse,
)
from ask_repos.api.security import require_api_key, verify_github_signature
from ask_repos.config import get_settings
from ask_repos.db.models import Chunk, File, Repo, WebhookDelivery
from ask_repos.db.session import ping, session_scope
from ask_repos.retrieval.search import search as run_search
from ask_repos.service import corpus_summary, reindex
from ask_repos.telemetry import ASK_LATENCY, SEARCH_LATENCY, metrics_payload, setup_telemetry

logger = logging.getLogger("ask_repos.api")


def background_reindex(target: str | None) -> None:
    """Re-index in the background. A GitHub failure must never turn a webhook that
    was already answered into a 500 afterwards, so the outcome is logged, not raised.
    """
    try:
        result = reindex(target)
        logger.info("reindex %s: %s", target, result.get("summary"))
    except Exception as exc:
        logger.warning("reindex %s failed: %s", target, exc)


DESCRIPTION = """\
Ask any GitHub account about its **public** repositories and get answers with receipts.

Every sentence is anchored to `owner/repo/path#Lstart-Lend@sha`, verified against the
stored file at that SHA before it is returned. Sentences that cannot be anchored are
dropped; when nothing survives, the service refuses instead of guessing.

Repository text is treated as **data, never instructions** — a README that says "ignore
your instructions" is content to be described, not a command to obey.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def instrument(app: FastAPI) -> bool:
    """Install the HTTP server span, and say so when it cannot be installed.

    This used to run inside `lifespan`, which is too late: Starlette has already built its
    middleware stack by then, so `instrument_app` had no effect and the failure was
    swallowed by a bare `except`. The result was the worst kind of observability - the
    service exported `retrieve`, `draft` and `cite_check` spans, each as the ROOT of its
    own trace, with no server span to carry the caller's `traceparent`. Tracing looked
    configured and the UI's trace context went nowhere. Measured on 2026-09-06 against
    v0.1.0: every `ask-repos` trace in Jaeger held exactly one span and no parent.
    """
    setup_telemetry()
    if get_settings().otel_exporter.lower() == "none":
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        return True
    except Exception as exc:  # never stop the service booting over telemetry
        logger.warning("OpenTelemetry FastAPI instrumentation is not active: %s", exc)
        return False


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ask-repos",
        version=__version__,
        description=DESCRIPTION,
        contact={"name": "Mohamed Mahmoud", "url": "https://github.com/Mohamed3042/ask-repos"},
        license_info={"name": "MIT"},
        lifespan=lifespan,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        """Throttle the answer and search routes on a public demo. Off by default."""
        try:
            headers = enforce_rate_limit(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or {},
            )
        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value
        return response

    # -- health ---------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.get("/ready", response_model=ReadyResponse, tags=["ops"])
    def ready(response: Response) -> ReadyResponse:
        alive = ping()
        chunks = 0
        if alive:
            with session_scope() as session:
                chunks = int(session.scalar(select(func.count(Chunk.id))) or 0)
        if not alive or chunks == 0:
            response.status_code = 503
        return ReadyResponse(
            status="ready" if (alive and chunks) else "not-ready", database=alive, chunks=chunks
        )

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics() -> Response:
        return Response(content=metrics_payload(), media_type="text/plain; version=0.0.4")

    # -- corpus ---------------------------------------------------------------

    @app.get("/v1/corpus", tags=["corpus"])
    def corpus() -> dict[str, Any]:
        with session_scope() as session:
            return corpus_summary(session)

    @app.get("/v1/files/{file_id}", response_model=FileSpanResponse, tags=["corpus"])
    def file_span(
        file_id: int,
        start: Annotated[int, Query(ge=1)] = 1,
        end: Annotated[int, Query(ge=0)] = 0,
    ) -> FileSpanResponse:
        with session_scope() as session:
            row = session.execute(
                select(File, Repo).join(Repo, Repo.id == File.repo_id).where(File.id == file_id)
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="no such file in the corpus")
            file, repo = row
            lines = file.content.splitlines()
            last = min(len(lines), end if end > 0 else len(lines))
            first = min(start, max(1, last))
            base = repo.html_url or f"https://github.com/{repo.full_name}"
            return FileSpanResponse(
                repo=repo.full_name,
                path=file.path,
                sha=file.sha,
                language=file.language,
                line_start=first,
                line_end=last,
                line_count=len(lines),
                text="\n".join(lines[first - 1 : last]),
                url=f"{base}/blob/{file.sha}/{file.path}#L{first}-L{last}",
            )

    # -- retrieval ------------------------------------------------------------

    @app.get("/v1/search", response_model=SearchResponse, tags=["retrieval"])
    def search(
        q: Annotated[str, Query(min_length=1, max_length=2000)],
        k: Annotated[int, Query(ge=1, le=50)] = 8,
        mode: Annotated[str, Query(pattern="^(hybrid|vector|text)$")] = "hybrid",
        repo: str | None = None,
        rerank: bool = True,
    ) -> SearchResponse:
        started = time.perf_counter()
        with session_scope() as session:
            hits = run_search(session, q, k=k, mode=mode, repo=repo, rerank=rerank)
        SEARCH_LATENCY.labels(mode=mode).observe(time.perf_counter() - started)
        return SearchResponse(
            query=q, mode=mode, count=len(hits), hits=[hit.as_dict() for hit in hits]
        )

    # -- ask ------------------------------------------------------------------

    def _ask(payload: AskRequest, thread_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        with session_scope() as session:
            result = run_ask(
                session,
                payload.question,
                k=payload.k,
                mode=payload.mode,
                repo=payload.repo,
                provider_name=payload.provider,
                thread_id=thread_id,
                reindexer=lambda target: reindex(target),
            )
        ASK_LATENCY.observe(time.perf_counter() - started)
        return result

    @app.post("/v1/ask", response_model=AskResponse, tags=["ask"])
    def ask(payload: AskRequest) -> AskResponse:
        thread_id = payload.thread_id or uuid.uuid4().hex
        return AskResponse(**{"thread_id": thread_id, **_ask(payload, thread_id)})

    @app.post("/v1/ask/stream", tags=["ask"], response_class=StreamingResponse)
    def ask_stream(payload: AskRequest) -> StreamingResponse:
        """Server-sent events: one `sentence` event per verified sentence, then `done`."""
        thread_id = payload.thread_id or uuid.uuid4().hex

        def emit() -> Iterator[str]:
            result = _ask(payload, thread_id)
            if result.get("status") == "interrupted":
                yield _sse("interrupt", {"thread_id": thread_id, "request": result["request"]})
                return
            for sentence in result.get("sentences", []):
                if sentence.get("kept"):
                    yield _sse("sentence", sentence)
            yield _sse(
                "done",
                {
                    "thread_id": thread_id,
                    "refused": result.get("refused", True),
                    "answer": result.get("answer"),
                    "dropped": result.get("dropped", {}),
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    # Why the configured provider is not the one that answered - a 429
                    # from Gemini must be visible, not a silently different answer.
                    "fallback_reason": result.get("fallback_reason"),
                },
            )

        return StreamingResponse(
            emit(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/ask/{thread_id}/resume", response_model=AskResponse, tags=["ask"])
    def ask_resume(thread_id: str, payload: ResumeRequest) -> AskResponse:
        # Declining is always allowed - refusing an action is never a write. Approving one
        # is, so a read-only deployment says so instead of pretending the run continued.
        if payload.approved:
            refuse_when_readonly()
        with session_scope() as session:
            result = resume_ask(
                session,
                thread_id,
                approved=payload.approved,
                reason=payload.reason,
                reindexer=lambda target: reindex(target),
            )
        return AskResponse(**{"thread_id": thread_id, **result})

    # -- write routes ---------------------------------------------------------

    @app.post("/v1/index", response_model=IndexResponse, tags=["admin"])
    def start_index(
        payload: IndexRequest,
        background: BackgroundTasks,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> IndexResponse:
        refuse_when_readonly()
        require_api_key(x_api_key)
        settings = get_settings()
        owner = payload.owner or settings.default_owner
        target = f"{owner}/{payload.repo}" if payload.repo else owner
        background.add_task(background_reindex, target)
        return IndexResponse(started=True, detail=f"indexing {target} in the background")

    @app.post("/webhooks/github", tags=["admin"])
    async def github_webhook(
        request: Request,
        background: BackgroundTasks,
        x_hub_signature_256: Annotated[str | None, Header()] = None,
        x_github_event: Annotated[str | None, Header()] = None,
        x_github_delivery: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        refuse_when_readonly()
        body = await request.body()
        verify_github_signature(body, x_hub_signature_256)
        if x_github_event == "ping":
            return {"ok": True, "pong": True}
        if x_github_event != "push":
            return {"ok": True, "ignored": x_github_event}
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="body is not JSON") from exc
        repository = (payload.get("repository") or {})
        full_name = repository.get("full_name")
        if not full_name:
            raise HTTPException(status_code=400, detail="push payload has no repository.full_name")
        if repository.get("private"):
            return {"ok": True, "ignored": "private repository"}
        delivery = x_github_delivery or f"anon-{uuid.uuid4().hex}"
        with session_scope() as session:
            seen = session.scalar(
                select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery)
            )
            if seen is not None:
                return {"ok": True, "duplicate": True, "repo": full_name}
            session.add(
                WebhookDelivery(
                    delivery_id=delivery,
                    event="push",
                    repo_full_name=full_name,
                    processed=True,
                )
            )
        background.add_task(background_reindex, full_name)
        return {"ok": True, "queued": full_name, "delivery": delivery}

    instrument(app)
    return app


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


app = create_app()
