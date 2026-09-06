# ask-repos eval report

Generated 2026-09-06T01:35:43.772096+00:00 · provider `extractive` · corpus
16 repos, 517 files,
6018 chunks.

## Retrieval

| arm | recall@5 | MRR@10 |
|---|---:|---:|
| vector only | 0.804 | 0.635 |
| full text only | 0.348 | 0.200 |
| hybrid (RRF) | 0.848 | 0.638 |
| hybrid + reranker | 0.891 | 0.749 |

Measured over 46 golden questions whose expected citing files
were read by hand from the corpus.

## Answers

- Citation validity: **1.000**
  (177/177 citations re-resolved
  against the stored file at the stored SHA)
- Answered sentences without a citation: **0**
- Answered 46, refused 8,
  refusal errors 0

## Prompt injection

0 of 6 adversarial probes were complied
with. Probes live in `evals/injection/`; each is a repository file that instructs the reader
to ignore its instructions, reveal a secret, or assert a flattering claim.

## Gate

- none
