# 0006 — Next.js 15 App Router, and no UI framework beyond it

Status: accepted · 2026-09-06

## Context

The API answered questions with verified citations, and nothing could see it but `curl`
and an MCP client. The interface had to do three things in about thirty seconds: show a
streamed, cited answer; show what the answers are drawn from; show the measurements. It
also had to be bilingual (English and Arabic, with real right-to-left), themed, and
accessible.

Streaming is the constraint that picked the stack. `POST /v1/ask/stream` is server-sent
events, and the browser must not hold the API address or key, so something has to run on
a server between them. That is a route handler, and a framework that gives me one next to
my React pages is worth more here than any component library.

## Decision

**Next.js 15 with the App Router, React 19, TypeScript strict.** Server components render
`/corpus` and `/evals` (they are data, fetched once, per request); the chat is a client
component because it reads a stream. Route handlers under `/api/*` proxy the API.

**No UI library, no CSS framework, no CSS-in-JS.** One hand-written stylesheet
(`app/globals.css`, ~700 lines) with custom properties for colour, and logical properties
(`margin-inline`, `inset-inline-start`, `border-inline-start`) for every horizontal rule.

Language and theme live in cookies read by the root layout, so `<html lang dir data-theme>`
is correct in the first byte of HTML.

## Consequences

* **RTL costs nothing.** Switching `dir` mirrors the entire layout because there is no
  physical `left`/`right` anywhere. Asserted in `web/e2e/chat.spec.ts`, which also checks
  the document does not overflow horizontally in Arabic.
* **No flash, no client-side re-layout.** The cookie is read on the server; there is no
  `useEffect` that sets the theme after paint. The cost is that every page is dynamic —
  acceptable for a service whose content changes whenever the corpus does.
* **No dependency to keep up with.** The runtime dependency list is React, Next,
  `server-only`, and OpenTelemetry. `npm audit` reports 0 vulnerabilities at the pinned
  versions; every version is pinned exactly, no `^`.
* **Contrast is a property of four tokens, not of every component.** Measured against
  WCAG AA (4.5:1) in both themes: light `--muted` #52605b on `--bg` #f5f7f6 → 5.5:1;
  light `--accent` #0b6b53 on `--surface` #ffffff → 6.4:1 (and white on `--accent` is the
  same ratio, which is what the primary button needs); dark `--muted` #9aa8a2 on `--bg`
  #0c1211 → 7.6:1; dark `--accent` #4fd1a5 on `--bg` → 9.8:1.
* **The cost of writing it by hand** is that there is no component library to reach for
  when the next screen is more complex than a table and a form. If that day comes, this
  ADR is the one to supersede.

## Alternatives

* **Tailwind** — the create-next-app default, declined. Its `ms-`/`me-` logical utilities
  would have worked, but the whole design is four colours and eight components; a build
  step and a class vocabulary to buy that is a poor trade, and the stylesheet is smaller
  than the config would have been.
* **Vite + React SPA** — no server, so either the API key reaches the browser or a
  separate proxy has to be deployed. The framework's server *is* the feature here.
* **Server-sent events via `EventSource`** — cannot POST, so the question would have to go
  in a query string. The stream is read off `fetch` instead.
