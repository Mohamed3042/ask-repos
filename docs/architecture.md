# Architecture

`ask-repos` turns a GitHub account's public repositories into a corpus that can be
questioned, and refuses to say anything it cannot anchor to file lines it has stored and
re-verified.

## C4 level 1 — context

```mermaid
flowchart LR
    R["Recruiter, teammate,<br/>or the author"]:::person
    A["MCP client<br/>(Claude Desktop / Claude Code)"]:::person
    W["ask-repos web<br/>chat · corpus · evals"]:::system
    S["ask-repos API<br/>answers with citations, or refuses"]:::system
    G["GitHub REST API<br/>public repositories"]:::ext
    L["Google Generative Language API<br/>(optional wording)"]:::ext

    R -->|"opens the site"| W
    W -->|"HTTP / SSE, server-side only,<br/>W3C traceparent forwarded"| S
    A -->|"MCP: search / answer / get_file_span"| S
    S -->|"reads trees and blobs;<br/>receives push webhooks"| G
    S -.->|"only when GEMINI_API_KEY is set"| L
    W -->|"sentences + citation chips<br/>linking to the exact GitHub lines"| R

    classDef person fill:#1f6f5c,stroke:#0d3b31,color:#fff
    classDef system fill:#14425c,stroke:#08222f,color:#fff
    classDef ext fill:#4a4a4a,stroke:#222,color:#fff
```

The browser never talks to the API. Every request it makes goes to a Next.js route handler
on the same origin, which calls the API from the server — so the API address and any key
stay out of the page (ADR 0007).

## C4 level 1 — where it actually runs

```mermaid
flowchart TB
    subgraph netlify["Netlify — ask-repos-live.netlify.app"]
        NX["Next.js 15 App Router<br/>server components + /api/* route handlers"]
    end
    subgraph hf["Hugging Face Space — medo4334-ask-repos.hf.space"]
        DOCK["one Docker container<br/>ghcr.io/mohamed3042/ask-repos + PostgreSQL 16 + pgvector"]
        PGD[("PGDATA built at image-build time<br/>14 repos · 250 files · 1,625 chunks")]
        DOCK --- PGD
    end
    subgraph gha["GitHub Actions"]
        CI["ci · web · evals gate"]
        UP["uptime: hourly curl of both URLs<br/>→ docs/proof/uptime.json → badge"]
    end

    NX -->|"HTTPS, traceparent"| DOCK
    UP -.->|"GET /"| NX
    UP -.->|"GET /health"| DOCK
    CI -->|"publishes"| DOCK

    classDef x fill:#14425c,stroke:#08222f,color:#fff
```

The Space is **read-only**: `POST /v1/index`, the push webhook and *approving* an
agent-requested re-index all answer 403, and `/v1/ask*` is rate limited. The corpus is a
fixed snapshot baked into the image, which is why it needs no attached database and no
first-boot indexing (ADR 0008).

Without a Gemini key the dotted edge simply does not exist: the service still indexes,
searches, answers extractively, serves MCP and runs its whole eval suite.

## C4 level 2 — containers

```mermaid
flowchart TB
    subgraph client["Clients"]
        UI["HTTP / SSE"]
        MC["MCP stdio or streamable HTTP"]
        CL["ask-repos CLI"]
    end

    subgraph svc["ask-repos service (one Python process)"]
        API["FastAPI<br/>/v1/ask · /v1/search · /v1/corpus<br/>/v1/index · /webhooks/github"]
        MCP["MCP server<br/>4 read-only tools"]
        AG["LangGraph agent<br/>plan → retrieve → expand → draft → cite_check → answer"]
        RET["Retrieval<br/>pgvector cosine + tsvector rank → RRF → cross-encoder"]
        ING["Ingestion<br/>tree walk → filters → chunkers → embeddings"]
        EMB["fastembed (ONNX, CPU)<br/>bge-small-en-v1.5 · ms-marco-MiniLM-L-6-v2"]
    end

    DB[("PostgreSQL 16 + pgvector<br/>repos · files · chunks · index_runs · webhook_deliveries")]
    GH["GitHub REST API"]
    GEM["Gemini (optional)"]

    UI --> API
    MC --> MCP
    CL --> ING
    CL --> AG
    API --> AG
    MCP --> AG
    MCP --> RET
    AG --> RET
    RET --> EMB
    RET --> DB
    ING --> EMB
    ING --> DB
    ING --> GH
    API --> ING
    AG -.-> GEM
```

## Data flow — one index run

```mermaid
sequenceDiagram
    participant C as CLI / webhook / API
    participant P as Ingestion
    participant G as GitHub
    participant E as fastembed
    participant D as PostgreSQL

    C->>P: index --owner <account>
    P->>G: GET /users/{owner}/repos  (public, non-fork, non-archived only)
    loop each repository
        P->>G: GET /git/trees/{branch}?recursive=1  (ETag)
        alt tree SHA unchanged
            P-->>D: nothing written
        else changed
            P->>P: select paths, drop vendored / lockfiles / binaries / >200 KB
            loop batches of 32 files
                P->>G: GET /git/blobs/{sha}  (8 concurrent)
                P->>P: chunk by heading or definition, whole lines only
                P->>E: embed(chunk texts)
                P->>D: INSERT files + chunks (+ generated tsvector)
                P-->>D: COMMIT
            end
            P->>D: UPDATE repo tree_sha, last_indexed_at
        end
    end
    P->>D: index_runs row: counts, seconds, status
```

A file whose blob SHA has not moved is never re-fetched, re-chunked or re-embedded, so a
re-index over an unchanged account writes zero chunks. That is asserted in
`tests/test_pipeline.py::test_reindex_of_an_unchanged_account_writes_nothing`.

## Data flow — one question

```mermaid
sequenceDiagram
    participant U as Caller
    participant A as Agent
    participant R as Retrieval
    participant M as Provider (Gemini or extractive)
    participant V as cite_check
    participant D as PostgreSQL

    U->>A: question
    A->>R: hybrid search (k)
    R->>D: pgvector cosine  +  websearch_to_tsquery rank
    R->>R: reciprocal rank fusion → cross-encoder rerank
    A->>D: neighbouring chunks of the best hits (still citable)
    A->>M: question + numbered chunks, marked untrusted
    M-->>A: [{text, citations:[chunk_id]}]
    A->>V: verify every sentence
    V->>D: resolve chunk → file → re-slice lines at that SHA
    V-->>A: kept sentences, dropped ones with reasons
    alt nothing survives
        A-->>U: "Not in the corpus."
    else
        A-->>U: sentences + owner/repo/path#Lx-Ly@sha + GitHub links
    end
```

## Data flow — one question, from the browser

```mermaid
sequenceDiagram
    participant B as Browser
    participant N as Next route handler (/api/ask)
    participant S as ask-repos API
    participant J as Jaeger

    B->>N: POST {question}
    N->>N: start a span; build `traceparent`
    N->>S: POST /v1/ask/stream  (traceparent: 00-<trace>-<span>-01)
    S->>S: server span joins the caller's trace
    S-->>N: text/event-stream: one `sentence` per verified sentence, then `done`
    N-->>B: the same byte stream, plus `x-trace-id`
    B->>B: render each sentence with its citation chips
    N-->>J: ask-repos-web spans
    S-->>J: ask-repos spans, parented to the route handler's
```

Measured on 2026-09-06 with the Compose tracing profile: trace
`9b182dc49461bbfe689e62cfc329fa7f`, `ask-repos-web` span `6637b33f0ec7a0f5`
(*executing api route (app) /api/ask/route*) is the parent of `ask-repos` span
`67a34151bd4380a7` (*POST /v1/ask/stream*) — 18 spans, 2 services, depth 4
([`proof/trace-ui-to-api.png`](proof/trace-ui-to-api.png)). The assertion is in
`web/e2e/tracing.spec.ts`; the picture is taken by the same test that makes the claim.

## Trust boundaries

| boundary | what crosses it | how it is controlled |
|---|---|---|
| GitHub → ingestion | repository text | Only public, non-fork, non-archived repositories; size, path and binary filters; text is stored as **data**, never executed or interpreted |
| corpus → model prompt | retrieved chunks | The system prompt declares the context untrusted; the red-team evals in `evals/injection/` prove an instruction inside a file does not become an instruction to the service |
| model → user | drafted sentences | `cite_check` re-resolves every citation against the database and drops unsupported sentences; the model cannot introduce a claim the corpus does not carry |
| caller → corpus (write) | index runs | `POST /v1/index` needs an API key; the webhook needs a valid HMAC signature and a fresh delivery id; the agent's own `reindex` tool needs a human approval (ADR 0003) |
| browser → route handler | the question | Same-origin; the handler validates length and shape, and is the only place that knows `ASK_REPOS_API_URL` / `ASK_REPOS_API_KEY` (`server-only` makes importing it from a client component a build error) |
| hosted demo → corpus | nothing | `ASK_REPOS_READONLY=1` refuses every write with a reason, and a fixed-window limiter caps `/v1/ask*` and `/v1/search`. `/health` and `/v1/corpus` are never throttled so an uptime probe costs a visitor nothing |
| caller → corpus (read) | search and answers | Public by design — everything indexed is already public on GitHub. Private repositories are refused twice: once in the listing filter, once in the pipeline (`PrivateRepoRefused`) |

## What is not here

* No authentication for read routes. The corpus is public data; adding auth would imply a
  privacy property the service does not have.
* No cross-process checkpointer, so an approval thread does not survive a restart.
* No incremental vector index maintenance beyond what pgvector's HNSW does on insert.
* No shared rate-limit state. The limiter is per-container and per-process — honest for a
  one-instance demo, wrong for anything horizontally scaled.
* No authentication on the UI. It is a public demo of public data.
* The hosted corpus is frozen at build time, so the Space cannot follow the repositories;
  the push webhook that would is documented, tested and disabled there on purpose.
