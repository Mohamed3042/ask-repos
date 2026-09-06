# 0002 — The cite-check guardrail: anchors *and* support

Status: accepted · 2026-09-05

## Context

A retrieval-augmented answer that names a file is not evidence. Two failure modes are easy
to demonstrate and both look identical to a reader:

1. The model invents a citation — a path, a line range, or a chunk id that does not exist.
2. The model attaches a *real* citation to a sentence the cited lines do not support.

The second is the dangerous one, because everything about it looks right: the file exists,
the line range opens on GitHub, and the sentence is fluent.

## Decision

A sentence reaches the user only if **both** hold:

1. **The anchor exists.** Each citation is resolved against the database, and the stored
   file at the stored SHA is re-sliced at the claimed line span; the slice must equal the
   chunk text exactly. A chunk id that is unknown, a file whose SHA has moved, or a span
   that no longer matches is invalid.
2. **The sentence is supported.** At least 34% of the sentence's content words appear in
   the text it cites.

Sentences that fail are dropped with a reason (`no_citation`, `unknown_chunk`,
`stale_sha`, `span_mismatch`, `span_out_of_range`, `unsupported`), and the reasons are
counted in `/metrics`. If nothing survives, the answer is the refusal string — never a
softened guess.

The support threshold is lexical on purpose: it is deterministic, it needs no model, it
runs in microseconds, and it cannot itself hallucinate. An LLM judge is available in the
eval suite and is reported beside the deterministic numbers, never as a gate.

## Consequences

* Clause 2 is what makes clause 1 worth having. `tests/test_cite_check.py` shows a planted
  hallucination surviving with `min_support=0.0` and dying at the default, so the clause is
  demonstrably load-bearing rather than decorative.
* A correct paraphrase that shares few words with its source is dropped. That is a real
  cost, paid deliberately: the product's promise is receipts, and a false negative is a
  missing sentence while a false positive is a lie with a link on it.
* Because the whole file is stored at index time, verification never depends on GitHub
  being reachable.
* The extractive provider quotes verbatim, so it scores ~1.0 support by construction. The
  guardrail therefore does most of its work on the generative path — which is exactly where
  invention is possible.
