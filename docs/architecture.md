# Architecture

`ask-repos` turns a GitHub account's public repositories into a corpus that can be
questioned, and refuses to say anything it cannot anchor to file lines it has stored and
re-verified.

## C4 level 1 — context

```mermaid
flowchart LR
    R["Recruiter, teammate,<br/>or the author"]:::person
    A["MCP client<br/>(Claude Desktop / Claude Code)"]:::person
    S["ask-repos<br/>answers with citations, or refuses"]:::system
    G["GitHub REST API<br/>public repositories"]:::ext
    L["Google Generative Language API<br/>(optional wording)"]:::ext

    R -->|"HTTP: asks a question"| S
    A -->|"MCP: search / answer / get_file_span"| S
    S -->|"reads trees and blobs;<br/>receives push webhooks"| G
    S -.->|"only when GEMINI_API_KEY is set"| L
    S -->|"answer + owner/repo/path#Lx-Ly@sha"| R

    classDef person fill:#1f6f5c,stroke:#0d3b31,color:#fff
    classDef system fill:#14425c,stroke:#08222f,color:#fff
    classDef ext fill:#4a4a4a,stroke:#222,color:#fff
```

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

## Trust boundaries

| boundary | what crosses it | how it is controlled |
|---|---|---|
| GitHub → ingestion | repository text | Only public, non-fork, non-archived repositories; size, path and binary filters; text is stored as **data**, never executed or interpreted |
| corpus → model prompt | retrieved chunks | The system prompt declares the context untrusted; the red-team evals in `evals/injection/` prove an instruction inside a file does not become an instruction to the service |
| model → user | drafted sentences | `cite_check` re-resolves every citation against the database and drops unsupported sentences; the model cannot introduce a claim the corpus does not carry |
| caller → corpus (write) | index runs | `POST /v1/index` needs an API key; the webhook needs a valid HMAC signature and a fresh delivery id; the agent's own `reindex` tool needs a human approval (ADR 0003) |
| caller → corpus (read) | search and answers | Public by design — everything indexed is already public on GitHub. Private repositories are refused twice: once in the listing filter, once in the pipeline (`PrivateRepoRefused`) |

## What is not here

* No authentication for read routes. The corpus is public data; adding auth would imply a
  privacy property the service does not have.
* No cross-process checkpointer, so an approval thread does not survive a restart.
* No incremental vector index maintenance beyond what pgvector's HNSW does on insert.
* No UI. That is the next lane (`gaps-ask-repos-ui`); the CORS allowlist is already
  configurable for it via `ASK_REPOS_CORS_ORIGINS`.
