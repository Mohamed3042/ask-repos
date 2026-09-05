"""The LangGraph agent.

    plan → retrieve → expand → draft → cite_check → answer
       └── reindex (human-in-the-loop interrupt) ──┘

`plan` and `expand` are deterministic; no model is asked to decide what to retrieve, so
the retrieval numbers in `docs/retrieval.md` describe the agent's real behaviour.

`reindex` is the one action with a side effect, and it is the one node that stops: it
raises a LangGraph `interrupt`, the API hands the request to a human, and the run only
continues when someone resumes the thread with an approval.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ask_repos.agent.cite_check import REFUSAL, cite_check
from ask_repos.agent.providers import Provider, get_provider
from ask_repos.db.models import Chunk, File
from ask_repos.retrieval.embed import Embedder
from ask_repos.retrieval.search import Hit, search
from ask_repos.telemetry import ASK_REQUESTS, SENTENCES_DROPPED, span

REINDEX_RE = re.compile(r"^\s*(re-?index|refresh the corpus|update the index)\b", re.IGNORECASE)
NEIGHBOUR_LIMIT = 4


def _keep_last(_current: Any, incoming: Any) -> Any:
    return incoming


class AskState(TypedDict, total=False):
    question: str
    k: int
    mode: str
    repo: str | None
    provider_name: str | None
    plan: Annotated[dict[str, Any], _keep_last]
    hits: Annotated[list[dict[str, Any]], _keep_last]
    draft: Annotated[dict[str, Any], _keep_last]
    result: Annotated[dict[str, Any], _keep_last]
    answer: str
    refused: bool
    reindex: Annotated[dict[str, Any] | None, _keep_last]
    steps: Annotated[list[str], _keep_last]


def _hit_from_dict(payload: dict[str, Any]) -> Hit:
    return Hit(
        chunk_id=payload["chunk_id"],
        repo=payload["repo"],
        path=payload["path"],
        sha=payload["sha"],
        line_start=payload["line_start"],
        line_end=payload["line_end"],
        kind=payload["kind"],
        symbol=payload.get("symbol"),
        text=payload["text"],
        score=payload.get("score", 0.0),
        vector_rank=payload.get("vector_rank"),
        text_rank=payload.get("text_rank"),
        rerank_score=payload.get("rerank_score"),
    )


def build_graph(
    session: Session,
    provider: Provider | None = None,
    embedder: Embedder | None = None,
    reindexer: Any = None,
    checkpointer: Any = None,
):
    """Compile the agent. The session is bound at build time; one graph per request."""

    def plan(state: AskState) -> dict[str, Any]:
        question = state["question"]
        planned = state.get("plan", {}).get("intent")
        wants_reindex = bool(REINDEX_RE.match(question)) or planned == "reindex"
        target = None
        if wants_reindex:
            match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", question)
            target = match.group(1) if match else None
        return {
            "plan": {
                "intent": "reindex" if wants_reindex else "answer",
                "query": question,
                "target": target,
                "k": state.get("k", 8),
            },
            "steps": [*state.get("steps", []), "plan"],
        }

    def route(state: AskState) -> str:
        return "reindex" if state["plan"]["intent"] == "reindex" else "retrieve"

    def retrieve(state: AskState) -> dict[str, Any]:
        with span("retrieve", question=state["question"], mode=state.get("mode", "hybrid")):
            hits = search(
                session,
                state["question"],
                k=state.get("k", 8),
                mode=state.get("mode", "hybrid"),
                repo=state.get("repo"),
                embedder=embedder,
            )
        return {
            "hits": [hit.as_dict() for hit in hits],
            "steps": [*state.get("steps", []), "retrieve"],
        }

    def expand(state: AskState) -> dict[str, Any]:
        """Pull the neighbouring chunks of the best hits so a cut definition is complete.

        Neighbours are real stored chunks with their own ids, so anything the model quotes
        from them is still citable and still verifiable.
        """
        hits = list(state.get("hits", []))
        if not hits:
            return {"steps": [*state.get("steps", []), "expand"]}
        known = {hit["chunk_id"] for hit in hits}
        added = 0
        for hit in list(hits)[:3]:
            row = session.get(Chunk, hit["chunk_id"])
            if row is None:
                continue
            file = session.get(File, row.file_id)
            if file is None:
                continue
            neighbours = session.scalars(
                select(Chunk)
                .where(
                    Chunk.file_id == row.file_id,
                    Chunk.ordinal.in_([row.ordinal - 1, row.ordinal + 1]),
                )
                .order_by(Chunk.ordinal)
            ).all()
            for neighbour in neighbours:
                if neighbour.id in known or added >= NEIGHBOUR_LIMIT:
                    continue
                known.add(neighbour.id)
                added += 1
                hits.append(
                    {
                        "chunk_id": neighbour.id,
                        "repo": hit["repo"],
                        "path": hit["path"],
                        "sha": neighbour.sha,
                        "line_start": neighbour.line_start,
                        "line_end": neighbour.line_end,
                        "kind": neighbour.kind,
                        "symbol": neighbour.symbol,
                        "text": neighbour.text,
                        "score": 0.0,
                        "expanded_from": hit["chunk_id"],
                    }
                )
        return {"hits": hits, "steps": [*state.get("steps", []), "expand"]}

    def draft(state: AskState) -> dict[str, Any]:
        chosen = provider or get_provider(state.get("provider_name"))
        hits = [_hit_from_dict(payload) for payload in state.get("hits", [])]
        with span("draft", provider=getattr(chosen, "name", "unknown"), hits=len(hits)):
            result = chosen.draft(state["question"], hits)
        return {"draft": result.as_dict(), "steps": [*state.get("steps", []), "draft"]}

    def check(state: AskState) -> dict[str, Any]:
        drafted = state.get("draft", {}).get("sentences", [])
        with span("cite_check", sentences=len(drafted)):
            result = cite_check(session, drafted)
        for reason, count in result.dropped_reasons.items():
            SENTENCES_DROPPED.labels(reason=reason).inc(count)
        return {"result": result.as_dict(), "steps": [*state.get("steps", []), "cite_check"]}

    def answer(state: AskState) -> dict[str, Any]:
        result = state.get("result", {})
        refused = bool(result.get("refused", True))
        ASK_REQUESTS.labels(outcome="refused" if refused else "answered").inc()
        return {
            "answer": result.get("answer", REFUSAL),
            "refused": refused,
            "steps": [*state.get("steps", []), "answer"],
        }

    def reindex(state: AskState) -> dict[str, Any]:
        """The only side-effecting node. It stops and waits for a human."""
        request = {
            "action": "reindex",
            "target": state["plan"].get("target"),
            "question": state["question"],
            "note": "Re-indexing calls the GitHub API and rewrites corpus rows."
            " Approve to continue.",
        }
        decision = interrupt(request)
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        if not approved:
            reason = (
                decision.get("reason") if isinstance(decision, dict) else None
            ) or "declined by a human"
            return {
                "reindex": {"approved": False, "reason": reason},
                "result": {
                    "refused": True,
                    "answer": f"Re-index not run: {reason}.",
                    "sentences": [],
                },
                "steps": [*state.get("steps", []), "reindex:declined"],
            }
        outcome: dict[str, Any] = {"approved": True}
        if reindexer is not None:
            outcome |= reindexer(state["plan"].get("target"))
        return {
            "reindex": outcome,
            "result": {
                "refused": False,
                "answer": f"Re-index approved and run: {outcome.get('summary', 'no summary')}.",
                "sentences": [],
            },
            "steps": [*state.get("steps", []), "reindex:approved"],
        }

    builder = StateGraph(AskState)
    builder.add_node("plan", plan)
    builder.add_node("retrieve", retrieve)
    builder.add_node("expand", expand)
    builder.add_node("draft", draft)
    builder.add_node("cite_check", check)
    builder.add_node("answer", answer)
    builder.add_node("reindex", reindex)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", route, {"retrieve": "retrieve", "reindex": "reindex"})
    builder.add_edge("retrieve", "expand")
    builder.add_edge("expand", "draft")
    builder.add_edge("draft", "cite_check")
    builder.add_edge("cite_check", "answer")
    builder.add_edge("reindex", "answer")
    builder.add_edge("answer", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())


CHECKPOINTER = InMemorySaver()


def ask(
    session: Session,
    question: str,
    k: int = 8,
    mode: str = "hybrid",
    repo: str | None = None,
    provider: Provider | None = None,
    provider_name: str | None = None,
    embedder: Embedder | None = None,
    thread_id: str = "cli",
    reindexer: Any = None,
    checkpointer: Any = None,
) -> dict[str, Any]:
    """Run the graph once. An interrupted run returns `{"status": "interrupted", ...}`."""
    graph = build_graph(
        session,
        provider=provider,
        embedder=embedder,
        reindexer=reindexer,
        checkpointer=checkpointer or CHECKPOINTER,
    )
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke(
        {
            "question": question,
            "k": k,
            "mode": mode,
            "repo": repo,
            "provider_name": provider_name,
            "steps": [],
        },
        config=config,
    )
    return _shape(state, graph, config, thread_id)


def resume(
    session: Session,
    thread_id: str,
    approved: bool,
    reason: str | None = None,
    reindexer: Any = None,
    provider: Provider | None = None,
    embedder: Embedder | None = None,
    checkpointer: Any = None,
) -> dict[str, Any]:
    """Resume an interrupted thread with a human decision."""
    from langgraph.types import Command

    graph = build_graph(
        session,
        provider=provider,
        embedder=embedder,
        reindexer=reindexer,
        checkpointer=checkpointer or CHECKPOINTER,
    )
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke(
        Command(resume={"approved": approved, "reason": reason}), config=config
    )
    return _shape(state, graph, config, thread_id)


def _shape(
    state: dict[str, Any], graph: Any, config: dict[str, Any], thread_id: str
) -> dict[str, Any]:
    snapshot = graph.get_state(config)
    pending = getattr(snapshot, "interrupts", None) or []
    if pending:
        return {
            "status": "interrupted",
            "thread_id": thread_id,
            "request": getattr(pending[0], "value", pending[0]),
            "steps": state.get("steps", []),
        }
    result = state.get("result", {})
    return {
        "status": "ok",
        "thread_id": thread_id,
        "question": state.get("question"),
        "answer": state.get("answer", REFUSAL),
        "refused": bool(state.get("refused", True)),
        "sentences": result.get("sentences", []),
        "dropped": result.get("dropped", {}),
        "hits": state.get("hits", []),
        "provider": state.get("draft", {}).get("provider"),
        "model": state.get("draft", {}).get("model"),
        "fallback_reason": state.get("draft", {}).get("fallback_reason"),
        "reindex": state.get("reindex"),
        "steps": state.get("steps", []),
    }
