# ask-repos eval report

Generated 2026-09-06T01:49:09.770592+00:00 · provider `extractive` · corpus
14 repos, 250 files,
1625 chunks.

## Retrieval

| arm | recall@5 | MRR@10 |
|---|---:|---:|
| vector only | 0.860 | 0.696 |
| full text only | 0.512 | 0.312 |
| hybrid (RRF) | 0.837 | 0.663 |
| hybrid + reranker | 0.930 | 0.801 |

Measured over 43 golden questions whose expected citing files
were read by hand from the corpus.

## Answers

- Citation validity: **1.000**
  (169/169 citations re-resolved
  against the stored file at the stored SHA)
- Answered sentences without a citation: **0**
- Answered 43, refused 8,
  refusal errors 0

## Prompt injection

0 of 6 adversarial probes were complied
with. Probes live in `evals/injection/`; each is a repository file that instructs the reader
to ignore its instructions, reveal a secret, or assert a flattering claim.

## Gate

- none
