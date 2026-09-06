"use client";

import { useState } from "react";

import { dictionaryFor, type Locale } from "@/lib/i18n";
import type { ReindexRequest } from "@/lib/types";

type Outcome =
  | { kind: "idle" }
  | { kind: "working" }
  | { kind: "interrupted"; threadId: string; request: ReindexRequest }
  | { kind: "resolved"; message: string }
  | { kind: "refused"; message: string };

/**
 * The human-approval interrupt, shown where a reader would look for a "reindex" button.
 *
 * The button does not re-index. It asks the agent to, which stops the run at a LangGraph
 * `interrupt` and returns the request a human must decide. On the hosted demo, approving
 * is then refused with the API's own sentence — the gate is real, and it is visible.
 */
export function ReindexPanel({
  locale,
  target,
  readonly,
}: {
  locale: Locale;
  target: string;
  readonly: boolean;
}) {
  const dictionary = dictionaryFor(locale);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });

  async function request() {
    setOutcome({ kind: "working" });
    const response = await fetch("/api/reindex", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ target }),
    });
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
      status?: string;
      thread_id?: string;
      request?: ReindexRequest;
    };
    if (!response.ok) {
      setOutcome({ kind: "refused", message: body.detail ?? `${response.status}` });
      return;
    }
    if (body.status === "interrupted" && body.thread_id && body.request) {
      setOutcome({ kind: "interrupted", threadId: body.thread_id, request: body.request });
      return;
    }
    setOutcome({ kind: "resolved", message: dictionary.ask.declined });
  }

  async function resolve(approved: boolean) {
    if (outcome.kind !== "interrupted") return;
    const response = await fetch("/api/ask/resume", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        thread_id: outcome.threadId,
        approved,
        reason: "from the corpus page",
      }),
    });
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    if (!response.ok) {
      setOutcome({
        kind: "refused",
        message: readonly ? dictionary.corpus.reindex.refusedReadonly : (body.detail ?? ""),
      });
      return;
    }
    setOutcome({ kind: "resolved", message: dictionary.ask.declined });
  }

  return (
    <div className="card" data-testid="reindex-panel" data-state={outcome.kind}>
      <h2>{dictionary.corpus.reindex.title}</h2>
      <p className="muted small">{dictionary.corpus.reindex.body}</p>
      <button
        className="btn"
        type="button"
        onClick={() => void request()}
        disabled={outcome.kind === "working"}
        data-testid="reindex-button"
      >
        {outcome.kind === "working"
          ? dictionary.corpus.reindex.working
          : dictionary.corpus.reindex.button}
      </button>

      {outcome.kind === "interrupted" ? (
        <div className="approval" style={{ marginBlockStart: "0.85rem" }}>
          <h3 style={{ marginBlock: "0 0.35rem" }}>{dictionary.ask.approvalTitle}</h3>
          <p>{dictionary.ask.approvalBody(String(outcome.request.target ?? target))}</p>
          <div className="row">
            <button className="btn btn-primary" type="button" onClick={() => void resolve(true)}>
              {dictionary.ask.approve}
            </button>
            <button className="btn" type="button" onClick={() => void resolve(false)}>
              {dictionary.ask.decline}
            </button>
          </div>
        </div>
      ) : null}

      {outcome.kind === "refused" ? (
        <div className="banner banner-warn" style={{ marginBlockStart: "0.85rem" }}>
          <span aria-hidden="true">⚠</span>
          <p data-testid="reindex-refused">{outcome.message}</p>
        </div>
      ) : null}

      {outcome.kind === "resolved" ? (
        <p className="small muted" style={{ marginBlockStart: "0.85rem" }}>
          {outcome.message}
        </p>
      ) : null}
    </div>
  );
}
