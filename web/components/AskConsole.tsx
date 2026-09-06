"use client";

import { useCallback, useRef, useState } from "react";

import { CitationChip } from "@/components/CitationChip";
import { answerToMarkdown } from "@/lib/citations";
import { readEvents } from "@/lib/sse";
import { EXAMPLE_QUESTIONS, dictionaryFor, type Locale } from "@/lib/i18n";
import type { AskDone, ReindexRequest, Sentence } from "@/lib/types";

type Phase = "idle" | "streaming" | "done" | "interrupted" | "error";

interface State {
  phase: Phase;
  question: string;
  sentences: Sentence[];
  done: AskDone | null;
  interrupt: { threadId: string; request: ReindexRequest } | null;
  resolution: string | null;
  error: string | null;
  traceId: string | null;
}

const EMPTY: State = {
  phase: "idle",
  question: "",
  sentences: [],
  done: null,
  interrupt: null,
  resolution: null,
  error: null,
  traceId: null,
};

export function AskConsole({ locale, repo }: { locale: Locale; repo?: string }) {
  const dictionary = dictionaryFor(locale);
  const [draft, setDraft] = useState("");
  const [state, setState] = useState<State>(EMPTY);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const run = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setCopied(false);
      setState({ ...EMPTY, phase: "streaming", question: trimmed });

      try {
        const response = await fetch("/api/ask", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question: trimmed, repo: repo ?? null }),
          signal: controller.signal,
        });
        const traceId = response.headers.get("x-trace-id");
        if (!response.ok || !response.body) {
          const detail = await response
            .json()
            .then((body: { detail?: string }) => body.detail)
            .catch(() => null);
          setState((previous) => ({
            ...previous,
            phase: "error",
            traceId,
            error: detail ?? `${response.status} ${response.statusText}`,
          }));
          return;
        }

        for await (const frame of readEvents(response.body, controller.signal)) {
          if (frame.event === "sentence") {
            const sentence = frame.data as Sentence;
            setState((previous) => ({
              ...previous,
              traceId,
              sentences: [...previous.sentences, sentence],
            }));
          } else if (frame.event === "interrupt") {
            const data = frame.data as { thread_id: string; request: ReindexRequest };
            setState((previous) => ({
              ...previous,
              phase: "interrupted",
              traceId,
              interrupt: { threadId: data.thread_id, request: data.request },
            }));
          } else if (frame.event === "done") {
            setState((previous) => ({
              ...previous,
              phase: previous.phase === "interrupted" ? previous.phase : "done",
              traceId,
              done: frame.data as AskDone,
            }));
          }
        }
        setState((previous) =>
          previous.phase === "streaming" ? { ...previous, phase: "done" } : previous,
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((previous) => ({
          ...previous,
          phase: "error",
          error: error instanceof Error ? error.message : String(error),
        }));
      }
    },
    [repo],
  );

  async function resolve(approved: boolean) {
    const interrupt = state.interrupt;
    if (!interrupt) return;
    setState((previous) => ({ ...previous, resolution: null }));
    const response = await fetch("/api/ask/resume", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ thread_id: interrupt.threadId, approved, reason: "from the UI" }),
    });
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
      answer?: string;
    };
    setState((previous) => ({
      ...previous,
      resolution: response.ok
        ? approved
          ? (body.answer ?? "")
          : dictionary.ask.declined
        : (body.detail ?? `${response.status}`),
      interrupt: response.ok ? null : previous.interrupt,
    }));
  }

  const kept = state.sentences.filter((sentence) => sentence.kept);
  const refused = state.phase === "done" && state.done?.refused === true;
  const dropped = Object.entries(state.done?.dropped ?? {});

  async function copyAnswer() {
    await navigator.clipboard.writeText(
      answerToMarkdown(state.question, kept, {
        provider: state.done?.provider,
        model: state.done?.model,
      }),
    );
    setCopied(true);
  }

  return (
    <div className="stack">
      <form
        className="ask-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run(draft);
        }}
      >
        <label htmlFor="question">
          <strong>{dictionary.ask.label}</strong>
        </label>
        <textarea
          id="question"
          ref={inputRef}
          name="question"
          value={draft}
          placeholder={dictionary.ask.placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void run(draft);
            }
          }}
          maxLength={2000}
          required
        />
        <div className="row">
          <button
            className="btn btn-primary"
            type="submit"
            disabled={state.phase === "streaming" || !draft.trim()}
          >
            {state.phase === "streaming" ? dictionary.ask.working : dictionary.ask.submit}
          </button>
          <span className="small muted">⌘/Ctrl + ↵</span>
        </div>
      </form>

      <section aria-label={dictionary.ask.examples}>
        <p className="small muted" style={{ marginBottom: "0.35rem" }}>
          {dictionary.ask.examples}
        </p>
        <div className="examples">
          {EXAMPLE_QUESTIONS[locale].map((example) => (
            <button
              key={example}
              type="button"
              className="example"
              onClick={() => {
                setDraft(example);
                inputRef.current?.focus();
                void run(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>
      </section>

      <section
        className="panel"
        aria-label={dictionary.ask.answered}
        aria-busy={state.phase === "streaming"}
        data-testid="answer-panel"
        data-phase={state.phase}
      >
        <div className="panel-head">
          <h2>{dictionary.ask.answered}</h2>
          {state.done?.provider ? (
            <span className="tag mono" data-testid="provider">
              {[state.done.provider, state.done.model].filter(Boolean).join(" ")}
            </span>
          ) : null}
          {state.traceId ? (
            <span className="tag mono tag-off" title="W3C trace id">
              trace {state.traceId.slice(0, 8)}
            </span>
          ) : null}
          {kept.length > 0 ? (
            <button
              type="button"
              className="btn btn-quiet"
              style={{ marginInlineStart: "auto" }}
              onClick={() => void copyAnswer()}
            >
              {copied ? dictionary.ask.copied : dictionary.ask.copy}
            </button>
          ) : null}
        </div>

        <div style={{ padding: "1rem 1.15rem" }}>
          {state.phase === "idle" ? (
            <p className="empty" data-testid="answer-empty">
              {dictionary.ask.empty}
            </p>
          ) : null}

          {state.phase === "error" ? (
            <div className="banner banner-danger" data-testid="answer-error">
              <span aria-hidden="true">✕</span>
              <p>
                <strong>{dictionary.ask.errorTitle}. </strong>
                {state.error}
              </p>
            </div>
          ) : null}

          {kept.length > 0 ? (
            <div className="answer" data-testid="answer-sentences">
              {kept.map((sentence, index) => (
                <article className="sentence" key={`${index}-${sentence.text.slice(0, 24)}`}>
                  <p>{sentence.text}</p>
                  <div
                    className="chips"
                    role="list"
                    aria-label={`${dictionary.ask.citationsFor} ${index + 1}`}
                  >
                    {sentence.citations.map((citation) => (
                      <span role="listitem" key={`${citation.chunk_id}-${citation.citation}`}>
                        <CitationChip citation={citation} hint={dictionary.ask.openOnGitHub} />
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          {state.phase === "streaming" ? (
            <p className="pending" style={{ marginBlockStart: kept.length ? "1rem" : 0 }}>
              <span className="pip" aria-hidden="true" />
              {dictionary.ask.working}
            </p>
          ) : null}

          {refused && kept.length === 0 ? (
            <div className="refusal" data-testid="answer-refusal">
              <h3>{dictionary.ask.refusedTitle}</h3>
              <p style={{ marginBottom: 0 }}>{state.done?.answer || dictionary.ask.refusedBody}</p>
            </div>
          ) : null}

          {state.interrupt ? (
            <div className="approval" data-testid="answer-interrupt">
              <h3 style={{ marginBlock: "0 0.35rem" }}>{dictionary.ask.approvalTitle}</h3>
              <p>
                {dictionary.ask.approvalBody(
                  String(state.interrupt.request.target ?? state.question),
                )}
              </p>
              <div className="row">
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={() => void resolve(true)}
                >
                  {dictionary.ask.approve}
                </button>
                <button className="btn" type="button" onClick={() => void resolve(false)}>
                  {dictionary.ask.decline}
                </button>
              </div>
            </div>
          ) : null}

          {state.resolution ? (
            <p className="small muted" data-testid="answer-resolution">
              {state.resolution}
            </p>
          ) : null}

          {state.done?.fallback_reason ? (
            <div
              className="banner banner-warn"
              style={{ marginBlockStart: "1rem" }}
              data-testid="answer-fallback"
            >
              <span aria-hidden="true">⚠</span>
              <p>{dictionary.ask.fallback(state.done.fallback_reason.split(/\r?\n/)[0])}</p>
            </div>
          ) : null}

          {dropped.length > 0 ? (
            <p className="dropped" style={{ marginBlockStart: "1rem" }}>
              <span className="muted small">{dictionary.ask.droppedTitle}:</span>
              {dropped.map(([reason, count]) => (
                <span className="tag tag-warn" key={reason}>
                  {reason} × {count}
                </span>
              ))}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
