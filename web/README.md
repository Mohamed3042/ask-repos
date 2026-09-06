# ask-repos web

The interface for [`ask-repos`](../README.md): a streaming chat whose citation chips open
the exact GitHub lines, a corpus page, and an evals page. Next.js 15 App Router, React 19,
TypeScript strict, and no UI framework — see
[ADR 0006](../docs/adr/0006-nextjs-app-router.md).

```bash
npm ci
cp .env.example .env.local        # defaults already point at http://localhost:8080
npm run dev                       # http://localhost:3000
```

The API has to be running: `docker compose up -d db api` from the repository root.

## Scripts

| | |
|---|---|
| `npm run dev` / `build` / `start` | the usual |
| `npm run lint` · `typecheck` | ESLint, `tsc --noEmit` |
| `npm test` | vitest — the citation parser and the trace context |
| `npm run e2e` | Playwright against a **real** API; `E2E_BASE_URL` points it at a deployed one. Includes `a11y.spec.ts`, which runs axe-core over every page in both themes, in Arabic, and over the answered and refused states |
| `npm run prove:gates` | sabotages `blobUrl` on a copy and requires the suite to go red, then green |
| `npm run prove:gates:e2e` | the same for the browser assertion |
| `npm run sync:evals` / `check:evals` | copy the eval report CI gates on into `data/`, or verify the committed copy still matches |
| `npm run check:lock` | asserts the lock file still carries the Linux-only optional packages `npm ci` needs |
| `npm run shots` | regenerate every screenshot in the documentation (`SHOTS=1`) |
| `npm run demo:record` + `demo:gif` | re-record `docs/proof/demo.gif` |

## Where the boundary is

`lib/api.ts` is the only module that knows `ASK_REPOS_API_URL` and `ASK_REPOS_API_KEY`, and
its first line is `import "server-only"` — importing it from a client component is a build
error. Everything the browser calls is a route handler under `app/api/`.

## The lock file is generated on Linux

`package-lock.json` must be regenerated in a Linux container, not on Windows. npm records
only the optional platform packages it resolved, so a lock produced on Windows is missing
`@emnapi/core` and `@emnapi/runtime` (Linux-only optional dependencies of `sharp`, which
Next pulls in), and `npm ci` on an Ubuntu runner then fails with
`can only install packages when your package.json and package-lock.json ... are in sync`.

```bash
docker run --rm -v "$PWD:/app" -w /app node:22-slim npm install --package-lock-only
```

On Git Bash prefix that with `MSYS_NO_PATHCONV=1`, or `/app` is rewritten to
`C:/Program Files/Git/app`.
