# 0009 — Netlify for the UI, and a self-measured uptime badge

Status: accepted · 2026-09-06

## Context

The UI needs a stable public URL with a Node runtime — the route handlers are the security
boundary (ADR 0007), so a static host is not an option. Two candidates were already on the
machine. `vercel`'s stored token was measured invalid on 2026-09-05 (*"The specified token
is not valid"*), and `netlify status` reported an authenticated session on the owner's
team. That decided it without spending one of the owner's steps.

Separately, "a live service" is a claim, and a green deploy badge only proves the minute
the deploy ran.

## Decision

**Netlify**, site `ask-repos-live`, at <https://ask-repos-live.netlify.app>, built with
`@netlify/plugin-nextjs` from `web/`. `ASK_REPOS_API_URL` is a site environment variable
pointing at the Space; no key is set, because the Space is read-only and needs none.

Deploys run from CI on pushes that touch `web/` or `netlify.toml`
(`.github/workflows/deploy-web.yml`), with `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` as
repository secrets, and the job **measures the live URL afterwards** — three pages must
answer 200 or the job fails.

An hourly workflow curls the UI and the API, appends a sample to
`docs/proof/uptime.json`, and regenerates a shields.io endpoint document. The badge label
is `self-measured uptime since <date>`.

## Consequences

* **The badge cannot overstate.** The label says self-measured; the samples it is computed
  from are committed beside it, so anyone can recompute the number. One prober, one region,
  hourly — that is written into the file's `method` field.
* **Unknown is not downtime.** A run where the prober itself could not reach the network
  records `null` and is counted separately (`unreachable_prober`), not as a failure.
* **"since" is the first sample actually recorded**, not the day the project started, so
  the window never claims history it does not have.
* **Vercel stays available** as the alternative the owner can switch to with
  `vercel login`; nothing in the app is Netlify-specific except `netlify.toml`.
* **A dead API is visible, not hidden.** Until the Space is published, the UI's own error
  state says the API is unreachable and the uptime record shows the API at 0% while the UI
  is at 100%. That is the correct reading of the situation, and it is what the first
  recorded sample says.
* **The free tier adds a "Powered by Netlify" badge** to the page. It is in the
  screenshots and is not worth a paid plan to remove.
