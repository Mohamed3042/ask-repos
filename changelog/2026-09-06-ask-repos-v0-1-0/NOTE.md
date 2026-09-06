# ask-repos - a question-answering service over public GitHub repositories that refuses rather than guesses

**What:** New public repository. Point `ask-repos` at any GitHub account and it indexes that
account's public repositories, then answers questions about them with anchors of the form
`owner/repo/path#Lstart-Lend@sha`. Before a sentence is returned the service re-opens the
stored file at that commit and checks those exact lines are still there; a sentence it cannot
anchor is dropped, and when nothing survives it answers "Not in the corpus." The whole thing
runs with no API key: local ONNX embeddings and reranking, PostgreSQL + pgvector, an
extractive answerer. Gemini is optional and only changes the wording.

**Proof:**

- Corpus indexed from live GitHub: **16 public repositories, 517 files, 6,018 chunks,
  6,425,129 bytes in 3,244.6 s**. Re-indexing with nothing changed: **12.9 s, 18 GitHub
  requests, 0 chunks written**.
- Retrieval measured on a 54-question golden set authored by reading the corpus —
  vector only 0.804, full text only 0.348, hybrid 0.848, **hybrid + reranker 0.891**
  recall@5 (`docs/retrieval.md`).
- **Citation validity 1.000** (177/177 citations re-resolved against the stored file at the
  stored SHA), 0 answered sentences without a citation, 0 refusal errors,
  **0 of 6 prompt-injection probes complied with**.
- The gate is shown RED first: `docs/proof/evals-gate-fail-first.txt` fires it three ways and
  shows the guardrail refusing a lying provider on the real corpus
  (`dropped by cite-check: {'unsupported': 1}`).
- 117 tests green, ruff clean, CI green on GitHub Actions including a live Gemini job.
- Verified from a clean clone in a temp directory: `./scripts/verify.sh` indexed 25 files
  into 200 chunks in 70.0 s and answered with a citation whose GitHub URL opens the lines.

**Boundary:** Public repositories only, text files only, nothing over 200 KB. Answers are
limited to what was indexed, and a repository that has moved since is answered from the
stored copy at the stored SHA — the citation says which. The refusal mechanism on the
keyless path is a lexical relevance floor, which is blunt in a predictable direction; the
golden set's 0 refusal errors is a measurement on that set, not a general claim. No UI yet.

**Shots:**

- `01-swagger-ask-cited.png` — the containerised API answering `POST /v1/ask` with the
  citation and GitHub URL highlighted.
- `02-refusal.png` — the same endpoint refusing a question the corpus cannot answer.
- `03-evals-gate.png` — the eval gate fired three ways and the guardrail dropping a planted
  hallucination.

**LinkedIn paste:**

I built ask-repos: point it at any GitHub account and it answers questions about that
account's public repositories with receipts — every sentence anchored to
`owner/repo/path#L10-L24@sha`, verified against the stored file at that commit before it is
returned. Anything it cannot anchor is dropped, and when nothing survives it says "not in
the corpus" instead of guessing. Hybrid retrieval (pgvector + Postgres full text, fused and
reranked) measured at 0.891 recall@5 on a hand-authored golden set, citation validity gated
at 100% in CI, and 0 of 6 prompt-injection probes obeyed. It runs with no API key at all —
local ONNX embeddings, an extractive answerer, Docker Compose, and an MCP server so Claude
Desktop or Claude Code can query the same corpus.

**Surfaces:** [ ] showcase-pdf [ ] resume [ ] website [ ] linkedin
