import { NextResponse } from "next/server";

import { apiFetch, safeDetail } from "@/lib/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * The streaming proxy.
 *
 * The browser talks only to this route: it never learns the API's address and never holds
 * `ASK_REPOS_API_KEY`. The route forwards a W3C `traceparent`, so the FastAPI span the
 * question produces is a child of this handler's span, and echoes the trace id back in
 * `x-trace-id` — that header is what ties a screenshot of the UI to a span in Jaeger.
 *
 * The upstream body is passed through untouched. Re-chunking server-sent events is a
 * classic way to break them; `Response.body` is already a byte stream, so it is simply
 * handed on.
 */
export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ detail: "body is not JSON" }, { status: 400 });
  }

  const body = payload as { question?: unknown; repo?: unknown; thread_id?: unknown };
  const question = typeof body.question === "string" ? body.question.trim() : "";
  if (!question) {
    return NextResponse.json({ detail: "question is required" }, { status: 400 });
  }
  if (question.length > 2000) {
    return NextResponse.json({ detail: "question is too long" }, { status: 400 });
  }

  try {
    const { response, trace } = await apiFetch("/v1/ask/stream", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify({
        question,
        repo: typeof body.repo === "string" && body.repo ? body.repo : null,
        thread_id: typeof body.thread_id === "string" ? body.thread_id : null,
      }),
      timeoutMs: 180_000,
    });

    if (!response.ok || !response.body) {
      return NextResponse.json(
        { detail: await safeDetail(response) },
        {
          status: response.status,
          headers: {
            "x-trace-id": trace.traceId,
            ...(response.headers.get("retry-after")
              ? { "retry-after": response.headers.get("retry-after")! }
              : {}),
          },
        },
      );
    }

    return new Response(response.body, {
      status: 200,
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-store, no-transform",
        connection: "keep-alive",
        "x-accel-buffering": "no",
        "x-trace-id": trace.traceId,
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          error instanceof Error && error.name === "AbortError"
            ? "the API took too long to answer"
            : "the ask-repos API is unreachable from this deployment",
      },
      { status: 502 },
    );
  }
}
