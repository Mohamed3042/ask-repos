import "server-only";

import { currentTraceContext, type TraceContext } from "./trace";
import type { Corpus } from "./types";

/**
 * The only place that knows the API's address or its key.
 *
 * `server-only` makes that structural rather than a convention: importing this file from
 * a client component is a build error, so `ASK_REPOS_API_KEY` cannot reach the browser by
 * accident. Every browser request goes to a route handler under `/api/*`, and the route
 * handler calls out from the server.
 */

export const DEFAULT_API_URL = "http://localhost:8080";

export function apiBaseUrl(): string {
  const raw = process.env.ASK_REPOS_API_URL?.trim() || DEFAULT_API_URL;
  return raw.replace(/\/+$/, "");
}

export function apiUrl(path: string): string {
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

export interface ApiCallOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
  /** Seconds; 0 or undefined means "never cache". */
  revalidate?: number;
  timeoutMs?: number;
}

export interface ApiCall {
  response: Response;
  trace: TraceContext;
}

/**
 * Call the ask-repos API with the W3C trace context and the server-side key attached.
 * Returns the trace context as well as the response so a route handler can echo the
 * trace id back to the browser — that id is what ties a screenshot to a span.
 */
export async function apiFetch(path: string, options: ApiCallOptions = {}): Promise<ApiCall> {
  const { headers = {}, revalidate, timeoutMs = 120_000, ...rest } = options;
  const traceContext = currentTraceContext();
  const key = process.env.ASK_REPOS_API_KEY?.trim();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(apiUrl(path), {
      ...rest,
      signal: controller.signal,
      headers: {
        accept: "application/json",
        traceparent: traceContext.traceparent,
        ...(key ? { "x-api-key": key } : {}),
        ...headers,
      },
      cache: revalidate ? undefined : "no-store",
      ...(revalidate ? { next: { revalidate } } : {}),
    });
    return { response, trace: traceContext };
  } finally {
    clearTimeout(timer);
  }
}

export class ApiUnreachable extends Error {
  constructor(readonly cause_: unknown) {
    super("the ask-repos API did not answer");
    this.name = "ApiUnreachable";
  }
}

/** The corpus summary, or a typed failure the page can render as an error state. */
export async function getCorpus(): Promise<
  { ok: true; corpus: Corpus } | { ok: false; status: number | null; detail: string }
> {
  try {
    const { response } = await apiFetch("/v1/corpus", { timeoutMs: 15_000 });
    if (!response.ok) {
      return { ok: false, status: response.status, detail: await safeDetail(response) };
    }
    return { ok: true, corpus: (await response.json()) as Corpus };
  } catch (error) {
    return {
      ok: false,
      status: null,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function safeDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body === "object" && "detail" in body) return String(body.detail);
    return JSON.stringify(body).slice(0, 400);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}
