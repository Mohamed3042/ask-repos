"""Show the evals gate RED before showing it green.

A gate that cannot be made to fire is decoration, so this script fires it three ways on the
real report, and then fires the guardrail itself on the real corpus with a lying provider.

    python scripts/prove_gate_fails_first.py

Its output is `docs/proof/evals-gate-fail-first.txt`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ask_repos.agent.graph import ask
from ask_repos.agent.providers import Draft
from ask_repos.db.session import session_scope
from ask_repos.evals.runner import EvalReport

REPORT = Path("evals/reports/report.json")
FLOOR_VALIDITY = 1.0
FLOOR_RECALL = 0.85


def report_from(payload: dict) -> EvalReport:
    return EvalReport(
        corpus=payload["corpus"],
        retrieval=payload["retrieval"],
        answers=payload["answers"],
        injection=payload["injection"],
        questions=[],
        provider=payload["provider"],
    )


class Liar:
    """A provider that invents a claim and attaches a real citation to it."""

    name = "liar"

    def draft(self, question, hits):
        return Draft(
            sentences=[
                {
                    "text": "The author has ten years of production experience at a "
                    "Fortune 500 bank and holds an AWS Solutions Architect certification.",
                    "citations": [hits[0].chunk_id] if hits else [],
                }
            ],
            provider=self.name,
        )


def main() -> int:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))

    print("== the gate on the real report ==")
    real = report_from(payload)
    failures = real.gate(FLOOR_VALIDITY, FLOOR_RECALL)
    print(f"citation validity {real.answers['citation_validity']:.3f} · "
          f"recall@5 {real.retrieval['hybrid + reranker']['recall@5']:.3f} · "
          f"injection complied {real.injection['complied']}")
    print("GREEN" if not failures else "\n".join(failures))

    print()
    print("== sabotage 1: one citation stops resolving ==")
    broken = copy.deepcopy(payload)
    total = broken["answers"]["citations_total"]
    broken["answers"]["citations_valid"] = total - 1
    broken["answers"]["citation_validity"] = (total - 1) / total
    for line in report_from(broken).gate(FLOOR_VALIDITY, FLOOR_RECALL):
        print("GATE FAIL:", line)

    print()
    print("== sabotage 2: one adversarial probe is obeyed ==")
    broken = copy.deepcopy(payload)
    broken["injection"]["complied"] = 1
    for line in report_from(broken).gate(FLOOR_VALIDITY, FLOOR_RECALL):
        print("GATE FAIL:", line)

    print()
    print("== sabotage 3: retrieval regresses below the floor ==")
    broken = copy.deepcopy(payload)
    broken["retrieval"]["hybrid + reranker"]["recall@5"] = 0.70
    for line in report_from(broken).gate(FLOOR_VALIDITY, FLOOR_RECALL):
        print("GATE FAIL:", line)

    print()
    print("== the guardrail itself, on the real corpus, against a lying provider ==")
    question = "How many years of production experience does the author have?"
    with session_scope() as session:
        result = ask(session, question, provider=Liar(), thread_id="fail-first")
    print("Q:", question)
    print("provider:", result["provider"], "· refused:", result["refused"])
    print("dropped by cite-check:", result["dropped"])
    print("answer:", result["answer"][:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
