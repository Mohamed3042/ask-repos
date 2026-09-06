# Retrieval, measured

Every number here comes from `ask-repos evals run` against the frozen corpus in
`evals/corpus/` — **16 public repositories, 517 files, 6,018 chunks, 6,425,129 bytes** —
using the golden set in `evals/golden.yaml` (46 questions whose expected citing files were
read by hand, plus 8 the corpus cannot answer).

Reproduce it:

```bash
docker compose up -d db
ask-repos migrate
ask-repos evals load --source evals/corpus     # offline; no GitHub, no key
ask-repos evals run --min-citation-validity 1.0 --min-recall5 0.85
```

## The four arms

| arm | recall@5 | MRR@10 |
|---|---:|---:|
| vector only (pgvector cosine, `bge-small-en-v1.5`) | 0.804 | 0.635 |
| full text only (`tsvector` + `ts_rank_cd`) | 0.348 | 0.197 |
| hybrid (reciprocal rank fusion of both) | 0.848 | 0.638 |
| **hybrid + cross-encoder reranker** | **0.891** | **0.749** |

Measured 2026-09-06 · report: `evals/reports/report.json`.

Read honestly:

* **Fusion earns its place, but only just.** Hybrid beats vector-only by 4.4 points of
  recall@5 (0.848 vs 0.804) and is within noise on MRR. On a corpus of this size, with
  questions phrased in natural language, the dense arm is doing most of the work.
* **Reranking is the biggest single win.** +4.3 points of recall@5 and +11 points of MRR
  over the fused list. It is also the slowest stage — a cross-encoder pass over 30
  candidates — and the one that can be switched off (`ASK_REPOS_RERANK=0`) if latency
  matters more than ordering.
* **The full-text arm is weak on its own, and that is expected.** 0.348 recall@5 for
  questions like "How does the pet retail hub turn repeat pet-food orders into reminders?"
  is what lexical matching gives you when the question and the file share few exact words.
  It still contributes: it is the arm that finds identifiers and exact tokens the embedding
  blurs, which is why fusion beats the dense arm at all.

## Two defects this table found

Both were invisible until the arms were measured separately.

**1. `websearch_to_tsquery` ANDs a whole question.** The first measurement of the full-text
arm was **recall@5 0.152** — worse than guessing among 30 candidates. The cause was not the
index: passing a whole sentence to `websearch_to_tsquery` requires *every* word of it to
appear in one chunk. Content words joined with `OR` fixed the query, and length-normalised
ranking (`ts_rank_cd(..., 2)`) fixed what the OR query then broke — without normalisation
the longest generated files rank first because they contain more of every word:

| full-text arm | recall@5 |
|---|---:|
| whole question, AND semantics, no normalisation (original) | 0.152 |
| content words OR-ed, no normalisation | 0.130 |
| content words OR-ed, length-normalised (shipped) | **0.348** |

The middle row is the point: the obvious half of the fix made things *worse*, and only the
measurement said so. Fusion followed the same curve — hybrid read 0.826, then 0.630 with
the unnormalised OR query, then 0.848 once normalised.

**2. A substring is not a word.** The relevance floor and the cite-check support clause both
asked "does this word appear in that text?" with a substring test. `author` therefore
matched `authoritative` and `authored`; `size` matched `font-size`. The question *"What is
the author's shoe size?"* scored 0.67 against a stylesheet and was answered from it.
Whole-word matching with a two-character tolerance for inflections
(`cite_check.word_matches`) fixed it; `tests/test_providers.py` keeps it fixed.

## Answers, refusals and the red team

| metric | value |
|---|---|
| citation validity | **1.000** (177 / 177 citations re-resolved against the stored file at the stored SHA) |
| answered sentences with no citation | **0** |
| answered / refused | 46 / 8 |
| refusal errors (extractive) | **0** (every question the corpus cannot answer was refused, and every one it can answer was answered) |
| prompt-injection probes complied with | **0 of 6** extractive · **0 of 6** Gemini |

Citation validity is a gate at 1.000, not a score to improve: a single citation that cannot
be re-resolved fails the build.

### What the refusal number does *not* mean

The refusal set was rewritten once, and the reason matters. The first draft asked about
salary, university and notice period, assuming a corpus of code could not answer them. It
could: `flagship-portfolio/public/cv-intake/app.js` is a CV intake form with fields for
exactly those things, and the service quoted it with a valid citation. That was correct
behaviour and a wrong golden set, so the questions were replaced with ones checked against
the corpus first (certifications, allergies, blood type, commute, performance review,
medication, football team, car).

The refusal mechanism on the extractive path is a **lexical relevance floor**: a chunk is
quoted only when it shares at least 40% of the question's content words. That is blunt in a
predictable direction — a question that reuses common corpus vocabulary can still be
answered with a quotation even when it is not really about the corpus. The 0 refusal errors
above are measured on this golden set, not a general claim about every possible question.

## What CI actually gates on

Indexing all 6,018 chunks takes **3,244.6 s** on a busy 16-core desktop and considerably
longer on a 2-vCPU GitHub runner — the first attempt was still inside the load step after 40
minutes. The gate therefore runs on **14 of the 16 repositories**: `flagship-portfolio` and
`Flagship-One-Page` are 73% of the corpus by chunk count and between them carry 3 of the 46
answerable questions. Questions whose evidence is not indexed are **skipped and counted**
(`answers.skipped_not_indexed` in the report), never scored as misses.

| | full corpus | CI subset |
|---|---:|---:|
| repositories | 16 | 14 |
| files | 517 | 250 |
| chunks | 6,018 | 1,625 |
| index time (same machine) | 3,244.6 s | 649.7 s |
| answerable questions measured | 46 | 43 |
| vector only, recall@5 | 0.804 | 0.860 |
| full text only, recall@5 | 0.348 | 0.512 |
| hybrid, recall@5 | 0.848 | 0.837 |
| **hybrid + reranker, recall@5** | **0.891** | **0.930** |
| citation validity | 1.000 (177/177) | 1.000 (169/169) |
| CI floor | — | **0.90** |

Two things in that table are worth saying out loud. Retrieval is *easier* on the smaller
corpus — fewer near-duplicate portfolio pages to confuse the ranking — so the CI number is
not a stand-in for the full-corpus number, and both are reported rather than one. And on the
subset the fused hybrid (0.837) sits **below** vector-only (0.860): with 14 repositories the
full-text arm pulls the fusion down, and only the reranker recovers it (0.930). Reciprocal
rank fusion is not free; it is a bet that two weak orderings disagree usefully, and on this
corpus that bet pays off only after reranking.

Reproduce either one:

```bash
ask-repos evals load --source evals/corpus                                     # full
ask-repos evals load --source evals/corpus --exclude flagship-portfolio,Flagship-One-Page
```

## Cost

Indexing is CPU-bound and the honest number is not flattering:

| stage | measurement |
|---|---|
| cold index, 16 repositories, 517 files, 6,018 chunks | **3,244.6 s** (54 minutes) |
| embedding throughput during that run | ~3.8 chunks/second |
| machine | 16-core desktop, three other builds running concurrently |
| re-index of an unchanged account | **12.9 s**, 18 GitHub requests, **0 chunks written** |

The last row is the one that matters in operation: incremental re-indexing compares tree
SHAs per repository and blob SHAs per file, so nothing is re-fetched, re-chunked or
re-embedded unless it actually changed.
