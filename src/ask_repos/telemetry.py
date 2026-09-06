"""OpenTelemetry tracing and Prometheus metrics.

Off by default (`ASK_REPOS_OTEL_EXPORTER=none`), console in development, OTLP/HTTP when
an endpoint is configured. Nothing here is required for the service to answer a question;
it is the observability surface a reviewer asks about.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from ask_repos import __version__
from ask_repos.config import get_settings

REGISTRY = CollectorRegistry()

ASK_REQUESTS = Counter(
    "ask_repos_ask_total", "Answers produced, by outcome", ["outcome"], registry=REGISTRY
)
ASK_LATENCY = Histogram(
    "ask_repos_ask_seconds", "End-to-end latency of /v1/ask", registry=REGISTRY
)
SEARCH_LATENCY = Histogram(
    "ask_repos_search_seconds", "Retrieval latency", ["mode"], registry=REGISTRY
)
SENTENCES_DROPPED = Counter(
    "ask_repos_sentences_dropped_total",
    "Sentences removed by the cite-check guardrail, by reason",
    ["reason"],
    registry=REGISTRY,
)
INDEX_CHUNKS = Counter(
    "ask_repos_index_chunks_total", "Chunks written by index runs", registry=REGISTRY
)

_configured = False


def setup_telemetry(service_name: str = "ask-repos") -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    exporter_kind = (settings.otel_exporter or "none").lower()
    if exporter_kind == "none":
        _configured = True
        return
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name, "service.version": __version__})
    )
    if exporter_kind == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        # `OTEL_EXPORTER_OTLP_ENDPOINT` is conventionally the *base* URL, and this
        # exporter wants the full traces path. Posting to the base gives a 404 that the
        # batch processor swallows: tracing looks configured and no span ever arrives.
        endpoint = (settings.otel_endpoint or "http://localhost:4318").rstrip("/")
        if not endpoint.endswith("/v1/traces"):
            endpoint = f"{endpoint}/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True


def tracer() -> trace.Tracer:
    return trace.get_tracer("ask_repos")


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    with tracer().start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def metrics_payload() -> bytes:
    return generate_latest(REGISTRY)
