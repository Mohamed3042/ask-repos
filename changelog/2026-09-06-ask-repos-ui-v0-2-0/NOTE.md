# ask-repos v0.2.0 - a face a recruiter can use in thirty seconds, and both halves live

**What:** `ask-repos` could already answer questions about a GitHub account's public
repositories with anchors of the form `owner/repo/path#Lstart-Lend@sha`, and nothing could
see it but `curl`. This release adds `web/` - a Next.js 15 interface where the answer
arrives sentence by sentence as each one clears citation checking, each with a chip like
`petpoint-ops-hub/README.md L9-L37` that opens those exact lines on GitHub - and puts both
halves on a URL: the API as a read-only Hugging Face Docker Space, the interface on
Netlify. There is also a corpus page that shows what the answers are drawn from and turns
"re-index" into a human-approval interrupt instead of an action, and an evals page that
renders the committed CI report, unflattering numbers included. English and Arabic with
real right-to-left, light and dark, no UI framework.

- Interface: **https://ask-repos-live.netlify.app**
- API: **https://medo4334-ask-repos.hf.space** (read-only, 12 requests/minute)

**Proof:**

- **The chip's link is rebuilt, not copied.** `blobUrl()` constructs the GitHub URL from
  the citation's repository, path, stored SHA and line span; a unit test asserts it equals
  the URL the API returned for every citation in a recorded response, and a Playwright test
  asserts the same against the live stream the browser actually received. Sabotaging
  `blobUrl` to use the short SHA turns both red: `4 failed` in `citations.test.ts`, and
  `expect(received).toBe(expected)` in the browser
  (`web/scripts/prove-fails-first.mjs`, both gates shown RED then GREEN).
- **One trace, two services.** Trace `9b182dc49461bbfe689e62cfc329fa7f`: `ask-repos-web`
  span `6637b33f0ec7a0f5` (*executing api route /api/ask/route*) is the parent of
  `ask-repos` span `67a34151bd4380a7` (*POST /v1/ask/stream*) - 18 spans, 2 services,
  depth 4. Asserted in `web/e2e/tracing.spec.ts`, which takes the screenshot itself.
- **The hosted API is read-only, measured on the built image:** `POST /v1/index` 403,
  `POST /webhooks/github` 403, approving a re-index 403, declining it 200, and the
  fixed-window limiter allowing 12 requests then answering 429 while `/health` stays open.
  It boots with `14 repos | 250 files | 1625 chunks` already in PostgreSQL - the data
  directory is built into the image, so there is no first-boot indexing (the cold index of
  this account measured 3,244.6 s).
- **Live:** `/`, `/corpus` and `/evals` all answer **HTTP 200** from
  ask-repos-live.netlify.app.
- **Tests:** 149 pytest (117 before), 24 vitest, 14 Playwright specs against a real API
  with no mocked routes. CI runs the browser journey keyless, because a flaky e2e is a
  deleted e2e.
- **Three v0.1.0 defects this lane surfaced,** each measured before it was fixed:
  an interrupted `POST /v1/ask` answered **500**; `FastAPIInstrumentor` ran too late to
  install its middleware and swallowed the failure, so every `ask-repos` trace held one
  root span and no server span; and `deploy/entrypoint.sh` under `core.autocrlf=true`
  produced an image that exits 255 with `exec .../entrypoint.sh: no such file or directory`.

**Boundary:** The hosted demo answers from a corpus frozen at image-build time, so it
cannot follow the repositories - the push webhook that would is documented, tested and
disabled there. Its rate limiter is in-process and per container: right for one instance,
wrong for several. Uptime is **self-measured** - one prober, one region, hourly, with the
samples committed beside the badge - not a monitoring service. The retrieval and citation
numbers on `/evals` describe the 14-repository CI subset, which is exactly what the Space
serves. Read routes are unauthenticated by design; everything indexed is already public.

**Shots:**

- `01-ask-cited.png` - the interface answering, with every citation chip outlined; each one
  opens the exact GitHub lines the sentence was verified against.
- `02-corpus-interrupt.png` - "Request a re-index" outlined, stopped at *A human has to
  approve this* with Approve and Decline, instead of re-indexing.
- `03-trace-two-services.png` - Jaeger, one trace, `Services 2 / Depth 4` outlined, and the
  `ask-repos-web` span with the `ask-repos` span nested under it.
- `04-live-evals.png` - the evals page on the live Netlify URL: citation validity 100.0 %
  (169/169), 0 uncited sentences, 0 of 6 injection probes obeyed, and full-text retrieval
  at 0.512 shown next to the reranked 0.930.

**LinkedIn paste:**

ask-repos now has a face, and both halves are live. Ask it about a GitHub account's public
repositories and the answer arrives sentence by sentence - each one only after the service
has re-opened the file it cites at the stored commit and confirmed those exact lines are
still there. Every sentence carries a chip like `petpoint-ops-hub/README.md L9-L37` that
opens the lines on GitHub, and the link is rebuilt from the citation rather than copied, so
a test can prove the two agree. Ask it something the corpus does not contain and it refuses
instead of guessing.

The interface is Next.js 15 with no UI framework, English and Arabic with real
right-to-left, and the browser never holds a secret: every request goes through a
same-origin route handler, and the module that knows the API key is `server-only`, so
importing it into the browser is a build error rather than a code-review comment. Those
handlers forward a W3C traceparent, so one Jaeger trace covers the route handler and the
FastAPI request underneath it - 18 spans across two services.

The API runs as a read-only Hugging Face Space with PostgreSQL and pgvector inside the
image and the corpus baked in at build time, so it boots in seconds instead of indexing for
an hour, and everything that writes answers 403 with a reason. The evals page shows the
numbers CI gates on, including the unflattering one: full-text retrieval alone is 0.512
recall@5 next to 0.930 for the reranked hybrid.

Interface: https://ask-repos-live.netlify.app
Code: https://github.com/Mohamed3042/ask-repos

**Surfaces:** [ ]pdf [ ]resume [ ]web [ ]li
