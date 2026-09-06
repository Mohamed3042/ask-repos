# 0007 — The browser never holds a secret, and the boundary is traced

Status: accepted · 2026-09-06

## Context

The UI needs the API. Two things must not happen: the browser must not learn
`ASK_REPOS_API_KEY`, and a reader must not have to take my word for that. Separately,
"observability" is a claim the project makes, and a metrics endpoint on one service is not
evidence that a request can be followed *across* two.

## Decision

Every browser request goes to a same-origin route handler under `/api/*`. The handlers are
the only code that reads `ASK_REPOS_API_URL` and `ASK_REPOS_API_KEY`, and they live behind
`lib/api.ts`, whose first line is `import "server-only"` — importing it from a client
component is a **build error**, not a code-review comment.

The same handlers attach a W3C `traceparent` to every upstream call and echo the trace id
back to the browser in `x-trace-id`.

`ASK_REPOS_CORS_ORIGINS` stays in the API for other callers (the portfolio-site widget),
but the UI does not rely on it: it is never a cross-origin caller.

## Consequences

* **The key cannot leak by refactor.** A future component that imports `getCorpus` fails
  to build. That is a stronger guarantee than "the fetch is in a server component".
* **Streaming survives the hop.** The route handler passes `Response.body` through
  untouched rather than re-chunking it; re-emitting server-sent events by hand is a
  reliable way to break them.
* **One trace covers both services.** Measured 2026-09-06: trace
  `9b182dc49461bbfe689e62cfc329fa7f`, `ask-repos-web` span `6637b33f0ec7a0f5` is the parent
  of `ask-repos` span `67a34151bd4380a7` — 18 spans, 2 services
  ([`proof/trace-ui-to-api.png`](../proof/trace-ui-to-api.png)). `web/e2e/tracing.spec.ts`
  asserts the parent relation and then takes the screenshot.
* **Tracing is off unless an endpoint is configured**, but `traceparent` is sent anyway,
  with a freshly generated id when there is no active span. A request is always
  correlatable in the API's logs; nothing silently drops the header.
* **Two exporter traps were paid for on the way**, both of the same shape — configured,
  silent, exporting nothing:
  1. The API instrumented FastAPI inside `lifespan`, after Starlette had built its
     middleware stack, and swallowed the failure with a bare `except`. Every `ask-repos`
     trace in Jaeger held one root span and no server span, so the UI's context had
     nothing to attach to. Instrumentation now happens in `create_app()` and logs a
     warning when it cannot.
  2. `OTEL_EXPORTER_OTLP_ENDPOINT` is conventionally a *base* URL; the Python exporter
     wants the full `/v1/traces` path and a POST to the base is a 404 the batch processor
     swallows. Both services now normalise it.
* **The extra hop costs latency.** Measured from Kuwait to the Netlify edge: ~1.0–1.2 s
  for a server-rendered page. Acceptable for a demo; a chat UI that needed 100 ms would
  put the key in a session instead.
